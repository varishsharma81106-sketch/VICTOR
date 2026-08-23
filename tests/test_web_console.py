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
            # Search is queried with the secret itself. An endpoint that takes
            # attacker-chosen text and reports which nodes contain it is the
            # most direct route out of the vault there is.
            "search_all": api.search(limit=500),
            "search_secret": api.search(q=SECRET),
            "search_value": api.search(q=SECRET_VALUE),
            "search_semantic": api.search(q=SECRET, mode="semantic"),
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


class TestSearchIsNotAnOracle:
    """
    A search box over a masked graph is a content leak waiting to happen.

    Even with labels redacted in the response, *membership* answers the
    question: ask for "palladium", see the masked node come back, and the mask
    has told you what it was hiding. Repeat with different guesses and you read
    the vault a word at a time without ever seeing a label. So masked nodes are
    matched on structure only, never on their text.
    """

    def test_searching_the_secret_returns_nothing(self, seeded, api):
        api.set_mask("secret1", True)

        res = api.search(q="PALLADIUM")

        assert res["results"] == []
        assert res["total"] == 0

    def test_a_substring_of_the_secret_also_returns_nothing(self, seeded, api):
        """The oracle is built from partial guesses, not whole ones."""
        api.set_mask("secret1", True)

        for guess in ("palladium", "40psi", "undisclosed", "catalyst", "carbon"):
            assert api.search(q=guess)["total"] == 0, f"leaked on {guess!r}"

    def test_it_cannot_be_confirmed_by_narrowing(self, seeded, api):
        """
        The attack is incremental: each guess that returns a hit confirms a
        substring. Every prefix must be equally silent, not just the words a
        test author happened to think of.
        """
        api.set_mask("secret1", True)
        for n in (3, 6, 10, 20, len(SECRET)):
            assert api.search(q=SECRET[:n])["total"] == 0, f"leaked at {n} chars"

    def test_public_nodes_are_still_findable(self, seeded, api):
        """Guards the tests above against passing because search is simply broken."""
        api.set_mask("secret1", True)
        assert [r["id"] for r in api.search(q="yield")["results"]] == ["public1"]

    def test_the_same_query_works_before_masking(self, seeded, api):
        """Guards the test above: prove the query would have matched."""
        assert api.search(q="PALLADIUM")["total"] == 1

    def test_revealing_in_session_restores_matching(self, seeded, api):
        api.set_mask("secret1", True)
        assert api.search(q="palladium")["total"] == 0

        api.reveal("secret1")
        assert api.search(q="palladium")["total"] == 1

        api.conceal("secret1")
        assert api.search(q="palladium")["total"] == 0

    def test_semantic_search_never_reaches_masked_nodes(self, seeded, api):
        api.set_mask("secret1", True)

        res = api.search(q=SECRET, mode="semantic", limit=50)

        assert all(r["id"] != "secret1" for r in res["results"])

    def test_masked_nodes_are_still_listable_by_structure(self, seeded, api):
        """
        Withholding content must not withhold the anchor. Browsing by
        masked=True is the vault view, and it is supposed to work.
        """
        api.set_mask("secret1", True)

        res = api.search(masked=True)

        assert [r["id"] for r in res["results"]] == ["secret1"]
        assert res["results"][0]["label"] == REDACTED
        assert res["results"][0]["ntype"] == NodeType.CLAIM


class TestSearchBrowsing:
    def test_filters_by_type(self, seeded, api):
        res = api.search(ntype=NodeType.PAPER)
        assert [r["id"] for r in res["results"]] == ["paper1"]

    def test_paging_covers_every_node_exactly_once(self, seeded, api):
        seen = []
        for offset in range(0, 10, 2):
            seen += [r["id"] for r in api.search(limit=2, offset=offset)["results"]]

        assert sorted(seen) == ["paper1", "public1", "secret1"]

    def test_total_counts_matches_not_the_page(self, seeded, api):
        res = api.search(limit=1)
        assert len(res["results"]) == 1
        assert res["total"] == 3

    def test_unknown_sort_key_falls_back_rather_than_crashing(self, seeded, api):
        """The sort key arrives from a query string; it cannot be trusted."""
        res = api.search(sort="'; DROP TABLE nodes; --")
        assert res["total"] == 3

    def test_results_are_sorted_by_importance_descending(self, seeded, api):
        scores = [r["importance"] for r in api.search()["results"]]
        assert scores == sorted(scores, reverse=True)


