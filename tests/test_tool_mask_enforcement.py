"""
test_tool_mask_enforcement.py

Regression test for a masking bypass found in review (2026-06-24):

retrieve.py enforces is_masked correctly at all three retrieval steps
(vector search, semantic graph query, 2-hop expansion) — see
test_masked_memory.py. But AgenticRetriever's agent loop also exposes four
graph-inspection tools directly to the LLM (get_node_details,
find_related_nodes, search_nodes_by_text, get_claims_for_source), and none
of them checked is_masked before this fix. Since a masked node's anchor
chunk hands the LLM the node_id ("...Use 'victor unmask {node_id}' to
reveal"), the LLM could call get_node_details(node_id) mid-answer and read
the full content — a complete bypass of masked memory that never required
the user to run `victor unmask`.

Fix: tools.py now checks self.graph.node_is_masked(...) in all four tools
and substitutes the same anchor shape retrieve.py already uses, so a
masked node looks identical (label preview truncated to 40 chars, full
content withheld) whether it's hit via retrieval or via a tool call.

Uses the real VictorKnowledgeGraph (not a mock) so the assertions are
against actual masking behavior, not a stub.
"""
import sys
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from victor.graph import VictorKnowledgeGraph
from victor.tools import _ToolImplementations
from victor.models import EdgeType

_SECRET_TAIL = "do not surface this anywhere"
_SECRET_LABEL = f"Compound Z cures everything, UNPUBLISHED embargoed details {_SECRET_TAIL}"


@pytest.fixture
def mock_embedder():
    emb = MagicMock()
    _cache = {}

    def _embed(text):
        if text not in _cache:
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            v = [((h >> i) & 0xFF) / 255.0 for i in range(0, 384 * 8, 8)]
            _cache[text] = v[:384]
        return _cache[text]

    emb.embed.side_effect = _embed
    emb.cosine = staticmethod(lambda a, b: sum(x * y for x, y in zip(a, b)))
    return emb


@pytest.fixture
def graph(tmp_path, mock_embedder):
    g = VictorKnowledgeGraph(graph_file=tmp_path / "graph.json", embedder=mock_embedder)
    g.add_node("paper1", "paper", "A paper about secret compound Z")
    g.add_node("claim_secret", "claim", _SECRET_LABEL)
    g.add_node("claim_public", "claim", "Water is wet")
    g.add_edge("paper1", "claim_secret", EdgeType.MAKES_CLAIM)
    g.add_edge("paper1", "claim_public", EdgeType.MAKES_CLAIM)
    g.mask_node("claim_secret")
    return g


@pytest.fixture
def impl(graph, mock_embedder):
    return _ToolImplementations(
        graph=graph,
        conflict_detector=MagicMock(),
        weighter=MagicMock(),
        gap_detector=MagicMock(),
        embedder=mock_embedder,
    )


class TestToolLayerRespectsMasking:
    def test_get_node_details_anchors_masked_node(self, impl):
        result = impl.get_node_details("claim_secret")
        assert _SECRET_TAIL not in str(result)
        assert result["is_masked"] is True
        assert "MASKED" in result["message"]

    def test_get_node_details_unaffected_for_unmasked_node(self, impl):
        result = impl.get_node_details("claim_public")
        assert result["label"] == "Water is wet"
        assert "is_masked" not in result  # unmasked path returns the normal inspect_node shape

    def test_find_related_nodes_anchors_masked_neighbor(self, impl):
        results = impl.find_related_nodes("paper1", hops=2)
        secret_hits = [r for r in results if r["node_id"] == "claim_secret"]
        assert secret_hits, "masked neighbor must still appear (structural routing intact)"
        assert all(_SECRET_TAIL not in str(h) for h in secret_hits)
        assert all(h.get("is_masked") for h in secret_hits)

        public_hits = [r for r in results if r["node_id"] == "claim_public"]
        assert public_hits and public_hits[0]["label"] == "Water is wet"

    def test_search_nodes_by_text_anchors_masked_hit(self, impl):
        results = impl.search_nodes_by_text(_SECRET_LABEL, top_k=5)
        assert all(_SECRET_TAIL not in str(r) for r in results)
        secret_hits = [r for r in results if r.get("node_id") == "claim_secret"]
        assert all(r.get("is_masked") for r in secret_hits)

    def test_get_claims_for_source_anchors_masked_claim(self, impl):
        claims = impl.get_claims_for_source("paper1")
        secret = [c for c in claims if c.get("claim_id") == "claim_secret"]
        public = [c for c in claims if c.get("claim_id") == "claim_public"]

        assert secret, "masked claim must still be listed (existence is not hidden)"
        assert all(_SECRET_TAIL not in str(c) for c in secret)
        assert all(c.get("is_masked") for c in secret)

        assert public and public[0]["text"] == "Water is wet"

    def test_unmask_then_tool_call_returns_full_content(self, impl, graph):
        """Confirms reversibility through the tool layer too, mirroring
        test_masked_memory.py's test_unmask_then_retrieve_returns_content."""
        graph.unmask_node("claim_secret")
        result = impl.get_node_details("claim_secret")
        assert result["label"] == _SECRET_LABEL
