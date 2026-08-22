"""
test_core_loop_regressions.py

Regression tests for four defects in the core loop that the 212-test suite
passed straight over. Each test here fails on the pre-fix code.

  1. retrieve.py  — masked anchor chunks carried epistemic_status=None, and both
                    answer_full() and _build_context() call .upper() on it.
                    Any `victor ask` whose retrieval touched a masked node raised
                    AttributeError. The masking tests all called retrieve()
                    directly and never went through answer assembly, so the
                    flagship feature crashed the primary command undetected.

  2. reasoning.py — GapDetector._importance() read importance_score from the top
                    level of the node dict; graph.add_node() writes it into
                    node["metadata"]. Every gap scored 0.0, so the sort was a
                    no-op and `--min-importance` discarded everything.

  3. reasoning.py — PatternDetector read a `retrieval_count` key that nothing in
                    the codebase ever wrote, so top_queried_sources was
                    permanently empty; and its dict items were unpacked as
                    2-tuples by core.py and cli.py, which would have raised
                    ValueError the moment the list became non-empty. The
                    existing mock in test_agent_loop.py used the tuple shape,
                    which is what kept both halves hidden.

  4. llm.py       — _ollama() sent no `options`, so every call silently inherited
                    the Ollama daemon's default temperature of 0.8 for what are
                    three-way classification judgments, with no way to set it.

No network, no Ollama, no model downloads.
"""
import json
import urllib.request
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from victor.models import NodeType, RetrievedChunk


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_embedder():
    """Deterministic embedder — unique vector per string, no HuggingFace load."""
    emb = MagicMock()
    _cache = {}

    def _embed(text):
        if text not in _cache:
            import hashlib
            h = int(hashlib.md5(text.encode()).hexdigest(), 16)
            v = [((h >> i) & 0xFF) / 255.0 for i in range(0, 384 * 8, 8)]
            _cache[text] = v[:384]
        return _cache[text]

    emb.embed.side_effect = _embed
    emb.cosine = staticmethod(lambda a, b: sum(x * y for x, y in zip(a, b)))
    return emb


@pytest.fixture
def graph(tmp_path, mock_embedder):
    from victor.graph import VictorKnowledgeGraph
    return VictorKnowledgeGraph(graph_file=tmp_path / "graph.json", embedder=mock_embedder)


@pytest.fixture
def mock_vector_store(mock_embedder):
    vs = MagicMock()
    vs.embedder = mock_embedder
    vs.query.return_value = []
    vs.get_by_source.return_value = []
    return vs


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.model = "mock-model"
    llm.generate.return_value = SimpleNamespace(
        text="A synthesized answer.", provider="mock", model="mock-model",
    )
    return llm


# ── 1. Masked node no longer crashes answer assembly ──────────────────────────

SECRET = "SECRET_PAYLOAD_the_catalyst_is_palladium_on_carbon"


