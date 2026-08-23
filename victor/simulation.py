"""
Sensor simulation — Victor inside a machine, with the understanding made visible.

Why this exists
---------------
VICTOR_CANON describes Victor as a physical research device: "a person alone,
who needs to understand their environment to survive." Only the software brain
exists. sensors.py can already turn a camera frame into a MEASUREMENT-tier
artifact, but nothing in the project ever ran that loop for longer than one
frame, so the claims that depend on *accumulation* were never observable:

  * compounding — value scales with connection density, not artifact count
  * contradiction — disagreeing sensors should produce a visible conflict
  * gaps — an unverified reading should stay marked unverified
  * masking — a sensitive reading should be withheld by default, not opt-in

This module runs the loop. A seeded scenario drives simulated sensors that
disagree with each other at known rates, feeds their observations into a real
VictorKnowledgeGraph, and emits a per-tick telemetry record showing what Victor
currently believes about each entity and how strongly. Watching `belief` firm up
while `margin` widens is the point: it is the compounding thesis as something
you can look at rather than assert.

Nothing here touches hardware, the network, or an LLM. Same seed, same run.

    victor simulate --scenario stranded-site --ticks 40

Relationship to sensors.py: SimulatedSensor implements the same
StreamIngestorBase contract as CameraIngestor, and its output goes through the
same graph.add_observation() path. The simulation is not a mock of Victor — it
is Victor, driven by a synthetic world.
"""
from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import EdgeType, EpistemicStatus, NodeType, ObservationResult
from .sensors import StreamIngestorBase

logger = logging.getLogger(__name__)


# ── Scenario description ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SensorSpec:
    """
    One instrument bolted to the machine.

    `reliability` is the probability it reports the true state. `confusions`
    lists the readings it mistakes the truth for — a thermal camera confusing
    "structural crack" with "surface stain" is a specific, plausible error,
    and modelling it that way produces contradictions Victor can actually
    reason about instead of uniform noise.
    """

    name: str
    sensor_type: str
    reliability: float
    confusions: Tuple[str, ...] = ()
    # Readings this sensor is not equipped to make at all.
    blind_to: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WorldState:
    """Ground truth for one entity over a span of ticks."""

    entity: str
    truth: str
    from_tick: int = 0
    to_tick: int = 10_000
    note: str = ""


@dataclass(frozen=True)
class Scenario:
    name: str
    description: str
    sensors: Tuple[SensorSpec, ...]
    states: Tuple[WorldState, ...]
    # Readings that must not be published in the clear. The original framing in
    # VICTOR_ORIGINAL.md makes masking memory's default posture; here it finally
    # is one, for the class of readings where the stakes are real.
    sensitive: frozenset = frozenset()
    tick_seconds: int = 60

    def entities(self) -> List[str]:
        seen: List[str] = []
        for s in self.states:
            if s.entity not in seen:
                seen.append(s.entity)
        return seen

    def truth_at(self, entity: str, tick: int) -> Optional[WorldState]:
        for s in self.states:
            if s.entity == entity and s.from_tick <= tick <= s.to_tick:
                return s
        return None


# ── The built-in scenario ─────────────────────────────────────────────────────

STRANDED_SITE = Scenario(
    name="stranded-site",
    description=(
        "A survey unit alone at a remote site with no uplink. Four instruments "
        "of differing reliability watch four things that matter: the air, the "
        "structure sheltering the operator, the power reserve, and a sample "
        "whose composition is commercially sensitive. Two of the four change "
        "state partway through, so the run shows Victor revising a belief and "
        "not merely accumulating agreement."
    ),
    sensors=(
        SensorSpec("cam-vis", "camera", 0.82,
                   confusions=("surface stain", "shadow artefact"),
                   blind_to=("trace methane", "cell degradation")),
        SensorSpec("cam-thermal", "camera", 0.74,
                   confusions=("thermal bloom", "surface stain"),
                   blind_to=("trace methane",)),
        SensorSpec("mic-array", "audio", 0.68,
                   confusions=("wind loading", "equipment hum"),
                   blind_to=("surface stain", "palladium-rich matrix")),
        SensorSpec("spectrometer", "manual", 0.94,
                   confusions=("inconclusive spectrum",)),
    ),
    states=(
        WorldState("atmosphere", "breathable", 0, 17,
                   note="Nominal at arrival."),
        WorldState("atmosphere", "trace methane", 18, 10_000,
                   note="Seep begins at tick 18 — the belief must flip."),
        WorldState("shelter-north", "structural crack", 0, 10_000,
                   note="Present from the start; low-reliability sensors argue."),
        WorldState("power-cell", "nominal charge", 0, 25,
                   note="Holding."),
        WorldState("power-cell", "cell degradation", 26, 10_000,
                   note="Degrades late — little evidence accrues before the run ends."),
        WorldState("sample-07", "palladium-rich matrix", 0, 10_000,
                   note="Commercially sensitive. Masked on arrival, not after."),
    ),
    sensitive=frozenset({"palladium-rich matrix"}),
)

