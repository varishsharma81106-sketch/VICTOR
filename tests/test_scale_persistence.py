"""
The split-sidecar storage format and the vectorised similarity search.

Both changes are invisible when they work and catastrophic when they don't: a
migration that drops vectors leaves a graph that still loads, still answers, and
silently returns worse results forever. So these tests care less about speed
than about the three ways the change can lose data —

  1. a graph written in the old single-file format stops loading,
  2. a vector changes value across a save/load round trip,
  3. the cached matrix goes stale and search answers from an old graph.

Only the last test looks at the clock, and it does so with a bound loose enough
to survive a loaded CI box while still failing if the O(N) Python loop returns.
"""
from __future__ import annotations

import json
import math
import time

import numpy as np
import pytest

from victor.graph import VictorKnowledgeGraph
from victor.models import NodeType


DIM = 32


class StubEmbedder:
    """Deterministic unit vectors keyed off the text — no model, no download."""

    def __init__(self, dim: int = DIM):
        self.dim = dim

    def embed(self, text: str):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(self.dim)
        return (v / np.linalg.norm(v)).tolist()

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


@pytest.fixture
def gfile(tmp_path):
    return tmp_path / "graph.json"


@pytest.fixture
def graph(gfile):
    g = VictorKnowledgeGraph(gfile, StubEmbedder())
    for i in range(12):
        g.add_node(f"n{i}", NodeType.CLAIM, f"claim number {i} about topic {i % 3}")
    return g


class TestSidecarFormat:
    def test_graph_json_no_longer_carries_vectors(self, graph, gfile):
        """
        The whole point of the split: graph.json stays small and readable.
        If vectors creep back in, the 117 MB / 8.9 s regression is back too.
        """
        graph.save()
        payload = json.loads(gfile.read_text())

        assert "embeddings" not in payload
        assert payload["graph"]["nodes"]
        assert graph._emb_file.exists()

    def test_round_trip_preserves_vectors(self, graph, gfile):
        before = {k: list(v) for k, v in graph._embeddings.items()}
        graph.save()

        reloaded = VictorKnowledgeGraph(gfile, StubEmbedder())

        assert set(reloaded._embeddings) == set(before)
        for nid, vec in before.items():
            # float32 on disk. Vectors from sentence-transformers are already
            # float32, so this is lossless in practice; the tolerance covers
            # hand-built float64 vectors like this fixture's.
            assert reloaded._embeddings[nid] == pytest.approx(vec, rel=1e-6)

    def test_sidecar_is_smaller_than_inlining_would_be(self, graph, gfile):
        graph.save()
        assert graph._emb_file.stat().st_size < gfile.stat().st_size * 20
        # The real assertion: binary float32 beats decimal text by a wide margin.
        inline_bytes = len(json.dumps({k: v for k, v in graph._embeddings.items()}))
        assert graph._emb_file.stat().st_size < inline_bytes


class TestLegacyMigration:
    def _write_legacy(self, gfile, graph):
        """Reproduce the pre-split single-file format byte-for-byte."""
        import networkx as nx

        gfile.write_text(json.dumps({
            "graph": nx.node_link_data(graph._g, edges="links"),
            "embeddings": {k: list(v) for k, v in graph._embeddings.items()},
        }, indent=2))

    def test_legacy_single_file_graph_still_loads(self, graph, gfile):
        expected = {k: list(v) for k, v in graph._embeddings.items()}
        self._write_legacy(gfile, graph)
        assert not graph._emb_file.exists()

        loaded = VictorKnowledgeGraph(gfile, StubEmbedder())

        assert loaded._g.number_of_nodes() == 12
        assert set(loaded._embeddings) == set(expected)
        assert loaded.semantic_query("topic 1", top_k=3)

    def test_legacy_graph_migrates_on_next_save(self, graph, gfile):
        self._write_legacy(gfile, graph)

        loaded = VictorKnowledgeGraph(gfile, StubEmbedder())
        loaded.save()

        assert "embeddings" not in json.loads(gfile.read_text())
        assert loaded._emb_file.exists()

        # And the migrated copy is still readable.
        again = VictorKnowledgeGraph(gfile, StubEmbedder())
        assert len(again._embeddings) == 12

    def test_missing_sidecar_keeps_the_topology(self, graph, gfile, caplog):
        """
        Losing vectors degrades search. Losing the graph loses the user's work.
        A deleted sidecar must cost only the former.
        """
        graph.save()
        graph._emb_file.unlink()

        loaded = VictorKnowledgeGraph(gfile, StubEmbedder())

        assert loaded._g.number_of_nodes() == 12
        assert loaded._embeddings == {}
        assert loaded.semantic_query("anything", top_k=3) == []

    def test_corrupt_sidecar_keeps_the_topology(self, graph, gfile):
        graph.save()
        graph._emb_file.write_bytes(b"not an npz file")

        loaded = VictorKnowledgeGraph(gfile, StubEmbedder())

        assert loaded._g.number_of_nodes() == 12
        assert loaded._embeddings == {}