class TestMaskedNodeAnswerAssembly:

    def _retriever_with_masked_hit(self, graph, mock_vector_store, mock_llm):
        from victor.retrieve import HybridRetriever

        graph.add_node("secret1", NodeType.PAPER, "Confidential synthesis route")
        graph.mask_node("secret1")

        mock_vector_store.query.return_value = [
            RetrievedChunk(
                text=SECRET,
                source_id="secret1",
                source_type=NodeType.PAPER,
                source_title="Confidential synthesis route",
                chunk_index=0,
                score=0.93,
            )
        ]
        return HybridRetriever(mock_vector_store, graph, mock_llm)

    def test_answer_full_does_not_raise_on_masked_node(
        self, graph, mock_vector_store, mock_llm
    ):
        """Pre-fix: AttributeError: 'NoneType' object has no attribute 'upper'."""
        retriever = self._retriever_with_masked_hit(graph, mock_vector_store, mock_llm)

        answer = retriever.answer_full("what is the synthesis route?")

        assert answer.no_context is False
        assert answer.answer == "A synthesized answer."

    def test_masked_anchor_carries_a_renderable_status(
        self, graph, mock_vector_store, mock_llm
    ):
        retriever = self._retriever_with_masked_hit(graph, mock_vector_store, mock_llm)

        chunks = retriever.retrieve("what is the synthesis route?")

        assert len(chunks) == 1
        anchor = chunks[0]
        assert anchor.epistemic_status == "masked"
        # The badge is what actually crashed — prove it renders.
        assert anchor.epistemic_status.upper() == "MASKED"

    def test_masked_content_still_withheld_from_the_prompt(
        self, graph, mock_vector_store, mock_llm
    ):
        """Unbreaking the crash must not have unbroken the masking."""
        retriever = self._retriever_with_masked_hit(graph, mock_vector_store, mock_llm)

        retriever.answer_full("what is the synthesis route?")

        prompt = mock_llm.generate.call_args[0][0]
        assert SECRET not in prompt
        assert "content withheld" in prompt
        assert "[MASKED]" in prompt

    def test_agentic_build_context_renders_masked_anchor(self, graph, mock_vector_store, mock_llm):
        """
        The second .upper() call site — AgenticRetriever._build_context.
        The anchor is built by _make_anchor rather than hand-rolled, so this
        exercises the real defect rather than a stand-in for it.
        """
        from victor.retrieve import AgenticRetriever

        graph.add_node("secret1", NodeType.PAPER, "Confidential synthesis route")
        graph.mask_node("secret1")

        retriever = AgenticRetriever(mock_vector_store, graph, mock_llm, tool_registry=None)
        anchor = retriever._make_anchor("secret1", graph.get_node("secret1"), 0.9)

        context = retriever._build_context([anchor], review_notes="")

        assert "[MASKED]" in context
        assert "content withheld" in context

    def test_ep_badge_tolerates_a_missing_status(self):
        """Defence in depth: a badge is cosmetic and must never break assembly."""
        from victor.retrieve import _ep_badge

        chunk = RetrievedChunk(
            text="x", source_id="n1", source_type=NodeType.NOTE,
            source_title="t", chunk_index=0, score=0.1,
        )
        chunk.epistemic_status = None

        assert _ep_badge(chunk) == "[UNKNOWN]"


# ── 2. Gap ranking reads importance from the right nesting level ──────────────

class TestGapImportance:

    def _two_claims(self, graph):
        # Insert the LOW-importance claim first, deliberately. Python's sort is
        # stable, so a no-op key function leaves insertion order untouched — if
        # this were the other way round the pre-fix code would "pass" by luck.
        graph.add_node("c_low", NodeType.CLAIM, "Weakly weighted unconfirmed claim")
        graph.add_node("c_high", NodeType.CLAIM, "Strongly weighted unconfirmed claim")
        graph.get_node("c_low")["metadata"]["importance_score"] = 0.20
        graph.get_node("c_high")["metadata"]["importance_score"] = 0.90

        from victor.reasoning import EvidenceWeighter, GapDetector
        return GapDetector(graph, EvidenceWeighter(graph))

    def test_gaps_are_sorted_by_importance_descending(self, graph):
        """Pre-fix: every gap scored 0.0, so the sort was a no-op."""
        detector = self._two_claims(graph)

        gaps = detector.find_gaps()

        assert [g.claim_id for g in gaps] == ["c_high", "c_low"]

    def test_min_importance_filters_instead_of_emptying(self, graph):
        """Pre-fix: _importance() returned 0.0 for all, so this returned []."""
        detector = self._two_claims(graph)

        gaps = detector.find_gaps(min_importance=0.5)

        assert [g.claim_id for g in gaps] == ["c_high"]

    def test_min_importance_above_everything_returns_nothing(self, graph):
        detector = self._two_claims(graph)

        assert detector.find_gaps(min_importance=0.99) == []


# ── 3. top_queried_sources is populated, and its consumers agree on the shape ──

