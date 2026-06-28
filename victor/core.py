"""
Victor — central controller — v4.1

Changes from v4:
  - ToolRegistry + _ToolImplementations wired in (Step 1)
  - AgenticRetriever replaces HybridRetriever (Step 2)
    * Bounded agent loop: Retrieve → Reason → Review → Respond
    * Max 5 tool calls, explicit token ceiling
    * ConflictDetector auto-runs in Review step on conflicting claims
  - PatternDetector output surfaced in ask() (Step 3)
  - Fallback: if agent loop fails, degrades to single-shot
"""
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import json
import logging
import datetime
import inspect

logger = logging.getLogger(__name__)

from .models import (
    Claim, Experiment, NodeType, EdgeType, VictorAnswer,
    ClaimEvidenceSummary, EpistemicStatus, IngestResult,
)
from .chunker import TextChunker
from .embedder import LocalEmbedder
from .vector_store import VictorVectorStore
from .graph import VictorKnowledgeGraph
from .llm import OllamaClient, create_inference_client
from .extractor import ClaimExtractor
from .ingest import PDFIngestor, MarkdownIngestor, ExperimentIngestor, INGESTOR_REGISTRY
from .retrieve import HybridRetriever, AgenticRetriever
from .evaluate import VictorEvaluator
from .reasoning import (
    ConflictDetector, EvidenceWeighter, GapDetector, PatternDetector,
    NLICrossEncoder, MockNLICrossEncoder,
)
from .tools import ToolRegistry, _ToolImplementations
from .kernels import StatisticsKernel, ComputedResult


