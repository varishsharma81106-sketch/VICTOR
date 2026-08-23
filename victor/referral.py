"""
Referral points — memory addressed by handle, dereferenced one at a time.

Everything Victor knows, masked or not, is reached through a *referral point*:
a handle that publishes what a piece of memory **is** without publishing what it
**says**. Type, epistemic tier, confidence, contradiction count, gaps, age,
degree, relevance to the question. Six properties and a shape. No content.

The reasoning model reads that table and spends a budget: it names one handle,
gives a reason, and receives that one piece of memory. Then it decides again.

Why this instead of top-k retrieval
-----------------------------------
The rest of Victor retrieves in bulk — five chunks of text pasted into a prompt,
chosen by cosine similarity, before the model has thought about anything. That
design has three costs this module exists to remove:

  1. **The model never decides what to look at.** Relevance is decided by an
     embedding, and the model rationalises whatever arrives. Here, choosing is
     the model's job and it must state why.

  2. **Masked nodes are inert.** `retrieve.py` emits a text anchor the model can
     read but cannot act on: "[MASKED — claim — content withheld]". It is a
     tombstone. A referral point is a live handle — the model can *request* it,
     and the request is answered with a grant or a refusal, both recorded. The
     mask stops being a hole in the context and becomes a door with a log.

  3. **Nothing is auditable at the level of a decision.** The unmask audit log
     records that a node was unmasked, not that a reasoning pass asked for it
     and why. The ledger here records every request, granted or denied, in
     order, with the model's stated reason — which is the artifact you produce
     when someone challenges a published result.

The one-at-a-time rule is not a performance choice. Serialising disclosure is
what makes the reason mandatory: a model that receives five things at once never
has to justify any of them.

Real-time fragments
-------------------
`offer()` accepts `fragments`: observations arriving now rather than out of the
graph. They enter the same table under the same rules, so a live sensor reading
and a six-month-old paper compete for the same budget on the same six
properties. `victor/simulation.py` produces exactly this shape.
"""
from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from victor.models import EpistemicStatus, NodeType

logger = logging.getLogger(__name__)

# What a referral point publishes in place of a masked node's descriptor. Fixed
# width: a placeholder that tracked the real length would leak it.
WITHHELD = "████████"

# Default number of dereferences one reasoning pass may spend. Small on purpose
# — the constraint is the mechanism. Raising it to the size of the table turns
# this back into bulk retrieval with extra steps.
DEFAULT_BUDGET = 3

# Why a request was refused. These strings reach the model, so they say that
# something was refused and on what grounds, never what was behind the door.
DENY_MASKED = "masked — not authorised for this reasoning pass"
DENY_UNKNOWN = "no such referral point in this table"
DENY_BUDGET = "dereference budget exhausted"
DENY_REPEAT = "already dereferenced in this pass"


# ══════════════════════════════════════════════════════════════════════════════
#  The handle
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class ReferralPoint:
    """
    One addressable piece of memory, described but not disclosed.

    The fields are the six epistemic properties `VICTOR_THEORY_v1` requires of
    an artifact — origin, type, confidence, contradictions, gaps, age — plus the
    two things needed to choose between handles: how connected it is, and how
    well it matched the question. `descriptor` is the node's label for visible
    memory and WITHHELD for masked memory; a label is a title, not a body, and
    for masked nodes not even that is published.
    """
    ref: str
    node_id: str
    ntype: str
    origin: str
    epistemic_status: str
    confidence: float
    contradictions: int
    gaps: int
    age_days: Optional[float]
    degree: int
    relevance: float
    masked: bool
    descriptor: str

    @property
    def tier_weight(self) -> float:
        """
        The epistemic ladder as a number, for ranking.

        `EpistemicStatus.weight` has existed since v4 with no call sites — the
        differentiator Victor claims and never used. This is a call site.
        """
        try:
            return EpistemicStatus(self.epistemic_status).weight
        except ValueError:
            return 0.5

    def describe(self) -> str:
        """The single line the reasoning model reads. Must never carry content."""
        age = "unknown age" if self.age_days is None else f"{self.age_days:.0f}d old"
        parts = [
            f"{self.ref}",
            f"{self.ntype}",
            f"{self.epistemic_status}",
            f"conf {self.confidence:.2f}",
            f"{self.degree} relation{'' if self.degree == 1 else 's'}",
            age,
            f"match {self.relevance:.2f}",
        ]
        if self.contradictions:
            parts.append(f"{self.contradictions} contradicted")
        if self.gaps:
            parts.append(f"{self.gaps} unverified")
        if self.masked:
            parts.append("MASKED")
        return f"[{' · '.join(parts)}] {self.descriptor}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "node_id": self.node_id,
            "ntype": self.ntype,
            "origin": self.origin,
            "epistemic_status": self.epistemic_status,
            "confidence": round(self.confidence, 3),
            "contradictions": self.contradictions,
            "gaps": self.gaps,
            "age_days": None if self.age_days is None else round(self.age_days, 1),
            "degree": self.degree,
            "relevance": round(self.relevance, 4),
            "masked": self.masked,
            "descriptor": self.descriptor,
        }