class TestTopQueriedSources:

    def test_record_retrieval_tallies_a_count(self, graph):
        """Nothing wrote retrieval_count before; PatternDetector only read it."""
        graph.add_node("p1", NodeType.PAPER, "Paper One")

        for _ in range(4):
            graph.record_retrieval("p1")

        assert graph.get_node("p1")["metadata"]["retrieval_count"] == 4

    def test_retrieval_count_is_independent_of_the_importance_cap(self, graph):
        """importance_score saturates at 1.0; the tally must keep counting."""
        graph.add_node("p1", NodeType.PAPER, "Paper One")

        for _ in range(30):
            graph.record_retrieval("p1")

        meta = graph.get_node("p1")["metadata"]
        assert meta["importance_score"] == 1.0
        assert meta["retrieval_count"] == 30

    def _analyze(self, graph):
        from victor.reasoning import EvidenceWeighter, GapDetector, PatternDetector
        weighter = EvidenceWeighter(graph)
        return PatternDetector(graph, GapDetector(graph, weighter)).analyze()

    def test_analyze_reports_queried_papers(self, graph):
        """Pre-fix: permanently []."""
        graph.add_node("p1", NodeType.PAPER, "Paper One")
        graph.add_node("p2", NodeType.PAPER, "Paper Two")
        for _ in range(5):
            graph.record_retrieval("p1")
        graph.record_retrieval("p2")

        top = self._analyze(graph)["top_queried_sources"]

        assert top == [
            {"source_id": "p1", "count": 5, "label": "Paper One"},
            {"source_id": "p2", "count": 1, "label": "Paper Two"},
        ]

    def test_never_retrieved_papers_are_omitted(self, graph):
        graph.add_node("p1", NodeType.PAPER, "Never Read")

        assert self._analyze(graph)["top_queried_sources"] == []

    def test_pattern_digest_consumes_the_dict_shape(self, graph):
        """
        core.get_pattern_digest() unpacked these items as 2-tuples. That only
        went unnoticed while the list was empty; populating it would have raised
        ValueError. get_pattern_digest touches nothing but self.pattern_detector,
        so the real method can be exercised against a stub.
        """
        from victor.core import Victor

        graph.add_node("p1", NodeType.PAPER, "Heavily Queried Paper")
        for _ in range(4):
            graph.record_retrieval("p1")

        from victor.reasoning import EvidenceWeighter, GapDetector, PatternDetector
        detector = PatternDetector(graph, GapDetector(graph, EvidenceWeighter(graph)))
        stub = SimpleNamespace(pattern_detector=detector)

        digest = Victor.get_pattern_digest(stub)

        assert digest["recurring_weak_topics"] == [{
            "topic": "Heavily Queried Paper",
            "query_count": 4,
            "note": "Frequently queried — check if evidence is strong enough",
        }]

    def test_digest_ignores_sources_below_the_weak_topic_threshold(self, graph):
        from victor.core import Victor
        from victor.reasoning import EvidenceWeighter, GapDetector, PatternDetector

        graph.add_node("p1", NodeType.PAPER, "Barely Queried Paper")
        graph.record_retrieval("p1")

        detector = PatternDetector(graph, GapDetector(graph, EvidenceWeighter(graph)))
        digest = Victor.get_pattern_digest(SimpleNamespace(pattern_detector=detector))

        assert digest["recurring_weak_topics"] == []
        assert digest["top_sources"][0]["count"] == 1


# ── 4. Sampling temperature is Victor's decision, not the daemon's ────────────

class TestOllamaTemperature:

    @pytest.fixture
    def captured_body(self, monkeypatch):
        captured = {}

        class _FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return b'{"response": "ok"}'

        def _fake_urlopen(req, timeout=None):
            captured["body"] = json.loads(req.data.decode())
            return _FakeResponse()

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
        return captured

    def test_default_temperature_is_sent(self, captured_body):
        """Pre-fix: no `options` key at all, so Ollama applied its own 0.8."""
        from victor.llm import OllamaClient

        OllamaClient(model="m", temperature=0.1)._ollama("hello")

        assert captured_body["body"]["options"]["temperature"] == 0.1

    def test_per_call_override_wins(self, captured_body):
        """What self-consistency voting needs: differing samples per call."""
        from victor.llm import OllamaClient

        OllamaClient(model="m", temperature=0.1)._ollama("hello", temperature=0.9)

        assert captured_body["body"]["options"]["temperature"] == 0.9

    def test_temperature_coexists_with_the_grammar_schema(self, captured_body):
        from victor.llm import OllamaClient

        schema = {"type": "object", "properties": {"direction": {"type": "string"}}}
        OllamaClient(model="m", temperature=0.2)._ollama("hello", response_schema=schema)

        body = captured_body["body"]
        assert body["options"]["temperature"] == 0.2
        assert body["format"] == schema

    def test_config_temperature_reaches_the_client(self):
        from victor.config import VictorConfig
        from victor.llm import create_inference_client

        client = create_inference_client(VictorConfig(llm_temperature=0.42))

        assert client.temperature == 0.42

    def test_default_config_is_near_greedy_not_the_daemon_default(self):
        """A three-way classification judgment should not run at 0.8."""
        from victor.config import VictorConfig

        assert VictorConfig().llm_temperature == 0.1
