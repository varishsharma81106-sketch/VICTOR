"""
VictorKnowledgeGraph — v4

Changes from v3:
  - CRITICAL BUG FIX: confirms/contradicts edge direction now uses ConflictDetector
    (LLM-based) instead of the broken keyword heuristic ("improv"/"better"/etc.)
  - EpistemicStatus stamped on every node at creation time
  - importance_score field on every node (starts at type default, increments on retrieval)
  - last_retrieved_at timestamp on every node (for temporal decay, F-014)
  - add_conversation_node: stores Q&A sessions as CONVERSATION nodes (Layer 5 Phase A)
  - freeze_node / delete_node: user control over individual nodes
  - inspect_node: structured view of any node by ID
  - delete_source: removes a document and all derived nodes from graph + vector store
"""
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import logging
import uuid

logger = logging.getLogger(__name__)

import networkx as nx
import numpy as np

from .models import (
    NodeType, EdgeType, EpistemicStatus,
    Claim, Experiment, ConversationTurn,
)
from .embedder import LocalEmbedder

if TYPE_CHECKING:
    from .reasoning import ConflictDetector


# Default importance scores by node type (PRD spec)
_DEFAULT_IMPORTANCE = {
    NodeType.EXPERIMENT:   0.80,
    NodeType.OBSERVATION:  0.90,   # MEASUREMENT tier — highest trust, highest importance
    NodeType.CLAIM:        0.70,
    NodeType.PAPER:        0.65,
    NodeType.NOTE:         0.60,
    NodeType.CONCEPT:      0.55,
    NodeType.CONVERSATION: 0.50,
}

# Default epistemic status by node type
_DEFAULT_EPISTEMIC = {
    NodeType.PAPER:        EpistemicStatus.LITERATURE,
    NodeType.CLAIM:        EpistemicStatus.LITERATURE,
    NodeType.EXPERIMENT:   EpistemicStatus.EXPERIMENT,
    NodeType.OBSERVATION:  EpistemicStatus.MEASUREMENT,  # sensors → highest trust
    NodeType.NOTE:         EpistemicStatus.NOTE,
    NodeType.CONCEPT:      EpistemicStatus.NOTE,
    NodeType.CONVERSATION: EpistemicStatus.NOTE,
}


class _EmbeddingStore(dict):
    """
    A dict of node_id -> vector that tells the graph when it has changed.

    The graph keeps a stacked float32 matrix of these vectors so similarity
    search is one matmul instead of N Python calls. That cache is only safe if
    *every* mutation invalidates it, and embeddings are written from six
    different places in this file. Rather than remember to invalidate at each
    one — the same "guard missed on one path" mistake that produced three
    separate masking leaks in this codebase — mutation itself is the signal.
    """

    def __init__(self, *args, **kwargs):
        self._dirty = True
        super().__init__(*args, **kwargs)

    def _touch(self):
        self._dirty = True

    def __setitem__(self, key, value):
        self._touch()
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self._touch()
        super().__delitem__(key)

    def pop(self, *args, **kwargs):
        self._touch()
        return super().pop(*args, **kwargs)

    def popitem(self):
        self._touch()
        return super().popitem()

    def clear(self):
        self._touch()
        super().clear()

    def update(self, *args, **kwargs):
        self._touch()
        super().update(*args, **kwargs)

    def setdefault(self, *args, **kwargs):
        self._touch()
        return super().setdefault(*args, **kwargs)


