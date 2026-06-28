"""
test_masking_enforcement_full.py
=================================
Regression tests for the three masked-memory bypass fixes:

  Pass 1  (from Victor_masking_bypass_fix.zip):
    tools.py — get_node_details, find_related_nodes,
               search_nodes_by_text, get_claims_for_source

  Pass 2  (this session — new patches):
    tools.py — summarize_claim_evidence, check_claims_in_context,
               find_research_gaps
    core.py  — _inject_pattern_note (most severe: auto-fires on every ask_full)

Each test is written against the real VictorKnowledgeGraph (not mocks) so the
enforcement is grounded in actual graph behaviour, not assumed mock returns.

Design principle (from VICTOR_WHAT_IS_BUILT.md "Sovereignty model"):
  "The LLM only sees an anchor placeholder for masked nodes.
   The researcher decides which nodes surface in answers."
  Direct CLI introspection (victor inspect, victor gaps) is outside this
  contract — those are user-initiated actions on their own data, not LLM answers.
"""
import sys, tempfile, hashlib
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import victor
from victor.graph import VictorKnowledgeGraph
from victor.embedder import LocalEmbedder
from victor.reasoning import EvidenceWeighter, GapDetector, PatternDetector, ConflictDetector
from victor.tools import _ToolImplementations
from victor.models import VictorAnswer

# ── Shared fixtures ────────────────────────────────────────────────────────────

_SECRET = "Unpublished: compound X reverses Alzheimer's in 72h — embargoed until publication"
_PUBLIC = "Standard result: compound Y shows mild neuroprotection at high doses"

def _det_embed(text: str) -> list:
    """Deterministic, stable embedder: hash → float vector."""
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    return [((h >> i) & 0xFF) / 255.0 for i in range(0, 384 * 8, 8)][:384]


def make_graph_with_masked_claim(tmp_path: Path):
    """
    Return a (graph, embedder) pair containing:
      - 'paper_pub'       : PAPER node (unmasked)
      - 'claim_secret'    : CLAIM node with _SECRET label  → MASKED
      - 'claim_public'    : CLAIM node with _PUBLIC label  (unmasked)
      - 'exp_public'      : EXPERIMENT confirming claim_public
    paper_pub --MAKES_CLAIM--> claim_secret
    paper_pub --MAKES_CLAIM--> claim_public
    exp_public --CONFIRMS--> claim_public
    """
    emb = LocalEmbedder()
    emb.embed    = _det_embed
    emb.cosine   = LocalEmbedder.cosine

    g = VictorKnowledgeGraph(graph_file=tmp_path / "g.json", embedder=emb)

    g.add_node("paper_pub",    "paper",      "Published paper on neuroprotection",  {})
    g.add_node("claim_secret", "claim",      _SECRET,  {"epistemic_status": "literature"})
    g.add_node("claim_public", "claim",      _PUBLIC,  {"epistemic_status": "literature"})
    g.add_node("exp_public",   "experiment", "Experiment A",
               {"epistemic_status": "experiment"})
    g.add_node("src_other",    "paper",      "Unrelated paper", {})

    from victor.models import EdgeType
    g.add_edge("paper_pub",  "claim_secret", EdgeType.MAKES_CLAIM)
    g.add_edge("paper_pub",  "claim_public", EdgeType.MAKES_CLAIM)
    g.add_edge("exp_public", "claim_public", EdgeType.CONFIRMS)

    g.mask_node("claim_secret")
    return g, emb