@dataclass
class ReferralTable:
    """Everything offered for one question, plus the budget for spending on it."""
    query: str
    points: List[ReferralPoint] = field(default_factory=list)
    budget: int = DEFAULT_BUDGET

    def __len__(self) -> int:
        return len(self.points)

    def get(self, ref: str) -> Optional[ReferralPoint]:
        want = (ref or "").strip().upper()
        for p in self.points:
            if p.ref == want:
                return p
        return None

    def render(self) -> str:
        """The table as the model sees it."""
        if not self.points:
            return "(memory holds nothing relevant to this question)"
        return "\n".join(p.describe() for p in self.points)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "budget": self.budget,
            "points": [p.as_dict() for p in self.points],
            "masked_count": sum(1 for p in self.points if p.masked),
        }


@dataclass
class Dereference:
    """The outcome of asking for exactly one referral point."""
    ref: str
    node_id: Optional[str]
    granted: bool
    reason: str
    content: Optional[str] = None
    denial: Optional[str] = None
    masked: bool = False
    sequence: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "node_id": self.node_id,
            "granted": self.granted,
            "reason": self.reason,
            "denial": self.denial,
            "masked": self.masked,
            "sequence": self.sequence,
            # Deliberately last, and absent when nothing was disclosed — a
            # serialised trace is the most likely thing to end up in a log.
            **({"content": self.content} if self.granted else {}),
        }


# ══════════════════════════════════════════════════════════════════════════════
#  Fragments — memory that has not landed yet
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class Fragment:
    """
    A reading arriving now, offered alongside stored memory.

    Sensor input is not a special kind of truth. It is a MEASUREMENT-tier
    artifact with a confidence and an age of zero, and it competes for the same
    budget as everything else. It can be sensitive, in which case it is masked
    on arrival and its content is behind the same door.
    """
    fragment_id: str
    text: str
    source: str
    confidence: float = 0.8
    masked: bool = False
    epistemic_status: str = EpistemicStatus.MEASUREMENT.value


# ══════════════════════════════════════════════════════════════════════════════
#  The desk
# ══════════════════════════════════════════════════════════════════════════════

