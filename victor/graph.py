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
        self._embeddings: Dict[str, List[float]] = {}
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if self.graph_file.exists():
            try:
                with open(self.graph_file) as f:
                    data = json.load(f)
                self._g          = nx.node_link_graph(data["graph"], edges="links")
                self._embeddings = data.get("embeddings", {})
                logger.info(
                    "Loaded graph: %d nodes, %d edges from %s",
                    self._g.number_of_nodes(),
                    self._g.number_of_edges(),
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
                self._embeddings = {}

    def save(self):
        """Atomically persist the graph.

        Writes to a .tmp sibling first, then renames over the target.
        A crash mid-write leaves the .tmp orphan; the original file is
        untouched.  Previously a crash mid-write corrupted graph.json
        permanently (Bug #4 from the v4.5 known-bug list).
        """
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "graph":      nx.node_link_data(self._g, edges="links"),
            "embeddings": self._embeddings,
        }
        tmp_file = self.graph_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w") as f:
                json.dump(data, f, indent=2)
            tmp_file.replace(self.graph_file)   # atomic on POSIX
        except Exception:
            tmp_file.unlink(missing_ok=True)    # clean up orphan on failure
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

    def semantic_query(
        self,
        query:         str,
        top_k:         int = 5,
        ntype_filter:  Optional[str] = None,
    ) -> List[Tuple[str, float, Dict]]:
        if not self._embeddings:
            return []
        q_emb  = self.embedder.embed(query)
        scores = []
        for nid, emb in self._embeddings.items():
            if not self._g.has_node(nid):
                continue
            node_data = self._g.nodes[nid]
            if ntype_filter and node_data.get("ntype") != ntype_filter:
                continue
            score = LocalEmbedder.cosine(q_emb, emb)
            scores.append((nid, score, node_data))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def get_neighbors(
        self, node_id: str, hops: int = 2
    ) -> List[Tuple[str, Dict, str]]:
        if not self._g.has_node(node_id):
            return []
        visited  = set()
        frontier = [(node_id, 0)]
        results  = []
        while frontier:
            nid, depth = frontier.pop(0)
            if nid in visited or depth > hops:
                continue
            visited.add(nid)
            for _, neighbor, edge_data in self._g.out_edges(nid, data=True):
                if neighbor not in visited:
                    results.append((
                        neighbor,
                        self._g.nodes[neighbor],
                        edge_data.get("etype", "related"),
                    ))
                    frontier.append((neighbor, depth + 1))
            for predecessor, _, edge_data in self._g.in_edges(nid, data=True):
                if predecessor not in visited:
                    results.append((
                        predecessor,
                        self._g.nodes[predecessor],
                        edge_data.get("etype", "related"),
                    ))
                    frontier.append((predecessor, depth + 1))
        return results

    # ── Importance + temporal decay ───────────────────────────────────────────

    def record_retrieval(self, node_id: str):
        """
        Called whenever a node contributes to a retrieval result.
        - Increments importance_score by 0.05 (capped at 1.0)
        - Updates last_retrieved_at to now
        """
        node = self._g.nodes.get(node_id)
        if node is None:
            return
        meta = node.get("metadata", {})
        current = meta.get("importance_score", _DEFAULT_IMPORTANCE.get(node.get("ntype", ""), 0.5))
        meta["importance_score"] = min(1.0, current + 0.05)
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
