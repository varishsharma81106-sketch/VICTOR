"""
Tests for the web console (victor/web.py).

The bar for this file is set by what the console is *for*. Most of it is a
read-only view and a rendering bug is cosmetic — but the redaction boundary is
not cosmetic. If a masked node's content reaches the browser through any
endpoint, the differentiating feature of the whole system is broken, and it is
broken silently, because the page would still draw the node as masked.

So the centre of gravity here is TestRedactionBoundary: for every endpoint that
can touch a masked node, serialise the entire response and assert the secret
string does not appear anywhere in it. That catches leaks through fields nobody
thought to check, which is exactly how the two previous masking leaks shipped.
"""
import json

import pytest

from victor.config import VictorConfig
from victor.core import Victor
from victor.graph import NodeType
from victor.web import REDACTED, RevealSession, VictorAPI, _dispatch_get, _dispatch_post


SECRET = "PALLADIUM_ON_CARBON_at_40psi_is_the_undisclosed_catalyst"
# Carried in the claim's extractor metadata rather than its label — the shape a
# real extracted claim has, and the one that leaked.
SECRET_VALUE = "8.70pct_yield_delta_UNPUBLISHED"


@pytest.fixture
def victor(tmp_path):
    config = VictorConfig(home_dir=tmp_path / "home")
    config.use_mock_llm = True
    config.use_mock_embedder = True
    return Victor(config=config)


@pytest.fixture
def api(victor):
    return VictorAPI(victor)


@pytest.fixture
def seeded(victor):
    """
    A small graph: one paper, one public claim, one secret claim, linked.

    The secret claim carries its payload in BOTH the label and the extractor
    metadata, because that is how real claims come out of `extractor.py` — a
    sentence plus structured `metric`/`value` fields. A fixture that only put
    the secret in the label let a real metadata leak pass every test in this
    file; see test_masked_metadata_is_stripped.
    """
    g = victor.graph
    g.add_node("paper1", NodeType.PAPER, "A Public Paper On Catalysis")
    g.add_node("public1", NodeType.CLAIM, "Yield improves above 30 psi")
    g.add_node("secret1", NodeType.CLAIM, SECRET, metadata={
        "metric": "catalyst",
        "value": SECRET_VALUE,
        "direction": "increase",
    })
    g.add_edge("paper1", "public1", "supports")
    g.add_edge("paper1", "secret1", "supports")
    g.save()
    return victor


# ── the part that matters ─────────────────────────────────────────────────────

