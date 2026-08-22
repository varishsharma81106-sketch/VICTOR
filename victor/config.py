"""
Victor configuration — v4

Defines VictorConfig, the settings object `victor/core.py` imports lazily via:

    from config import DEFAULT_CONFIG

Every attribute referenced anywhere in the v4 modules is defined here:
  embedding_model, vector_db_dir, graph_file, ollama_base_url, ollama_model,
  openai_model, openai_api_url, use_mock_llm, llm_timeout, llm_log_file,
  extraction_log_file, chunk_size_words, chunk_overlap_words, top_k_vectors,
  graph_hop_depth, claim_similarity_threshold, extract_claims_by_default,
  extraction_max_chunks, plus the ensure_dirs() method.

All storage paths default to a single VICTOR_HOME directory (default
~/.victor, override with the VICTOR_HOME env var or by constructing your
own VictorConfig) so the whole knowledge base — vector DB, graph, logs —
lives in one place that's easy to back up, sync, or wipe.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _default_home() -> Path:
    return Path(os.environ.get("VICTOR_HOME", str(Path.home() / ".victor")))


@dataclass
class VictorConfig:
    # ── Storage root ──────────────────────────────────────────────────────────
    home_dir: Path = field(default_factory=_default_home)

    # Derived paths — leave as None to default to a subpath of home_dir,
    # or set explicitly to put the vector DB / graph / logs somewhere else
    # (e.g. a faster disk for vector_db_dir).
    vector_db_dir:       Optional[Path] = None
    graph_file:          Optional[Path] = None
    llm_log_file:        Optional[Path] = None
    extraction_log_file: Optional[Path] = None
    unmask_audit_log_file: Optional[Path] = None

    # ── Embedding ─────────────────────────────────────────────────────────────
    # v4.3: target is nomic-embed-text-v1.5 (PRD spec) with Qwen3-Embedding-small
    # as the alternative to benchmark before committing (field research, June 2026:
    # Qwen3-Embedding-8B #1 on MTEB multilingual; the small variant shares the
    # qwen2.5:7b architecture family already used for inference). LocalEmbedder
    # tries embedding_model first, then embedding_model_fallback chain, in order,
    # so a machine without network/model access still works fully offline.
    embedding_model:          str  = "nomic-embed-text-v1.5"
    embedding_model_fallback: tuple = ("all-MiniLM-L6-v2",)

    # ── Chunking ──────────────────────────────────────────────────────────────
    chunk_size_words:    int = 300
    chunk_overlap_words: int = 50

    # ── Retrieval ─────────────────────────────────────────────────────────────
    top_k_vectors:   int = 8
    graph_hop_depth: int = 2

    # ── Claim extraction ──────────────────────────────────────────────────────
    extract_claims_by_default:  bool           = True
    extraction_max_chunks:      Optional[int]  = None   # None = no limit, extract on every chunk
    claim_similarity_threshold: float          = 0.75

    # ── Inference backend (DoD item #5 — provider-agnostic InferenceClient) ───
    # "ollama" | "llama_cpp" | "mlx". Constructed via llm.create_inference_client().
    inference_backend:    str           = "ollama"
    llama_cpp_model_path: Optional[str] = None
    mlx_model_path:       Optional[str] = None

    # ── LLM provider chain (Ollama → OpenAI → mock) ───────────────────────────
    ollama_base_url: str  = "http://localhost:11434"
    ollama_model:    str  = "qwen2.5:7b"          # was phi3:mini (3.8B); qwen2.5:7b Q4_K_M ≈5GB
    openai_model:    str  = "gpt-4o-mini"
    openai_api_url:  str  = "https://api.openai.com/v1/chat/completions"
    use_mock_llm:     bool = False
    use_mock_embedder: bool = False   # skip HuggingFace load in tests/offline envs
    llm_timeout:     int  = 60

    # Sampling temperature for every LLM call that doesn't override it.
    # Previously unset on the Ollama path, which meant Victor silently inherited
    # Ollama's server default of 0.8 — far too hot for the three-way
    # confirm/contradict/inconclusive judgment ConflictDetector makes, while the
    # OpenAI path was hardcoded to 0.1. Judgments now default to near-greedy on
    # both backends; callers that genuinely want sampling diversity (e.g.
    # self-consistency voting) pass temperature= explicitly per call.
    llm_temperature: float = 0.1

    # ── Agent loop budget (read by AgenticRetriever via getattr) ──────────────
    agent_max_tool_calls:     int = 5
    agent_max_context_tokens: int = 8000

    # ── NLI cross-encoder (agreement-bias cross-check in ConflictDetector) ──────
    # When True, ConflictDetector.judge() runs the cross-encoder after the LLM
    # call. If LLM says confirm/inconclusive but the cross-encoder predicts
    # contradiction with confidence > nli_override_threshold, the judgment is
    # overridden to "contradict". Set False to skip the model entirely (e.g.
    # offline / low-disk environments) or use_mock_nli to inject a test double.
    use_nli_crossencoder:    bool  = True
    use_mock_nli:            bool  = False   # inject MockNLICrossEncoder in tests
    nli_model:               str   = "cross-encoder/nli-deberta-v3-base"
    nli_override_threshold:  float = 0.5    # min cross-encoder confidence to override

    # ── Node deduplication (background maintenance, not yet in any PRD version) ─
    dedup_similarity_threshold: float = 0.92

    def __post_init__(self):
        self.home_dir = Path(self.home_dir)

        if self.vector_db_dir is None:
            self.vector_db_dir = self.home_dir / "vector_db"
        if self.graph_file is None:
            self.graph_file = self.home_dir / "graph" / "knowledge_graph.json"
        if self.llm_log_file is None:
            self.llm_log_file = self.home_dir / "logs" / "llm_calls.jsonl"
        if self.extraction_log_file is None:
            self.extraction_log_file = self.home_dir / "logs" / "extraction_log.jsonl"
        if self.unmask_audit_log_file is None:
            self.unmask_audit_log_file = self.home_dir / "logs" / "unmask_audit.jsonl"

        # Normalize in case any were passed in as strings
        self.vector_db_dir         = Path(self.vector_db_dir)
        self.graph_file            = Path(self.graph_file)
        self.llm_log_file          = Path(self.llm_log_file)
        self.extraction_log_file   = Path(self.extraction_log_file)
        self.unmask_audit_log_file = Path(self.unmask_audit_log_file)

    def ensure_dirs(self) -> None:
        """Create every directory Victor needs before first use. Called by Victor.__init__."""
        self.vector_db_dir.mkdir(parents=True, exist_ok=True)
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)
        self.llm_log_file.parent.mkdir(parents=True, exist_ok=True)
        self.extraction_log_file.parent.mkdir(parents=True, exist_ok=True)
        self.unmask_audit_log_file.parent.mkdir(parents=True, exist_ok=True)


# Module-level instance — what `from config import DEFAULT_CONFIG` actually imports.
DEFAULT_CONFIG = VictorConfig()