class TestCacheInvalidation:
    """
    The matrix cache is the one piece of state that can silently answer from a
    stale graph. Every mutation path gets its own test.
    """

    def test_node_added_after_a_query_is_searchable(self, graph):
        graph.semantic_query("topic 0", top_k=3)          # populates the cache

        graph.add_node("fresh", NodeType.CLAIM, "a brand new distinctive claim")
        hits = graph.semantic_query("claim: a brand new distinctive claim", top_k=1)

        assert hits and hits[0][0] == "fresh"

    def test_node_deleted_after_a_query_disappears(self, graph):
        hits = graph.semantic_query("claim: claim number 5 about topic 2", top_k=1)
        assert hits[0][0] == "n5"

        graph.delete_node("n5")

        assert all(nid != "n5" for nid, _, _ in graph.semantic_query("claim: claim number 5 about topic 2", top_k=5))

    def test_masking_after_a_query_removes_the_node(self, graph):
        assert graph.semantic_query("claim: claim number 7 about topic 1", top_k=1)[0][0] == "n7"

        graph.mask_node("n7")

        assert all(nid != "n7" for nid, _, _ in graph.semantic_query("claim: claim number 7 about topic 1", top_k=5))

    def test_direct_embedding_write_invalidates(self, graph):
        """
        Not every vector arrives through add_node — conversation turns write
        straight into the dict. That path must invalidate too.
        """
        graph.semantic_query("topic 0", top_k=3)

        target = graph.add_node("conv", NodeType.CONVERSATION, "placeholder")
        graph._embeddings["conv"] = graph.embedder.embed("uniquely phrased sentinel text")

        hits = graph.semantic_query("uniquely phrased sentinel text", top_k=1)
        assert hits and hits[0][0] == "conv"