def make_impl(g, emb):
    """Construct a _ToolImplementations for the given graph."""
    weighter     = EvidenceWeighter(g)
    gap_detector = GapDetector(g, weighter)
    conflict_det = ConflictDetector(llm=None)
    return _ToolImplementations(
        graph=g,
        conflict_detector=conflict_det,
        weighter=weighter,
        gap_detector=gap_detector,
        embedder=emb,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Pass-1 regression: graph-traversal tools (get_node_details etc.)
# ═══════════════════════════════════════════════════════════════════════════════

def test_get_node_details_anchors_masked_claim():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        result = impl.get_node_details("claim_secret")

        assert result is not None
        assert result.get("is_masked") is True,    "should flag as masked"
        assert _SECRET not in str(result),         "secret label must not appear"
        assert "message" in result,                "anchor must include message field"
        print("PASS: test_get_node_details_anchors_masked_claim")


def test_get_node_details_passes_unmasked_claim():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        result = impl.get_node_details("claim_public")

        assert result is not None
        assert not result.get("is_masked", False), "unmasked node must not be anchored"
        print("PASS: test_get_node_details_passes_unmasked_claim")


def test_find_related_nodes_anchors_masked_neighbours():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        results = impl.find_related_nodes("paper_pub", hops=2)

        node_ids = [r.get("node_id") for r in results]
        assert "claim_secret" in node_ids, "masked neighbour must appear as anchor"

        secret_entry = next(r for r in results if r.get("node_id") == "claim_secret")
        assert secret_entry.get("is_masked") is True
        assert _SECRET not in str(secret_entry)
        print("PASS: test_find_related_nodes_anchors_masked_neighbours")


def test_search_nodes_by_text_anchors_masked_hit():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        results = impl.search_nodes_by_text("Alzheimer compound reversal")

        for r in results:
            if r.get("node_id") == "claim_secret":
                assert r.get("is_masked") is True
                assert _SECRET not in str(r)
                print("PASS: test_search_nodes_by_text_anchors_masked_hit")
                return
        # If claim_secret doesn't appear in results at all, that's also safe
        print("PASS: test_search_nodes_by_text_anchors_masked_hit (not in results)")


def test_get_claims_for_source_anchors_masked_claim():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        results = impl.get_claims_for_source("paper_pub")

        claim_ids = [r.get("claim_id") for r in results]
        assert "claim_secret" in claim_ids, "masked claim must appear with anchor"

        secret_entry = next(r for r in results if r.get("claim_id") == "claim_secret")
        assert secret_entry.get("is_masked") is True
        assert _SECRET not in str(secret_entry)
        print("PASS: test_get_claims_for_source_anchors_masked_claim")


# ═══════════════════════════════════════════════════════════════════════════════
# Pass-2: summarize_claim_evidence
# ═══════════════════════════════════════════════════════════════════════════════

def test_summarize_claim_evidence_anchors_masked_claim():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        result = impl.summarize_claim_evidence("claim_secret")

        assert result is not None
        assert result.get("is_masked") is True,       "masked claim must return anchor"
        assert result.get("claim_id") == "claim_secret", "claim_id alias must be set"
        assert "claim_text" not in result,             "real claim_text must be withheld"
        assert _SECRET not in str(result),             "secret text must not appear"
        assert "message" in result,                    "anchor message must be present"
        print("PASS: test_summarize_claim_evidence_anchors_masked_claim")


def test_summarize_claim_evidence_unmasked_returns_full():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        result = impl.summarize_claim_evidence("claim_public")

        assert result is not None
        assert not result.get("is_masked", False),     "unmasked claim must not anchor"
        assert "claim_text" in result,                 "claim_text must be present"
        assert result["claim_text"] == _PUBLIC
        assert "n_confirms" in result,                 "evidence counts must be present"
        assert result["n_confirms"] == 1,              "exp_public confirms claim_public"
        print("PASS: test_summarize_claim_evidence_unmasked_returns_full")


# ═══════════════════════════════════════════════════════════════════════════════
# Pass-2: check_claims_in_context (batch wrapper)
# ═══════════════════════════════════════════════════════════════════════════════

def test_check_claims_in_context_anchors_masked_claim():
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        results = impl.check_claims_in_context(["claim_secret", "claim_public"])

        by_id = {r.get("claim_id"): r for r in results if r.get("claim_id")}
        assert "claim_secret" in by_id,                "masked claim must appear in batch"
        assert by_id["claim_secret"].get("is_masked") is True
        assert _SECRET not in str(by_id["claim_secret"])
        assert "claim_public"  in by_id,               "unmasked claim must also appear"
        assert "claim_text" in by_id["claim_public"],  "unmasked claim must have claim_text"
        print("PASS: test_check_claims_in_context_anchors_masked_claim")


# ═══════════════════════════════════════════════════════════════════════════════
# Pass-2: find_research_gaps
# ═══════════════════════════════════════════════════════════════════════════════

def test_find_research_gaps_anchors_masked_gap():
    """
    claim_secret is both masked AND a gap (n_confirms == 0).
    find_research_gaps must return an anchor, not the secret claim_text.
    """
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        results = impl.find_research_gaps()

        # claim_public has 1 confirm so is NOT a gap
        # claim_secret has 0 confirms → IS a gap
        ids_in_gaps = [r.get("claim_id") for r in results]
        assert "claim_secret" in ids_in_gaps,          "masked gap must appear in results"
        assert "claim_public" not in ids_in_gaps,      "confirmed claim must not be a gap"

        secret_entry = next(r for r in results if r.get("claim_id") == "claim_secret")
        assert secret_entry.get("is_masked") is True
        assert "claim_text" not in secret_entry,       "real claim_text must be withheld"
        assert _SECRET not in str(secret_entry)
        print("PASS: test_find_research_gaps_anchors_masked_gap")


def test_find_research_gaps_unmasked_gap_passes_through():
    """
    A gap whose claim is unmasked must still return the full claim_text.
    """
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        impl = make_impl(g, emb)

        # Add a new, unmasked, unconfirmed claim
        g.add_node("claim_open", "claim", "Open question: mechanism X unknown", {})
        from victor.models import EdgeType
        g.add_edge("src_other", "claim_open", EdgeType.MAKES_CLAIM)

        # Re-create impl so gap_detector sees the new node
        impl2 = make_impl(g, emb)
        results = impl2.find_research_gaps()

        open_entries = [r for r in results if r.get("claim_id") == "claim_open"]
        assert open_entries, "unmasked open gap must appear"
        entry = open_entries[0]
        assert not entry.get("is_masked", False),      "unmasked gap must not be anchored"
        assert "claim_text" in entry,                  "claim_text must be present"
        print("PASS: test_find_research_gaps_unmasked_gap_passes_through")


# ═══════════════════════════════════════════════════════════════════════════════
# Pass-2 (most severe): _inject_pattern_note in core.py
# ═══════════════════════════════════════════════════════════════════════════════

def _make_fake_victor(g, emb):
    """
    Build a minimal Victor-like object that has the patched _inject_pattern_note
    bound to real reasoning components, without needing a full LLM or vector store.
    """
    import victor.core as core_mod

    weighter     = EvidenceWeighter(g)
    gap_detector = GapDetector(g, weighter)
    pd           = PatternDetector(g, gap_detector)

    class FakeVictor:
        graph           = g
        embedder        = emb
        pattern_detector = pd

        def _inject_pattern_note(self_, query, answer):
            return core_mod.Victor._inject_pattern_note(self_, query, answer)

    return FakeVictor()


def test_inject_pattern_note_skips_masked_gap():
    """
    When the only high-similarity gap is masked, _inject_pattern_note must
    leave the answer unchanged (the most severe of the three leaks: it fires
    automatically on every ask_full without any explicit tool call).
    """
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        fv = _make_fake_victor(g, emb)

        answer = VictorAnswer(answer="original answer text", retrieved_chunks=[], provenance_summary="")
        # Query is semantically close to the secret claim
        fv._inject_pattern_note(_SECRET, answer)

        assert answer.answer == "original answer text", (
            "_inject_pattern_note must not modify answer when only match is masked"
        )
        assert _SECRET not in answer.answer, "secret must not appear in answer"
        print("PASS: test_inject_pattern_note_skips_masked_gap")


def test_inject_pattern_note_still_fires_for_unmasked_gap():
    """
    An unmasked gap that semantically matches the query MUST still fire
    the pattern note — the masking gate must not suppress legitimate insights.
    """
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))

        # Add an unmasked, unconfirmed claim whose text is the query itself
        open_text = "Open unconfirmed: mechanism Q is completely unknown territory"
        g.add_node("claim_open2", "claim", open_text, {"epistemic_status": "literature"})
        from victor.models import EdgeType
        g.add_edge("src_other", "claim_open2", EdgeType.MAKES_CLAIM)

        fv = _make_fake_victor(g, emb)
        answer = VictorAnswer(answer="original", retrieved_chunks=[], provenance_summary="")
        # Query identical to the unmasked claim → similarity should be ~1.0 > 0.65
        fv._inject_pattern_note(open_text, answer)

        assert answer.answer != "original", (
            "pattern note must fire for unmasked gap with high similarity"
        )
        assert open_text[:30] in answer.answer or "Pattern insight" in answer.answer, (
            "pattern note must include the unmasked claim text"
        )
        assert _SECRET not in answer.answer, (
            "secret masked claim must never appear even when unmasked gap fires"
        )
        print("PASS: test_inject_pattern_note_still_fires_for_unmasked_gap")


