"""
Ingestors — one class per source type.

PDFIngestor        : research papers, technical documents
MarkdownIngestor   : personal notes, research summaries
ExperimentIngestor : W&B-style experiment JSON logs

F-004 fix: claim extraction runs per-chunk (_extract_per_chunk),
not once on a hard-truncated prefix of the whole document.

v4.3 — IngestorBase (DoD item #7):
  Every ingestor now subclasses IngestorBase and returns a single
  IngestResult dataclass instead of a bespoke tuple per class. core.py's
  ingest_file() dispatches by file extension through INGESTOR_REGISTRY
  instead of hardcoded if/elif branches per source type.

  Adding a new source type (e.g. a future CSVIngestor for raw sensor logs,
  Phase 2 hardware) means:
    1. Write a class that subclasses IngestorBase and sets `extensions`
    2. Append an entry to INGESTOR_REGISTRY
  No changes to core.py's dispatch logic are needed — that loop already
  iterates the registry generically.
"""
import json
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Tuple, List, Optional, ClassVar, Type

from .models import TextChunk, Claim, Experiment, NodeType, IngestResult
from .chunker import TextChunker
from .extractor import ClaimExtractor


def _extract_per_chunk(
    extractor:    ClaimExtractor,
    chunks:       List[TextChunk],
    source_id:    str,
    source_title: str,
    max_chunks:   Optional[int],
) -> Tuple[List[Claim], List[str]]:
    """
    Runs ClaimExtractor.extract() against every chunk individually.
    Concepts are deduplicated case-insensitively across chunks.
    """
    all_claims:   List[Claim] = []
    seen_concepts: dict        = {}

    target = chunks if max_chunks is None else chunks[:max_chunks]

    for chunk in target:
        c_claims, c_concepts = extractor.extract(
            chunk.text, source_id, source_title, chunk_id=chunk.chunk_id,
        )
        all_claims.extend(c_claims)
        for concept in c_concepts:
            key = concept.strip().lower()
            if key and key not in seen_concepts:
                seen_concepts[key] = concept.strip()

    return all_claims, list(seen_concepts.values())


class IngestorBase(ABC):
    """
    Plugin interface for every source type Victor can ingest.

    extensions: file suffixes this ingestor claims, e.g. (".pdf",).
                core.py's registry is keyed on these — that's the whole
                dispatch mechanism. No type-checking elsewhere.
    """
    extensions: ClassVar[Tuple[str, ...]] = ()

    @abstractmethod
    def ingest(self, filepath: Path, title: Optional[str] = None) -> IngestResult:
        ...