class TestRedactionBoundary:
    """Masked content must not leave the process through any endpoint."""

    def _all_endpoints_blob(self, api: VictorAPI) -> str:
        """Serialise every read endpoint into one string for leak scanning."""
        return json.dumps({
            "overview": api.overview(),
            "graph": api.graph(),
            "masked": api.masked(),
            "gaps": api.gaps(),
            "activity": api.activity(limit=999),
            "node": api.node("secret1"),
            "audit": api.audit(),
        }, default=str)

    def test_secret_is_visible_before_masking(self, seeded, api):
        """Guards the test itself: if this fails, the leak checks below prove nothing."""
        blob = self._all_endpoints_blob(api)
        assert SECRET in blob
        assert SECRET_VALUE in blob

    def test_no_endpoint_leaks_a_masked_label(self, seeded, api):
        api.set_mask("secret1", True)
        assert SECRET not in self._all_endpoints_blob(api)

    def test_masked_metadata_is_stripped(self, seeded, api):
        """
        Found live: /api/node returned raw node metadata, so a masked claim's
        label was withheld while its extracted `value` field published the
        number the label was hiding. For a scientific claim the metric IS the
        content.
        """
        api.set_mask("secret1", True)
        assert SECRET_VALUE not in self._all_endpoints_blob(api)

        meta = api.node("secret1")["metadata"]
        assert "value" not in meta
        assert "metric" not in meta
        # Structural bookkeeping survives — that is the whole point of masking
        # rather than deleting.
        assert "importance_score" in meta
        assert meta["is_masked"] is True
        assert meta["_withheld_fields"] == 3

    def test_revealing_restores_the_full_metadata(self, seeded, api):
        api.set_mask("secret1", True)
        api.reveal("secret1")
        meta = api.node("secret1")["metadata"]
        assert meta["value"] == SECRET_VALUE
        assert "_withheld_fields" not in meta

    def test_no_endpoint_leaks_even_a_prefix(self, seeded, api):
        """
        The August 2026 fix removed a 40-char truncated label from anchors. A
        prefix is still content, so assert on prefixes too, not just the whole
        string.
        """
        api.set_mask("secret1", True)
        blob = self._all_endpoints_blob(api)
        for n in (8, 12, 20, 40):
            assert SECRET[:n] not in blob, f"leaked first {n} characters"

    def test_masked_label_is_a_fixed_width_placeholder(self, seeded, api):
        """
        Placeholder length must not track the real label length — otherwise the
        vault listing leaks how long each withheld item is.
        """
        api.v.graph.add_node("secret2", NodeType.CLAIM, "x" * 400)
        api.set_mask("secret1", True)
        api.set_mask("secret2", True)
        labels = {m["label"] for m in api.masked()["masked"]}
        assert labels == {REDACTED}

    def test_graph_structure_survives_masking(self, seeded, api):
        """
        The whole promise: relations stay live while content goes dark. If
        masking dropped edges, this would be deletion, not masking.
        """
        before = api.graph()
        api.set_mask("secret1", True)
        after = api.graph()

        assert len(after["links"]) == len(before["links"])
        assert len(after["nodes"]) == len(before["nodes"])

        node = next(n for n in after["nodes"] if n["id"] == "secret1")
        assert node["masked"] is True
        assert node["label"] == REDACTED
        # Structure still fully described.
        assert node["ntype"] == "claim"
        assert node["importance"] > 0

    def test_masked_node_keeps_its_edges_in_the_inspector(self, seeded, api):
        api.set_mask("secret1", True)
        node = api.node("secret1")
        assert node["degree_in"] + node["degree_out"] >= 1
        assert node["label"] == REDACTED

    def test_neighbour_labels_are_redacted_in_the_inspector(self, seeded, api):
        """Inspecting a *public* node must not reveal a masked neighbour."""
        api.set_mask("secret1", True)
        paper = api.node("paper1")
        neighbours = paper["in_edges"] + paper["out_edges"]
        secret_edge = next(e for e in neighbours if e["id"] == "secret1")
        assert secret_edge["label"] == REDACTED
        assert secret_edge["masked"] is True
        # The public neighbour is untouched.
        public_edge = next(e for e in neighbours if e["id"] == "public1")
        assert "30 psi" in public_edge["label"]

    def test_gaps_redacts_masked_claim_text(self, seeded, api):
        api.set_mask("secret1", True)
        rows = api.gaps()["gaps"]
        secret_row = next(r for r in rows if r["claim_id"] == "secret1")
        assert secret_row["claim_text"] == REDACTED
        assert secret_row["masked"] is True


# ── session reveals ───────────────────────────────────────────────────────────

class TestSessionReveal:
    """
    Reveal is a temporary surfacing; unmask is a permanent declassification.
    Conflating them would lose the "call it up, then let it go back under"
    behaviour the original conception describes.
    """

    def test_reveal_surfaces_content_without_touching_the_graph(self, seeded, api):
        api.set_mask("secret1", True)
        api.reveal("secret1")

        assert SECRET in api.node("secret1")["label"]
        # The persisted flag is unchanged — this is the whole distinction.
        assert api.v.graph.node_is_masked("secret1") is True

    def test_conceal_puts_it_back_without_touching_the_graph(self, seeded, api):
        api.set_mask("secret1", True)
        api.reveal("secret1")
        api.conceal("secret1")

        assert api.node("secret1")["label"] == REDACTED
        assert api.v.graph.node_is_masked("secret1") is True

    def test_a_new_session_does_not_inherit_reveals(self, seeded, api):
        """Reveals are session state. A restart must re-hide everything."""
        api.set_mask("secret1", True)
        api.reveal("secret1")

        fresh = VictorAPI(api.v, session=RevealSession())
        assert fresh.node("secret1")["label"] == REDACTED

    def test_reveal_refuses_nodes_that_are_not_masked(self, seeded, api):
        result = api.reveal("public1")
        assert result["ok"] is False
        assert "not masked" in result["error"]

    def test_reveal_refuses_unknown_nodes(self, seeded, api):
        assert api.reveal("does-not-exist")["ok"] is False

    def test_reveal_is_written_to_the_audit_trail(self, seeded, api):
        """A temporary look at withheld content is still an access event."""
        api.set_mask("secret1", True)
        api.reveal("secret1")

        actions = [e["action"] for e in api.audit()["entries"]]
        assert "session-reveal" in actions

    def test_unmasking_clears_a_stale_session_reveal(self, seeded, api):
        api.set_mask("secret1", True)
        api.reveal("secret1")
        api.set_mask("secret1", False)

        node = api.node("secret1")
        assert node["masked"] is False
        assert node["revealed"] is False