def test_inject_pattern_note_never_leaks_secret_regardless_of_similarity():
    """
    Paranoia check: even if somehow both claims match the query, the masked
    one must NEVER surface.  Unmask it mid-check only to verify the unmasked
    path works, then re-mask and confirm the answer is clean.
    """
    with tempfile.TemporaryDirectory() as td:
        g, emb = make_graph_with_masked_claim(Path(td))
        fv = _make_fake_victor(g, emb)

        # First confirm: masked → no leak
        answer = VictorAnswer(answer="base", retrieved_chunks=[], provenance_summary="")
        fv._inject_pattern_note(_SECRET, answer)
        assert _SECRET not in answer.answer
        assert answer.answer == "base"

        # Unmask → now it SHOULD fire (verify the gate isn't sticky)
        g.unmask_node("claim_secret")
        answer2 = VictorAnswer(answer="base", retrieved_chunks=[], provenance_summary="")
        fv._inject_pattern_note(_SECRET, answer2)
        assert answer2.answer != "base", "after unmask, pattern note should fire"

        # Re-mask → back to silent
        g.mask_node("claim_secret")
        answer3 = VictorAnswer(answer="base", retrieved_chunks=[], provenance_summary="")
        fv._inject_pattern_note(_SECRET, answer3)
        assert answer3.answer == "base", "re-masking must restore silence"
        assert _SECRET not in answer3.answer

        print("PASS: test_inject_pattern_note_never_leaks_secret_regardless_of_similarity")


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════

