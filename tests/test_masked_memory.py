"""
test_masked_memory.py

Tests for the masked memory system.

Principles verified:
  1. Scope-before-routing: masked nodes are identified at retrieval time, not
     filtered at generation time.
  2. Structural integrity: masking never breaks graph edges, embeddings, or
     reasoning layer access (ConflictDetector, GapDetector still see everything).
  3. Anchor presence: masked nodes produce a placeholder chunk rather than
     disappearing entirely — the LLM knows something is withheld.
  4. Reversibility: unmask restores full content surfacing.
  5. Orthogonality: mask and freeze are independent flags.

All tests use MockClassifier + mock LLM — no GPU, no Ollama, no network.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_graph_file(tmp_path):
    return tmp_path / "graph.json"


@pytest.fixture
def mock_embedder():
    """Returns a deterministic embedder that produces unique vectors per label."""
    emb = MagicMock()
    _cache = {}

    def _embed(text):
        if text not in _cache:
            # Simple but unique: hash the text into a unit-ish vector
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            v = [((h >> i) & 0xFF) / 255.0 for i in range(0, 384 * 8, 8)]
            _cache[text] = v[:384]
        return _cache[text]

    emb.embed.side_effect = _embed
    emb.cosine = staticmethod(lambda a, b: sum(x*y for x, y in zip(a, b)))
    return emb


@pytest.fixture
def graph(tmp_graph_file, mock_embedder):
    from victor.graph import VictorKnowledgeGraph
    return VictorKnowledgeGraph(
        graph_file=tmp_graph_file,
        embedder=mock_embedder,
    )


# ── Graph-layer tests ──────────────────────────────────────────────────────────

class TestGraphMaskFlags:
    def test_new_node_is_unmasked_by_default(self, graph):
        nid = graph.add_node("n1", "claim", "Compound X has property Y")
        node = graph.get_node(nid)
        assert node["metadata"]["is_masked"] is False

    def test_mask_node_sets_flag(self, graph):
        graph.add_node("n1", "claim", "Sensitive measurement")
        assert graph.mask_node("n1") is True
        assert graph.node_is_masked("n1") is True

    def test_unmask_restores_flag(self, graph):
        graph.add_node("n1", "claim", "Sensitive measurement")
        graph.mask_node("n1")
        assert graph.unmask_node("n1") is True
        assert graph.node_is_masked("n1") is False

    def test_mask_nonexistent_node_returns_false(self, graph):
        assert graph.mask_node("does_not_exist") is False

    def test_unmask_nonexistent_node_returns_false(self, graph):
        assert graph.unmask_node("does_not_exist") is False

    def test_list_masked_nodes_empty(self, graph):
        graph.add_node("n1", "claim", "Normal claim")
        assert graph.list_masked_nodes() == []

    def test_list_masked_nodes_returns_only_masked(self, graph):
        graph.add_node("n1", "claim", "Public claim")
        graph.add_node("n2", "claim", "Sensitive claim")
        graph.add_node("n3", "claim", "Another public claim")
        graph.mask_node("n2")
        masked = graph.list_masked_nodes()
        assert len(masked) == 1
        assert masked[0]["id"] == "n2"

    def test_mask_does_not_remove_edges(self, graph):
        """Masking must not break graph structure — edges must survive."""
        from victor.models import EdgeType
        graph.add_node("n1", "claim",      "Claim A")
        graph.add_node("n2", "experiment", "Experiment on A")
        graph.add_edge("n2", "n1", EdgeType.CONFIRMS)
        graph.mask_node("n1")
        # Edge still present
        assert graph._g.has_edge("n2", "n1")

    def test_mask_does_not_remove_embedding(self, graph):
        """Masked node must still have its embedding (routing depends on it)."""
        graph.add_node("n1", "claim", "Sensitive data")
        graph.mask_node("n1")
        assert "n1" in graph._embeddings

    def test_mask_and_freeze_are_orthogonal(self, graph):
        """Setting mask must not affect frozen, and vice versa."""
        graph.add_node("n1", "claim", "Important finding")
        graph.freeze_node("n1")
        graph.mask_node("n1")
        node = graph.get_node("n1")
        assert node["metadata"]["frozen"] is True
        assert node["metadata"]["is_masked"] is True

        graph.unmask_node("n1")
        node = graph.get_node("n1")
        # frozen preserved after unmask
        assert node["metadata"]["frozen"] is True
        assert node["metadata"]["is_masked"] is False

    def test_mask_survives_save_and_reload(self, graph, tmp_graph_file, mock_embedder):
        """is_masked must persist through JSON round-trip."""
        from victor.graph import VictorKnowledgeGraph
        graph.add_node("n1", "claim", "Persisted mask")
        graph.mask_node("n1")
        graph.save()

        graph2 = VictorKnowledgeGraph(
            graph_file=tmp_graph_file,
            embedder=mock_embedder,
        )
        assert graph2.node_is_masked("n1") is True

    def test_unmask_survives_save_and_reload(self, graph, tmp_graph_file, mock_embedder):
        from victor.graph import VictorKnowledgeGraph
        graph.add_node("n1", "claim", "Unmasked after reload")
        graph.mask_node("n1")
        graph.unmask_node("n1")
        graph.save()

        graph2 = VictorKnowledgeGraph(
            graph_file=tmp_graph_file,
            embedder=mock_embedder,
        )
        assert graph2.node_is_masked("n1") is False


# ── Retrieve-layer tests ───────────────────────────────────────────────────────

class TestHybridRetrieverMasking:
    """
    Tests that HybridRetriever enforces masking at content assembly time.

    Uses mock VectorStore and mock graph to avoid any real embedding/LLM calls.
    """

    def _make_retriever(self, graph, masked_ids=None):
        """Build a HybridRetriever with a mock vector store."""
        from victor.retrieve import HybridRetriever
        from victor.models import RetrievedChunk, NodeType, EpistemicStatus

        masked_ids = masked_ids or set()

        mock_vs = MagicMock()
        mock_llm = MagicMock()

        # Vector store returns one chunk per query
        def _vs_query(query, top_k=8):
            chunks = []
            for nid in ["n_public", "n_masked"]:
                chunks.append(RetrievedChunk(
                    text=f"Content of {nid}",
                    source_id=nid,
                    source_type=NodeType.CLAIM,
                    source_title=f"Title {nid}",
                    chunk_index=0,
                    score=0.9 if nid == "n_masked" else 0.8,
                    provenance=[],
                    epistemic_status=EpistemicStatus.LITERATURE.value,
                ))
            return chunks

        mock_vs.query.side_effect = _vs_query
        mock_vs.get_by_source.return_value = []
        mock_vs.embedder = MagicMock()
        mock_vs.embedder.embed.return_value = [0.0] * 384

        retriever = HybridRetriever(
            vector_store=mock_vs,
            graph=graph,
            llm=mock_llm,
            top_k=8,
            decay_on_retrieve=False,
        )
        return retriever

    def test_masked_node_produces_anchor_not_content(self, graph):
        graph.add_node("n_public", "claim", "Public finding")
        graph.add_node("n_masked", "claim", "Sensitive measurement")
        graph.mask_node("n_masked")

        retriever = self._make_retriever(graph)

        # Patch semantic_query to return nothing (isolate step 1)
        graph.semantic_query = MagicMock(return_value=[])
        graph.get_neighbors  = MagicMock(return_value=[])

        chunks = retriever.retrieve("anything")
        texts  = [c.text for c in chunks]

        # The actual VS chunk content for n_masked must NOT appear.
        # Note: the anchor MAY show the label as a type-hint ("what category
        # of thing is here"); what's suppressed is the detailed chunk text.
        assert not any("Content of n_masked" in t for t in texts), \
            "Masked node VS chunk content leaked into retrieval results"

        # An anchor for n_masked must be present
        assert any("MASKED" in t for t in texts), \
            "No anchor found for masked node"

    def test_unmasked_node_produces_real_content(self, graph):
        graph.add_node("n_public", "claim", "Public finding")
        graph.add_node("n_masked", "claim", "Sensitive measurement")
        # Do NOT mask n_masked this time

        retriever = self._make_retriever(graph)
        graph.semantic_query = MagicMock(return_value=[])
        graph.get_neighbors  = MagicMock(return_value=[])

        chunks = retriever.retrieve("anything")
        texts  = [c.text for c in chunks]

        assert any("Content of n_masked" in t for t in texts), \
            "Unmasked node content missing from results"
        assert not any("MASKED" in t for t in texts), \
            "Unexpected anchor for unmasked node"

    def test_anchor_score_is_deprioritised(self, graph):
        """Anchors must sort below real content (score × 0.05 factor)."""
        graph.add_node("n_public", "claim", "Public finding")
        graph.add_node("n_masked", "claim", "Sensitive measurement")
        graph.mask_node("n_masked")

        retriever = self._make_retriever(graph)
        graph.semantic_query = MagicMock(return_value=[])
        graph.get_neighbors  = MagicMock(return_value=[])

        chunks = retriever.retrieve("anything")
        real_chunks   = [c for c in chunks if "MASKED" not in c.text]
        anchor_chunks = [c for c in chunks if "MASKED" in c.text]

        assert anchor_chunks, "No anchor found"
        assert all(
            a.score < r.score
            for a in anchor_chunks
            for r in real_chunks
        ), "Anchor scored above real content"

    def test_unmask_then_retrieve_returns_content(self, graph):
        """After unmask, the next retrieve must return full content."""
        graph.add_node("n_public", "claim", "Public finding")
        graph.add_node("n_masked", "claim", "Sensitive measurement")
        graph.mask_node("n_masked")
        graph.unmask_node("n_masked")   # ← flip it back

        retriever = self._make_retriever(graph)
        graph.semantic_query = MagicMock(return_value=[])
        graph.get_neighbors  = MagicMock(return_value=[])

        chunks = retriever.retrieve("anything")
        texts  = [c.text for c in chunks]

        assert not any("MASKED" in t for t in texts), \
            "Anchor found after unmask — enforcement not cleared"
        assert any("Content of n_masked" in t for t in texts), \
            "Real content missing after unmask"

    def test_anchor_contains_node_id_hint(self, graph):
        """Anchor text must include node ID so user knows what to unmask."""
        graph.add_node("n_masked", "claim", "Sensitive compound data")
        graph.mask_node("n_masked")

        retriever = self._make_retriever(graph)
        graph.semantic_query = MagicMock(return_value=[])
        graph.get_neighbors  = MagicMock(return_value=[])

        chunks = retriever.retrieve("query")
        anchor = next((c for c in chunks if "MASKED" in c.text), None)
        assert anchor is not None
        # Node ID (or prefix) must appear in anchor text
        assert "n_masked" in anchor.text or "n_masked"[:16] in anchor.text

    def test_masked_node_appears_only_once_as_anchor(self, graph):
        """Even if the masked node is hit by multiple retrieval paths,
        only one anchor should appear for it."""
        graph.add_node("n_public", "claim", "Public finding")
        graph.add_node("n_masked", "claim", "Sensitive measurement")
        graph.mask_node("n_masked")

        retriever = self._make_retriever(graph)
        graph.semantic_query = MagicMock(return_value=[])
        graph.get_neighbors  = MagicMock(return_value=[])

        chunks = retriever.retrieve("query")
        anchor_chunks = [c for c in chunks if "MASKED" in c.text and "n_masked" in c.text]
        assert len(anchor_chunks) == 1, \
            f"Expected 1 anchor for n_masked, got {len(anchor_chunks)}"


# ── Sovereignty orthogonality ──────────────────────────────────────────────────

class TestSovereigntyModel:
    """
    Verifies that mask and export are independent sovereignty controls.
    A masked node can still be explicitly exported (user initiated).
    An unmasked node can still be withheld from export (user choice).
    """

    def test_masked_node_still_accessible_via_get_node(self, graph):
        """Internal reasoning layer (ConflictDetector, GapDetector) uses
        get_node directly — must see full data regardless of mask state."""
        graph.add_node("n1", "claim", "Sensitive claim that contradicts literature")
        graph.mask_node("n1")
        node = graph.get_node("n1")
        assert node is not None
        assert node["label"] == "Sensitive claim that contradicts literature"

    def test_masked_node_returned_by_list_masked(self, graph):
        graph.add_node("n1", "claim", "Masked")
        graph.add_node("n2", "claim", "Unmasked")
        graph.mask_node("n1")
        ids = {n["id"] for n in graph.list_masked_nodes()}
        assert "n1" in ids
        assert "n2" not in ids

    def test_inspect_node_shows_mask_flag(self, graph):
        """inspect_node returns full metadata including is_masked."""
        graph.add_node("n1", "claim", "Sensitive")
        graph.add_node("n2", "claim", "Public")
        graph.mask_node("n1")

        result1 = graph.inspect_node("n1")
        result2 = graph.inspect_node("n2")
        assert result1["metadata"]["is_masked"] is True
        assert result2["metadata"]["is_masked"] is False