class ReferralDesk:
    """
    Turns a question into a table of handles, and handles into content.

    `authority` decides masked access — it receives a node id and returns
    True/False. The default refuses everything, which is the right default: a
    reasoning pass that can silently unmask is not a trust boundary. Pass
    `RevealSession.is_revealed` to honour console reveals, or a policy callable
    for anything richer.
    """

    def __init__(
        self,
        graph,
        vector_store=None,
        authority: Optional[Callable[[str], bool]] = None,
        budget: int = DEFAULT_BUDGET,
        ledger_path: Optional[Path] = None,
        now: Optional[datetime.datetime] = None,
    ):
        self.graph = graph
        self.vs = vector_store
        self.authority = authority or (lambda _node_id: False)
        self.budget = max(1, int(budget))
        self.ledger_path = Path(ledger_path) if ledger_path else None
        # Injectable so a trace is reproducible in tests and in the simulation,
        # where "now" is a tick number rather than a wall clock.
        self._now = now

    # ── offering ──────────────────────────────────────────────────────────────

    def offer(
        self,
        query: str,
        limit: int = 8,
        fragments: Sequence[Fragment] = (),
    ) -> ReferralTable:
        """
        Build the table for one question.

        Masked nodes are found structurally, never by matching the query against
        their content — `semantic_query` already drops them at the graph layer,
        so they are added back here by relevance-to-the-neighbourhood rather
        than relevance-to-the-text. That ordering matters: if a masked node's
        rank moved with the query wording, the rank would be an oracle.
        """
        table = ReferralTable(query=query, budget=self.budget)
        points: List[ReferralPoint] = []
        seen: set = set()

        for frag in fragments:
            points.append(self._point_from_fragment(frag, len(points)))
            seen.add(frag.fragment_id)

        for node_id, score, data in self.graph.semantic_query(query, top_k=limit):
            if node_id in seen:
                continue
            seen.add(node_id)
            points.append(self._point_from_node(node_id, data, score))

        # Masked neighbours of what matched: present, positioned, unreadable.
        #
        # Anchors are drawn from points that are actually *in the graph*. A live
        # fragment has no neighbourhood, so letting fragments fill the three
        # anchor slots meant that during a busy sensor tick — exactly when the
        # machine most needs its stored context — masked memory stopped being
        # offered at all and the table silently went quiet about it.
        anchors = [
            p for p in points
            if not p.masked and self.graph._g.has_node(p.node_id)
        ][:3]
        for anchor in anchors:
            for nbr_id, nbr_data, _etype in self.graph.get_neighbors(anchor.node_id, hops=1):
                if nbr_id in seen or not self.graph.node_is_masked(nbr_id):
                    continue
                seen.add(nbr_id)
                # Relevance inherited from the anchor, discounted. Not computed
                # from the masked node's own text, which is the whole point.
                points.append(self._point_from_node(nbr_id, nbr_data, anchor.relevance * 0.6))

        # Rank by match quality lifted by epistemic standing. A measurement that
        # matched moderately beats a hypothesis that matched well.
        points.sort(key=lambda p: p.relevance * (0.5 + p.tier_weight), reverse=True)
        table.points = [
            ReferralPoint(**{**p.__dict__, "ref": f"R{i + 1}"})
            for i, p in enumerate(points[:limit])
        ]
        return table

    def _point_from_node(self, node_id: str, data: Dict[str, Any], score: float) -> ReferralPoint:
        meta = data.get("metadata") or {}
        masked = bool(meta.get("is_masked", False))
        visible = not masked or self.authority(node_id)
        g = getattr(self.graph, "_g", None)
        degree = (g.in_degree(node_id) + g.out_degree(node_id)) if g is not None and g.has_node(node_id) else 0

        return ReferralPoint(
            ref="R?",
            node_id=node_id,
            ntype=data.get("ntype", NodeType.NOTE),
            origin=str(meta.get("source_id") or meta.get("origin") or node_id)[:48],
            epistemic_status=str(meta.get("epistemic_status") or EpistemicStatus.LITERATURE.value),
            confidence=float(meta.get("confidence", meta.get("importance_score", 0.5)) or 0.0),
            contradictions=int(meta.get("contradictions", 0) or 0),
            gaps=int(bool(meta.get("gaps", False))) if not isinstance(meta.get("gaps"), int)
                 else int(meta.get("gaps") or 0),
            age_days=self._age_days(meta.get("created_at") or meta.get("timestamp")),
            degree=degree,
            relevance=float(score),
            masked=masked,
            descriptor=(str(data.get("label", ""))[:90] if visible else WITHHELD),
        )

    def _point_from_fragment(self, frag: Fragment, index: int) -> ReferralPoint:
        return ReferralPoint(
            ref="R?",
            node_id=frag.fragment_id,
            ntype=NodeType.OBSERVATION,
            origin=frag.source,
            epistemic_status=frag.epistemic_status,
            confidence=frag.confidence,
            contradictions=0,
            gaps=0,
            age_days=0.0,
            degree=0,
            # Arriving now is its own claim on attention: a live reading is
            # offered near the top rather than competing on cosine distance
            # against text it has not been indexed against yet.
            relevance=0.95 - index * 0.01,
            masked=frag.masked,
            descriptor=(frag.text[:90] if not frag.masked else WITHHELD),
        )

    def _age_days(self, stamp: Any) -> Optional[float]:
        if not stamp:
            return None
        try:
            then = datetime.datetime.fromisoformat(str(stamp))
        except (TypeError, ValueError):
            return None
        now = self._now or datetime.datetime.now(then.tzinfo)
        try:
            return max(0.0, (now - then).total_seconds() / 86400.0)
        except TypeError:
            # One side is timezone-aware and the other is not. Comparing them
            # raises rather than being wrong by an offset, so report unknown.
            return None

    # ── dereferencing ─────────────────────────────────────────────────────────

    def dereference(
        self,
        table: ReferralTable,
        ref: str,
        reason: str = "",
        spent: int = 0,
        fragments: Sequence[Fragment] = (),
    ) -> Dereference:
        """
        Spend one unit of budget on exactly one handle.

        Every outcome — granted, refused, unknown handle, exhausted budget — is
        returned as a Dereference and written to the ledger. A refusal that
        vanished would make the trace a record of what succeeded rather than a
        record of what was asked.
        """
        want = (ref or "").strip().upper()
        point = table.get(want)
        seq = spent + 1

        def deny(msg: str, node_id: Optional[str] = None, masked: bool = False) -> Dereference:
            d = Dereference(ref=want, node_id=node_id, granted=False, reason=reason,
                            denial=msg, masked=masked, sequence=seq)
            self._record(table, d)
            return d

        if spent >= table.budget:
            return deny(DENY_BUDGET)
        if point is None:
            return deny(DENY_UNKNOWN)
        if point.masked and not self.authority(point.node_id):
            return deny(DENY_MASKED, node_id=point.node_id, masked=True)

        content = self._content_for(point, fragments)
        d = Dereference(ref=want, node_id=point.node_id, granted=True, reason=reason,
                        content=content, masked=point.masked, sequence=seq)
        self._record(table, d)
        # Consulting memory is what makes it important. Bulk retrieval credited
        # everything it touched; here only what was actually read is credited.
        try:
            self.graph.record_retrieval(point.node_id)
        except Exception:  # a fragment has no node to credit
            pass
        return d

    def _content_for(self, point: ReferralPoint, fragments: Sequence[Fragment]) -> str:
        for frag in fragments:
            if frag.fragment_id == point.node_id:
                return frag.text

        data = self.graph.get_node(point.node_id) or {}
        label = str(data.get("label", ""))
        body: List[str] = [label] if label else []

        if self.vs is not None:
            try:
                meta = data.get("metadata") or {}
                source_id = meta.get("source_id") or point.node_id
                for chunk in self.vs.get_by_source(source_id)[:2]:
                    if chunk.text and chunk.text not in body:
                        body.append(chunk.text)
            except Exception as exc:
                logger.debug("chunk lookup failed for %s: %s", point.node_id, exc)

        return "\n\n".join(body) if body else "(node has no stored text)"

    # ── ledger ────────────────────────────────────────────────────────────────

    def _record(self, table: ReferralTable, d: Dereference) -> None:
        entry = {
            "ts": (self._now or datetime.datetime.now(datetime.timezone.utc)).isoformat(),
            "query": table.query,
            **d.as_dict(),
        }
        # The ledger says what was asked for and whether it was answered. The
        # content itself is not written: a disclosure log that copies the
        # disclosure has doubled the exposure it exists to bound.
        entry.pop("content", None)
        if self.ledger_path is None:
            return
        try:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("referral ledger write failed: %s", exc)