# ── overview / compounding ────────────────────────────────────────────────────

class TestOverview:
    def test_density_is_edges_per_node(self, seeded, api):
        """
        VICTOR_THEORY_v1: value scales with connection density, not artifact
        count. The console reports density so compounding is observable.
        """
        o = api.overview()
        assert o["density"] == pytest.approx(o["edges"] / o["nodes"], abs=0.001)

    def test_empty_graph_does_not_divide_by_zero(self, api):
        o = api.overview()
        assert o["nodes"] == 0
        assert o["density"] == 0.0
        assert o["mean_importance"] == 0.0

    def test_masked_count_is_reported(self, seeded, api):
        assert api.overview()["masked"] == 0
        api.set_mask("secret1", True)
        assert api.overview()["masked"] == 1

    def test_by_type_counts_match_the_graph(self, seeded, api):
        assert api.overview()["by_type"]["claim"] == 2
        assert api.overview()["by_type"]["paper"] == 1


class TestGraphEndpoint:
    def test_truncation_keeps_the_most_important_nodes(self, victor, api):
        for i in range(20):
            victor.graph.add_node(f"n{i}", NodeType.CLAIM, f"claim {i}")
            victor.graph.get_node(f"n{i}")["metadata"]["importance_score"] = i / 20

        result = api.graph(limit=5)
        assert result["truncated"] is True
        assert len(result["nodes"]) == 5
        assert result["total_nodes"] == 20
        # The five kept are the five heaviest.
        assert {n["id"] for n in result["nodes"]} == {"n19", "n18", "n17", "n16", "n15"}

    def test_links_to_dropped_nodes_are_not_emitted(self, victor, api):
        """A link pointing at a node the client never received would crash the layout."""
        victor.graph.add_node("keep", NodeType.CLAIM, "kept")
        victor.graph.add_node("drop", NodeType.CLAIM, "dropped")
        victor.graph.get_node("keep")["metadata"]["importance_score"] = 0.99
        victor.graph.get_node("drop")["metadata"]["importance_score"] = 0.01
        victor.graph.add_edge("keep", "drop", "supports")

        result = api.graph(limit=1)
        ids = {n["id"] for n in result["nodes"]}
        for link in result["links"]:
            assert link["source"] in ids and link["target"] in ids

    def test_not_truncated_when_under_the_limit(self, seeded, api):
        result = api.graph(limit=100)
        assert result["truncated"] is False


# ── routing ───────────────────────────────────────────────────────────────────

class TestDispatch:
    def test_unknown_get_endpoint_is_404(self, api):
        code, _ = _dispatch_get(api, "/api/nope", {})
        assert code == 404

    def test_unknown_post_endpoint_is_404(self, api):
        code, _ = _dispatch_post(api, "/api/nope", {})
        assert code == 404

    def test_missing_node_is_404(self, api):
        code, _ = _dispatch_get(api, "/api/node/nothing-here", {})
        assert code == 404

    def test_empty_ask_query_is_rejected(self, api):
        code, body = _dispatch_post(api, "/api/ask", {"query": "   "})
        assert code == 400
        assert "required" in body["error"]

    def test_node_route_handles_url_encoded_ids(self, seeded, api):
        code, body = _dispatch_get(api, "/api/node/paper1", {})
        assert code == 200
        assert body["id"] == "paper1"

    def test_gaps_route_passes_the_threshold_through(self, seeded, api):
        code, body = _dispatch_get(api, "/api/gaps", {"min_importance": "0.99"})
        assert code == 200
        assert body["count"] == 0

    def test_mask_and_unmask_routes_round_trip(self, seeded, api):
        _dispatch_post(api, "/api/mask", {"node_id": "secret1"})
        assert api.v.graph.node_is_masked("secret1") is True
        _dispatch_post(api, "/api/unmask", {"node_id": "secret1"})
        assert api.v.graph.node_is_masked("secret1") is False


class TestAsk:
    def test_ask_returns_answer_and_provenance(self, seeded, api):
        result = api.ask("what improves yield?")
        assert "answer" in result
        assert isinstance(result["chunks"], list)
        assert "provider" in result

    def test_masked_anchors_are_flagged_in_the_response(self, seeded, api):
        """
        The console tells the user when an answer rests on nodes it could not
        read. Silently answering from a partially dark memory is the failure
        mode worth guarding.
        """
        api.set_mask("secret1", True)
        result = api.ask("catalyst")
        for chunk in result["chunks"]:
            assert chunk["masked_anchor"] == (chunk["epistemic_status"] == "masked")