TESTS = [
    # Pass-1: graph traversal tools
    test_get_node_details_anchors_masked_claim,
    test_get_node_details_passes_unmasked_claim,
    test_find_related_nodes_anchors_masked_neighbours,
    test_search_nodes_by_text_anchors_masked_hit,
    test_get_claims_for_source_anchors_masked_claim,
    # Pass-2: claim-evidence and gap tools
    test_summarize_claim_evidence_anchors_masked_claim,
    test_summarize_claim_evidence_unmasked_returns_full,
    test_check_claims_in_context_anchors_masked_claim,
    test_find_research_gaps_anchors_masked_gap,
    test_find_research_gaps_unmasked_gap_passes_through,
    # Pass-2: _inject_pattern_note
    test_inject_pattern_note_skips_masked_gap,
    test_inject_pattern_note_still_fires_for_unmasked_gap,
    test_inject_pattern_note_never_leaks_secret_regardless_of_similarity,
]

if __name__ == "__main__":
    passed = 0
    failed = 0
    errors = []
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as exc:
            failed += 1
            errors.append((t.__name__, exc))
            print(f"FAIL: {t.__name__}: {exc}")

    print(f"\n{'='*60}")
    print(f"Results: {passed}/{len(TESTS)} passed", end="")
    if failed:
        print(f", {failed} FAILED")
    else:
        print(" ✓")
    print('='*60)
    if errors:
        raise SystemExit(1)
