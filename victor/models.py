"""
Victor data models — v4

Changes from v3:
  - EpistemicStatus enum: MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS
  - importance_score + last_retrieved_at on all nodes (for weighted retrieval + temporal decay)
  - ConversationTurn dataclass (conversation memory as graph nodes)
  - RetrievedChunk gets epistemic_status field surfaced from graph
  - VictorAnswer unchanged (backward compat)
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import uuid


# ── Epistemic status hierarchy ────────────────────────────────────────────────

class EpistemicStatus(str, Enum):
    """
    Ordered trust hierarchy for knowledge nodes.
    MEASUREMENT is highest trust (directly observed).
    HYPOTHESIS is lowest (speculative).
    Used by EvidenceWeighter and surfaced in every answer.
    """
    MEASUREMENT = "measurement"   # directly observed data point — highest trust
    EXPERIMENT  = "experiment"    # controlled test result
    LITERATURE  = "literature"    # claim from a published paper
    NOTE        = "note"          # personal annotation or summary
    HYPOTHESIS  = "hypothesis"    # speculative, unverified — lowest trust

    @property
    def weight(self) -> float:
        """Numeric weight for evidence aggregation."""
        return {
            EpistemicStatus.MEASUREMENT: 1.0,
            EpistemicStatus.EXPERIMENT:  0.85,
            EpistemicStatus.LITERATURE:  0.70,
            EpistemicStatus.NOTE:        0.50,
            EpistemicStatus.HYPOTHESIS:  0.25,
        }[self]


# ── Node / Edge type constants ────────────────────────────────────────────────

class NodeType:
    PAPER        = "paper"
    CLAIM        = "claim"
    EXPERIMENT   = "experiment"
    NOTE         = "note"
    CONCEPT      = "concept"
    CONVERSATION = "conversation"   # Q&A session stored as graph node (Layer 5 Phase A)
    COMPUTED     = "computed"       # output of a ComputationKernel (e.g. StatisticsKernel)
    OBSERVATION  = "observation"    # raw sensor observation — EpistemicStatus.MEASUREMENT tier

class EdgeType:
    MAKES_CLAIM  = "makes_claim"    # paper/note → claim
    TESTED_BY    = "tested_by"      # claim      → experiment
    CONFIRMS     = "confirms"       # experiment → claim  (LLM-verified positive)
    CONTRADICTS  = "contradicts"    # experiment → claim  (LLM-verified negative)
    INCONCLUSIVE = "inconclusive"   # experiment → claim  (LLM could not determine)
    REFERENCES   = "references"     # note       → paper
    IMPLEMENTS   = "implements"     # experiment → concept
    RELATED_TO   = "related_to"     # concept    → concept
    CONTAINS     = "contains"       # paper/note → concept
    GROUNDED_IN  = "grounded_in"    # conversation → source nodes
    DERIVED_FROM = "derived_from"   # computed     → input nodes (StatisticsKernel etc.)
    SIMILAR_TO   = "similar_to"     # node         → node  (dedup candidate, not merged)


# ── Core data classes ─────────────────────────────────────────────────────────

@dataclass
class TextChunk:
    """A single chunk of text from any source, ready for embedding."""
    text:         str
    source_id:    str
    source_type:  str
    source_title: str
    chunk_index:  int
    word_start:   int          = 0
    word_end:     int          = 0
    chunk_id:     str          = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:    str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata:     Dict[str, Any] = field(default_factory=dict)

    def to_chroma_doc(self) -> Dict[str, Any]:
        return {
            "id":       self.chunk_id,
            "document": self.text,
            "metadata": {
                "source_id":    self.source_id,
                "source_type":  self.source_type,
                "source_title": self.source_title,
                "chunk_index":  self.chunk_index,
                "word_start":   self.word_start,
                "word_end":     self.word_end,
                "timestamp":    self.timestamp,
                **self.metadata,
            },
        }


@dataclass
class Claim:
    """A structured claim extracted from a paper or note."""
    text:         str
    source_id:    str
    source_title: str
    claim_type:   str          # quantitative | architectural | methodological
    claim_id:     str          = field(default_factory=lambda: str(uuid.uuid4()))
    metric:       Optional[str] = None
    value:        Optional[str] = None
    benchmark:    Optional[str] = None
    timestamp:    str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    chunk_id:       Optional[str] = None
    extracted_by:   Optional[str] = None
    low_confidence: bool          = False
    # v4: epistemic status on every claim
    epistemic_status: str = EpistemicStatus.LITERATURE.value


@dataclass
class Experiment:
    """A research experiment log ingested from a JSON file."""
    name:          str
    description:   str
    results:       Dict[str, Any]
    experiment_id: str          = field(default_factory=lambda: str(uuid.uuid4()))
    date:          Optional[str] = None
    model:         Optional[str] = None
    technique:     Optional[str] = None
    dataset:       Optional[str] = None
    notes:         Optional[str] = None
    claims_tested: List[str]    = field(default_factory=list)
    timestamp:     str          = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # v4: experiments always start at EXPERIMENT epistemic status
    epistemic_status: str = EpistemicStatus.EXPERIMENT.value


@dataclass
class ConversationTurn:
    """
    A single Q&A session stored as a node in the knowledge graph.
    Phase A of self-learning: the graph grows from usage, not just ingestion.
    """
    query:          str
    answer:         str
    provider_used:  str
    source_ids:     List[str]   = field(default_factory=list)
    turn_id:        str         = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:      str         = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    query_embedding: Optional[List[float]] = None


@dataclass
class RetrievedChunk:
    """A chunk returned by the hybrid retriever, with provenance."""
    text:             str
    source_id:        str
    source_type:      str
    source_title:     str
    chunk_index:      int
    score:            float
    provenance:       List[str] = field(default_factory=list)
    # v4: epistemic status surfaced from graph node
    epistemic_status: str       = EpistemicStatus.LITERATURE.value


@dataclass
class VictorAnswer:
    """What Victor returns after a query."""
    answer:             str
    retrieved_chunks:   List[RetrievedChunk]
    provenance_summary: str
    provider_used:  str  = "none"
    no_context:     bool = False
    cited_sources:  List[str] = field(default_factory=list)


# ── Evidence aggregation result ───────────────────────────────────────────────

@dataclass
class ClaimEvidenceSummary:
    """
    Output of EvidenceWeighter for a single claim.
    Surfaced in answers and graph-search output.
    """
    claim_id:         str
    claim_text:       str
    epistemic_status: str
    confidence:       float          # 0.0 – 1.0, weighted aggregate
    n_confirms:       int
    n_contradicts:    int
    n_inconclusive:   int
    supporting_experiments:  List[str] = field(default_factory=list)
    conflicting_experiments: List[str] = field(default_factory=list)
    gap:              bool = False    # True if no experimental confirmation exists


@dataclass
class IngestResult:
    """
    Unified return type for every IngestorBase subclass.

    Lets core.py file the result into the graph + vector store generically,
    regardless of source type — this is what makes IngestorBase a real plugin
    interface instead of three parallel hand-wired code paths.
    """
    source_id:   str
    node_type:   str              # NodeType.PAPER | NOTE | EXPERIMENT | ...
    title:       str
    chunks:      List[TextChunk]  = field(default_factory=list)
    claims:      List[Claim]      = field(default_factory=list)
    concepts:    List[str]        = field(default_factory=list)
    experiment:  Optional[Experiment] = None


@dataclass
class ObservationResult:
    """
    Output of a StreamIngestor — a sensor observation with all 6 Epistemic
    Artifact properties pre-populated.  Enters the graph as a MEASUREMENT node
    via graph.add_observation().

    The six properties (from VICTOR_THEORY_v1):
      1. Origin      — sensor_type, sensor_id, model_used, session_id, timestamp
      2. Type        — epistemic_status = MEASUREMENT (always, for sensor data)
      3. Confidence  — model confidence or 1.0 for manual observations
      4. Contradictions — empty at creation; filled by ConflictDetector later
      5. Gaps        — what needs verification before this can be trusted
      6. Age         — timestamp (ISO) + decay_status
    """
    # 1. Origin
    sensor_type:  str             # "camera" | "audio" | "manual"
    sensor_id:    str             # device string, e.g. "camera:0" or "file:photo.jpg"
    model_used:   str             # classifier model name, or "manual"
    session_id:   str             # groups observations from the same session

    # 2. Type
    epistemic_status: str = EpistemicStatus.MEASUREMENT.value

    # 3. Confidence
    label:       str   = ""       # human-readable classification
    confidence:  float = 0.0      # 0.0–1.0; model confidence or user-supplied

    # 4. Contradictions — empty list at creation
    contradictions: List[str] = field(default_factory=list)

    # 5. Gaps — auto-populated from sensor type; researcher can extend
    gaps: List[str] = field(default_factory=list)

    # 6. Age
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    decay_status: str = "active"

    # Provenance extras
    observation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    image_path:     Optional[str] = None   # path to saved image for provenance
    metadata:       Dict[str, Any] = field(default_factory=dict)

    def to_label(self) -> str:
        """Short human-readable label for graph display."""
        date_part = self.timestamp[:10]
        return f"[{self.sensor_type}] {self.label} ({date_part})"


@dataclass
class ConflictResult:
    """Output of ConflictDetector for a single experiment→claim pair."""
    direction:   str    # "confirm" | "contradict" | "inconclusive"
    confidence:  float  # 0.0 – 1.0
    reason:      str
    raw_response: str = ""