class TestGraphSlicing:
    def test_focus_restricts_to_a_neighbourhood(self, seeded, api):
        api.v.graph.add_node("far", NodeType.NOTE, "unconnected to anything")

        res = api.graph(focus="paper1", hops=1)

        ids = {n["id"] for n in res["nodes"]}
        assert "far" not in ids
        assert {"paper1", "public1", "secret1"} <= ids
        assert res["focus"] == "paper1"

    def test_unknown_focus_falls_back_to_the_whole_graph(self, seeded, api):
        res = api.graph(focus="does-not-exist")
        assert res["focus"] is None
        assert len(res["nodes"]) == 3

    def test_min_importance_filters(self, seeded, api):
        res = api.graph(min_importance=0.99)
        assert res["nodes"] == []
        assert res["matched"] == 0
        assert res["total_nodes"] == 3

    def test_truncation_keeps_the_most_important(self, seeded, api):
        res = api.graph(limit=1)
        assert res["truncated"] is True
        assert res["matched"] == 3
        assert len(res["nodes"]) == 1
        # The survivor is whatever scores highest, asserted against the graph
        # rather than against a hardcoded id: the default importance table is a
        # tuning knob (CLAIM 0.70 currently beats PAPER 0.65) and a test that
        # pins one type is testing the knob, not the truncation.
        best = max(d["metadata"]["importance_score"]
                   for _, d in api.v.graph._g.nodes(data=True))
        assert res["nodes"][0]["importance"] == best

    def test_links_never_dangle(self, seeded, api):
        res = api.graph(limit=2)
        ids = {n["id"] for n in res["nodes"]}
        for link in res["links"]:
            assert link["source"] in ids and link["target"] in ids


class TestQueryStringHardening:
    def test_absurd_limit_is_clamped(self, seeded, api):
        code, body = _dispatch_get(api, "/api/graph", {"limit": "999999999"})
        assert code == 200
        assert len(body["nodes"]) <= 5000

    def test_garbage_limit_falls_back_to_the_default(self, seeded, api):
        code, body = _dispatch_get(api, "/api/search", {"limit": "not-a-number"})
        assert code == 200
        assert body["limit"] == 50

    def test_negative_offset_is_clamped(self, seeded, api):
        code, body = _dispatch_get(api, "/api/search", {"offset": "-5"})
        assert code == 200
        assert body["offset"] == 0

    def test_search_endpoint_is_routed(self, seeded, api):
        code, body = _dispatch_get(api, "/api/search", {"q": "yield"})
        assert code == 200
        assert [r["id"] for r in body["results"]] == ["public1"]

    def test_masked_flag_parses(self, seeded, api):
        api.set_mask("secret1", True)
        code, body = _dispatch_get(api, "/api/search", {"masked": "true"})
        assert code == 200
        assert [r["id"] for r in body["results"]] == ["secret1"]


# ── scale: finding things in a graph too large to look at ─────────────────────

class TestSearchPaging:
    @pytest.fixture
    def many(self, victor):
        g = victor.graph
        for i in range(120):
            g.add_node(f"n{i}", NodeType.CLAIM, f"finding {i} about topic {i % 5}",
                       metadata={"importance_score": i / 200.0,
                                 "retrieval_count": 120 - i})
        return victor

    def test_paging_covers_everything_exactly_once(self, many, api):
        seen, offset = [], 0
        while True:
            page = api.search(limit=25, offset=offset)
            if not page["results"]:
                break
            seen += [r["id"] for r in page["results"]]
            offset += 25
        assert len(seen) == len(set(seen)) == 120

    def test_total_is_the_match_count_not_the_page_size(self, many, api):
        page = api.search(q="topic 3", limit=5)
        assert len(page["results"]) == 5
        assert page["total"] == 24

    def test_sort_by_importance_is_descending(self, many, api):
        scores = [r["importance"] for r in api.search(sort="importance", limit=10)["results"]]
        assert scores == sorted(scores, reverse=True)

    def test_sort_by_retrievals_differs_from_importance(self, many, api):
        """An allowlisted sort key that silently fell back would be invisible."""
        by_imp = [r["id"] for r in api.search(sort="importance", limit=5)["results"]]
        by_ret = [r["id"] for r in api.search(sort="retrievals", limit=5)["results"]]
        assert by_imp != by_ret

    def test_unknown_sort_key_falls_back_instead_of_crashing(self, many, api):
        assert api.search(sort="; DROP TABLE", limit=3)["results"]

    def test_type_filter_narrows(self, many, api):
        assert api.search(ntype=NodeType.PAPER)["total"] == 0
        assert api.search(ntype=NodeType.CLAIM)["total"] == 120


