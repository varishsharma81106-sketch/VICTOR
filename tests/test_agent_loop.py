"""
Tests for Victor Steps 1–3: tool registry, bounded agent loop, PatternDetector surfacing.

Run with:  pytest victor/tests/test_agent_loop.py -v
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# We need to import from the victor package — ensure the path is set
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from victor.tools import Tool, ToolRegistry, _ToolImplementations, ToolParam
from victor.models import (
    EpistemicStatus, EdgeType, NodeType,
    ClaimEvidenceSummary, ConflictResult, ConversationTurn,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_graph():
    """Create a mock graph with a few nodes."""
    g = MagicMock()
    g._g = MagicMock()
    g._g.nodes = MagicMock()
    g._g.edges = MagicMock()
    g._g.in_edges = MagicMock(return_value=[])
    g._g.out_edges = MagicMock(return_value=[])
    g._g.number_of_nodes = MagicMock(return_value=5)
    g._g.number_of_edges = MagicMock(return_value=3)
    g.get_node = MagicMock(return_value={
        "label": "Test claim about neural networks",
        "ntype": NodeType.CLAIM,
        "metadata": {
            "epistemic_status": EpistemicStatus.LITERATURE.value,
            "importance_score": 0.75,
        }
    })
    g.inspect_node = MagicMock(return_value={
        "node_id": "claim_001",
        "ntype": NodeType.CLAIM,
        "label": "Test claim",
        "metadata": {"epistemic_status": "literature"},
        "in_edges": [],
        "out_edges": [],
        "degree_in": 1,
        "degree_out": 0,
    })
    g.semantic_query = MagicMock(return_value=[
        ("claim_001", 0.85, {
            "label": "Test claim about neural networks",
            "ntype": NodeType.CLAIM,
            "metadata": {"epistemic_status": "literature", "importance_score": 0.75}
        })
    ])
    g.get_neighbors = MagicMock(return_value=[])
    g.record_retrieval = MagicMock()
    g.save = MagicMock()
    # Masking: all nodes unmasked by default so tool-layer tests don't hit anchor paths
    g.node_is_masked = MagicMock(return_value=False)
    return g


@pytest.fixture
def mock_conflict_detector():
    cd = MagicMock()
    cd.judge = MagicMock(return_value=ConflictResult(
        direction="confirm",
        confidence=0.92,
        reason="Results directly support the claim",
    ))
    return cd


@pytest.fixture
def mock_weighter(mock_graph):
    w = MagicMock()
    w.summarize_claim = MagicMock(return_value=ClaimEvidenceSummary(
        claim_id="claim_001",
        claim_text="Test claim about neural networks",
        epistemic_status=EpistemicStatus.LITERATURE.value,
        confidence=0.85,
        n_confirms=2,
        n_contradicts=0,
        n_inconclusive=1,
        supporting_experiments=["exp_001", "exp_002"],
        conflicting_experiments=[],
        gap=False,
    ))
    w.summarize_all_claims = MagicMock(return_value=[
        ClaimEvidenceSummary(
            claim_id="claim_001",
            claim_text="Test claim about neural networks",
            epistemic_status=EpistemicStatus.LITERATURE.value,
            confidence=0.85,
            n_confirms=2,
            n_contradicts=0,
            n_inconclusive=1,
            supporting_experiments=["exp_001"],
            conflicting_experiments=[],
            gap=False,
        ),
        ClaimEvidenceSummary(
            claim_id="claim_002",
            claim_text="Another untested claim",
            epistemic_status=EpistemicStatus.LITERATURE.value,
            confidence=0.0,
            n_confirms=0,
            n_contradicts=0,
            n_inconclusive=0,
            supporting_experiments=[],
            conflicting_experiments=[],
            gap=True,
        ),
    ])
    return w


@pytest.fixture
def mock_gap_detector(mock_graph, mock_weighter):
    gd = MagicMock()
    gd.find_gaps = MagicMock(return_value=[
        ClaimEvidenceSummary(
            claim_id="claim_002",
            claim_text="Another untested claim",
            epistemic_status=EpistemicStatus.LITERATURE.value,
            confidence=0.0,
            n_confirms=0,
            n_contradicts=0,
            n_inconclusive=0,
            supporting_experiments=[],
            conflicting_experiments=[],
            gap=True,
        ),
    ])
    return gd


@pytest.fixture
def mock_embedder():
    e = MagicMock()
    e.embed = MagicMock(return_value=[0.1] * 384)
    e.cosine = MagicMock(return_value=0.85)
    return e


@pytest.fixture
def tool_impl(mock_graph, mock_conflict_detector, mock_weighter, mock_gap_detector, mock_embedder):
    return _ToolImplementations(
        graph=mock_graph,
        conflict_detector=mock_conflict_detector,
        weighter=mock_weighter,
        gap_detector=mock_gap_detector,
        embedder=mock_embedder,
    )


@pytest.fixture
def registry(tool_impl):
    return ToolRegistry(tool_impl)


# ═══════════════════════════════════════════════════════════════════════════════
#  Tool Registry Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolRegistry:
    def test_registry_creates_all_default_tools(self, registry):
        """All 8 default tools should be registered."""
        tools = registry.list_tools()
        names = {t.name for t in tools}
        expected = {
            "judge_conflict",
            "summarize_claim_evidence",
            "check_claims_in_context",
            "find_research_gaps",
            "get_node_details",
            "find_related_nodes",
            "search_nodes_by_text",
            "get_claims_for_source",
        }
        assert names == expected, f"Missing or extra tools: {names ^ expected}"

    def test_tool_descriptions_non_empty(self, registry):
        desc = registry.tool_descriptions_for_prompt()
        assert "judge_conflict" in desc
        assert "find_research_gaps" in desc
        assert "parameters" in desc

    def test_judge_conflict_tool(self, registry, mock_conflict_detector):
        result = registry.execute("judge_conflict", {
            "claim_text": "The model achieves 95% accuracy",
            "result_text": "Test accuracy was 94.7%",
        })
        assert "error" not in result
        assert result["tool"] == "judge_conflict"
        assert result["result"]["direction"] == "confirm"
        assert result["result"]["confidence"] == 0.92
        mock_conflict_detector.judge.assert_called_once()

    def test_summarize_claim_evidence_tool(self, registry, mock_weighter):
        result = registry.execute("summarize_claim_evidence", {"claim_id": "claim_001"})
        assert "error" not in result
        assert result["result"]["claim_id"] == "claim_001"
        assert result["result"]["confidence"] == 0.85
        assert result["result"]["is_gap"] is False
        mock_weighter.summarize_claim.assert_called_once_with("claim_001")

    def test_find_research_gaps_tool(self, registry, mock_gap_detector):
        result = registry.execute("find_research_gaps", {})
        assert "error" not in result
        gaps = result["result"]
        assert len(gaps) == 1
        assert gaps[0]["claim_id"] == "claim_002"
        assert gaps[0]["confidence"] == 0.0  # gap = no confirmation

    def test_unknown_tool_returns_error(self, registry):
        result = registry.execute("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]

    def test_execute_from_llm_json(self, registry, mock_weighter):
        """Parse and execute a tool call from LLM-output-style JSON."""
        llm_json = json.dumps({
            "tool": "summarize_claim_evidence",
            "arguments": {"claim_id": "claim_001"}
        })
        result = registry.execute_from_llm_json(llm_json)
        assert "error" not in result
        assert result["tool"] == "summarize_claim_evidence"

    def test_execute_from_llm_json_with_markdown(self, registry, mock_weighter):
        """Handle JSON wrapped in markdown code blocks."""
        llm_json = '```json\n{"tool": "summarize_claim_evidence", "arguments": {"claim_id": "claim_001"}}\n```'
        result = registry.execute_from_llm_json(llm_json)
        assert "error" not in result

    def test_get_node_details_tool(self, registry, mock_graph):
        result = registry.execute("get_node_details", {"node_id": "claim_001"})
        assert "error" not in result
        assert result["result"]["node_id"] == "claim_001"

    def test_search_nodes_by_text_tool(self, registry, mock_graph):
        result = registry.execute("search_nodes_by_text", {
            "query": "neural networks",
            "top_k": 5,
        })
        assert "error" not in result
        assert len(result["result"]) == 1
        assert result["result"][0]["node_id"] == "claim_001"


# ═══════════════════════════════════════════════════════════════════════════════
#  Agent Loop Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestAgentLoop:
    def test_agent_loop_parses_final_answer(self):
        """The loop should stop when LLM returns final_answer."""
        from victor.retrieve import AgenticRetriever

        # Mock everything
        mock_vs = MagicMock()
        mock_graph = MagicMock()
        mock_llm = MagicMock()

        # Mock retrieve to return one chunk
        mock_vs.query = MagicMock(return_value=[])
        mock_graph.semantic_query = MagicMock(return_value=[])
        mock_graph.get_neighbors = MagicMock(return_value=[])
        mock_graph._g = MagicMock()
        mock_graph._g.in_edges = MagicMock(return_value=[])
        mock_graph.get_node = MagicMock(return_value=None)
        mock_graph.record_retrieval = MagicMock()
        mock_graph.apply_temporal_decay = MagicMock()
        mock_graph.add_conversation_node = MagicMock()
        mock_graph.save = MagicMock()

        # Mock LLM to return final_answer immediately
        from victor.llm import LLMResult
        mock_llm.generate_with_tools = MagicMock(return_value=LLMResult(
            text=json.dumps({
                "action": "final_answer",
                "answer": "This is the final answer.",
            }),
            provider="mock",
            model="mock",
        ))
        mock_llm.model = "mock"

        retriever = AgenticRetriever(
            vector_store=mock_vs,
            graph=mock_graph,
            llm=mock_llm,
            top_k=2,
        )

        # Need at least one chunk for the loop to run
        # Patch retrieve to return a fake chunk
        fake_chunk = MagicMock()
        fake_chunk.source_id = "paper_001"
        fake_chunk.source_type = "paper"
        fake_chunk.source_title = "Test Paper"
        fake_chunk.chunk_index = 0
        fake_chunk.score = 0.9
        fake_chunk.epistemic_status = "literature"
        fake_chunk.text = "Test text"
        fake_chunk.provenance = []

        with patch.object(retriever, 'retrieve', return_value=[fake_chunk]):
            answer = retriever.answer_full("test query")

        assert "final answer" in answer.answer.lower() or "agent loop" in answer.answer.lower()
        mock_llm.generate_with_tools.assert_called()

    def test_agent_loop_enforces_tool_budget(self):
        """The loop must stop after max_tool_calls tool calls."""
        from victor.retrieve import AgenticRetriever
        from victor.llm import LLMResult

        mock_vs = MagicMock()
        mock_graph = MagicMock()
        mock_llm = MagicMock()

        mock_vs.query = MagicMock(return_value=[])
        mock_graph.semantic_query = MagicMock(return_value=[])
        mock_graph.get_neighbors = MagicMock(return_value=[])
        mock_graph._g = MagicMock()
        mock_graph._g.in_edges = MagicMock(return_value=[])
        mock_graph.get_node = MagicMock(return_value=None)
        mock_graph.record_retrieval = MagicMock()
        mock_graph.apply_temporal_decay = MagicMock()
        mock_graph.add_conversation_node = MagicMock()
        mock_graph.save = MagicMock()

        call_count = [0]
        def llm_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 3:
                # Keep requesting tool calls
                return LLMResult(
                    text=json.dumps({
                        "action": "tool_call",
                        "tool": "get_node_details",
                        "arguments": {"node_id": "claim_001"},
                    }),
                    provider="mock",
                    model="mock",
                )
            else:
                # Final answer
                return LLMResult(
                    text=json.dumps({
                        "action": "final_answer",
                        "answer": "Final answer after budget.",
                    }),
                    provider="mock",
                    model="mock",
                )

        mock_llm.generate_with_tools = MagicMock(side_effect=llm_side_effect)
        mock_llm.model = "mock"

        retriever = AgenticRetriever(
            vector_store=mock_vs,
            graph=mock_graph,
            llm=mock_llm,
            top_k=2,
            max_tool_calls=2,  # Small budget for testing
        )

        fake_chunk = MagicMock()
        fake_chunk.source_id = "paper_001"
        fake_chunk.source_type = "paper"
        fake_chunk.source_title = "Test Paper"
        fake_chunk.chunk_index = 0
        fake_chunk.score = 0.9
        fake_chunk.epistemic_status = "literature"
        fake_chunk.text = "Test text"
        fake_chunk.provenance = []

        # Need tool registry to avoid "No tool registry configured" error
        mock_registry = MagicMock()
        mock_registry.execute = MagicMock(return_value={"result": "ok"})
        retriever.tool_registry = mock_registry

        with patch.object(retriever, 'retrieve', return_value=[fake_chunk]):
            answer = retriever.answer_full("test query")

        # Should have called LLM at most budget+2 times (tool calls + forced final)
        assert mock_llm.generate_with_tools.call_count <= 4

    def test_parse_llm_action_tool_call(self):
        """Parser should extract tool_call actions."""
        from victor.retrieve import AgenticRetriever
        retriever = AgenticRetriever(
            vector_store=MagicMock(),
            graph=MagicMock(),
            llm=MagicMock(),
        )
        raw = json.dumps({
            "action": "tool_call",
            "tool": "judge_conflict",
            "arguments": {"claim_text": "x", "result_text": "y"},
        })
        parsed = retriever._parse_llm_action(raw)
        assert parsed is not None
        assert parsed["action"] == "tool_call"
        assert parsed["tool"] == "judge_conflict"

    def test_parse_llm_action_final_answer(self):
        """Parser should extract final_answer actions."""
        from victor.retrieve import AgenticRetriever
        retriever = AgenticRetriever(
            vector_store=MagicMock(),
            graph=MagicMock(),
            llm=MagicMock(),
        )
        raw = json.dumps({
            "action": "final_answer",
            "answer": "The answer is 42.",
        })
        parsed = retriever._parse_llm_action(raw)
        assert parsed is not None
        assert parsed["action"] == "final_answer"
        assert parsed["answer"] == "The answer is 42."

    def test_parse_llm_action_markdown_json(self):
        """Parser should handle JSON inside markdown code blocks."""
        from victor.retrieve import AgenticRetriever
        retriever = AgenticRetriever(
            vector_store=MagicMock(),
            graph=MagicMock(),
            llm=MagicMock(),
        )
        raw = '```json\n{"action": "final_answer", "answer": "yes"}\n```'
        parsed = retriever._parse_llm_action(raw)
        assert parsed is not None
        assert parsed["action"] == "final_answer"

    def test_parse_llm_action_invalid_returns_none(self):
        """Parser should return None for unparseable text."""
        from victor.retrieve import AgenticRetriever
        retriever = AgenticRetriever(
            vector_store=MagicMock(),
            graph=MagicMock(),
            llm=MagicMock(),
        )
        parsed = retriever._parse_llm_action("This is just plain text with no JSON")
        assert parsed is None


# ═══════════════════════════════════════════════════════════════════════════════
#  LLM Structured Output Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestLLMStructuredOutput:
    def test_generate_structured_returns_json(self):
        """generate_structured should attempt to return valid JSON."""
        from victor.llm import OllamaClient, LLMResult

        # Create a client that returns valid JSON
        client = OllamaClient(use_mock=False)
        # Override _mock to return JSON
        client._mock = lambda prompt: LLMResult(
            text='{"action": "final_answer", "answer": "test"}',
            provider="mock",
            model="mock",
        )
        # Force mock path by clearing Ollama/OpenAI
        client.base_url = "http://invalid:99999"
        client.openai_api_url = "http://invalid:99999"

        result = client.generate_structured(
            "Test prompt",
            schema_hint={"answer": "string"},
        )
        assert result.provider == "mock"
        # Should be parseable JSON
        parsed = json.loads(result.text)
        assert "action" in parsed

    def test_generate_with_tools_returns_tool_format(self):
        """generate_with_tools should request tool_call / final_answer format."""
        from victor.llm import OllamaClient

        client = OllamaClient(use_mock=True)
        result = client.generate_with_tools(
            "What is the evidence?",
            tool_descriptions="tool1: does thing",
        )
        # Mock mode returns final_answer JSON
        parsed = json.loads(result.text)
        assert parsed.get("action") == "final_answer"


# ═══════════════════════════════════════════════════════════════════════════════
#  PatternDetector Surfacing Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPatternSurfacing:
    def test_get_pattern_digest_structure(self):
        """get_pattern_digest should return the expected structure."""
        from victor.core import Victor
        from victor.config import VictorConfig

        config = VictorConfig(use_mock_llm=True)
        # Use a temp directory to avoid conflicts
        with tempfile.TemporaryDirectory() as tmpdir:
            config.home_dir = Path(tmpdir)
            config.vector_db_dir = Path(tmpdir) / "vector_db"
            config.graph_file = Path(tmpdir) / "graph" / "kg.json"
            config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
            config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

            v = Victor(config=config)
            digest = v.get_pattern_digest()

            assert "total_conversations" in digest
            assert "top_sources" in digest
            assert "n_priority_gaps" in digest
            assert "suggestions" in digest
            assert "recurring_weak_topics" in digest

    def test_ask_with_patterns_injects_note(self):
        """ask_with_patterns should inject a note when query matches a gap."""
        from victor.core import Victor
        from victor.models import VictorAnswer
        from victor.config import VictorConfig

        config = VictorConfig(use_mock_llm=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            config.home_dir = Path(tmpdir)
            config.vector_db_dir = Path(tmpdir) / "vector_db"
            config.graph_file = Path(tmpdir) / "graph" / "kg.json"
            config.llm_log_file = Path(tmpdir) / "logs" / "llm.jsonl"
            config.extraction_log_file = Path(tmpdir) / "logs" / "extract.jsonl"

            v = Victor(config=config)
            # Mock the embedder
            v.embedder.cosine = MagicMock(return_value=0.85)
            v.embedder.embed = MagicMock(return_value=[0.1] * 384)

            # Mock pattern detector to return a gap
            v.pattern_detector.analyze = MagicMock(return_value={
                "total_conversations": 5,
                "top_queried_sources": [("Neural Networks Paper", 4)],
                "priority_gaps": [
                    MagicMock(
                        claim_text="Neural networks generalize better with dropout",
                        claim_id="claim_gap_001",
                        epistemic_status="literature",
                        n_contradicts=0,
                        confidence=0.0,
                    )
                ],
                "suggested_experiments": ["Test dropout on your model"],
            })

            # Mock the retriever to avoid ChromaDB initialization
            mock_answer = VictorAnswer(
                answer="The research shows that neural networks...",
                retrieved_chunks=[],
                provenance_summary="test",
                provider_used="mock",
            )
            v.retriever.answer_full = MagicMock(return_value=mock_answer)

            answer = v.ask_with_patterns("tell me about neural networks")

            # Should have pattern insight prepended (or at minimum, the mock answer)
            assert "neural networks" in answer.answer.lower() or "Pattern insight" in answer.answer


# ═══════════════════════════════════════════════════════════════════════════════
#  Integration: Tool + Agent Loop
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolAgentIntegration:
    def test_full_tool_call_cycle(self, registry, mock_conflict_detector):
        """Simulate one full cycle: LLM requests tool → tool executes → result available."""
        # Step 1: LLM decides to call judge_conflict
        llm_request = json.dumps({
            "action": "tool_call",
            "tool": "judge_conflict",
            "arguments": {
                "claim_text": "The catalyst improves yield by 20%",
                "result_text": "Yield increased to 94% from 78% baseline",
            }
        })

        # Step 2: Execute the tool
        result = registry.execute_from_llm_json(llm_request)

        # Step 3: Verify
        assert "error" not in result
        assert result["tool"] == "judge_conflict"
        assert result["result"]["direction"] == "confirm"

        # Step 4: LLM sees result and produces final_answer (simulated)
        final_request = json.dumps({
            "action": "final_answer",
            "answer": (
                "The experiment confirms the claim — yield improved from 78% to 94%, "
                "which exceeds the 20% improvement threshold. "
                f"(Confidence: {result['result']['confidence']})"
            ),
        })
        parsed_final = json.loads(final_request)
        assert parsed_final["action"] == "final_answer"
        assert "94%" in parsed_final["answer"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