class VictorKnowledgeGraph:
    def __init__(
        self,
        graph_file: Path,
        embedder:   LocalEmbedder,
        conflict_detector: Optional["ConflictDetector"] = None,
    ):
        self.graph_file         = graph_file
        self.embedder           = embedder
        self.conflict_detector  = conflict_detector
        self._g:         nx.DiGraph            = nx.DiGraph()
        self._embeddings: Dict[str, List[float]] = _EmbeddingStore()
        self._emb_ids:    List[str]               = []
        self._emb_matrix: Optional[np.ndarray]    = None
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────
    #
    # Vectors live beside the graph, not inside it.
    #
    # Embeddings are ~95% of the bytes: at 10,000 nodes the single-file format
    # produced a 117 MB JSON that took 8.9 s to write and 2.4 s to read, and it
    # was rewritten in full after every ingest. 384 float64s rendered as decimal
    # text cost ~8 KB per node; the same vector as binary float32 costs 1.5 KB.
    # Splitting them makes graph.json small enough to stay human-readable and
    # diffable — which is the reason it was JSON in the first place.
    #
    # Old single-file graphs still load; the next save migrates them.

    @property
    def _emb_file(self) -> Path:
        return self.graph_file.with_suffix(".emb.npz")

    def _load(self):
        if not self.graph_file.exists():
            return
        try:
            with open(self.graph_file) as f:
                data = json.load(f)
            self._g = nx.node_link_graph(data["graph"], edges="links")

            inline = data.get("embeddings") or {}
            if inline:
                # Legacy single-file graph, or a ragged-dimension fallback.
                self._embeddings = _EmbeddingStore(inline)
            else:
                self._embeddings = _EmbeddingStore(self._load_embeddings())

            logger.info(
                "Loaded graph: %d nodes, %d edges, %d embeddings from %s",
                self._g.number_of_nodes(),
                self._g.number_of_edges(),
                len(self._embeddings),
                self.graph_file,
            )
        except Exception as exc:
            # Previously swallowed silently — a corrupted graph.json would
            # produce an empty graph with no warning, causing silent data loss.
            logger.error(
                "Failed to load graph from %s: %s — starting with empty graph. "
                "Original file preserved; investigate before next save.",
                self.graph_file,
                exc,
            )
            self._g          = nx.DiGraph()
            self._embeddings = _EmbeddingStore()

    def _load_embeddings(self) -> Dict[str, List[float]]:
        if not self._emb_file.exists():
            return {}
        try:
            with np.load(self._emb_file, allow_pickle=False) as npz:
                ids = npz["ids"]
                mat = npz["vectors"]
            return {str(i): v.tolist() for i, v in zip(ids, mat)}
        except Exception as exc:
            # A missing or unreadable sidecar degrades search quality but must
            # not cost the user their graph — the topology is the irreplaceable
            # part, and embeddings can be recomputed from labels.
            logger.error(
                "Failed to load embeddings from %s: %s — graph loaded without "
                "vectors; semantic search will be empty until re-embedded.",
                self._emb_file,
                exc,
            )
            return {}

    def save(self):
        """Atomically persist the graph and its vector sidecar.

        Each file is written to a .tmp sibling and renamed over the target, so
        a crash mid-write leaves an orphan .tmp and the original intact (Bug #4
        from the v4.5 known-bug list).

        The sidecar is renamed *before* graph.json. A crash between the two
        renames therefore leaves new vectors with an old topology, and vectors
        for nodes that do not exist are already skipped by every reader. The
        reverse order would leave nodes with no vector, which silently drops
        them out of search.
        """
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"graph": nx.node_link_data(self._g, edges="links")}

        ids, matrix = self._stack_embeddings()
        if matrix is None:
            # Ragged or non-numeric vectors — usually a mid-life embedder model
            # change. Fall back to inlining rather than dropping them.
            if self._embeddings:
                payload["embeddings"] = dict(self._embeddings)
            # Any sidecar still on disk is now stale, and _load prefers the
            # inline copy only when it is non-empty — leaving the old file would
            # resurrect deleted vectors on the next load.
            self._emb_file.unlink(missing_ok=True)
        else:
            def _write_npz(p: Path) -> None:
                # Handed an open file, not a path: np.savez appends ".npz" to
                # any path that lacks it, which would turn the atomic temp file
                # "graph.emb.npz.tmp" into "graph.emb.npz.tmp.npz" and leave the
                # rename pointing at nothing.
                with open(p, "wb") as fh:
                    np.savez(fh, ids=np.array(ids), vectors=matrix)

            self._atomic_write(self._emb_file, _write_npz)

        self._atomic_write(
            self.graph_file,
            lambda p: p.write_text(json.dumps(payload, indent=2)),
        )

    @staticmethod
    def _atomic_write(target: Path, write: Any) -> None:
        tmp = target.with_suffix(target.suffix + ".tmp")
        try:
            write(tmp)
            tmp.replace(target)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    # ── Nodes ─────────────────────────────────────────────────────────────────

    def add_node(
        self,
        node_id:          str,
        ntype:            str,
        label:            str,
        metadata:         Optional[Dict[str, Any]] = None,
        epistemic_status: Optional[str]            = None,
    ) -> str:
        """
        Add a node with:
          - semantic embedding of its label
          - EpistemicStatus (defaults by ntype)
          - importance_score (defaults by ntype)
          - last_retrieved_at = now
          - frozen = False
        """
        meta = metadata or {}

        # Set defaults for v4 fields if not supplied
        if "epistemic_status" not in meta:
            default_ep = _DEFAULT_EPISTEMIC.get(ntype, EpistemicStatus.NOTE)
            meta["epistemic_status"] = (
                epistemic_status if epistemic_status else default_ep.value
            )
        if "importance_score" not in meta:
            meta["importance_score"] = _DEFAULT_IMPORTANCE.get(ntype, 0.5)
        if "last_retrieved_at" not in meta:
            meta["last_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        if "frozen" not in meta:
            meta["frozen"] = False

        # Masked memory: content withheld from LLM answers until user unmasks.
        # Graph structure (edges, embeddings) remains fully intact regardless.
        # Principle: scope-before-routing (ShardMemo 2601.21545) — the flag is
        # checked at retrieval time, not at generation time.
        if "is_masked" not in meta:
            meta["is_masked"] = False

        self._g.add_node(node_id, ntype=ntype, label=label, metadata=meta)

        if node_id not in self._embeddings:
            self._embeddings[node_id] = self.embedder.embed(f"{ntype}: {label}")

        return node_id

    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        return self._g.nodes.get(node_id)

    def freeze_node(self, node_id: str) -> bool:
        """Lock a node so it cannot be overwritten by new extraction."""
        node = self._g.nodes.get(node_id)
        if node is None:
            return False
        node["metadata"]["frozen"] = True
        return True

    def unfreeze_node(self, node_id: str) -> bool:
        node = self._g.nodes.get(node_id)
        if node is None:
            return False
        node["metadata"]["frozen"] = False
        return True

    # ── Masked memory ─────────────────────────────────────────────────────────
    # Based on three principles from recent research:
    #   1. Scope-before-routing (ShardMemo 2601.21545): apply eligibility
    #      constraints before ANN/routing, not after.
    #   2. Retrieval-phase enforcement (SD-RAG 2601.11199): disclosure controls
    #      belong in retrieve.py, not in the LLM prompt.
    #   3. Dual-view (PrivGemo 2601.08739): full graph for structure reasoning
    #      (ConflictDetector, GapDetector), masked view for LLM context assembly.
    #
    # Victor-specific: unlike those papers (privacy from remote LLMs), this is
    # user-controlled revelation on a local device. The researcher decides which
    # nodes surface in answers. Masked nodes still contribute to graph routing,
    # edge traversal, and epistemic reasoning — they just don't appear as content
    # in retrieval results.

    def mask_node(self, node_id: str) -> bool:
        """Mask a node — withholds content from LLM answers.
        Graph edges, embeddings, and structural reasoning are unaffected."""
        node = self._g.nodes.get(node_id)
        if node is None:
            return False
        node["metadata"]["is_masked"] = True
        return True

    def unmask_node(self, node_id: str) -> bool:
        """Unmask a node — allow its content to surface in answers."""
        node = self._g.nodes.get(node_id)
        if node is None:
            return False
        node["metadata"]["is_masked"] = False
        return True

    def node_is_masked(self, node_id: str) -> bool:
        """Return True if node exists and is currently masked."""
        node = self._g.nodes.get(node_id)
        if node is None:
            return False
        return bool(node.get("metadata", {}).get("is_masked", False))

    def list_masked_nodes(self) -> List[Dict[str, Any]]:
        """Return all masked nodes with their full data."""
        return [
            {"id": nid, **data}
            for nid, data in self._g.nodes(data=True)
            if data.get("metadata", {}).get("is_masked", False)
        ]

    def inspect_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Return a structured view of any node by ID.
        Includes edges in/out, evidence summary sketch, and all metadata.
        """
        node = self._g.nodes.get(node_id)
        if node is None:
            return None

        in_edges  = [
            {"from": src, "etype": data.get("etype"), "weight": data.get("weight", 1.0),
             "confidence": data.get("metadata", {}).get("confidence")}
            for src, _, data in self._g.in_edges(node_id, data=True)
        ]
        out_edges = [
            {"to": dst, "etype": data.get("etype"), "weight": data.get("weight", 1.0),
             "confidence": data.get("metadata", {}).get("confidence")}
            for _, dst, data in self._g.out_edges(node_id, data=True)
        ]

        return {
            "node_id":         node_id,
            "ntype":           node.get("ntype"),
            "label":           node.get("label"),
            "metadata":        node.get("metadata", {}),
            "in_edges":        in_edges,
            "out_edges":       out_edges,
            "degree_in":       self._g.in_degree(node_id),
            "degree_out":      self._g.out_degree(node_id),
        }

    def delete_node(self, node_id: str, force: bool = False) -> bool:
        """
        Remove a node and all its edges from the graph.
        Frozen nodes cannot be deleted unless force=True.
        """
        node = self._g.nodes.get(node_id)
        if node is None:
            return False
        if node.get("metadata", {}).get("frozen") and not force:
            return False   # frozen — refuse unless forced
        self._g.remove_node(node_id)
        self._embeddings.pop(node_id, None)
        return True

    def delete_source(self, source_id: str) -> Dict[str, int]:
        """
        Remove a document and ALL nodes derived from it:
          - the document node itself
          - all claim nodes with source_id == source_id
          - all concept nodes added from source_id
          - all GROUNDED_IN edges pointing to any of those

        Returns counts of what was removed.
        Call vector_store.delete_source(source_id) separately for chunks.
        """
        to_delete = []

        # The source node itself
        if self._g.has_node(source_id):
            to_delete.append(source_id)

        # Derived nodes
        for nid, data in list(self._g.nodes(data=True)):
            meta = data.get("metadata", {})
            if meta.get("source_id") == source_id:
                to_delete.append(nid)

        deleted = 0
        for nid in set(to_delete):
            if self._g.has_node(nid):
                node_data = self._g.nodes[nid]
                if node_data.get("metadata", {}).get("frozen"):
                    logger.info("Skipping frozen node %s during source deletion", nid)
                    continue
                self._g.remove_node(nid)
                self._embeddings.pop(nid, None)
                deleted += 1

        return {"deleted_nodes": deleted}

    # ── Edges ─────────────────────────────────────────────────────────────────

    def add_edge(
        self,
        from_id:  str,
        to_id:    str,
        etype:    str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        if not self._g.has_node(from_id) or not self._g.has_node(to_id):
            return
        if self._g.has_edge(from_id, to_id):
            # Update weight but PRESERVE the etype — previously this branch
            # silently dropped etype on duplicate edges, corrupting the typed
            # edge layer (the most foundational component of the graph).
            edge = self._g[from_id][to_id]
            edge["weight"] = edge.get("weight", 1.0) + 0.1
            if etype and edge.get("etype") != etype:
                edge["etype"] = etype
            if metadata:
                edge.setdefault("metadata", {}).update(metadata)
        else:
            self._g.add_edge(from_id, to_id, etype=etype,
                             weight=1.0, metadata=metadata or {})

    # ── Domain helpers ────────────────────────────────────────────────────────

    def add_paper(self, paper_id: str, title: str, metadata: dict = None) -> str:
        meta = metadata or {}
        meta.setdefault("epistemic_status", EpistemicStatus.LITERATURE.value)
        return self.add_node(paper_id, NodeType.PAPER, title, meta)

    def add_claim(self, claim: Claim) -> str:
        frozen_check = self._g.nodes.get(claim.claim_id)
        if frozen_check and frozen_check.get("metadata", {}).get("frozen"):
            return claim.claim_id   # skip frozen nodes

        nid = self.add_node(claim.claim_id, NodeType.CLAIM, claim.text, {
            "claim_type":       claim.claim_type,
            "metric":           claim.metric,
            "value":            claim.value,
            "benchmark":        claim.benchmark,
            "source_id":        claim.source_id,
            "epistemic_status": claim.epistemic_status,
            "extracted_by":     claim.extracted_by,
            "low_confidence":   claim.low_confidence,
        })
        self.add_edge(claim.source_id, claim.claim_id, EdgeType.MAKES_CLAIM)
        return nid

    def add_experiment(self, exp: Experiment) -> str:
        return self.add_node(exp.experiment_id, NodeType.EXPERIMENT, exp.name, {
            "description":      exp.description,
            "model":            exp.model,
            "technique":        exp.technique,
            "results":          json.dumps(exp.results),
            "date":             exp.date,
            "epistemic_status": exp.epistemic_status,
        })

    def add_note(self, note_id: str, title: str, metadata: dict = None) -> str:
        meta = metadata or {}
        meta.setdefault("epistemic_status", EpistemicStatus.NOTE.value)
        return self.add_node(note_id, NodeType.NOTE, title, meta)

    def add_concept(self, name: str, source_id: str) -> str:
        concept_id = f"concept_{name.lower().replace(' ', '_')}"
        self.add_node(concept_id, NodeType.CONCEPT, name, {})
        self.add_edge(source_id, concept_id, EdgeType.CONTAINS)
        return concept_id

    def add_observation(self, obs) -> str:
        """
        Add an ObservationResult as a MEASUREMENT node — the highest-trust
        tier in the Epistemic Artifact hierarchy.

        All 6 Epistemic Artifact properties are stored in node metadata:
          1. Origin      — sensor_type, sensor_id, model_used, session_id
          2. Type        — ntype=OBSERVATION, epistemic_status=MEASUREMENT
          3. Confidence  — obs.confidence (model or manual)
          4. Contradictions — obs.contradictions (empty list at creation)
          5. Gaps        — obs.gaps (verification needed)
          6. Age         — obs.timestamp, obs.decay_status

        Returns the node ID (obs.observation_id).
        """
        from .models import ObservationResult   # avoid circular import at module level
        nid = self.add_node(
            node_id          = obs.observation_id,
            ntype            = NodeType.OBSERVATION,
            label            = obs.to_label(),
            epistemic_status = obs.epistemic_status,
            metadata         = {
                # 1. Origin
                "sensor_type": obs.sensor_type,
                "sensor_id":   obs.sensor_id,
                "model_used":  obs.model_used,
                "session_id":  obs.session_id,
                # 2. Type (also encoded in ntype + epistemic_status above)
                "epistemic_status": obs.epistemic_status,
                # 3. Confidence
                "label":       obs.label,
                "confidence":  obs.confidence,
                # 4. Contradictions
                "contradictions": obs.contradictions,
                # 5. Gaps
                "gaps":        obs.gaps,
                # 6. Age
                "timestamp":   obs.timestamp,
                "decay_status": obs.decay_status,
                # Provenance extras
                "image_path":  obs.image_path,
                **obs.metadata,
            },
        )
        logger.info(
            "Added OBSERVATION node %s — label='%s' confidence=%.3f sensor=%s",
            nid, obs.label, obs.confidence, obs.sensor_id,
        )
        return nid

    def add_conversation_node(self, turn: ConversationTurn) -> str:
        """
        Store a Q&A session as a CONVERSATION node in the graph.
        Creates GROUNDED_IN edges to every source node that contributed.
        This is Phase A of Layer 5 (self-learning via conversation memory).
        """
        label = turn.query[:120]   # label = the question asked
        nid = self.add_node(turn.turn_id, NodeType.CONVERSATION, label, {
            "query":         turn.query,
            "answer":        turn.answer[:2000],   # cap storage
            "provider_used": turn.provider_used,
            "timestamp":     turn.timestamp,
            "epistemic_status": EpistemicStatus.NOTE.value,
        })

        # Link to source nodes
        for src_id in turn.source_ids:
            if self._g.has_node(src_id):
                self.add_edge(nid, src_id, EdgeType.GROUNDED_IN)

        # Store embedding of the query for pattern detection
        if turn.query_embedding:
            self._embeddings[nid] = turn.query_embedding

        return nid

    # ── Experiment → Claim linking (FIXED — LLM-based, not keyword heuristic) ─

    def link_experiment_to_claims(
        self,
        experiment:           Experiment,
        similarity_threshold: float = 0.75,
    ) -> List[Tuple[str, str, str, float]]:
        """
        For each string in experiment.claims_tested, find the most similar
        claim node and create confirms/contradicts/inconclusive edges.

        v4 FIX: direction is determined by ConflictDetector (LLM-based).
        If ConflictDetector is not available, falls back to INCONCLUSIVE
        (never to the broken keyword heuristic).

        Returns list of (claim_id, claim_label, edge_type, confidence).
        """
        if not experiment.claims_tested:
            return []

        claim_nodes = [
            (nid, data["label"])
            for nid, data in self._g.nodes(data=True)
            if data.get("ntype") == NodeType.CLAIM
        ]
        if not claim_nodes:
            return []

        result_text = json.dumps(experiment.results)
        links = []

        for tested_text in experiment.claims_tested:
            q_emb      = self.embedder.embed(tested_text)
            best_score = 0.0
            best_nid   = None
            best_label = ""

            for claim_id, claim_label in claim_nodes:
                if claim_id not in self._embeddings:
                    continue
                score = LocalEmbedder.cosine(q_emb, self._embeddings[claim_id])
                if score > best_score:
                    best_score = score
                    best_nid   = claim_id
                    best_label = claim_label

            if not (best_nid and best_score >= similarity_threshold):
                continue

            # ── LLM-based direction judgment (THE FIX) ────────────────────────
            if self.conflict_detector is not None:
                judgment = self.conflict_detector.judge(
                    claim_text=best_label,
                    result_text=result_text,
                )
                direction  = judgment.direction    # "confirm" | "contradict" | "inconclusive"
                confidence = judgment.confidence
                reason     = judgment.reason
            else:
                # No LLM available — safe default, not a wrong answer
                direction  = "inconclusive"
                confidence = 0.0
                reason     = "ConflictDetector not available"

            edge_map = {
                "confirm":      EdgeType.CONFIRMS,
                "contradict":   EdgeType.CONTRADICTS,
                "inconclusive": EdgeType.INCONCLUSIVE,
            }
            etype = edge_map.get(direction, EdgeType.INCONCLUSIVE)

            self.add_edge(experiment.experiment_id, best_nid, etype, {
                "score":          best_score,
                "confidence":     confidence,
                "reason":         reason,
                "tested_text":    tested_text,
                "nli_direction":  judgment.nli_direction  if self.conflict_detector else None,
                "nli_confidence": judgment.nli_confidence if self.conflict_detector else None,
                "nli_override":   judgment.nli_override   if self.conflict_detector else False,
            })
            links.append((best_nid, best_label, etype, confidence))

        return links

    # ── Retrieval ─────────────────────────────────────────────────────────────

    def _stack_embeddings(self) -> Tuple[List[str], Optional[np.ndarray]]:
        """
        Return (ids, row-normalised float32 matrix), rebuilding only when the
        embedding store has been mutated since the last call.

        Returns (ids, None) when the vectors are ragged — different dimensions
        in one graph, which happens if the embedder model changes mid-life.
        Callers fall back to the per-vector path rather than guessing.
        """
        if self._emb_matrix is not None and not self._embeddings._dirty:
            return self._emb_ids, self._emb_matrix

        ids = list(self._embeddings.keys())
        if not ids:
            self._emb_ids, self._emb_matrix = [], None
            self._embeddings._dirty = False
            return [], None

        try:
            mat = np.asarray([self._embeddings[i] for i in ids], dtype=np.float32)
        except (ValueError, TypeError):
            mat = None
        if mat is None or mat.ndim != 2:
            logger.warning(
                "Embeddings are not a uniform matrix (%d vectors) — falling back "
                "to per-vector similarity. Re-embed the graph to restore speed.",
                len(ids),
            )
            self._emb_ids, self._emb_matrix = ids, None
            self._embeddings._dirty = False
            return ids, None

        # LocalEmbedder already returns unit vectors, but conversation turns and
        # legacy graphs may carry un-normalised ones. Normalising once here is
        # what lets the query be a bare dot product.
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        np.divide(mat, norms, out=mat, where=norms > 0)

        self._emb_ids, self._emb_matrix = ids, mat
        self._embeddings._dirty = False
        return ids, mat

    def semantic_query(
        self,
        query:         str,
        top_k:         int = 5,
        ntype_filter:  Optional[str] = None,
    ) -> List[Tuple[str, float, Dict]]:
        if not self._embeddings:
            return []
        q_emb = self.embedder.embed(query)

        ids, mat = self._stack_embeddings()
        if mat is None:
            return self._semantic_query_scalar(q_emb, top_k, ntype_filter)

        q = np.asarray(q_emb, dtype=np.float32)
        if q.shape[0] != mat.shape[1]:
            # Query embedder disagrees with the stored vectors — comparing them
            # would produce a shape error or, worse, a meaningless number.
            logger.error(
                "Query embedding is %d-dim but the graph stores %d-dim vectors; "
                "returning no results rather than nonsense scores.",
                q.shape[0], mat.shape[1],
            )
            return []
        qn = float(np.linalg.norm(q))
        if qn > 0:
            q = q / qn

        sims = mat @ q

        # Rank first, filter second. Filtering is per-node Python work, so doing
        # it after the sort means it touches only as many nodes as it takes to
        # fill top_k — typically top_k itself, not the whole graph.
        results: List[Tuple[str, float, Dict]] = []
        for idx in np.argsort(-sims):
            nid = ids[idx]
            if not self._g.has_node(nid):
                continue
            if self.node_is_masked(nid):
                continue
            node_data = self._g.nodes[nid]
            if ntype_filter and node_data.get("ntype") != ntype_filter:
                continue
            results.append((nid, float(sims[idx]), node_data))
            if len(results) >= top_k:
                break
        return results

    def _semantic_query_scalar(
        self,
        q_emb:        List[float],
        top_k:        int,
        ntype_filter: Optional[str],
    ) -> List[Tuple[str, float, Dict]]:
        """Ragged-embedding fallback. Correct, O(N) in Python, and rare."""
        scores = []
        for nid, emb in self._embeddings.items():
            if not self._g.has_node(nid):
                continue
            if self.node_is_masked(nid):
                continue
            node_data = self._g.nodes[nid]
            if ntype_filter and node_data.get("ntype") != ntype_filter:
                continue
            if len(emb) != len(q_emb):
                continue
            scores.append((nid, LocalEmbedder.cosine(q_emb, emb), node_data))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_neighbors(
        self, node_id: str, hops: int = 2
    ) -> List[Tuple[str, Dict, str]]:
        """
        Nodes reachable from `node_id` within `hops` edges, either direction.

        `hops` counts edges walked and excludes the focus itself: hops=1 is the
        immediate neighbours, hops=2 adds theirs. The previous version expanded
        nodes that had already reached the limit, so every caller got one hop
        more than it asked for — a configured `graph_hop_depth` of 2 pulled
        3-hop nodes into retrieval context, which on a dense graph is an order
        of magnitude more text for the model to read.
        """
        if not self._g.has_node(node_id) or hops < 1:
            return []
        visited  = {node_id}
        frontier = [(node_id, 0)]
        results  = []
        while frontier:
            nid, depth = frontier.pop(0)
            if depth >= hops:
                continue
            adjacent = [(n, d) for _, n, d in self._g.out_edges(nid, data=True)]
            adjacent += [(n, d) for n, _, d in self._g.in_edges(nid, data=True)]
            for neighbor, edge_data in adjacent:
                if neighbor in visited:
                    continue
                # Marked on discovery rather than on expansion. BFS reaches a
                # node by its shortest path first, so this also fixes the
                # duplicate a node found from two parents in the same layer
                # used to produce.
                visited.add(neighbor)
                results.append((
                    neighbor,
                    self._g.nodes[neighbor],
                    edge_data.get("etype", "related"),
                ))
                frontier.append((neighbor, depth + 1))
        return results

    # ── Importance + temporal decay ───────────────────────────────────────────

    def record_retrieval(self, node_id: str):
        """
        Called whenever a node contributes to a retrieval result.
        - Increments importance_score by 0.05 (capped at 1.0)
        - Increments retrieval_count by 1 (uncapped, never decays)
        - Updates last_retrieved_at to now

        retrieval_count is deliberately separate from importance_score:
        importance is capped at 1.0 and decays over time (apply_temporal_decay),
        so it cannot answer "which sources do I consult most often?".
        PatternDetector.top_queried_sources reads this raw tally.
        """
        node = self._g.nodes.get(node_id)
        if node is None:
            return
        meta = node.get("metadata", {})
        current = meta.get("importance_score", _DEFAULT_IMPORTANCE.get(node.get("ntype", ""), 0.5))
        meta["importance_score"]  = min(1.0, current + 0.05)
        meta["retrieval_count"]   = meta.get("retrieval_count", 0) + 1
        meta["last_retrieved_at"] = datetime.now(timezone.utc).isoformat()

    def apply_temporal_decay(
        self,
        decay_rate:      float = 0.02,
        decay_period_days: int = 30,
        floor:           float = 0.10,
        stale_days:      int   = 90,
    ):
        """
        F-014: Nodes not retrieved in `stale_days` days decay their
        importance_score by `decay_rate` per `decay_period_days`.
        Score is floored at `floor` and never goes negative.

        Frozen nodes are exempt from decay.
        Conversation nodes are also exempt (they record history, not active knowledge).
        """
        now = datetime.now(timezone.utc)
        stale_threshold = timedelta(days=stale_days)
        period          = timedelta(days=decay_period_days)

        for nid, data in self._g.nodes(data=True):
            meta = data.get("metadata", {})
            if meta.get("frozen"):
                continue
            if data.get("ntype") == NodeType.CONVERSATION:
                continue

            last_str = meta.get("last_retrieved_at")
            if not last_str:
                continue

            try:
                last = datetime.fromisoformat(last_str)
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue

            age = now - last
            if age < stale_threshold:
                continue   # recently used — no decay

            periods_stale = (age - stale_threshold) / period
            decay_amount  = decay_rate * periods_stale
            current       = meta.get("importance_score", 0.5)
            meta["importance_score"] = max(floor, current - decay_amount)

    # ── Stats + listing ───────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for _, data in self._g.nodes(data=True):
            ntype = data.get("ntype", "unknown")
            counts[ntype] = counts.get(ntype, 0) + 1
        return {
            "total_nodes": self._g.number_of_nodes(),
            "total_edges": self._g.number_of_edges(),
            "by_type":     counts,
        }

    def list_nodes(self, ntype: str) -> List[Dict[str, Any]]:
        return [
            {"id": nid, **data}
            for nid, data in self._g.nodes(data=True)
            if data.get("ntype") == ntype
        ]