class PDFIngestor(IngestorBase):
    extensions: ClassVar[Tuple[str, ...]] = (".pdf",)

    def __init__(
        self,
        chunker:               TextChunker,
        extractor:             ClaimExtractor,
        extract_claims:        bool          = True,
        max_extraction_chunks: Optional[int] = None,
    ):
        self.chunker               = chunker
        self.extractor             = extractor
        self.extract_claims        = extract_claims
        self.max_extraction_chunks = max_extraction_chunks

    def ingest(self, filepath: Path, title: Optional[str] = None) -> IngestResult:
        text = self._extract_text(filepath)
        if not text.strip():
            raise ValueError(f"No text extracted from {filepath}")

        source_id    = str(uuid.uuid5(uuid.NAMESPACE_URL, str(filepath)))
        source_title = title or filepath.stem

        chunks = self.chunker.chunk(
            text, source_id, NodeType.PAPER, source_title,
            extra_metadata={"filepath": str(filepath)},
        )

        claims:   List[Claim] = []
        concepts: List[str]   = []

        if self.extract_claims:
            claims, concepts = _extract_per_chunk(
                self.extractor, chunks, source_id, source_title,
                self.max_extraction_chunks,
            )

        return IngestResult(
            source_id=source_id, node_type=NodeType.PAPER, title=source_title,
            chunks=chunks, claims=claims, concepts=concepts,
        )

    @staticmethod
    def _extract_text(filepath: Path) -> str:
        try:
            import fitz
            doc  = fitz.open(str(filepath))
            text = "\n".join(page.get_text() for page in doc)
            doc.close()
            return text
        except ImportError:
            pass

        try:
            import pdfplumber
            with pdfplumber.open(str(filepath)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except ImportError:
            pass

        raise ImportError(
            "PDF extraction requires PyMuPDF or pdfplumber.\n"
            "  pip install pymupdf   (recommended)\n"
            "  pip install pdfplumber"
        )


class MarkdownIngestor(IngestorBase):
    extensions: ClassVar[Tuple[str, ...]] = (".md", ".txt", ".rst")

    def __init__(
        self,
        chunker:               TextChunker,
        extractor:             ClaimExtractor,
        extract_claims:        bool          = True,
        max_extraction_chunks: Optional[int] = None,
    ):
        self.chunker               = chunker
        self.extractor             = extractor
        self.extract_claims        = extract_claims
        self.max_extraction_chunks = max_extraction_chunks

    def ingest(self, filepath: Path, title: Optional[str] = None) -> IngestResult:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            raise ValueError(f"Empty file: {filepath}")

        source_id    = str(uuid.uuid5(uuid.NAMESPACE_URL, str(filepath)))
        source_title = title or filepath.stem

        chunks = self.chunker.chunk(
            text, source_id, NodeType.NOTE, source_title,
            extra_metadata={"filepath": str(filepath)},
        )

        claims:   List[Claim] = []
        concepts: List[str]   = []

        if self.extract_claims:
            claims, concepts = _extract_per_chunk(
                self.extractor, chunks, source_id, source_title,
                self.max_extraction_chunks,
            )

        return IngestResult(
            source_id=source_id, node_type=NodeType.NOTE, title=source_title,
            chunks=chunks, claims=claims, concepts=concepts,
        )


class ExperimentIngestor(IngestorBase):
    """
    Expects a JSON file with this schema (all fields optional except name):
    {
        "name":          "my_experiment",
        "description":   "What this tests",
        "date":          "YYYY-MM-DD",
        "model":         "model name",
        "technique":     "training technique",
        "dataset":       "dataset used",
        "results":       {"metric_name": 0.0},
        "notes":         "anything worth remembering",
        "claims_tested": ["Exact or approximate claim from a paper you tested"]
    }
    """
    extensions: ClassVar[Tuple[str, ...]] = (".json",)

    def __init__(self, chunker: TextChunker):
        self.chunker = chunker

    def ingest(self, filepath: Path, title: Optional[str] = None) -> IngestResult:
        raw = json.loads(filepath.read_text(encoding="utf-8"))

        exp = Experiment(
            name          = raw["name"],
            description   = raw.get("description", ""),
            results       = raw.get("results", {}),
            date          = raw.get("date"),
            model         = raw.get("model"),
            technique     = raw.get("technique"),
            dataset       = raw.get("dataset"),
            notes         = raw.get("notes"),
            claims_tested = raw.get("claims_tested", []),
        )

        parts = [f"Experiment: {exp.name}", f"Description: {exp.description}"]
        if exp.model:
            parts.append(f"Model: {exp.model}")
        if exp.technique:
            parts.append(f"Technique: {exp.technique}")
        if exp.results:
            parts.append("Results: " + ", ".join(f"{k}={v}" for k, v in exp.results.items()))
        if exp.notes:
            parts.append(f"Notes: {exp.notes}")
        if exp.claims_tested:
            parts.append("Claims tested: " + "; ".join(exp.claims_tested))

        full_text = "\n".join(parts)
        chunks = self.chunker.chunk(
            full_text, exp.experiment_id, NodeType.EXPERIMENT, exp.name,
            extra_metadata={"filepath": str(filepath)},
        )
        return IngestResult(
            source_id=exp.experiment_id, node_type=NodeType.EXPERIMENT,
            title=exp.name, chunks=chunks, experiment=exp,
        )


# ── Registry — the whole point of IngestorBase ───────────────────────────────
# core.py builds instances of these and dispatches by file extension. Adding a
# new source type means adding one entry here, not editing dispatch logic.
INGESTOR_REGISTRY: List[Type[IngestorBase]] = [
    PDFIngestor,
    MarkdownIngestor,
    ExperimentIngestor,
]


EXPERIMENT_SCHEMA = {
    "name":          "my_experiment_name",
    "description":   "What this experiment tests",
    "date":          "YYYY-MM-DD",
    "model":         "model name (optional)",
    "technique":     "training technique (optional)",
    "dataset":       "dataset used (optional)",
    "results":       {"metric_name": 0.0},
    "notes":         "anything worth remembering (optional)",
    "claims_tested": ["Exact or approximate text of a claim from a paper you tested"],
}