class Victor:
    def __init__(self, config=None):
        if config is None:
            from .config import DEFAULT_CONFIG
            config = DEFAULT_CONFIG

        self.config = config
        config.ensure_dirs()

        if getattr(config, "use_mock_embedder", False):
            from unittest.mock import MagicMock
            self.embedder = MagicMock()
            self.embedder.embed = MagicMock(return_value=[0.1] * 384)
            self.embedder.embed_batch = MagicMock(side_effect=lambda texts: [[0.1] * 384 for _ in texts])
            self.embedder.cosine = MagicMock(return_value=0.5)
        else:
            self.embedder = LocalEmbedder(
                config.embedding_model,
                fallback_models=getattr(config, "embedding_model_fallback", ("all-MiniLM-L6-v2",)),
            )

        self.vector_store = VictorVectorStore(
            db_path  = config.vector_db_dir,
            embedder = self.embedder,
        )

        self.llm = create_inference_client(config)

        # NLI cross-encoder — optional agreement-bias catch for ConflictDetector
        nli = None
        if getattr(config, "use_nli_crossencoder", True):
            if getattr(config, "use_mock_nli", False):
                nli = MockNLICrossEncoder()
            else:
                nli = NLICrossEncoder(
                    model_name=getattr(config, "nli_model", "cross-encoder/nli-deberta-v3-base")
                )

        self.conflict_detector = ConflictDetector(
            llm=self.llm,
            nli=nli,
            nli_override_threshold=getattr(config, "nli_override_threshold", 0.5),
        )

        self.graph = VictorKnowledgeGraph(
            graph_file        = config.graph_file,
            embedder          = self.embedder,
            conflict_detector = self.conflict_detector,
        )

        self.extractor = ClaimExtractor(
            llm      = self.llm,
            log_file = config.extraction_log_file,
        )

        self.chunker = TextChunker(
            chunk_size = config.chunk_size_words,
            overlap    = config.chunk_overlap_words,
        )

        # ── Reasoning layer ───────────────────────────────────────────────────
        self.weighter         = EvidenceWeighter(self.graph)
        self.gap_detector     = GapDetector(self.graph, self.weighter)
        self.pattern_detector = PatternDetector(self.graph, self.gap_detector)

        # ── Computation kernels (DoD #8) ───────────────────────────────────────
        self.statistics_kernel = StatisticsKernel()

        # ── Tool registry (Step 1) ────────────────────────────────────────────
        self.tool_impl = _ToolImplementations(
            graph             = self.graph,
            conflict_detector = self.conflict_detector,
            weighter          = self.weighter,
            gap_detector      = self.gap_detector,
            embedder          = self.embedder,
        )
        self.tool_registry = ToolRegistry(self.tool_impl)

        # ── Retriever: AgenticRetriever with fallback (Step 2) ────────────────
        try:
            self.retriever = AgenticRetriever(
                vector_store       = self.vector_store,
                graph              = self.graph,
                llm                = self.llm,
                top_k              = config.top_k_vectors,
                graph_hop          = config.graph_hop_depth,
                decay_on_retrieve  = True,
                max_tool_calls     = getattr(config, "agent_max_tool_calls", 5),
                max_context_tokens = getattr(config, "agent_max_context_tokens", 8000),
                auto_review        = True,
                tool_registry      = self.tool_registry,
            )
        except Exception as e:
            logger.warning(
                "AgenticRetriever init failed (%s), falling back to HybridRetriever. "
                "Agent loop features (tool calling, auto-review) will be unavailable.",
                e,
            )
            # Fallback to single-shot retriever
            self.retriever = HybridRetriever(
                vector_store      = self.vector_store,
                graph             = self.graph,
                llm               = self.llm,
                top_k             = config.top_k_vectors,
                graph_hop         = config.graph_hop_depth,
                decay_on_retrieve = True,
            )

        self.evaluator = VictorEvaluator(self.retriever)

        # ── Ingestors (v4.3: built from INGESTOR_REGISTRY, keyed by extension) ──
        # Adding a new source type means adding it to INGESTOR_REGISTRY in
        # ingest.py — nothing here needs to change.
        self._ingestors_by_ext: Dict[str, Any] = {}
        for cls in INGESTOR_REGISTRY:
            if cls is PDFIngestor:
                instance = PDFIngestor(
                    self.chunker, self.extractor,
                    extract_claims        = config.extract_claims_by_default,
                    max_extraction_chunks = config.extraction_max_chunks,
                )
            elif cls is MarkdownIngestor:
                instance = MarkdownIngestor(
                    self.chunker, self.extractor,
                    extract_claims        = config.extract_claims_by_default,
                    max_extraction_chunks = config.extraction_max_chunks,
                )
            elif cls is ExperimentIngestor:
                instance = ExperimentIngestor(self.chunker)
            else:
                # Generic construction path for future ingestors that only
                # need (chunker, extractor) — covers the common case without
                # requiring this loop to know about every future subclass.
                try:
                    instance = cls(self.chunker, self.extractor)
                except TypeError:
                    instance = cls(self.chunker)
            for ext in instance.extensions:
                self._ingestors_by_ext[ext] = instance

    # ── Observation (Reality → Artifact pipeline) ─────────────────────────────

    def observe(
        self,
        *,
        sensor:           str                    = "camera",
        image_path:       Optional[str | Path]   = None,
        audio_path:       Optional[str | Path]   = None,
        camera_index:     int                    = 0,
        audio_duration:   int                    = 5,
        candidate_labels: Optional[List[str]]    = None,
        classifier        = None,
        extra_gaps:       Optional[List[str]]    = None,
        session_id:       Optional[str]          = None,
        metadata:         Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Capture one sensor observation and store it as a MEASUREMENT node.

        This is the Reality → Artifact pipeline. A sensor reading becomes a
        graph node with all 6 Epistemic Artifact properties populated:

          Origin, Type (MEASUREMENT), Confidence, Contradictions (empty),
          Gaps (auto-populated by sensor type), Age (timestamp).

        Parameters
        ──────────
        sensor            "camera" | "audio" | "manual"
        image_path        Path to an existing image (skips webcam capture)
        audio_path        Path to an existing audio file (skips mic recording)
        camera_index      Webcam device index (used when image_path is None)
        audio_duration    Recording duration in seconds (audio mode, default 5)
        candidate_labels  Text labels to classify against.  Required for
                          camera/audio mode.
        classifier        Classifier instance.  Default: CLIPClassifier (camera)
                          or LibrosaFeatureClassifier (audio).
        extra_gaps        Additional verification requirements beyond defaults.
        session_id        Groups observations from the same session.
        metadata          Arbitrary extras attached to the node.

        Returns a summary dict (node_id, label, confidence, gaps, media_path).
        """
        from .sensors import CameraIngestor, AudioIngestor

        obs_dir = self.config.home_dir / "observations"

        if candidate_labels is None:
            raise ValueError(
                "candidate_labels is required for observations. "
                "Example: ['high-carbon steel', 'aluminum', 'copper']"
            )

        if sensor == "camera":
            ingestor = CameraIngestor(
                classifier   = classifier,
                image_path   = Path(image_path) if image_path else None,
                camera_index = camera_index,
            )
            obs = ingestor.observe(
                candidate_labels = candidate_labels,
                save_dir         = obs_dir,
                extra_gaps       = extra_gaps,
                session_id       = session_id,
                metadata         = metadata,
            )
            media_path = obs.image_path

        elif sensor == "audio":
            ingestor = AudioIngestor(
                classifier  = classifier,
                audio_path  = Path(audio_path) if audio_path else None,
                duration    = audio_duration,
            )
            obs = ingestor.observe(
                candidate_labels = candidate_labels,
                save_dir         = obs_dir,
                extra_gaps       = extra_gaps,
                session_id       = session_id,
                metadata         = metadata,
            )
            media_path = obs.metadata.get("audio_path")

        else:
            raise NotImplementedError(
                f"Sensor type '{sensor}' not yet implemented. "
                "Available: 'camera', 'audio'."
            )

        # Store in graph as a MEASUREMENT node
        node_id = self.graph.add_observation(obs)
        self.graph.save()

        result = {
            "node_id":    node_id,
            "label":      obs.label,
            "confidence": obs.confidence,
            "sensor_id":  obs.sensor_id,
            "model_used": obs.model_used,
            "gaps":       obs.gaps,
            "timestamp":  obs.timestamp,
            "epistemic_status": obs.epistemic_status,
        }
        # Include media path (image_path for camera, audio_path for audio)
        if media_path:
            result["media_path"] = media_path
        if obs.image_path:
            result["image_path"] = obs.image_path
        return result

    # ── Ingestion ─────────────────────────────────────────────────────────────

    def ingest_file(
        self,
        filepath:       str | Path,
        title:          Optional[str]  = None,
        extract_claims: Optional[bool] = None,
    ) -> Dict[str, Any]:
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(filepath)

        suffix = path.suffix.lower()
        ingestor = self._ingestors_by_ext.get(suffix)
        if ingestor is None:
            raise ValueError(
                f"Unsupported file type: {suffix}\n"
                f"Supported: {', '.join(sorted(self._ingestors_by_ext))}"
            )

        if extract_claims is not None and hasattr(ingestor, "extract_claims"):
            ingestor.extract_claims = extract_claims

        result = ingestor.ingest(path, title)
        return self._file_ingest_result(result)

    def _file_ingest_result(self, result: IngestResult) -> Dict[str, Any]:
        """
        Generic post-processing shared by every ingestor: write chunks to the
        vector store, file the source + claims + concepts (or experiment +
        links) into the graph. This is the part that used to be duplicated
        across _ingest_pdf / _ingest_markdown / _ingest_experiment.
        """
        self.vector_store.add_chunks(result.chunks)

        if result.node_type == NodeType.EXPERIMENT and result.experiment is not None:
            exp = result.experiment
            self.graph.add_experiment(exp)
            links = self.graph.link_experiment_to_claims(
                exp, similarity_threshold=self.config.claim_similarity_threshold,
            )
            self.graph.save()
            return {
                "source_id": exp.experiment_id, "type": "experiment",
                "title":     exp.name, "n_chunks": len(result.chunks),
                "linked_claims": [
                    {"claim": label, "edge": etype, "confidence": conf}
                    for _, label, etype, conf in links
                ],
            }

        if result.node_type == NodeType.PAPER:
            self.graph.add_paper(result.source_id, result.title)
            type_label = "paper"
        else:
            self.graph.add_note(result.source_id, result.title)
            type_label = "note"

        for claim in result.claims:
            self.graph.add_claim(claim)
        for concept in result.concepts:
            self.graph.add_concept(concept, result.source_id)
        self.graph.save()

        out = {
            "source_id":  result.source_id, "type": type_label,
            "title":      result.title,
            "n_chunks":   len(result.chunks), "n_claims": len(result.claims),
            "n_concepts": len(result.concepts),
        }
        if type_label == "paper":
            out["claims"] = [
                {"text": c.text, "type": c.claim_type,
                 "low_confidence": c.low_confidence,
                 "extracted_by": c.extracted_by,
                 "epistemic_status": c.epistemic_status} for c in result.claims
            ]
        return out

    # ── Query ─────────────────────────────────────────────────────────────────

    def ask(self, query: str) -> Tuple[str, List]:
        return self.retriever.answer(query)

    def ask_full(self, query: str) -> VictorAnswer:
        """
        Full agent-loop answer with automatic PatternDetector surfacing.
        PatternDetector insights are injected whenever the query semantically
        overlaps a priority gap — no flag needed from the caller.
        """
        answer = self.retriever.answer_full(query)
        self._inject_pattern_note(query, answer)
        return answer

    # ── Step 3: PatternDetector surfacing ─────────────────────────────────────

    def _inject_pattern_note(self, query: str, answer: VictorAnswer) -> None:
        """
        Mutate answer in-place: prepend a pattern insight if the query
        semantically overlaps a PatternDetector priority gap (similarity > 0.65).
        Silently skips on any error so pattern detection never breaks an answer.

        Masking enforcement: gaps whose claim node is masked are never surfaced
        here.  Before this fix, _inject_pattern_note embedded gap.claim_text[:120]
        directly in the final answer text on every ask_full() call — no tool call
        required — bypassing masked memory completely for any masked claim that
        also happened to be an unconfirmed gap (the common case for early-stage
        research).
        """
        try:
            pattern_result = self.pattern_detector.analyze()
            if not pattern_result.get("priority_gaps"):
                return
            query_emb = self.embedder.embed(query)
            for gap in pattern_result["priority_gaps"][:3]:
                # ── MASKING GATE ──────────────────────────────────────────────
                if self.graph.node_is_masked(gap.claim_id):
                    continue          # never surface masked claims in auto-inject
                # ─────────────────────────────────────────────────────────────
                gap_emb = self.embedder.embed(gap.claim_text)
                from .embedder import LocalEmbedder
                similarity = LocalEmbedder.cosine(query_emb, gap_emb)
                if similarity > 0.65:
                    pattern_note = (
                        f"\n_[Pattern insight: This topic has an unconfirmed claim: "
                        f"\"{gap.claim_text[:120]}\" — no experiments confirm it yet.]_\n"
                    )
                    answer.answer = pattern_note + "\n" + answer.answer
                    break
        except Exception:
            pass  # pattern detection must never break an answer

    def ask_with_patterns(self, query: str) -> VictorAnswer:
        """
        Alias for ask_full() — pattern surfacing is now automatic in ask_full.
        Kept for backwards compatibility with callers and the CLI --show-patterns flag.
        """
        return self.ask_full(query)

    def get_pattern_digest(self) -> Dict[str, Any]:
        """Return a human-readable pattern digest for display."""
        result = self.pattern_detector.analyze()

        digest = {
            "total_conversations": result["total_conversations"],
            "top_sources": result["top_queried_sources"][:5],
            "n_priority_gaps": len(result["priority_gaps"]),
            "n_suggestions": len(result["suggested_experiments"]),
            "suggestions": result["suggested_experiments"][:5],
        }

        # Add recurring weak topics (sources queried often with weak evidence)
        weak_topics = []
        for title, count in result["top_queried_sources"]:
            if count >= 3:
                weak_topics.append({
                    "topic": title,
                    "query_count": count,
                    "note": "Frequently queried — check if evidence is strong enough",
                })
        digest["recurring_weak_topics"] = weak_topics[:5]

        return digest

    # ── Evaluation ────────────────────────────────────────────────────────────

    def evaluate(self, eval_filepath: str | Path, k: int = 5) -> Dict:
        queries = self.evaluator.load_queries(Path(eval_filepath))
        return self.evaluator.evaluate(queries, k=k)

    # ── Node inspection / control ─────────────────────────────────────────────

    def inspect(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self.graph.inspect_node(node_id)

    def freeze(self, node_id: str) -> bool:
        ok = self.graph.freeze_node(node_id)
        if ok:
            self.graph.save()
        return ok

    def unfreeze(self, node_id: str) -> bool:
        ok = self.graph.unfreeze_node(node_id)
        if ok:
            self.graph.save()
        return ok

    # ── Masked memory ─────────────────────────────────────────────────────────
    # Separate sovereignty control from freeze/unfreeze:
    #   freeze  → prevents overwrite of node content
    #   mask    → suppresses content from LLM answers while keeping the node in
    #             the graph for structural routing, gap detection, conflict detection
    #
    # A node can be frozen AND masked independently. They are orthogonal flags.

    # ── Audit log ─────────────────────────────────────────────────────────────

    def _write_mask_audit(self, action: str, node_id: str, success: bool) -> None:
        """
        Append one JSONL line to the unmask audit log every time a node is
        masked or unmasked.  Fields:
          ts        – ISO-8601 UTC timestamp
          action    – "mask" | "unmask"
          node_id   – the node being operated on
          success   – False means the node did not exist
          caller    – best-effort: module + function that triggered this call
        """
        # Walk the call stack to find the first frame outside core.py
        caller = "unknown"
        try:
            stack = inspect.stack()
            for frame_info in stack[2:]:  # skip _write_mask_audit and mask/unmask
                module = frame_info.frame.f_globals.get("__name__", "")
                if "core" not in module:
                    caller = f"{module}:{frame_info.function}:{frame_info.lineno}"
                    break
        except Exception:
            pass

        entry = {
            "ts":      datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "action":  action,
            "node_id": node_id,
            "success": success,
            "caller":  caller,
        }
        try:
            log_path = self.config.unmask_audit_log_file
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as exc:
            logger.warning("unmask audit log write failed: %s", exc)

    def mask(self, node_id: str) -> bool:
        """Suppress a node's content from LLM answers. Graph structure unaffected."""
        ok = self.graph.mask_node(node_id)
        if ok:
            self.graph.save()
        self._write_mask_audit("mask", node_id, ok)
        return ok

    def unmask(self, node_id: str) -> bool:
        """Allow a previously masked node to surface in answers again."""
        ok = self.graph.unmask_node(node_id)
        if ok:
            self.graph.save()
        self._write_mask_audit("unmask", node_id, ok)
        return ok

    def list_masked(self) -> List[Dict]:
        """Return all currently masked nodes."""
        return self.graph.list_masked_nodes()

    def delete(self, source_id: str) -> Dict[str, Any]:
        graph_result = self.graph.delete_source(source_id)
        self.vector_store.delete_source(source_id)
        self.graph.save()
        return {
            "source_id":     source_id,
            "deleted_nodes": graph_result["deleted_nodes"],
            "chunks_removed": True,
        }

    def export(
        self,
        node_ids:      List[str],
        filepath:      str | Path,
        include_edges: bool = True,
    ) -> Dict[str, Any]:
        """Export specific nodes to JSON — the permission switch."""
        filepath       = Path(filepath).resolve()
        # Prevent writing to system directories
        forbidden = {Path("/etc"), Path("/usr"), Path("/bin"), Path("/sbin"), Path("/var")}
        if any(f in filepath.parents or filepath == f for f in forbidden):
            raise ValueError(f"Export path {filepath} is in a system directory. Aborting.")

        exported_nodes = []
        exported_edges = []

        for nid in node_ids:
            node = self.graph.get_node(nid)
            if node is None:
                continue
            exported_nodes.append({"node_id": nid, **node})
            if include_edges:
                inspection = self.graph.inspect_node(nid)
                if inspection:
                    exported_edges.extend(inspection.get("out_edges", []))

        payload = {
            "victor_export":    True,
            "export_timestamp": __import__("datetime").datetime.now().isoformat(),
            "n_nodes":          len(exported_nodes),
            "nodes":            exported_nodes,
            "edges":            exported_edges if include_edges else [],
        }

        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text(json.dumps(payload, indent=2, default=str))

        return {
            "filepath": str(filepath),
            "n_nodes":  len(exported_nodes),
            "n_edges":  len(exported_edges),
        }

    # ── Reasoning layer ───────────────────────────────────────────────────────

    def gaps(self, min_importance: float = 0.0) -> List[ClaimEvidenceSummary]:
        return self.gap_detector.find_gaps(min_importance=min_importance)

    def evidence(self, claim_id: str) -> Optional[ClaimEvidenceSummary]:
        return self.weighter.summarize_claim(claim_id)

    def patterns(self) -> Dict[str, Any]:
        return self.pattern_detector.analyze()

    def apply_decay(self) -> None:
        self.graph.apply_temporal_decay()
        self.graph.save()

    # ── Introspection ─────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        return {
            "vector_store": self.vector_store.stats(),
            "graph":        self.graph.stats(),
            "llm_online":   self.llm.is_available(),
            "llm_model":    self.llm.model,
            "openai_ready": self.llm.openai_configured(),
            "retriever_type": type(self.retriever).__name__,
            "tool_count":   len(self.tool_registry.list_tools()),
        }

    def list_claims(self)        -> List[Dict]: return self.graph.list_nodes(NodeType.CLAIM)
    def list_papers(self)        -> List[Dict]: return self.graph.list_nodes(NodeType.PAPER)
    def list_experiments(self)   -> List[Dict]: return self.graph.list_nodes(NodeType.EXPERIMENT)
    def list_conversations(self) -> List[Dict]: return self.graph.list_nodes(NodeType.CONVERSATION)

    # ── Computation kernels (DoD #8: StatisticsKernel) ─────────────────────────

    def compute_statistics(
        self,
        node_ids: List[str],
        metric_name: str = "value",
        confidence_level: float = 0.95,
    ) -> Dict[str, Any]:
        """
        Run StatisticsKernel on EXPERIMENT/MEASUREMENT nodes.

        Pulls numeric values from the nodes' metadata/results, computes
        descriptive statistics, and stores the result as a COMPUTED node
        with DERIVED_FROM edges to each input node.

        Returns a summary dict with the computed node ID and all outputs.
        """
        values = []
        resolved_ids = []
        for nid in node_ids:
            node = self.graph.get_node(nid)
            if node is None:
                raise ValueError(f"Node not found: {nid}")
            meta = node.get("metadata", {})
            # Try to pull numeric values from common experiment fields
            numeric = []
            # Look in results dict (stored as JSON string for experiments)
            if "results" in meta and isinstance(meta["results"], str):
                try:
                    results_dict = json.loads(meta["results"])
                    # Only extract the requested metric — never average all numeric
                    # fields together (e.g. precision + recall + f1 are not the same
                    # measurement and must not be conflated).
                    if metric_name in results_dict:
                        v = results_dict[metric_name]
                        if isinstance(v, (int, float)):
                            numeric.append(float(v))
                except (json.JSONDecodeError, TypeError):
                    pass
            # Also check for a direct metric_name key in metadata
            if metric_name in meta:
                val = meta[metric_name]
                if isinstance(val, (int, float)):
                    numeric.append(float(val))
                elif isinstance(val, str):
                    try:
                        numeric.append(float(val))
                    except ValueError:
                        pass
            if not numeric:
                raise ValueError(
                    f"No numeric values found in node {nid} for metric '{metric_name}'. "
                    f"Node metadata keys: {list(meta.keys())}"
                )
            values.extend(numeric)
            resolved_ids.append(nid)

        if not values:
            raise ValueError("No numeric values collected from the given nodes.")

        result: ComputedResult = self.statistics_kernel.compute(
            values,
            input_node_ids=resolved_ids,
            confidence_level=confidence_level,
            metric_name=metric_name,
        )

        # Build a deterministic-but-unique node ID
        node_id = f"computed_{result.reproducibility_hash[:12]}"

        # Store as COMPUTED node
        self.graph.add_node(
            node_id=node_id,
            ntype=NodeType.COMPUTED,
            label=f"Statistics: {metric_name} (n={int(result.outputs['n'])})",
            metadata={
                "kernel": result.kernel,
                "kernel_version": result.kernel_version,
                "outputs": result.outputs,
                "uncertainty": result.uncertainty,
                "notes": result.notes,
                "reproducibility_hash": result.reproducibility_hash,
                "epistemic_status": EpistemicStatus.MEASUREMENT.value,
            },
        )

        # Add DERIVED_FROM edges from COMPUTED node to each input
        for nid in resolved_ids:
            self.graph.add_edge(node_id, nid, EdgeType.DERIVED_FROM)

        self.graph.save()

        return {
            "computed_node_id": node_id,
            "kernel": result.kernel,
            "kernel_version": result.kernel_version,
            "outputs": result.outputs,
            "uncertainty": result.uncertainty,
            "notes": result.notes,
            "reproducibility_hash": result.reproducibility_hash,
            "input_node_ids": resolved_ids,
            "n_values": len(values),
        }

    def compute_effect_size(
        self,
        group_a_node_ids: List[str],
        group_b_node_ids: List[str],
        metric_name: str = "value",
    ) -> Dict[str, Any]:
        """
        Run StatisticsKernel.effect_size() on two groups of nodes.

        Pulls numeric values for the specified metric from each group's nodes,
        computes Cohen's d, and stores the result as a COMPUTED node with
        DERIVED_FROM edges.

        Parameters
        ----------
        group_a_node_ids, group_b_node_ids:
            Node IDs for each group (EXPERIMENT or MEASUREMENT nodes).
        metric_name:
            Which metric to extract. Must match a key in the node's
            `results` JSON dict or a direct metadata key.
            Default: "value" (the standard MEASUREMENT field).

            IMPORTANT: precision, recall, and f1 are not the same
            measurement -- never omit this parameter when nodes contain
            multiple numeric fields. Averaging all numeric values from
            a node (the v4.6 bug this fixes) conflates distinct metrics.

        Returns a summary dict with the computed node ID and all outputs.
        """
        def _pull_values(node_ids: List[str]) -> List[float]:
            values = []
            for nid in node_ids:
                node = self.graph.get_node(nid)
                if node is None:
                    raise ValueError(f"Node not found: {nid}")
                meta = node.get("metadata", {})
                numeric = []
                # Extract only the requested metric -- never iterate all values().
                # Iterating all values conflates distinct metrics (e.g. precision,
                # recall, f1) into a single list, producing meaningless statistics.
                if "results" in meta and isinstance(meta["results"], str):
                    try:
                        results_dict = json.loads(meta["results"])
                        if metric_name in results_dict:
                            v = results_dict[metric_name]
                            if isinstance(v, (int, float)):
                                numeric.append(float(v))
                    except (json.JSONDecodeError, TypeError):
                        pass
                # Also check direct metadata key
                if metric_name in meta:
                    val = meta[metric_name]
                    if isinstance(val, (int, float)):
                        numeric.append(float(val))
                    elif isinstance(val, str):
                        try:
                            numeric.append(float(val))
                        except ValueError:
                            pass
                if not numeric:
                    raise ValueError(
                        f"No numeric values found in node {nid} for metric '{metric_name}'. "
                        f"Node metadata keys: {list(meta.keys())}"
                    )
                values.extend(numeric)
            return values

        group_a_values = _pull_values(group_a_node_ids)
        group_b_values = _pull_values(group_b_node_ids)

        all_ids = list(group_a_node_ids) + list(group_b_node_ids)

        result: ComputedResult = self.statistics_kernel.effect_size(
            group_a_values,
            group_b_values,
            input_node_ids=all_ids,
        )

        node_id = f"computed_{result.reproducibility_hash[:12]}"

        self.graph.add_node(
            node_id=node_id,
            ntype=NodeType.COMPUTED,
            label=f"Effect Size: Cohen's d={result.outputs['cohens_d']:.3f}",
            metadata={
                "kernel": result.kernel,
                "kernel_version": result.kernel_version,
                "outputs": result.outputs,
                "uncertainty": result.uncertainty,
                "notes": result.notes,
                "reproducibility_hash": result.reproducibility_hash,
                "epistemic_status": EpistemicStatus.MEASUREMENT.value,
            },
        )

        for nid in all_ids:
            self.graph.add_edge(node_id, nid, EdgeType.DERIVED_FROM)

        self.graph.save()

        return {
            "computed_node_id": node_id,
            "kernel": result.kernel,
            "kernel_version": result.kernel_version,
            "outputs": result.outputs,
            "reproducibility_hash": result.reproducibility_hash,
            "group_a_node_ids": list(group_a_node_ids),
            "group_b_node_ids": list(group_b_node_ids),
            "n_group_a": len(group_a_values),
            "n_group_b": len(group_b_values),
        }