SCENARIOS: Dict[str, Scenario] = {STRANDED_SITE.name: STRANDED_SITE}


# ── Simulated sensor ──────────────────────────────────────────────────────────


class SimulatedSensor(StreamIngestorBase):
    """
    A StreamIngestorBase that reads from a scenario instead of hardware.

    Deliberately implements the real interface: the observations it produces
    travel the same add_observation() path as a webcam's, so a bug in that path
    fails here too. A simulation that used a private shortcut would prove
    nothing about the code that ships.
    """

    def __init__(self, spec: SensorSpec, rng: random.Random) -> None:
        self.spec = spec
        self.sensor_type = spec.sensor_type
        self._rng = rng

    def can_observe(self, truth: str) -> bool:
        return truth not in self.spec.blind_to

    def observe(
        self,
        *,
        candidate_labels: List[str],
        save_dir: Path,
        extra_gaps: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ObservationResult:
        truth = candidate_labels[0]
        correct = self._rng.random() < self.spec.reliability

        if correct or not self.spec.confusions:
            label = truth
            # Confidence tracks reliability but is never certainty — a sensor
            # that reports 1.0 is a sensor whose confidence carries no
            # information, and the whole evidence-weighting stack downstream
            # depends on that number meaning something.
            conf = min(0.99, self._rng.gauss(self.spec.reliability, 0.06))
        else:
            label = self._rng.choice(self.spec.confusions)
            # A wrong reading that announces itself as wrong would be easy.
            # Real misclassifications arrive confident, so these do too.
            conf = min(0.95, max(0.35, self._rng.gauss(self.spec.reliability - 0.1, 0.10)))

        return ObservationResult(
            sensor_type=self.spec.sensor_type,
            sensor_id=f"sim:{self.spec.name}",
            model_used=f"simulated/{self.spec.name}",
            session_id=session_id or "sim",
            epistemic_status=EpistemicStatus.MEASUREMENT.value,
            label=label,
            confidence=round(max(0.0, min(1.0, conf)), 3),
            gaps=list(extra_gaps or []),
            metadata=dict(metadata or {}),
        )


# ── Telemetry ─────────────────────────────────────────────────────────────────


@dataclass
class Belief:
    """What Victor currently thinks about one entity, and how firmly."""

    entity: str
    belief: str
    support: float           # summed confidence behind the winning reading
    margin: float            # lead over the runner-up, 0.0 when tied
    observations: int
    correct: bool
    masked: bool = False

    # What a masked belief publishes instead of the reading.
    WITHHELD = "████ withheld"

    def as_dict(self) -> Dict[str, Any]:
        """
        Serialised form — masked beliefs do not carry their reading.

        `belief` stays readable on the dataclass so in-process scoring can
        check it against ground truth, but the moment this leaves the process
        the withheld reading has to be withheld. The CLI already redacted at
        print time; that is the wrong layer, because anything else that
        serialises a report — a log line, an API response, a saved run — would
        publish the very reading the mask exists to protect.
        """
        return {
            "entity": self.entity,
            "belief": self.WITHHELD if self.masked else self.belief,
            "support": round(self.support, 3),
            "margin": round(self.margin, 3),
            "observations": self.observations,
            "correct": self.correct,
            "masked": self.masked,
        }


@dataclass
class Tick:
    tick: int
    nodes: int
    edges: int
    density: float
    observations: int
    masked: int
    contradictions: int
    beliefs: List[Belief] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "tick": self.tick,
            "nodes": self.nodes,
            "edges": self.edges,
            "density": round(self.density, 3),
            "observations": self.observations,
            "masked": self.masked,
            "contradictions": self.contradictions,
            "beliefs": [b.as_dict() for b in self.beliefs],
        }


# ── The run loop ──────────────────────────────────────────────────────────────