# ══════════════════════════════════════════════════════════════════════════════
#  The loop
# ══════════════════════════════════════════════════════════════════════════════

CHOICE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["dereference", "answer"]},
        "ref": {"type": "string"},
        "reason": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["action"],
}

_PROMPT = """You are reasoning from a memory you cannot read directly.

Below is a table of referral points. Each line says what a piece of memory IS —
its type, how well grounded it is, how confident, how connected, how old, how
well it matches the question — but not what it says. Some are MASKED: they exist
and are relevant, and you may request them, but the request can be refused.

You may dereference {budget} point{plural}, one at a time. Each time, name one
handle and say why that one. After each disclosure you decide again. When you
have enough, answer.

QUESTION: {query}

REFERRAL POINTS:
{table}
{history}
Respond with JSON: {{"action":"dereference","ref":"R2","reason":"..."}} or
{{"action":"answer","answer":"..."}}.
"""


@dataclass
class Deliberation:
    """One reasoning pass: what was offered, what was opened, what came out."""
    query: str
    table: ReferralTable
    steps: List[Dereference] = field(default_factory=list)
    answer: str = ""
    provider: str = "none"

    @property
    def granted(self) -> int:
        return sum(1 for s in self.steps if s.granted)

    @property
    def refused(self) -> int:
        return sum(1 for s in self.steps if not s.granted)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "table": self.table.as_dict(),
            "steps": [s.as_dict() for s in self.steps],
            "granted": self.granted,
            "refused": self.refused,
            "answer": self.answer,
            "provider": self.provider,
        }


