"""
Victor Reasoning Layer

ConflictDetector  — LLM-based judgment of experiment vs claim direction.
EvidenceWeighter  — builds ClaimEvidenceSummary for any claim node.
GapDetector       — surfaces claims with no confirming experiment.
PatternDetector   — cross-gap pattern analysis; auto-surfaced in ask_full().
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from .models import ClaimEvidenceSummary, EdgeType, NodeType

if TYPE_CHECKING:
    from .graph import VictorKnowledgeGraph


# ──────────────────────────────────────────────────────────────────────────────
# ConflictDetector
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ConflictJudgment:
    direction:      str            # "confirm" | "contradict" | "inconclusive"
    confidence:     float
    reason:         str
    # NLI cross-encoder provenance — None when NLI was not run
    nli_direction:  Optional[str]   = None
    nli_confidence: Optional[float] = None
    nli_override:   bool            = False  # True when NLI overrode the LLM judgment


# ──────────────────────────────────────────────────────────────────────────────
# NLICrossEncoder
# ──────────────────────────────────────────────────────────────────────────────

class NLICrossEncoder:
    """
    Lazy wrapper around a sentence-transformers NLI cross-encoder.

    Loaded once on first call to predict().  Returns (direction, confidence)
    where direction is one of "confirm" | "contradict" | "inconclusive".

    The default model (cross-encoder/nli-deberta-v3-base) outputs three scores
    in the order [contradiction, neutral, entailment]; this class applies
    softmax and maps them to Victor's label set.

    Pass label_order explicitly to bypass auto-detection entirely — required for
    models like dleemiller/ModernCE-large-nli whose id2label attribute path
    differs from deberta-v3 and whose order is the inverse default.

    Subclass and override predict() to inject a test double — MockNLICrossEncoder
    in the test suite does this.
    """

    # Label order emitted by cross-encoder/nli-deberta-v3-base.
    # CORRECTED 2026-06-27: actual model output order is [contradiction, neutral, entailment].
    # Original comment had indices 1 and 2 swapped, causing all entailment predictions
    # to map to "neutral" → "inconclusive". Verified by diagnostic:
    #   scores[[-7.22, 1.43, 4.98]] for an entailment pair → argmax=2 → should be "entailment".
    # _load() auto-detects label order from model config (id2label) when available,
    # so this default applies only to models that don't expose id2label.
    _LABEL_ORDER = ["contradiction", "entailment", "neutral"]  # auto-detection overrides this; fallback only
    _LABEL_MAP   = {
        "contradiction": "contradict",
        "entailment":    "confirm",
        "neutral":       "inconclusive",
    }

    # Known label orders for common models, for reference.
    # cross-encoder/nli-deberta-v3-base:  contradiction, neutral, entailment
    # cross-encoder/nli-deberta-v3-large: contradiction, neutral, entailment
    # dleemiller/ModernCE-large-nli:      entailment, neutral, contradiction
    # dleemiller/EttinX-nli-s:            entailment, neutral, contradiction

    def __init__(
        self,
        model_name: str = "cross-encoder/nli-deberta-v3-base",
        label_order: Optional[List[str]] = None,
    ):
        """
        Parameters
        ----------
        model_name:
            sentence-transformers CrossEncoder model name or local path.
        label_order:
            Explicit label order as a list of three strings chosen from
            {"contradiction", "entailment", "neutral"}, matching the output
            logit indices of the model.  When provided, auto-detection is
            skipped entirely.  Use this for models whose id2label attribute
            path differs from the deberta-v3 layout (e.g. ModernCE).
            Example: ["entailment", "neutral", "contradiction"]
        """
        self._model_name          = model_name
        self._model               = None   # loaded lazily on first predict()
        self._explicit_label_order: Optional[List[str]] = None

        if label_order is not None:
            lo = [s.lower() for s in label_order]
            if set(lo) != {"contradiction", "entailment", "neutral"} or len(lo) != 3:
                raise ValueError(
                    f"label_order must be a permutation of "
                    f"['contradiction', 'entailment', 'neutral']; got {label_order!r}"
                )
            self._explicit_label_order = lo

    def _load(self) -> None:
        if self._model is None:
            from sentence_transformers import CrossEncoder  # type: ignore
            self._model = CrossEncoder(self._model_name)

        # If an explicit label_order was supplied at construction time, use it
        # and skip auto-detection entirely.
        if self._explicit_label_order is not None:
            self._label_order = list(self._explicit_label_order)
            return

        # Auto-detect label order from the model's config (id2label).
        # Try three attribute paths — different CrossEncoder versions and model
        # families expose id2label at different locations.
        id2label = None
        _paths_tried: List[str] = []
        try:
            id2label = self._model.model.config.id2label
            _paths_tried.append("model.model.config.id2label")
        except Exception:
            pass
        if id2label is None:
            try:
                id2label = self._model.config.id2label
                _paths_tried.append("model.config.id2label")
            except Exception:
                pass
        if id2label is None:
            try:
                id2label = self._model.model.config["id2label"]
                _paths_tried.append("model.model.config['id2label']")
            except Exception:
                pass

        if id2label is not None:
            try:
                detected = [id2label[i].lower() for i in sorted(id2label.keys())]
                if set(detected) == {"contradiction", "entailment", "neutral"}:
                    self._label_order = detected
                    return
            except Exception:
                pass

        # Fall back to the class-level default (corrected order above).
        self._label_order = list(self._LABEL_ORDER)

    def validate_label_order(self) -> bool:
        """
        Run two known pairs through the model and verify the label mapping
        is correct.  Call this before a benchmark run to catch label-order
        mismatches early.

        Returns True if both pairs produce the expected direction.
        Raises RuntimeError with a diagnostic message on mismatch so the
        caller can abort before running 100+ samples with a broken mapping.

        Pairs tested:
          Entailment:    "A dog is sleeping." / "An animal is resting."   → confirm
          Contradiction: "The sky is blue."   / "The sky is green."       → contradict
        """
        pairs = [
            ("A dog is sleeping.", "An animal is resting.", "confirm"),
            ("The sky is blue.", "The sky is green.", "contradict"),
        ]
        print("  Smoke-testing label order...")
        for premise, hypothesis, expected in pairs:
            direction, conf = self.predict(premise, hypothesis)
            icon = "OK" if direction == expected else "FAIL"
            print(f"    [{icon}] '{premise}' / '{hypothesis}' -> {direction} (conf={conf:.2f}), expected {expected}")
            if direction != expected:
                order_str = ", ".join(getattr(self, "_label_order", self._LABEL_ORDER))
                raise RuntimeError(
                    f"Label order validation FAILED for model '{self._model_name}'.\n"
                    f"  Pair:     '{premise}' / '{hypothesis}'\n"
                    f"  Expected: {expected}\n"
                    f"  Got:      {direction} (conf={conf:.2f})\n"
                    f"  Current label order: [{order_str}]\n\n"
                    f"Known correct orders:\n"
                    f"  cross-encoder/nli-deberta-v3-base:  contradiction,neutral,entailment\n"
                    f"  cross-encoder/nli-deberta-v3-large: contradiction,neutral,entailment\n"
                    f"  dleemiller/ModernCE-large-nli:      entailment,neutral,contradiction\n"
                    f"  dleemiller/EttinX-nli-s:            entailment,neutral,contradiction\n\n"
                    f"Pass the correct order via --nli-label-order (CLI) or "
                    f"label_order= (constructor)."
                )
        print("  Label order OK")
        return True

    def predict(self, premise: str, hypothesis: str) -> tuple:
        """
        Return (direction, confidence).

        Gracefully returns ("inconclusive", 0.0) on any load or inference
        error so a missing / incompatible model never crashes a judge() call.
        """
        try:
            self._load()
            import numpy as np
            raw = self._model.predict([(premise, hypothesis)])[0]
            exp_s = np.exp(raw - np.max(raw))
            probs = exp_s / exp_s.sum()
            best  = int(np.argmax(probs))
            label_order = getattr(self, "_label_order", self._LABEL_ORDER)
            label = label_order[best]
            return self._LABEL_MAP[label], float(probs[best])
        except Exception:
            return "inconclusive", 0.0


class MockNLICrossEncoder(NLICrossEncoder):
    """
    Test double for NLICrossEncoder.

    Pass a fixed (direction, confidence) at construction time; predict()
    always returns it without loading any model.  Useful for exercising the
    override logic in ConflictDetector without downloading or running DeBERTa.
    """

    def __init__(self, direction: str = "inconclusive", confidence: float = 0.0):
        super().__init__()           # model_name stored but never used
        self._fixed_direction   = direction
        self._fixed_confidence  = confidence

    def predict(self, premise: str, hypothesis: str) -> tuple:
        return self._fixed_direction, self._fixed_confidence


class ConflictDetector:
    """LLM-based judgment of whether an experiment result confirms,
    contradicts, or is inconclusive with respect to a claim.

    Optionally augmented by an NLI cross-encoder (see NLICrossEncoder) that
    acts as an agreement-bias catch: if the LLM says confirm/inconclusive but
    the cross-encoder predicts contradiction with sufficient confidence, the
    judgment is overridden to "contradict".  Both verdicts are recorded in the
    returned ConflictJudgment for edge provenance.

    nli_primary=True enables the Step-1a architecture:
    "NLI as judge, LLM as annotator."  The NLI cross-encoder makes the
    direction decision; the LLM is called only for a free-form reasoning
    trace (stored as provenance).  This avoids the JSON-schema agreement-bias
    amplification identified in the v5.0 ConflictDetector rewrite.
    nli_primary has no effect when nli is None.
    """

    def __init__(self, llm=None, nli: Optional["NLICrossEncoder"] = None,
                 nli_override_threshold: float = 0.5,
                 nli_primary: bool = False):
        self.llm                    = llm
        self.nli                    = nli
        self.nli_override_threshold = nli_override_threshold
        self.nli_primary            = nli_primary

    # JSON schema for structured generation — forces valid output at the
    # token level on backends that support it (Ollama v0.5+ via `format`),
    # and gives a real per-call confidence instead of a hardcoded constant.
    _RESPONSE_SCHEMA: Dict[str, Any] = {
        "type": "object",
        "properties": {
            "reasoning":  {"type": "string"},
            "direction":  {"type": "string", "enum": ["confirm", "contradict", "inconclusive"]},
            "confidence": {"type": "number"},
        },
        "required": ["reasoning", "direction", "confidence"],
    }

    def judge(self, claim_text: str, result_text: str) -> ConflictJudgment:
        """
        Use the LLM to determine the direction of an experiment result
        relative to a claim.  Falls back to inconclusive when no LLM.

        Standard mode (nli_primary=False):
            LLM makes the direction decision.  If an NLI cross-encoder is
            configured, it runs after the LLM call.  When the LLM says
            confirm/inconclusive and the cross-encoder predicts contradiction
            with confidence > nli_override_threshold, the judgment is
            overridden to "contradict".  Both verdicts are stored in the
            returned ConflictJudgment for provenance.

        NLI-primary mode (nli_primary=True, Step-1a architecture):
            The NLI cross-encoder makes the direction decision.  The LLM is
            called only for a free-form reasoning trace (no JSON schema,
            no direction token) which is stored as the reason field.
            This avoids the JSON-schema agreement-bias amplification where
            Qwen2.5-7B routes to "confirm" as the lowest-perplexity
            schema-satisfying token.  Requires nli to be set; falls back to
            standard mode if nli is None.
        """
        # ── NLI-primary path (Step 1a) ────────────────────────────────────────
        if self.nli_primary and self.nli is not None:
            return self._nli_primary_judge(claim_text, result_text)

        # ── Standard path: LLM judgment first ────────────────────────────────
        llm_judgment = self._llm_judge(claim_text, result_text)

        # ── NLI cross-check (optional) ────────────────────────────────────────
        if self.nli is None:
            return llm_judgment

        nli_dir, nli_conf = self.nli.predict(claim_text, result_text)

        # Agreement-bias catch: LLM too lenient + NLI confident about contradiction
        override = (
            llm_judgment.direction in ("confirm", "inconclusive")
            and nli_dir == "contradict"
            and nli_conf > self.nli_override_threshold
        )

        if override:
            reason = (
                f"[NLI override — LLM said '{llm_judgment.direction}' "
                f"(conf {llm_judgment.confidence:.2f}); cross-encoder predicted "
                f"'contradict' with {nli_conf:.2f} confidence] "
                f"{llm_judgment.reason}"
            )
            return ConflictJudgment(
                direction      = "contradict",
                confidence     = nli_conf,
                reason         = reason,
                nli_direction  = nli_dir,
                nli_confidence = nli_conf,
                nli_override   = True,
            )

        return ConflictJudgment(
            direction      = llm_judgment.direction,
            confidence     = llm_judgment.confidence,
            reason         = llm_judgment.reason,
            nli_direction  = nli_dir,
            nli_confidence = nli_conf,
            nli_override   = False,
        )

    def _nli_primary_judge(self, claim_text: str, result_text: str) -> ConflictJudgment:
        """
        Step-1a architecture: NLI cross-encoder decides direction;
        LLM generates free-form reasoning text as provenance only.

        The LLM is called without a JSON schema or direction token, so the
        structured-output agreement-bias amplification cannot occur.  If the
        LLM is unavailable, the reason field is left empty.
        """
        # NLI makes the direction call
        nli_dir, nli_conf = self.nli.predict(claim_text, result_text)

        # LLM provides free-form reasoning trace (provenance only — no direction)
        reason = ""
        if self.llm is not None:
            reasoning_prompt = (
                "Briefly explain in one or two sentences why the following "
                "evidence CONFIRMS, CONTRADICTS, or is INCONCLUSIVE with "
                "respect to the claim.  Do not state a label — just explain "
                "the relationship.\n\n"
                f"Claim: {claim_text}\n\n"
                f"Evidence: {result_text}"
            )
            try:
                resp = self.llm.generate(reasoning_prompt)
                reason = (resp.text or "").strip()[:400]
            except Exception:
                reason = ""

        return ConflictJudgment(
            direction      = nli_dir,
            confidence     = nli_conf,
            reason         = f"[NLI-primary] {reason}".strip(),
            nli_direction  = nli_dir,
            nli_confidence = nli_conf,
            nli_override   = True,   # NLI was the decision-maker, not override
        )

    def _llm_judge(self, claim_text: str, result_text: str) -> ConflictJudgment:
        """LLM-only judgment; used internally and directly by tests."""
        if self.llm is None:
            return ConflictJudgment(
                direction="inconclusive", confidence=0.0,
                reason="No LLM available for conflict detection"
            )

        prompt = (
            "You are checking whether a piece of evidence CONFIRMS, CONTRADICTS, "
            "or is INCONCLUSIVE with respect to a claim.\n\n"
            "IMPORTANT: Language models are statistically biased toward 'confirm'. "
            "Actively resist this bias. Before choosing 'confirm', ask yourself: "
            "does the evidence directly address the same specific finding as the "
            "claim, and does it say the opposite? If yes, the answer is 'contradict', "
            "not 'confirm'.\n\n"
            "Definitions:\n"
            "- confirm: the evidence directly supports the specific finding stated "
            "in the claim. The claim's assertion is upheld by the evidence.\n"
            "- contradict: the evidence directly opposes the claim's specific finding. "
            "The evidence and claim make incompatible assertions about the same thing. "
            "Even if the wording differs, the core assertion is opposed.\n"
            "- inconclusive: the evidence addresses a different aspect, uses a "
            "different methodology, or is genuinely ambiguous. The evidence does "
            "not directly address the specific assertion in the claim.\n\n"
            "Examples:\n"
            "\n"
            "Example 1 (contradict):\n"
            'Claim: "Drug X reduces blood pressure."\n'
            'Evidence: "In a randomized trial, Drug X produced no significant '
            'change in blood pressure compared to placebo."\n'
            "-> contradict (same topic, opposite finding).\n\n"
            "Example 2 (confirm):\n"
            'Claim: "Drug X reduces blood pressure."\n'
            'Evidence: "A double-blind trial showed Drug X lowered systolic BP '
            'by 12 mmHg versus placebo (p<0.01)."'
            "\n"
            "-> confirm (same topic, same direction, quantitative support).\n\n"
            "Example 3 (inconclusive):\n"
            'Claim: "Drug X reduces blood pressure."\n'
            'Evidence: "Drug X was well-tolerated with mild gastrointestinal '
            'side effects in the trial population."'
            "\n"
            "-> inconclusive (addresses side effects, not efficacy).\n\n"
            "Now classify the following:\n\n"
            f"Claim: {claim_text}\n\n"
            f"Evidence: {result_text}\n\n"
            "Step 1: Identify the specific assertion in the claim.\n"
            "Step 2: Check whether the evidence addresses that same assertion.\n"
            "Step 3: If yes, determine whether the evidence supports or opposes it.\n"
            "Step 4: Give the direction and your confidence (0.0 to 1.0)."
        )
        try:
            resp = self.llm.generate_structured(
                prompt, response_schema=self._RESPONSE_SCHEMA, retries=1
            )
            return self._parse_structured(resp.text)
        except Exception:
            return ConflictJudgment(
                direction="inconclusive", confidence=0.0,
                reason="LLM call failed"
            )

    @staticmethod
    def _parse_structured(text: str) -> ConflictJudgment:
        """
        Parse the JSON response from generate_structured().

        Falls back to simple keyword matching over the raw text if the
        response isn't valid JSON (e.g. backend doesn't support
        response_schema and the retry loop still didn't produce clean JSON),
        so a parsing hiccup degrades gracefully instead of crashing.
        """
        try:
            parsed = json.loads(text.strip())
            direction = str(parsed.get("direction", "")).strip().lower()
            if direction not in ("confirm", "contradict", "inconclusive"):
                direction = "inconclusive"
            try:
                confidence = float(parsed.get("confidence", 0.5))
            except (TypeError, ValueError):
                confidence = 0.5
            confidence = max(0.0, min(1.0, confidence))
            reason = str(parsed.get("reasoning", "")).strip()
            return ConflictJudgment(direction=direction, confidence=confidence, reason=reason)
        except (json.JSONDecodeError, TypeError, AttributeError):
            lowered = text.strip().lower()
            direction = "inconclusive"
            for candidate in ("contradict", "confirm", "inconclusive"):
                if re.search(rf"\b{candidate}\b", lowered):
                    direction = candidate
                    break
            return ConflictJudgment(direction=direction, confidence=0.4, reason=text[:200].strip())


# ──────────────────────────────────────────────────────────────────────────────
# EvidenceWeighter
# ──────────────────────────────────────────────────────────────────────────────

class EvidenceWeighter:
    """
    Builds ClaimEvidenceSummary objects by walking the graph edges inbound
    to a given CLAIM node.

    Edge directions (from graph.py):
        experiment  → CONFIRMS      → claim
        experiment  → CONTRADICTS   → claim
        experiment  → INCONCLUSIVE  → claim

    Masking enforcement: if a claim node is masked, summarize_claim() returns
    a ClaimEvidenceSummary with a masked placeholder instead of the real
    claim_text.  Evidence counts are withheld — they could indirectly disclose
    what the node says.  This is defense-in-depth: the tools layer (tools.py)
    and retrieval layer (retrieve.py) also enforce masking, but callers of
    EvidenceWeighter directly (e.g. core.py's gaps() and evidence() methods)
    were not protected.
    """

    def __init__(self, graph: "VictorKnowledgeGraph"):
        self.graph = graph

    @staticmethod
    def _masked_summary(claim_id: str, node_data: dict) -> ClaimEvidenceSummary:
        """
        Return a ClaimEvidenceSummary that preserves the node's existence
        and structural position without disclosing its content.

        The claim_text is replaced by a [MASKED] anchor matching the pattern
        used in tools.py and retrieve.py.  Evidence counts (n_confirms, etc.)
        are zeroed — revealing that a masked claim has 3 confirming experiments
        would indirectly disclose information about its content.
        """
        ntype = node_data.get("ntype", "claim")
        epistemic = node_data.get("metadata", {}).get(
            "epistemic_status", "literature"
        )
        return ClaimEvidenceSummary(
            claim_id   = claim_id,
            claim_text = (
                f"[MASKED — {ntype} — content withheld. "
                f"Use 'victor unmask {claim_id[:16]}' to reveal.]"
            ),
            epistemic_status        = epistemic,
            confidence              = 0.0,
            n_confirms              = 0,
            n_contradicts           = 0,
            n_inconclusive          = 0,
            supporting_experiments  = [],
            conflicting_experiments = [],
            gap                     = True,  # masked claims are still gaps — researcher needs to know
        )

    def summarize_claim(self, claim_id: str) -> Optional[ClaimEvidenceSummary]:
        """
        Return a full evidence summary for one claim node, or None if not
        found.  If the claim node is masked, returns a masked anchor summary
        that preserves referential presence without disclosing content.
        """
        claim_node = self.graph.get_node(claim_id)
        if claim_node is None:
            return None

        # ── MASKING GATE ──────────────────────────────────────────────────
        if self.graph.node_is_masked(claim_id):
            return self._masked_summary(claim_id, claim_node)
        # ─────────────────────────────────────────────────────────────────

        claim_text = claim_node.get("label", "")
        epistemic  = claim_node.get("metadata", {}).get(
            "epistemic_status", claim_node.get("epistemic_status", "literature")
        )

        n_confirms    = 0
        n_contradicts = 0
        n_inconclusive = 0
        supporting: List[str]  = []
        conflicting: List[str] = []

        # Walk all inbound edges to this claim
        for src, dst, data in self.graph._g.in_edges(claim_id, data=True):
            etype = data.get("etype")
            src_node = self.graph.get_node(src)
            src_label = (src_node.get("label", src) if src_node else src)[:80]

            if etype == EdgeType.CONFIRMS:
                n_confirms += 1
                supporting.append(src_label)
            elif etype == EdgeType.CONTRADICTS:
                n_contradicts += 1
                conflicting.append(src_label)
            elif etype == EdgeType.INCONCLUSIVE:
                n_inconclusive += 1

        # Confidence: proportion of non-contradicting evidence
        total = n_confirms + n_contradicts + n_inconclusive
        if total == 0:
            confidence = 0.0
        else:
            confidence = n_confirms / total

        return ClaimEvidenceSummary(
            claim_id                 = claim_id,
            claim_text               = claim_text,
            epistemic_status         = epistemic,
            confidence               = round(confidence, 3),
            n_confirms               = n_confirms,
            n_contradicts            = n_contradicts,
            n_inconclusive           = n_inconclusive,
            supporting_experiments   = supporting,
            conflicting_experiments  = conflicting,
            gap                      = (n_confirms == 0),
        )

    def summarize_all_claims(self) -> List[ClaimEvidenceSummary]:
        """Return an evidence summary for every CLAIM node in the graph."""
        results = []
        for nid, data in self.graph._g.nodes(data=True):
            if data.get("ntype") == NodeType.CLAIM:
                s = self.summarize_claim(nid)
                if s:
                    results.append(s)
        return results


# ──────────────────────────────────────────────────────────────────────────────
# GapDetector
# ──────────────────────────────────────────────────────────────────────────────

class GapDetector:
    """Surfaces claims that have no confirming experiment."""

    def __init__(self, graph: "VictorKnowledgeGraph", weighter: EvidenceWeighter):
        self.graph    = graph
        self.weighter = weighter

    def find_gaps(self, min_importance: float = 0.0) -> List[ClaimEvidenceSummary]:
        """
        Return all CLAIM nodes that are gaps (n_confirms == 0).
        Sorted by importance score descending so callers see the most important
        gaps first.
        """
        summaries = self.weighter.summarize_all_claims()
        gaps = [s for s in summaries if s.gap]

        # Sort by node importance if available
        def _importance(s: ClaimEvidenceSummary) -> float:
            node = self.graph.get_node(s.claim_id)
            if node is None:
                return 0.0
            return float(node.get("importance_score", 0.0))

        gaps.sort(key=_importance, reverse=True)

        if min_importance > 0.0:
            gaps = [g for g in gaps if _importance(g) >= min_importance]

        return gaps


# ──────────────────────────────────────────────────────────────────────────────
# PatternDetector
# ──────────────────────────────────────────────────────────────────────────────

class PatternDetector:
    """
    Cross-gap pattern analysis, surfaced automatically in ask_full().

    analyze() returns:
      priority_gaps           — top-5 gap ClaimEvidenceSummary objects
      suggested_experiments   — human-readable experiment suggestions
      top_queried_sources     — most frequently retrieved source IDs
      total_conversations     — how many conversation nodes in graph
    """

    def __init__(self, graph: "VictorKnowledgeGraph", gap_detector: GapDetector):
        self.graph        = graph
        self.gap_detector = gap_detector

    def analyze(self) -> Dict[str, Any]:
        gaps = self.gap_detector.find_gaps()
        priority_gaps = gaps[:5]

        suggested_experiments = [
            f"Run an experiment to test: \"{gap.claim_text[:120]}\""
            f"{'...' if len(gap.claim_text) > 120 else ''}"
            for gap in priority_gaps
        ]

        # Count conversation nodes for total_conversations
        total_convs = sum(
            1 for _, d in self.graph._g.nodes(data=True)
            if d.get("ntype") == NodeType.CONVERSATION
        )

        # Top queried sources — nodes with highest retrieval_count
        source_counts: List[tuple] = []
        for nid, d in self.graph._g.nodes(data=True):
            if d.get("ntype") == NodeType.PAPER:
                count = d.get("retrieval_count", 0)
                if count > 0:
                    source_counts.append((nid, count, d.get("label", nid)))
        source_counts.sort(key=lambda x: x[1], reverse=True)
        top_sources = [
            {"source_id": nid, "count": cnt, "label": lbl}
            for nid, cnt, lbl in source_counts[:5]
        ]

        return {
            "priority_gaps":         priority_gaps,
            "suggested_experiments": suggested_experiments,
            "top_queried_sources":   top_sources,
            "total_conversations":   total_convs,
        }
