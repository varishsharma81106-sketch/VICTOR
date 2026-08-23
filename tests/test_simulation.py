"""
The sensor simulation, tested on its claims rather than its plumbing.

A simulation is only worth running if it can fail. Each test below pins one
thing the run is supposed to demonstrate, so that a change which quietly breaks
the demonstration — beliefs that stop revising, masking that stops applying,
density that starts exploding again — shows up as a red test rather than as a
still-impressive-looking console table.
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from victor.graph import VictorKnowledgeGraph
from victor.models import EdgeType, EpistemicStatus, NodeType
from victor.simulation import (
    SCENARIOS,
    STRANDED_SITE,
    Belief,
    Scenario,
    SensorSpec,
    SimulatedSensor,
    Simulation,
    WorldState,
)


SECRET = "palladium-rich matrix"


class StubEmbedder:
    def embed(self, text: str):
        rng = np.random.default_rng(abs(hash(text)) % (2**32))
        v = rng.standard_normal(16)
        return (v / np.linalg.norm(v)).tolist()

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


def make_sim(tmp_path, seed=7, scenario=STRANDED_SITE):
    graph = VictorKnowledgeGraph(tmp_path / "graph.json", StubEmbedder())
    return Simulation(graph, scenario, seed=seed, save_dir=tmp_path / "frames")


@pytest.fixture
def sim(tmp_path):
    s = make_sim(tmp_path)
    s.run(ticks=45)
    return s


class TestDeterminism:
    """Same seed, same run — otherwise nothing below is a real assertion."""

    def test_identical_seeds_produce_identical_reports(self, tmp_path):
        a = make_sim(tmp_path / "a", seed=11)
        b = make_sim(tmp_path / "b", seed=11)
        a.run(ticks=20)
        b.run(ticks=20)

        assert json.dumps(a.report(), sort_keys=True) == json.dumps(b.report(), sort_keys=True)

    def test_different_seeds_diverge(self, tmp_path):
        a = make_sim(tmp_path / "a", seed=11)
        b = make_sim(tmp_path / "b", seed=12)
        a.run(ticks=20)
        b.run(ticks=20)

        assert a.report() != b.report()

    def test_no_wall_clock_in_timestamps(self, sim):
        """
        Observations carry simulated time. If they picked up datetime.now(), two
        runs of the same seed would differ and every assertion here would rot.
        """
        stamps = [
            d["metadata"]["timestamp"]
            for _, d in sim.graph._g.nodes(data=True)
            if d.get("ntype") == NodeType.OBSERVATION
        ]
        assert stamps
        assert all(s.startswith("2026-01-01") for s in stamps)


class TestBeliefRevision:
    """
    The scenario scripts the air going bad at tick 18. A machine that cannot
    notice is the failure mode this whole module exists to expose — an earlier
    version summed evidence cumulatively and never revised at all.
    """

    def _belief_at(self, sim, tick, entity):
        return next(b for b in sim.history[tick].beliefs if b.entity == entity)

    def test_air_is_believed_breathable_before_the_seep(self, sim):
        b = self._belief_at(sim, 17, "atmosphere")
        assert b.belief == "breathable"
        assert b.correct

    def test_air_belief_flips_after_the_seep(self, sim):
        assert self._belief_at(sim, 44, "atmosphere").belief == "trace methane"

    def test_revision_lag_is_bounded(self, sim):
        """
        How long the machine stayed wrong is the number that matters. Bounded at
        15 ticks: fast enough to be worth reporting, loose enough to survive the
        stochastic sensors rather than pinning today's seed.
        """
        flip = next(
            (t for t in range(18, 45)
             if self._belief_at(sim, t, "atmosphere").belief == "trace methane"),
            None,
        )
        assert flip is not None, "belief never revised"
        assert flip - 18 <= 15, f"took {flip - 18} ticks to notice the methane"

    def test_margin_collapses_before_it_flips(self, sim):
        """Confidence should erode visibly, not snap. That erosion is the UI."""
        before = self._belief_at(sim, 17, "atmosphere").margin
        crossing = min(
            (self._belief_at(sim, t, "atmosphere").margin for t in range(18, 30)),
        )
        assert crossing < before / 2

    def test_every_entity_is_understood_by_the_end(self, sim):
        rep = sim.report()
        assert rep["correct_beliefs"] == rep["entities"] == 4
        assert rep["unsettled"] == 0


class TestMaskingOnArrival:
    """
    VICTOR_ORIGINAL.md wants masking to be memory's default posture. Everywhere
    else in Victor it is opt-in per node after the fact; here a sensitive
    reading is withheld from the moment it is recorded.
    """

    def _sensitive_nodes(self, sim):
        return [
            (nid, d) for nid, d in sim.graph._g.nodes(data=True)
            if d.get("metadata", {}).get("label") == SECRET
        ]

    def test_sensitive_readings_are_masked_in_the_graph(self, sim):
        nodes = self._sensitive_nodes(sim)
        assert nodes
        assert all(d["metadata"]["is_masked"] for _, d in nodes)

    def test_no_sensitive_reading_is_ever_left_unmasked(self, sim):
        """Not "most were masked" — a single miss is the whole leak."""
        for tick in sim.history:
            assert tick.masked >= 0
        unmasked = [
            nid for nid, d in self._sensitive_nodes(sim)
            if not d["metadata"]["is_masked"]
        ]
        assert unmasked == []

    def test_the_report_does_not_publish_the_masked_reading(self, sim):
        """
        The report is the artifact most likely to be logged, saved, or served.
        If the secret survives serialisation, the mask is decorative.
        """
        blob = json.dumps(sim.report(), ensure_ascii=False)
        assert SECRET not in blob
        assert Belief.WITHHELD in blob

    def test_masked_reading_is_still_scored_internally(self, sim):
        """Redaction must not cost correctness — sample-07 is still judged."""
        b = next(b for b in sim.history[-1].beliefs if b.entity == "sample-07")
        assert b.masked
        assert b.belief == SECRET          # readable in-process
        assert b.correct
        assert b.as_dict()["belief"] == Belief.WITHHELD

    def test_masked_observations_are_absent_from_semantic_search(self, sim):
        hits = sim.graph.semantic_query(f"observation: {SECRET}", top_k=20)
        for nid, _, data in hits:
            assert data.get("metadata", {}).get("label") != SECRET


class TestGraphShape:
    def test_observations_are_measurement_tier(self, sim):
        obs = [d for _, d in sim.graph._g.nodes(data=True)
               if d.get("ntype") == NodeType.OBSERVATION]
        assert obs
        assert all(
            d["metadata"]["epistemic_status"] == EpistemicStatus.MEASUREMENT.value
            for d in obs
        )

    def test_all_six_epistemic_properties_are_present(self, sim):
        """VICTOR_THEORY_v1: without all six it is not an artifact, it is text."""
        _, data = next(
            (n, d) for n, d in sim.graph._g.nodes(data=True)
            if d.get("ntype") == NodeType.OBSERVATION
        )
        meta = data["metadata"]
        for field in ("sensor_type", "epistemic_status", "confidence",
                      "contradictions", "gaps", "timestamp"):
            assert field in meta, f"missing epistemic property: {field}"

    def test_disagreement_becomes_contradicts_edges(self, sim):
        etypes = [d.get("etype") for _, _, d in sim.graph._g.edges(data=True)]
        assert EdgeType.CONTRADICTS in etypes
        assert EdgeType.CONFIRMS in etypes
        assert etypes.count(EdgeType.CONTRADICTS) == sim.history[-1].contradictions

    def test_density_stays_bounded(self, sim):
        """
        Regression guard on the clique bug: linking each observation to all of
        history gave a 30-tick run 22,797 edges and a "density" of 53.5, a
        number that rises forever and means nothing. Windowed cross-checking
        converges just above the window size.
        """
        final = sim.history[-1].density
        assert final <= sim.CROSS_CHECK_WINDOW + 2, f"density {final:.1f} is exploding"
        assert final > 2.0, "no cross-checking happened at all"

    def test_density_rises_then_settles(self, sim):
        early, mid, late = (sim.history[i].density for i in (0, 20, 44))
        assert early < mid < late          # still compounding
        assert (late - mid) < (mid - early)  # but converging, not exploding

    def test_every_observation_attaches_to_its_entity(self, sim):
        g = sim.graph._g
        entity_nodes = {n for n in g.nodes if n.startswith("entity::")}
        assert len(entity_nodes) == 4
        for nid, d in g.nodes(data=True):
            if d.get("ntype") != NodeType.OBSERVATION:
                continue
            targets = {t for _, t in g.out_edges(nid)}
            assert targets & entity_nodes, f"{nid} is not attached to an entity"


class TestSensorModel:
    def test_a_blind_sensor_never_reports(self, sim):
        """
        cam-vis cannot smell methane. If it reports on the atmosphere after the
        seep, the blindness model is not being applied and the disagreement
        rates are fiction.
        """
        for nid, d in sim.graph._g.nodes(data=True):
            meta = d.get("metadata", {})
            if meta.get("entity") != "atmosphere":
                continue
            if meta.get("ground_truth") == "trace methane":
                assert meta.get("sensor_id") != "sim:cam-vis"

    def test_reported_confidence_is_never_certainty(self, sim):
        confs = [
            d["metadata"]["confidence"] for _, d in sim.graph._g.nodes(data=True)
            if d.get("ntype") == NodeType.OBSERVATION
        ]
        assert confs
        assert max(confs) < 1.0
        assert min(confs) > 0.0

    def test_a_perfect_sensor_is_always_right(self, tmp_path):
        """Sanity check on the noise model itself, at its boundary."""
        scenario = Scenario(
            name="perfect", description="one flawless instrument",
            sensors=(SensorSpec("ideal", "manual", 1.0, confusions=("wrong",)),),
            states=(WorldState("thing", "true reading"),),
        )
        s = make_sim(tmp_path, scenario=scenario)
        s.run(ticks=10)

        b = s.history[-1].beliefs[0]
        assert b.belief == "true reading"
        assert s.history[-1].contradictions == 0

    def test_a_useless_sensor_produces_no_confident_belief(self, tmp_path):
        """The other boundary: pure noise must not look like understanding."""
        scenario = Scenario(
            name="noise", description="an instrument that is never right",
            sensors=(SensorSpec("broken", "manual", 0.0,
                                confusions=("junk a", "junk b", "junk c")),),
            states=(WorldState("thing", "true reading"),),
        )
        s = make_sim(tmp_path, scenario=scenario)
        s.run(ticks=20)

        assert s.history[-1].beliefs[0].belief != "true reading"
        assert s.report()["correct_beliefs"] == 0


class TestScenarioRegistry:
    def test_the_shipped_scenario_is_registered(self):
        assert SCENARIOS["stranded-site"] is STRANDED_SITE

    def test_scenario_covers_every_tick_it_claims_to(self):
        """A gap in the timeline would silently stop observations mid-run."""
        for entity in STRANDED_SITE.entities():
            for tick in range(0, 60):
                assert STRANDED_SITE.truth_at(entity, tick) is not None, (
                    f"{entity} has no ground truth at tick {tick}"
                )

    def test_report_on_an_unrun_simulation_is_honest(self, tmp_path):
        assert make_sim(tmp_path).report()["ticks"] == 0