class DeliberateReasoner:
    """
    Retrieve-by-request instead of retrieve-by-default.

    `chooser` exists so the loop is testable without a model: any callable
    taking (table, history) and returning a dict shaped like CHOICE_SCHEMA. When
    it is None the LLM does the choosing.
    """

    def __init__(self, desk: ReferralDesk, llm=None, chooser: Optional[Callable] = None):
        self.desk = desk
        self.llm = llm
        self.chooser = chooser

    def run(
        self,
        query: str,
        limit: int = 8,
        fragments: Sequence[Fragment] = (),
    ) -> Deliberation:
        table = self.desk.offer(query, limit=limit, fragments=fragments)
        result = Deliberation(query=query, table=table)
        disclosed: List[str] = []
        opened: set = set()

        for spent in range(table.budget):
            choice = self._choose(table, result.steps, disclosed)
            if choice.get("action") != "dereference":
                result.answer = str(choice.get("answer", "")).strip()
                break

            ref = str(choice.get("ref", "")).strip().upper()
            reason = str(choice.get("reason", "")).strip()

            if ref in opened:
                # Re-asking is a loop, not a decision. Refuse it and let the
                # model see the refusal rather than silently burning budget on
                # a duplicate.
                step = Dereference(ref=ref, node_id=None, granted=False, reason=reason,
                                   denial=DENY_REPEAT, sequence=spent + 1)
            else:
                step = self.desk.dereference(table, ref, reason=reason,
                                             spent=spent, fragments=fragments)
            result.steps.append(step)
            opened.add(ref)
            if step.granted:
                disclosed.append(f"{ref}: {step.content}")
            else:
                disclosed.append(f"{ref}: REFUSED — {step.denial}")

        if not result.answer:
            result.answer = self._final(query, table, disclosed, result.steps)
        result.provider = getattr(self.llm, "model", "chooser") if self.llm else "chooser"
        return result

    def _choose(self, table: ReferralTable, steps: List[Dereference],
                disclosed: List[str]) -> Dict[str, Any]:
        if self.chooser is not None:
            return self.chooser(table, steps)
        if self.llm is None:
            return {"action": "answer", "answer": ""}

        history = ""
        if disclosed:
            history = "\nWHAT YOU HAVE OPENED SO FAR:\n" + "\n\n".join(disclosed) + "\n"
        prompt = _PROMPT.format(
            query=table.query,
            table=table.render(),
            budget=table.budget,
            plural="" if table.budget == 1 else "s",
            history=history,
        )
        res = self.llm.generate_structured(prompt, response_schema=CHOICE_SCHEMA)
        try:
            return json.loads(res.text)
        except (TypeError, ValueError):
            # An unparseable choice is not a licence to grab everything; it ends
            # the pass with whatever has already been disclosed.
            return {"action": "answer", "answer": res.text or ""}

    def _final(self, query: str, table: ReferralTable, disclosed: List[str],
               steps: List[Dereference]) -> str:
        # A chooser that can decide can also close. Without this the common
        # machine case — a policy chooser that spends its whole budget and so
        # never gets to return an "answer" action — ends the pass with an empty
        # string, silently dropping the account of what was refused.
        conclude = getattr(self.chooser, "conclude", None)
        if callable(conclude):
            return conclude(table, steps)
        if self.llm is None:
            return ""
        body = "\n\n".join(disclosed) if disclosed else "(nothing was opened)"
        prompt = (
            f"Answer the question using only what you opened. If it is not enough, "
            f"say so and name what you would need.\n\n"
            f"QUESTION: {query}\n\nWHAT YOU OPENED:\n{body}\n\nANSWER:"
        )
        return self.llm.generate(prompt).text.strip()