class TestGraphSlicingAtScale:
    @pytest.fixture
    def many(self, victor):
        g = victor.graph
        for i in range(300):
            g.add_node(f"n{i}", NodeType.CLAIM, f"finding {i}",
                       metadata={"importance_score": i / 300.0})
        for i in range(299):
            g.add_edge(f"n{i}", f"n{i + 1}", "related_to")
        return victor

    def test_truncation_keeps_the_most_important(self, many, api):
        res = api.graph(limit=10)
        assert res["truncated"] is True
        assert res["total_nodes"] == 300
        assert res["matched"] == 300
        assert min(n["importance"] for n in res["nodes"]) > 0.9

    def test_links_never_dangle(self, many, api):
        res = api.graph(limit=50)
        ids = {n["id"] for n in res["nodes"]}
        for link in res["links"]:
            assert link["source"] in ids and link["target"] in ids

    def test_focus_returns_a_neighbourhood_not_the_graph(self, many, api):
        res = api.graph(focus="n150", hops=2, limit=600)
        ids = {n["id"] for n in res["nodes"]}
        assert res["focus"] == "n150"
        assert "n150" in ids
        assert ids == {f"n{i}" for i in range(148, 153)}

    def test_unknown_focus_falls_back_to_the_whole_graph(self, many, api):
        res = api.graph(focus="does-not-exist", limit=600)
        assert res["focus"] is None
        assert res["matched"] == 300

    def test_min_importance_filters_before_the_cut(self, many, api):
        res = api.graph(limit=600, min_importance=0.5)
        assert res["matched"] == len(res["nodes"]) == 150


class TestQueryParamHardening:
    def test_absurd_limit_is_clamped(self, seeded, api):
        code, body = _dispatch_get(api, "/api/graph", {"limit": "999999999"})
        assert code == 200
        assert len(body["nodes"]) <= 5000

    def test_garbage_limit_falls_back_to_the_default(self, seeded, api):
        code, body = _dispatch_get(api, "/api/search", {"limit": "abc"})
        assert code == 200
        assert body["limit"] == 50

    def test_negative_offset_is_clamped(self, seeded, api):
        code, body = _dispatch_get(api, "/api/search", {"offset": "-5"})
        assert code == 200
        assert body["offset"] == 0

    def test_masked_flag_parses(self, seeded, api):
        api.set_mask("secret1", True)
        code, body = _dispatch_get(api, "/api/search", {"masked": "true"})
        assert code == 200
        assert [r["id"] for r in body["results"]] == ["secret1"]

    def test_search_is_routed(self, seeded, api):
        code, body = _dispatch_get(api, "/api/search", {"q": "yield"})
        assert code == 200
        assert body["mode"] == "text"


# ── the machine view: Victor doing the understanding, not the operator ────────

class TestDeliberate:
    """
    /api/deliberate is the only endpoint where the *machine* decides what to
    read. That makes it the one place a masked node could be opened without a
    person choosing to open it, so it gets the same leak scan as everything
    else — plus a check that the refusals actually appear in the response
    rather than being quietly dropped on the way out.
    """

    def test_the_machine_reaches_the_masked_node_and_is_refused(self, seeded, api):
        api.set_mask("secret1", True)
        out = api.deliberate("what raises the catalyst yield", budget=5)

        refusals = [s for s in out["deliberation"]["steps"] if not s["granted"]]
        assert refusals, "the pass never even asked for the withheld memory"
        assert any(s["node_id"] == "secret1" for s in refusals)
        assert out["deliberation"]["refused"] >= 1

    def test_the_whole_response_is_free_of_the_secret(self, seeded, api):
        api.set_mask("secret1", True)
        blob = json.dumps(api.deliberate("catalyst yield", budget=8), default=str)
        assert SECRET not in blob
        assert SECRET_VALUE not in blob
        for n in (8, 12, 20, 40):
            assert SECRET[:n] not in blob, f"leaked first {n} characters"

    def test_the_masked_handle_is_still_offered(self, seeded, api):
        """
        A table that dropped the masked node would be tidier and would be
        lying: the machine has to be able to see that something relevant is
        being withheld from it.
        """
        api.set_mask("secret1", True)
        table = api.deliberate("catalyst yield", budget=1)["deliberation"]["table"]
        assert table["masked_count"] == 1
        masked = next(p for p in table["points"] if p["masked"])
        assert masked["descriptor"] == REDACTED
        assert masked["ntype"] == NodeType.CLAIM      # structure still published

    def test_a_session_reveal_authorises_the_machine(self, seeded, api):
        """
        Reveal is the operator's decision and it is the *only* thing that opens
        the door. Without it the default is refuse-all, because a reasoning pass
        that can unmask itself is not a boundary.
        """
        api.set_mask("secret1", True)
        assert api.deliberate("catalyst yield", budget=8)["deliberation"]["refused"] >= 1

        api.reveal("secret1")
        out = api.deliberate("catalyst yield", budget=8)
        assert out["revealed_this_session"] == ["secret1"]
        opened = [s for s in out["deliberation"]["steps"]
                  if s["granted"] and s["node_id"] == "secret1"]
        assert opened, "an authorised handle was still refused"
        assert SECRET in opened[0]["content"]

    def test_every_step_states_a_reason(self, seeded, api):
        api.set_mask("secret1", True)
        steps = api.deliberate("catalyst yield", budget=4)["deliberation"]["steps"]
        assert steps
        assert all(s["reason"] for s in steps)

    def test_the_conclusion_admits_what_it_could_not_read(self, seeded, api):
        api.set_mask("secret1", True)
        out = api.deliberate("catalyst yield", budget=8)
        assert "incomplete record" in out["deliberation"]["answer"]

    def test_it_runs_without_a_language_model(self, seeded, api):
        """The field case: no network, no model, still has to deliberate."""
        out = api.deliberate("catalyst yield", budget=3)
        assert "policy" in out["chose_by"]
        assert out["deliberation"]["steps"]

    def test_budget_bounds_the_pass(self, seeded, api):
        out = api.deliberate("catalyst yield", budget=2)
        assert len(out["deliberation"]["steps"]) <= 2
        assert out["deliberation"]["table"]["budget"] == 2

    def test_a_ledger_line_is_written_per_request(self, seeded, api, victor):
        ledger = victor.graph.graph_file.parent / "referral_ledger.jsonl"
        api.set_mask("secret1", True)
        out = api.deliberate("catalyst yield", budget=3)

        rows = [json.loads(l) for l in ledger.read_text(encoding="utf-8").splitlines() if l]
        assert len(rows) == len(out["deliberation"]["steps"])
        assert any(r["granted"] is False for r in rows)
        # The log records that a disclosure happened, never the disclosure.
        assert SECRET not in ledger.read_text(encoding="utf-8")


