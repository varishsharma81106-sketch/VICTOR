"""
Referral points: memory addressed by handle, dereferenced one at a time.

Two properties carry this module and everything else here is support:

  1. **A referral point never carries content.** The table exists so a model can
     choose what to read; the moment describing a point discloses it, the
     choosing is decoration and the mask is decoration too.

  2. **Disclosure is serialised and recorded.** One handle, one reason, one
     ledger line — including the refusals. A trace that records only what
     succeeded is a record of nothing.

The rest checks that the machine can run this loop unaided: the policy chooser
must decide, hit the boundary, and report an incomplete record rather than
routing around it.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from victor.graph import VictorKnowledgeGraph
from victor.models import EpistemicStatus, NodeType
from victor.referral import (
    DENY_BUDGET,
    DENY_MASKED,
    DENY_REPEAT,
    DENY_UNKNOWN,
    WITHHELD,
    DeliberateReasoner,
    Fragment,
    PolicyChooser,
    ReferralDesk,
    ReferralPoint,
    summarise,
)


SECRET = "PALLADIUM_ON_CARBON_at_40psi"

# Bag-of-words over a fixed vocabulary. A hash-seeded random embedder makes
# similarity arbitrary, and then every ordering assertion below is really an
# assertion about the seed. Here similarity tracks shared words, so when a test
# says a measurement outranks a hypothesis it is testing the ranking rule.
VOCAB = (
    "hydrogenation arene yield run measurement pressure catalyst "
    "palladium carbon psi air methane sample safe"
).split()


class LexicalEmbedder:
    def embed(self, text: str):
        low = str(text).lower()
        v = np.array([float(low.count(w)) for w in VOCAB] + [0.35])
        #                                                     ^ a floor, so an
        # out-of-vocabulary string still has a direction and cosine is defined.
        return (v / np.linalg.norm(v)).tolist()

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


@pytest.fixture
def graph(tmp_path):
    g = VictorKnowledgeGraph(tmp_path / "graph.json", LexicalEmbedder())
    g.add_node("paper1", NodeType.PAPER, "Hydrogenation of substituted arenes",
               metadata={"epistemic_status": EpistemicStatus.LITERATURE.value,
                         "confidence": 0.7, "importance_score": 0.65})
    g.add_node("run1", NodeType.EXPERIMENT, "Run 14 yield measurement",
               metadata={"epistemic_status": EpistemicStatus.MEASUREMENT.value,
                         "confidence": 0.95, "importance_score": 0.9})
    g.add_node("guess1", NodeType.CLAIM, "Pressure probably drives the effect",
               metadata={"epistemic_status": EpistemicStatus.HYPOTHESIS.value,
                         "confidence": 0.3, "importance_score": 0.4})
    g.add_node("secret1", NodeType.CLAIM, SECRET,
               metadata={"epistemic_status": EpistemicStatus.EXPERIMENT.value,
                         "confidence": 0.9, "importance_score": 0.95})
    g.add_edge("paper1", "run1", "supports")
    g.add_edge("run1", "secret1", "supports")
    g.add_edge("paper1", "guess1", "supports")
    g.mask_node("secret1")
    return g


@pytest.fixture
def desk(graph, tmp_path):
    return ReferralDesk(graph, ledger_path=tmp_path / "referral.jsonl")


@pytest.fixture
def open_desk(graph, tmp_path):
    """A desk authorised for everything — the reveal case."""
    return ReferralDesk(graph, authority=lambda _nid: True,
                        ledger_path=tmp_path / "open.jsonl")


def point_for(table, node_id):
    return next(p for p in table.points if p.node_id == node_id)


# ── 1. a handle is not content ────────────────────────────────────────────────

class TestTheTableDisclosesNothing:
    def test_masked_descriptor_is_a_placeholder(self, desk):
        p = point_for(desk.offer("catalyst yield"), "secret1")
        assert p.descriptor == WITHHELD
        assert SECRET not in p.describe()

    def test_the_whole_rendered_table_is_clean(self, desk):
        blob = desk.offer("catalyst yield pressure").render()
        assert SECRET not in blob
        assert "PALLADIUM" not in blob.upper()

    def test_no_prefix_of_the_secret_survives(self, desk):
        blob = json.dumps(desk.offer("catalyst yield").as_dict())
        for n in (6, 10, 16, len(SECRET)):
            assert SECRET[:n] not in blob, f"leaked first {n} chars"

    def test_the_masked_point_is_still_offered(self, desk):
        """
        Withholding content is the point; withholding existence is not. If the
        masked node vanished from the table the model could not know there is
        something it is not being told.
        """
        table = desk.offer("catalyst yield")
        assert any(p.node_id == "secret1" and p.masked for p in table.points)
        assert table.as_dict()["masked_count"] == 1

    def test_masked_points_publish_structure(self, desk):
        p = point_for(desk.offer("catalyst yield"), "secret1")
        assert p.ntype == NodeType.CLAIM
        assert p.degree >= 1
        assert p.epistemic_status == EpistemicStatus.EXPERIMENT.value

    def test_masked_rank_is_inherited_not_matched(self, desk):
        """
        The oracle property. A masked node's relevance is its anchor's, scaled —
        never a score against its own text. If it moved with the query wording,
        the ranking would spell out the content one query at a time.
        """
        table = desk.offer("catalyst yield")
        anchor = point_for(table, "run1")
        assert point_for(table, "secret1").relevance == pytest.approx(
            anchor.relevance * 0.6
        )

    def test_naming_the_secret_carries_no_extra_information(self, desk):
        """
        The masked score is a fixed multiple of a *visible* point's score, so it
        states nothing the table has not already published. Querying the node by
        its own hidden words moves it only insofar as it moves the anchor — and
        here it moves it *down*, because the extra terms dilute the anchor's
        match. Either way the ratio is constant, so an attacker probing with
        guesses learns the anchor's relevance and nothing else.
        """
        seen = []
        for query in ("catalyst yield",
                      "palladium carbon psi",           # the content itself
                      "PALLADIUM_ON_CARBON_at_40psi",   # the label, verbatim
                      "hydrogenation run"):
            table = desk.offer(query)
            secret = point_for(table, "secret1")
            anchor = point_for(table, "run1")
            assert secret.relevance / anchor.relevance == pytest.approx(0.6)
            seen.append(secret.relevance)
        # And the probe never wins: naming it exactly does not float it to the top.
        assert max(seen) == pytest.approx(seen[0])

    def test_authorised_descriptor_is_the_real_label(self, open_desk):
        assert point_for(open_desk.offer("catalyst yield"), "secret1").descriptor == SECRET


# ── 2. one at a time, and everything recorded ─────────────────────────────────

class TestDereference:
    def test_a_visible_point_yields_its_content(self, desk):
        table = desk.offer("run 14 yield")
        d = desk.dereference(table, point_for(table, "run1").ref, reason="highest tier")
        assert d.granted
        assert "Run 14" in d.content

    def test_a_masked_point_is_refused_not_hidden(self, desk):
        table = desk.offer("catalyst yield")
        d = desk.dereference(table, point_for(table, "secret1").ref, reason="looks central")

        assert d.granted is False
        assert d.denial == DENY_MASKED
        assert d.content is None
        # The refusal names the node — which the table already published — and
        # nothing else.
        assert SECRET not in json.dumps(d.as_dict())

    def test_authority_turns_the_refusal_into_a_grant(self, open_desk):
        table = open_desk.offer("catalyst yield")
        d = open_desk.dereference(table, point_for(table, "secret1").ref, reason="authorised")
        assert d.granted
        assert SECRET in d.content

    def test_unknown_handle_is_refused(self, desk):
        assert desk.dereference(desk.offer("yield"), "R99").denial == DENY_UNKNOWN

    def test_budget_is_enforced_at_the_desk(self, desk):
        table = desk.offer("yield")
        d = desk.dereference(table, table.points[0].ref, spent=table.budget)
        assert d.denial == DENY_BUDGET

    def test_serialised_denial_carries_no_content_key(self, desk):
        table = desk.offer("catalyst yield")
        assert "content" not in desk.dereference(
            table, point_for(table, "secret1").ref).as_dict()

    def test_reading_a_point_credits_the_node(self, desk, graph):
        table = desk.offer("run 14 yield")
        desk.dereference(table, point_for(table, "run1").ref)
        assert graph.get_node("run1")["metadata"]["retrieval_count"] == 1

    def test_a_refused_request_credits_nothing(self, desk, graph):
        table = desk.offer("catalyst yield")
        desk.dereference(table, point_for(table, "secret1").ref)
        assert graph.get_node("secret1")["metadata"].get("retrieval_count", 0) == 0


class TestLedger:
    def _lines(self, path):
        return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l]

    def test_grants_and_refusals_are_both_recorded(self, desk, tmp_path):
        table = desk.offer("catalyst yield")
        desk.dereference(table, point_for(table, "run1").ref, reason="best grounded")
        desk.dereference(table, point_for(table, "secret1").ref,
                         reason="central to the question", spent=1)

        rows = self._lines(tmp_path / "referral.jsonl")
        assert [r["granted"] for r in rows] == [True, False]
        assert rows[1]["denial"] == DENY_MASKED
        assert rows[1]["node_id"] == "secret1"

    def test_the_stated_reason_is_kept(self, desk, tmp_path):
        table = desk.offer("run 14 yield")
        desk.dereference(table, point_for(table, "run1").ref,
                         reason="the only measurement tier point")
        assert self._lines(tmp_path / "referral.jsonl")[0]["reason"] == \
            "the only measurement tier point"

    def test_the_ledger_never_copies_the_disclosure(self, open_desk, tmp_path):
        """
        A disclosure log that writes the disclosure has doubled the exposure it
        exists to bound — and unlike an answer in a terminal, the log persists.
        """
        table = open_desk.offer("catalyst yield")
        assert open_desk.dereference(table, point_for(table, "secret1").ref).granted

        blob = (tmp_path / "open.jsonl").read_text(encoding="utf-8")
        assert SECRET not in blob
        assert "secret1" in blob          # the handle is recorded, the body is not

    def test_a_desk_with_no_ledger_path_still_works(self, graph):
        desk = ReferralDesk(graph)
        table = desk.offer("run 14 yield")
        assert desk.dereference(table, table.points[0].ref).granted


# ── 3. the machine decides, unaided ───────────────────────────────────────────

class TestPolicyChooser:
    """
    No LLM. Victor on a machine in the field often has no model to call, and the
    deliberation loop has to run anyway.
    """

    def test_it_opens_the_best_grounded_point_first(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("what is the yield")
        first = result.table.get(result.steps[0].ref)
        assert first.node_id == "run1"
        assert first.epistemic_status == EpistemicStatus.MEASUREMENT.value

    def test_the_hypothesis_is_not_opened_first(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("what is the yield")
        first = result.table.get(result.steps[0].ref)
        assert first.epistemic_status != EpistemicStatus.HYPOTHESIS.value

    def test_it_does_not_route_around_the_boundary(self, desk):
        """
        A policy that skipped masked points would produce clean traces and a
        machine that never records being stopped. It has to ask and be refused.
        """
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        assert result.refused >= 1
        assert any(s.denial == DENY_MASKED and s.node_id == "secret1"
                   for s in result.steps)

    def test_it_says_the_record_is_incomplete(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        assert "incomplete record" in result.answer
        assert DENY_MASKED in result.answer

    def test_it_does_not_cry_incomplete_when_nothing_was_refused(self, graph, tmp_path):
        graph.unmask_node("secret1")
        result = DeliberateReasoner(
            ReferralDesk(graph, ledger_path=tmp_path / "l.jsonl"), chooser=PolicyChooser()
        ).run("catalyst yield")
        assert result.refused == 0
        assert "incomplete record" not in result.answer

    def test_every_choice_carries_a_reason(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        assert result.steps
        assert all(s.reason for s in result.steps)

    def test_the_reason_for_a_masked_request_is_explicit(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        masked_step = next(s for s in result.steps if s.denial == DENY_MASKED)
        assert "masked" in masked_step.reason

    def test_it_is_deterministic(self, desk):
        a = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        b = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        assert [s.ref for s in a.steps] == [s.ref for s in b.steps]


class TestTheLoop:
    def test_budget_bounds_the_pass(self, graph, tmp_path):
        desk = ReferralDesk(graph, budget=2, ledger_path=tmp_path / "l.jsonl")
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        assert len(result.steps) == 2

    def test_re_asking_the_same_handle_is_refused(self, desk):
        """A model looping on one handle must burn budget visibly, not silently."""
        def stubborn(table, steps):
            return {"action": "dereference", "ref": table.points[0].ref,
                    "reason": "again"}

        result = DeliberateReasoner(desk, chooser=stubborn).run("run 14 yield")
        assert result.steps[0].granted
        assert result.granted == 1
        assert all(s.denial == DENY_REPEAT for s in result.steps[1:])

    def test_answering_early_ends_the_pass(self, desk):
        result = DeliberateReasoner(
            desk, chooser=lambda t, s: {"action": "answer", "answer": "enough"}
        ).run("yield")
        assert result.answer == "enough"
        assert result.steps == []

    def test_a_chooser_with_no_conclusion_leaves_the_answer_empty(self, desk):
        """
        Not every chooser can summarise. The loop must not invent one — an empty
        answer beside a full step list is honest; a fabricated summary is not.
        """
        result = DeliberateReasoner(
            desk, chooser=lambda t, s: {"action": "dereference",
                                        "ref": t.points[0].ref, "reason": "first"}
        ).run("yield")
        assert result.answer == ""
        assert result.steps

    def test_the_full_trace_serialises_without_the_secret(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        assert SECRET not in json.dumps(result.as_dict(), ensure_ascii=False)

    def test_summary_reports_offers_grants_and_refusals(self, desk):
        result = DeliberateReasoner(desk, chooser=PolicyChooser()).run("catalyst yield")
        line = summarise(result)
        assert "referral point" in line
        assert f"opened {result.granted}" in line
        assert f"refused {result.refused}" in line

    def test_an_empty_graph_produces_an_empty_table_not_a_crash(self, tmp_path):
        empty = VictorKnowledgeGraph(tmp_path / "empty.json", LexicalEmbedder())
        result = DeliberateReasoner(ReferralDesk(empty), chooser=PolicyChooser()).run("x")
        assert result.steps == []
        assert "no grounded conclusion" in result.answer


# ── 4. real-time fragments ────────────────────────────────────────────────────

class TestFragments:
    def test_a_live_reading_competes_in_the_same_table(self, desk):
        frag = Fragment("frag:1", "methane 0.4% and rising", "sim:spectrometer", 0.94)
        assert point_for(desk.offer("is the air safe", fragments=[frag]), "frag:1")

    def test_a_fresh_measurement_outranks_a_stored_hypothesis(self, desk):
        frag = Fragment("frag:1", "methane 0.4% and rising", "sim:spectrometer", 0.94)
        order = [p.node_id for p in desk.offer("is the air safe", fragments=[frag]).points]
        assert order.index("frag:1") < order.index("guess1")

    def test_a_sensitive_reading_is_withheld_on_arrival(self, desk):
        frag = Fragment("frag:2", "palladium-rich matrix", "sim:spectrometer",
                        0.94, masked=True)
        table = desk.offer("what is the sample", fragments=[frag])
        p = point_for(table, "frag:2")

        assert p.descriptor == WITHHELD
        assert "palladium" not in table.render().lower()
        assert desk.dereference(table, p.ref, fragments=[frag]).denial == DENY_MASKED

    def test_an_open_fragment_dereferences_to_its_text(self, desk):
        frag = Fragment("frag:1", "methane 0.4% and rising", "sim:spectrometer", 0.94)
        table = desk.offer("is the air safe", fragments=[frag])
        d = desk.dereference(table, point_for(table, "frag:1").ref, fragments=[frag])
        assert d.content == frag.text

    def test_live_readings_do_not_crowd_out_stored_masked_memory(self, desk):
        """
        Regression. Anchors used to be the top three visible points of any kind,
        and a fragment has no neighbourhood — so during a busy sensor tick the
        fragments took all three slots, no masked graph node was ever reached,
        and the table went quiet about the withheld memory precisely when the
        machine most needed to know it was there.
        """
        live = [
            Fragment(f"frag:{i}", f"methane {i} and rising", "sim:spectrometer", 0.9)
            for i in range(5)
        ]
        table = desk.offer("catalyst yield", fragments=live)
        assert point_for(table, "secret1").masked
        assert table.as_dict()["masked_count"] == 1

    def test_a_fragment_grant_does_not_break_on_having_no_node(self, desk):
        """`record_retrieval` has nothing to credit for a reading that never landed."""
        frag = Fragment("frag:1", "methane 0.4% and rising", "sim:spectrometer", 0.94)
        table = desk.offer("is the air safe", fragments=[frag])
        assert desk.dereference(table, point_for(table, "frag:1").ref,
                                fragments=[frag]).granted


# ── 5. the tier weight finally has a call site ────────────────────────────────

def _pt(ref, status, relevance=0.6, degree=1, masked=False):
    return ReferralPoint(
        ref=ref, node_id=ref, ntype=NodeType.CLAIM, origin="x",
        epistemic_status=status, confidence=0.8, contradictions=0, gaps=0,
        age_days=1.0, degree=degree, relevance=relevance, masked=masked,
        descriptor=WITHHELD if masked else "a label",
    )


class TestEpistemicWeightIsUsed:
    def test_tier_weight_reads_the_ladder(self):
        assert _pt("R1", EpistemicStatus.MEASUREMENT.value).tier_weight == 1.0
        assert _pt("R2", EpistemicStatus.HYPOTHESIS.value).tier_weight == 0.25

    def test_an_unknown_tier_does_not_crash_ranking(self):
        assert 0.0 < _pt("R1", "not-a-tier").tier_weight <= 1.0

    def test_standing_breaks_a_tie(self):
        assert PolicyChooser.score(_pt("R1", EpistemicStatus.MEASUREMENT.value)) > \
               PolicyChooser.score(_pt("R2", EpistemicStatus.HYPOTHESIS.value))

    def test_standing_beats_a_modest_matching_advantage(self):
        """
        The differentiator, doing work: a measurement that matched less well
        still gets opened first. This is the whole claim, as a number.
        """
        measurement = _pt("R1", EpistemicStatus.MEASUREMENT.value, relevance=0.60)
        hypothesis = _pt("R2", EpistemicStatus.HYPOTHESIS.value, relevance=0.75)
        assert PolicyChooser.score(measurement) > PolicyChooser.score(hypothesis)

    def test_standing_does_not_beat_an_overwhelming_one(self):
        """And it is a tilt, not an override — a far better match still wins."""
        measurement = _pt("R1", EpistemicStatus.MEASUREMENT.value, relevance=0.05)
        hypothesis = _pt("R2", EpistemicStatus.HYPOTHESIS.value, relevance=0.90)
        assert PolicyChooser.score(hypothesis) > PolicyChooser.score(measurement)