class Simulation:
    """
    Drives a Scenario against a real VictorKnowledgeGraph.

    The graph is injected rather than constructed so the same run can either
    populate a throwaway graph for a demo or write into the user's actual
    knowledge base — the caller decides, and `victor simulate` defaults to a
    separate directory so a demo never contaminates real work.
    """

    # How many recent readings a new observation is cross-checked against.
    # Bounds edge growth at O(n) instead of O(n^2) — see _link_to_prior.
    CROSS_CHECK_WINDOW = 6

    # Ticks for a reading's weight in the belief vote to halve. Short enough
    # that a scripted world change is detected within a few ticks, long enough
    # that one noisy sensor cannot flip a settled belief on its own.
    BELIEF_HALF_LIFE = 6

    def __init__(
        self,
        graph,
        scenario: Scenario = STRANDED_SITE,
        seed: int = 7,
        save_dir: Optional[Path] = None,
    ) -> None:
        self.graph = graph
        self.scenario = scenario
        self.seed = seed
        self.save_dir = save_dir or Path.cwd() / ".victor_sim_frames"
        self._rng = random.Random(seed)
        self.sensors = [SimulatedSensor(s, self._rng) for s in scenario.sensors]
        self.session_id = f"sim-{scenario.name}-{seed}"
        self.history: List[Tick] = []

        # entity -> [(node_id, reading, confidence, tick)], in arrival order
        self._evidence: Dict[str, List[Tuple[str, str, float, int]]] = {}
        self._entity_nodes: Dict[str, str] = {}
        self._contradictions = 0
        self._masked = 0
        self._t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

    # ── graph wiring ──────────────────────────────────────────────────────────

    def _entity_node(self, entity: str) -> str:
        """One CONCEPT node per thing being observed; observations hang off it."""
        if entity not in self._entity_nodes:
            nid = f"entity::{entity}"
            self.graph.add_node(
                nid,
                NodeType.CONCEPT,
                f"{entity} (monitored entity)",
                metadata={"simulation": self.scenario.name, "entity": entity},
            )
            self._entity_nodes[entity] = nid
        return self._entity_nodes[entity]

    def _link_to_prior(
        self, entity: str, reading: str, node_id: str, conf: float, tick: int
    ) -> int:
        """
        Cross-check the new observation against recent readings of the same
        entity. Agreement becomes CONFIRMS, disagreement CONTRADICTS.

        Bounded to the last CROSS_CHECK_WINDOW readings on purpose. Linking to
        all history builds a clique: a 30-tick run produced 22,797 edges over
        426 nodes and a "density" of 53, which looks like a spectacular result
        and measures nothing but n². Comparing a reading against the recent
        record is also what an instrument actually does. With the window,
        density converges on the window size and a *change* in it means
        something.
        """
        made = 0
        recent = self._evidence.setdefault(entity, [])
        for other_id, other_reading, other_conf, _ in recent[-self.CROSS_CHECK_WINDOW:]:
            etype = EdgeType.CONFIRMS if other_reading == reading else EdgeType.CONTRADICTS
            self.graph.add_edge(
                node_id, other_id, etype,
                {"confidence": round(min(conf, other_conf), 3),
                 "reason": f"simulated cross-check on {entity}"},
            )
            made += 1
            if etype == EdgeType.CONTRADICTS:
                self._contradictions += 1
        recent.append((node_id, reading, conf, tick))
        return made

    def _beliefs(self, tick: int) -> List[Belief]:
        """
        Confidence-weighted vote with an exponential recency half-life.

        A plain cumulative sum cannot revise: in an earlier version the air
        stayed "breathable" for twelve ticks after the methane seep began,
        because four hundred stale observations outvoted the new ones. Evidence
        about a world that changes has to lose weight with age, or the machine
        is confidently reporting the past.

        This mirrors the graph's own temporal decay rather than reusing it —
        apply_temporal_decay works in days and adjusts retrieval importance,
        which is a different question from "what is true right now".
        """
        out = []
        for entity in self.scenario.entities():
            recent = self._evidence.get(entity, [])
            if not recent:
                continue

            totals: Dict[str, float] = {}
            for _, reading, conf, seen_at in recent:
                weight = 0.5 ** ((tick - seen_at) / self.BELIEF_HALF_LIFE)
                totals[reading] = totals.get(reading, 0.0) + conf * weight

            ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
            top, support = ranked[0]
            runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
            state = self.scenario.truth_at(entity, tick)
            out.append(Belief(
                entity=entity,
                belief=top,
                support=support,
                margin=support - runner_up,
                observations=len(recent),
                correct=bool(state and top == state.truth),
                masked=top in self.scenario.sensitive,
            ))
        return out

    # ── the loop ──────────────────────────────────────────────────────────────

    def run(self, ticks: int = 40, on_tick=None) -> List[Tick]:
        """
        Advance the world `ticks` times. Returns the telemetry history.

        `on_tick(Tick)` is called after each step so a caller can render live
        without this module importing a UI.
        """
        for t in range(ticks):
            made = 0
            for entity in self.scenario.entities():
                state = self.scenario.truth_at(entity, t)
                if state is None:
                    continue
                entity_nid = self._entity_node(entity)

                for sensor in self.sensors:
                    if not sensor.can_observe(state.truth):
                        continue

                    obs = sensor.observe(
                        candidate_labels=[state.truth],
                        save_dir=self.save_dir,
                        session_id=self.session_id,
                        extra_gaps=[f"Unconfirmed by a second modality at tick {t}"],
                        metadata={
                            "simulation": self.scenario.name,
                            "entity": entity,
                            "tick": t,
                            "ground_truth": state.truth,
                        },
                    )
                    # A simulated clock, not the wall clock: reruns must be
                    # byte-identical, and temporal decay needs spacing anyway.
                    obs.timestamp = (
                        self._t0 + timedelta(seconds=t * self.scenario.tick_seconds)
                    ).isoformat()

                    nid = self.graph.add_observation(obs)
                    self.graph.add_edge(nid, entity_nid, EdgeType.CONTAINS)
                    made += 1

                    # Masking happens at arrival, before the reading has ever
                    # been retrievable — the "default posture" the original
                    # framing asked for, rather than a later declassification.
                    if obs.label in self.scenario.sensitive:
                        self.graph.mask_node(nid)
                        self._masked += 1

                    self._link_to_prior(entity, obs.label, nid, obs.confidence, t)

            n = self.graph._g.number_of_nodes()
            e = self.graph._g.number_of_edges()
            snap = Tick(
                tick=t,
                nodes=n,
                edges=e,
                density=(e / n) if n else 0.0,
                observations=made,
                masked=self._masked,
                contradictions=self._contradictions,
                beliefs=self._beliefs(t),
            )
            self.history.append(snap)
            if on_tick:
                on_tick(snap)
        return self.history

    # ── reporting ─────────────────────────────────────────────────────────────

    def fragments(self, per_entity: int = 1) -> List["Fragment"]:
        """
        The freshest readings, as referral fragments.

        This is the join between the simulation and `victor.referral`: what the
        machine is seeing right now, offered into the same table as what it has
        stored, competing on the same properties. A reading of a sensitive
        reading is masked on arrival, so it reaches the table as a handle with
        no content -- the machine can see that a live observation exists and is
        relevant, ask for it, and be refused.

        Ordered newest-first so a caller taking the first N gets the current
        picture rather than the start of the run.
        """
        from .referral import Fragment

        out: List[Fragment] = []
        for entity, evidence in self._evidence.items():
            for node_id, reading, conf, tick in sorted(
                evidence, key=lambda e: e[3], reverse=True
            )[:max(1, per_entity)]:
                out.append(Fragment(
                    fragment_id=node_id,
                    text=f"{entity}: {reading}",
                    source=f"sim:{self.scenario.name}@t{tick}",
                    confidence=conf,
                    masked=reading in self.scenario.sensitive,
                    epistemic_status=EpistemicStatus.MEASUREMENT.value,
                ))
        out.sort(key=lambda f: f.confidence, reverse=True)
        return out

    def report(self) -> Dict[str, Any]:
        """A scoreable summary — what the run demonstrated, in numbers."""
        if not self.history:
            return {"scenario": self.scenario.name, "ticks": 0}

        last = self.history[-1]
        beliefs = last.beliefs
        settled = [b for b in beliefs if b.margin > 0]
        return {
            "scenario": self.scenario.name,
            "seed": self.seed,
            "ticks": len(self.history),
            "nodes": last.nodes,
            "edges": last.edges,
            "density_start": round(self.history[0].density, 3),
            "density_end": round(last.density, 3),
            "contradictions": last.contradictions,
            "masked": last.masked,
            "entities": len(beliefs),
            "correct_beliefs": sum(1 for b in beliefs if b.correct),
            # Unsettled entities are the honest part of the score: an entity
            # whose belief is tied has not been understood, and reporting it as
            # a win is how simulations start lying.
            "unsettled": len(beliefs) - len(settled),
            "beliefs": [b.as_dict() for b in beliefs],
        }