class PolicyChooser:
    """
    A chooser that reasons without a language model.

    Victor is specified as a device that has to work with no network and,
    on a machine in the field, often no LLM either. The deliberation loop must
    therefore be able to run on an explicit policy: score each unopened handle
    on what the handle itself says, take the best, state why.

        score = relevance × (0.5 + epistemic tier) × (1 + 0.08 × degree)

    Masked points are **not** penalised. The policy cannot know it will be
    refused until it asks, and pre-emptively skipping them would mean the
    machine quietly routes around its own trust boundary instead of hitting it
    and recording that it did. The refusals in a trace are real refusals.
    """

    def __init__(self, stop_when_confident: float = 0.0):
        # Above this much disclosed confidence the policy stops early rather
        # than spending the rest of the budget. 0.0 means always spend it all.
        self.stop_when_confident = stop_when_confident

    @staticmethod
    def score(p: ReferralPoint) -> float:
        return p.relevance * (0.5 + p.tier_weight) * (1 + 0.08 * p.degree)

    def __call__(self, table: ReferralTable, steps: List[Dereference]) -> Dict[str, Any]:
        opened = {s.ref for s in steps}
        gained = sum(1 for s in steps if s.granted)
        candidates = [p for p in table.points if p.ref not in opened]
        if not candidates:
            return {"action": "answer", "answer": self.conclude(table, steps)}
        if self.stop_when_confident and gained:
            got = [p for p in table.points if p.ref in opened and p.masked is False]
            if got and sum(p.confidence for p in got) / len(got) >= self.stop_when_confident:
                return {"action": "answer", "answer": self.conclude(table, steps)}

        best = max(candidates, key=self.score)
        why = (
            f"highest expected value: {best.epistemic_status} tier, "
            f"match {best.relevance:.2f}, {best.degree} relation"
            f"{'' if best.degree == 1 else 's'}"
        )
        if best.masked:
            why += " — masked, requesting anyway to see whether it is authorised"
        if best.contradictions:
            why += f"; {best.contradictions} recorded contradiction(s) to resolve"
        return {"action": "dereference", "ref": best.ref, "reason": why}

    @staticmethod
    def conclude(table: ReferralTable, steps: List[Dereference]) -> str:
        """
        The account the machine gives of its own pass.

        Public because `DeliberateReasoner._final` calls it: when the budget runs
        out before the chooser volunteers an answer, this is the answer.
        """
        granted = [s for s in steps if s.granted]
        refused = [s for s in steps if not s.granted]
        bits = [
            f"Consulted {len(granted)} of {len(table)} available referral points."
        ]
        if refused:
            bits.append(
                f"{len(refused)} request(s) refused: "
                + "; ".join(f"{s.ref} ({s.denial})" for s in refused)
                + ". Those are known to be relevant and remain unread, so this "
                  "conclusion is drawn from an incomplete record."
            )
        if not granted:
            bits.append("Nothing was disclosed; no grounded conclusion is available.")
        return " ".join(bits)


def summarise(deliberation: Deliberation) -> str:
    """One line for a CLI footer or a log."""
    d = deliberation
    return (
        f"offered {len(d.table)} referral point"
        f"{'' if len(d.table) == 1 else 's'} "
        f"({d.table.as_dict()['masked_count']} masked) · "
        f"opened {d.granted} · refused {d.refused}"
    )