class TestSearchCorrectness:
    def test_matches_the_scalar_implementation(self, graph):
        """
        The vectorised path must rank identically to the loop it replaced —
        otherwise this is a behaviour change wearing a performance change's
        clothes.
        """
        q = graph.embedder.embed("claim number 3 about topic 0")

        fast = graph.semantic_query("claim number 3 about topic 0", top_k=5)
        slow = graph._semantic_query_scalar(q, top_k=5, ntype_filter=None)

        assert [n for n, _, _ in fast] == [n for n, _, _ in slow]
        for (_, a, _), (_, b, _) in zip(fast, slow):
            assert a == pytest.approx(b, abs=1e-5)

    def test_scores_are_real_cosines(self, graph):
        """A node queried by its own text scores ~1.0, not some rescaled number."""
        hits = graph.semantic_query("claim: claim number 4 about topic 1", top_k=1)
        assert hits[0][0] == "n4"
        assert hits[0][1] == pytest.approx(1.0, abs=1e-4)

    def test_ntype_filter_still_applies(self, graph):
        graph.add_node("p1", NodeType.PAPER, "claim number 1 about topic 1")
        hits = graph.semantic_query("claim number 1 about topic 1", top_k=5,
                                    ntype_filter=NodeType.PAPER)
        assert [n for n, _, _ in hits] == ["p1"]

    def test_top_k_is_respected_when_most_nodes_are_masked(self, graph):
        """
        Rank-then-filter fills top_k by walking down the ranking. If the walk
        stopped early this returns too few results.
        """
        for i in range(10):
            graph.mask_node(f"n{i}")

        hits = graph.semantic_query("topic", top_k=5)
        assert len(hits) == 2
        assert {n for n, _, _ in hits} == {"n10", "n11"}

    def test_dimension_mismatch_returns_nothing_not_garbage(self, graph):
        """A re-embedded query against old vectors must refuse, not guess."""
        hits = graph.semantic_query("topic 0", top_k=3)
        assert hits

        graph.embedder = StubEmbedder(dim=DIM * 2)
        assert graph.semantic_query("topic 0", top_k=3) == []

    def test_ragged_embeddings_fall_back_rather_than_crash(self, graph):
        graph._embeddings["odd"] = [0.1] * (DIM + 5)
        graph.add_node("odd", NodeType.NOTE, "an oddly sized vector")
        graph._embeddings["odd"] = [0.1] * (DIM + 5)

        ids, mat = graph._stack_embeddings()
        assert mat is None

        # Still answers, using the scalar path and skipping the odd vector.
        hits = graph.semantic_query("claim number 2 about topic 2", top_k=3)
        assert hits
        assert all(nid != "odd" for nid, _, _ in hits)

    def test_ragged_graph_round_trips_through_the_inline_fallback(self, graph, gfile):
        graph.add_node("odd", NodeType.NOTE, "an oddly sized vector")
        graph._embeddings["odd"] = [0.1] * (DIM + 5)
        graph.save()

        assert "embeddings" in json.loads(gfile.read_text())
        assert not graph._emb_file.exists()

        loaded = VictorKnowledgeGraph(gfile, StubEmbedder())
        assert len(loaded._embeddings["odd"]) == DIM + 5

    def test_stale_sidecar_is_removed_when_falling_back(self, graph, gfile):
        """
        Save clean, then save ragged. The old sidecar must go, or the next load
        resurrects vectors the inline copy no longer agrees with.
        """
        graph.save()
        assert graph._emb_file.exists()

        graph.add_node("odd", NodeType.NOTE, "an oddly sized vector")
        graph._embeddings["odd"] = [0.1] * (DIM + 5)
        graph.save()

        assert not graph._emb_file.exists()


class TestScaleBudget:
    """
    A guard rail, not a benchmark. Before the rewrite a 20,000-node query cost
    roughly 800 ms of pure Python; the matmul path costs single-digit ms. The
    bound below sits far above the fast path and far below the slow one, so it
    catches a regression to O(N) interpreted work without failing on a busy
    machine.
    """

    N = 20_000

    @pytest.fixture(scope="class")
    def big(self, tmp_path_factory):
        gf = tmp_path_factory.mktemp("big") / "graph.json"
        g = VictorKnowledgeGraph(gf, StubEmbedder())
        emb = StubEmbedder()
        # Bypass add_node's per-node embed call: this fixture is about query
        # cost, and building 20k nodes honestly would dominate the test run.
        for i in range(self.N):
            g._g.add_node(
                f"n{i}", ntype=NodeType.CLAIM, label=f"claim {i}",
                metadata={"importance_score": 0.5, "is_masked": False},
            )
        g._embeddings.update({f"n{i}": emb.embed(f"claim {i}") for i in range(self.N)})
        return g

    def test_query_stays_in_the_millisecond_range(self, big):
        big.semantic_query("claim 1", top_k=10)          # warm the matrix

        t0 = time.perf_counter()
        for i in range(5):
            big.semantic_query(f"claim {i * 37}", top_k=10)
        per_query = (time.perf_counter() - t0) / 5

        assert per_query < 0.15, f"{per_query * 1000:.0f} ms/query at {self.N:,} nodes"

    def test_the_matrix_is_built_once_not_per_query(self, big):
        big.semantic_query("claim 1", top_k=10)
        first = big._emb_matrix

        big.semantic_query("claim 2", top_k=10)

        assert big._emb_matrix is first
        assert first.dtype == np.float32
        assert first.shape == (self.N, DIM)

    def test_stored_vectors_are_unit_length(self, big):
        big.semantic_query("claim 1", top_k=10)
        norms = np.linalg.norm(big._emb_matrix, axis=1)
        assert np.allclose(norms, 1.0, atol=1e-5)