class TestDeliberateRouting:
    def test_it_is_routed(self, seeded, api):
        code, body = _dispatch_post(api, "/api/deliberate", {"query": "yield"})
        assert code == 200
        assert "deliberation" in body

    def test_an_empty_query_is_rejected(self, seeded, api):
        code, _ = _dispatch_post(api, "/api/deliberate", {"query": "   "})
        assert code == 400

    def test_a_junk_budget_falls_back(self, seeded, api):
        code, body = _dispatch_post(api, "/api/deliberate",
                                    {"query": "yield", "budget": "lots"})
        assert code == 200
        assert body["deliberation"]["table"]["budget"] == 3

    def test_an_absurd_budget_is_clamped(self, seeded, api):
        """The budget is the mechanism; an unbounded one is bulk retrieval."""
        code, body = _dispatch_post(api, "/api/deliberate",
                                    {"query": "yield", "budget": 10_000})
        assert code == 200
        assert body["deliberation"]["table"]["budget"] == 8

    def test_sensor_ticks_are_clamped(self, seeded, api):
        code, body = _dispatch_post(api, "/api/deliberate",
                                    {"query": "yield", "sensors": 9999})
        assert code == 200
        assert body["sensors"]["ticks"] == 40


class TestDeliberateWithSensors:
    """
    Live readings and stored memory in one table. The scenario's sensitive
    reading is masked on arrival, so the machine meets the same boundary on a
    fragment that it meets on a graph node.
    """

    SENSITIVE = "palladium-rich matrix"

    def test_live_readings_join_the_table(self, seeded, api):
        out = api.deliberate("is the site safe to enter", budget=3, sensors=8)
        assert out["sensors"]["ticks"] == 8
        assert out["sensors"]["readings"]
        node_ids = {p["node_id"] for p in out["deliberation"]["table"]["points"]}
        assert node_ids & {r["id"] for r in out["sensors"]["readings"]}

    def test_a_sensitive_reading_is_withheld_on_arrival(self, seeded, api):
        out = api.deliberate("what is the sample", budget=3, sensors=12)
        blob = json.dumps(out, default=str)
        assert self.SENSITIVE not in blob

    def test_the_simulation_does_not_touch_the_real_graph(self, seeded, api, victor):
        """A demonstration must not write simulated observations into real memory."""
        before = victor.graph._g.number_of_nodes()
        api.deliberate("is the site safe", budget=2, sensors=10)
        assert victor.graph._g.number_of_nodes() == before

    def test_stored_masked_memory_survives_a_busy_tick(self, seeded, api):
        """
        Regression: fragments used to take every anchor slot, so during a sensor
        burst the graph's own masked nodes stopped being offered at all.
        """
        api.set_mask("secret1", True)
        out = api.deliberate("catalyst yield", budget=1, sensors=12)
        ids = {p["node_id"] for p in out["deliberation"]["table"]["points"]}
        assert "secret1" in ids
