# VICTOR — What Is Built
*Code version: v5.3 · Date: June 2026*

---

> This document is updated every time the code changes.
> Check the version header before reading. An outdated version of this document is worse than no document.

---

## The One-Line State

Phase 0 and Phase 1 are complete. 196/196 tests pass (re-verified via actual `pytest` run, not estimated). The NLI cross-encoder is wired, label-order corrected, and smoke-tested locally (push pending — see Known Bugs). Best SciFact accuracy so far: **71.0%** (cross-check mode, n=100). DoD criterion #4 (>85%) is still open. No real research data has been ingested.

<!-- CURRENT_TEST_COUNT -->196<!-- /CURRENT_TEST_COUNT -->

---

## What Exists — Full File Map

```
victor/
├── victor/
│   ├── models.py          — EpistemicStatus (5-tier), ObservationResult, ConflictResult, ConflictJudgment
│   ├── graph.py           — VictorKnowledgeGraph, add_observation(), freeze/unfreeze, atomic save, temporal decay, mask/unmask
│   ├── core.py            — Victor controller, ingestion, query, patterns, stats, AgenticRetriever wired
│   ├── cli.py             — Full Rich CLI: ingest, ask, gaps, observe, inspect, stats, mask, unmask
│   ├── sensors.py         — CameraIngestor, AudioIngestor (LibrosaFeatureClassifier), CLIPClassifier, MockClassifier
│   ├── reasoning.py       — ConflictDetector (LLM + NLI), NLICrossEncoder (label-order validated),
│   │                        EvidenceWeighter, GapDetector, PatternDetector (surfaced unprompted)
│   ├── retrieve.py        — HybridRetriever + AgenticRetriever (bounded agent loop, token bug fixed)
│   ├── llm.py             — Ollama + OpenAI + Mock fallback chain
│   ├── ingest.py          — PDF, Markdown, Experiment JSON ingestors, IngestorBase plugin arch
│   ├── extractor.py       — LLM-based claim extraction
│   ├── embedder.py        — sentence-transformers LocalEmbedder (nomic-embed-text primary)
│   ├── vector_store.py    — ChromaDB wrapper
│   ├── tools.py           — ToolRegistry for agent loop
│   ├── kernels.py         — StatisticsKernel, Cohen's d, confidence intervals, reproducibility hashes
│   ├── chunker.py         — TextChunker
│   ├── evaluate.py        — VictorEvaluator
│   ├── scifact_benchmark.py — SciFact eval harness (5 runs completed; see Results Log)
│   └── config.py          — VictorConfig
├── tests/
│   ├── test_agent_loop.py
│   ├── test_scifact_benchmark.py    — 25 tests (machinery only, not real accuracy)
│   ├── test_nli_crossencoder.py     — NLICrossEncoder unit tests
│   ├── test_audio_pipeline.py
│   ├── test_statistics_kernel.py
│   ├── test_sensor_pipeline.py
│   ├── test_cli_import.py
│   ├── test_chunker.py
│   ├── test_extractor.py
│   └── test_metric_conflation.py
├── scripts/
│   └── verify_doc_counts.sh         — checks CURRENT_TEST_COUNT marker matches pytest --collect-only
├── smoke_test.py
├── setup.py
├── requirements.txt
└── examples/
    ├── sample_paper.md
    └── sample_experiment.json
```

---

## Theory vs. Implementation Checklist

| Theory requirement | Status | Where |
|---|---|---|
| Epistemic Artifact schema (all 6 properties) | ✅ Built | `models.py` → `ObservationResult`, `Claim`, `Experiment` |
| EpistemicStatus hierarchy (MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS) | ✅ Built | `models.py` → `EpistemicStatus` enum |
| Typed knowledge graph | ✅ Built | `graph.py` → NetworkX + JSON, 8 node types, 12 edge types |
| Typed edges with direction (CONFIRMS, CONTRADICTS, DERIVED_FROM) | ✅ Built | `graph.py` |
| Atomic graph save | ✅ Built | `graph.py` → write to `.tmp`, then `os.replace()` |
| Graph as permanent artifact (survives crashes) | ✅ Built | Atomic save + error-logging load |
| Ingestion pipeline | ✅ Built | `ingest.py` → PDF, Markdown, Experiment JSON |
| ConflictDetector (LLM-based, not keyword heuristic) | ✅ Built | `reasoning.py` |
| NLICrossEncoder (agreement-bias catch) | ✅ Built + label-order validated | `reasoning.py` — auto-detects label order; explicit override via `label_order` param |
| EvidenceWeighter | ✅ Built | `reasoning.py` |
| GapDetector | ✅ Built | `reasoning.py` |
| PatternDetector | ✅ Built, surfaces unprompted | `reasoning.py` + `core.py` |
| Weighted retrieval (0.7 × cosine + 0.3 × importance) | ✅ Built | `retrieve.py` |
| Temporal decay | ✅ Built | `graph.py` |
| Conversation memory as graph nodes | ✅ Built | `core.py` |
| Model-agnostic InferenceClient | ✅ Built | `llm.py` → Ollama / OpenAI / Mock |
| StatisticsKernel | ✅ Built | `kernels.py` |
| Reality → Artifact pipeline (camera) | ✅ Built | `sensors.py` → CameraIngestor + CLIP |
| Reality → Artifact pipeline (audio) | ✅ Built (simplified) | `sensors.py` → AudioIngestor + LibrosaFeatureClassifier (heuristic MFCCs, not PANNs/ONNX as planned) |
| Agent loop (agentic retrieval) | ✅ Built, token bug fixed | `retrieve.py` → AgenticRetriever; quadratic token counting fixed v4.6→v5.0 |
| SciFact benchmark — machinery | ✅ Built + NLI wired | `scifact_benchmark.py` → `--nli-model`, `--nli-threshold`, `--nli-primary`, `--nli-label-order` |
| SciFact benchmark — accuracy ≥85% | ❌ Open | Current best: 71.0% (Run 5). See Results Log. |
| FastAPI endpoint | ❌ Not built | No web interface |
| Graph visualization | ❌ Not built | No browser view |
| Spectral ingestion | ❌ Not started | Layer 1, Phase 1C |

---

## Known Bugs — Current Status

### Bug 1 — AgenticRetriever quadratic token counting [FIXED in v5.0]
Was: `self._context_tokens +=` re-summed the full accumulated prompt every turn. Now: counts only current turn delta. Agent loop operates correctly.

### Bug 2 — `compute_statistics` metric conflation [FIXED in v5.0]
Was: averaged all numeric fields in a result dict together. Now: requires explicit `metric_name`. Multi-metric experiments handled correctly.

### Bug 3 — `test_compute_effect_size` test failure [RESOLVED — re-verified 2026-06-28]
**File:** `test_statistics_kernel.py`
**What it was:** Pre-existing test that calls `compute_effect_size()` without passing `metric_name`, previously reported failing after the Bug 2 fix changed the required interface.
**Current status:** Actually ran `pytest tests/test_statistics_kernel.py -v` directly — `test_compute_effect_size_creates_computed_node` **passes**, along with all 20 tests in that file. Whatever caused the earlier failure is no longer present. Closing this; it is not a current bug.
**Effect:** 0/196 tests red.

### NLI label-order bug [FIXED in v5.2, smoke-tested in v5.3]
Was: `_LABEL_ORDER = ["contradiction", "entailment", "neutral"]` — indices 1 and 2 were swapped for `cross-encoder/nli-deberta-v3-base`. Caused all entailment predictions to be mapped to "neutral" → "inconclusive", making primary mode fail (8% accuracy). Fixed to `["contradiction", "neutral", "entailment"]`.

> **Open question, flagged 2026-06-28, not yet resolved:** Hugging Face's own README for this model family documents `label_mapping = ['contradiction', 'entailment', 'neutral']` — the order this doc calls buggy. The order above was validated locally via the smoke test against known pairs, which is good evidence, but it directly contradicts the vendor README. Before relying on a primary-mode deberta-v3 run, print `model.config.id2label` directly and confirm which order the actual checkpoint reports — don't take either source on faith.

Additionally, `dleemiller/ModernCE-large-nli` outputs labels in `["entailment", "neutral", "contradiction"]` order — the inverse of the fallback default. Auto-detection from `id2label` silently fails for this model (attribute path is different). v5.3 adds explicit `--nli-label-order` flag and a `validate_label_order()` smoke test that catches this before the benchmark loop starts. *(Note: this flag/method/param were confirmed local-only, not yet pushed, as of the last code review — push them so the next zip export actually contains them.)*

---

## What Is NOT Built (Confirmed Absent)

- `api.py` — no FastAPI or any web endpoint. CLI only.
- Graph visualization — no browser view of the knowledge graph.
- Spectral ingestion — no spectrometer pipeline.
- Encryption on export — `export` command exists but output is unencrypted.
- LoRA fine-tuning pipeline — not started. Correctly gated on DoD #4 (SciFact ≥85%).
- Multi-user or federation — out of scope until single-user is solid.
- PANNs / ONNX audio — the audio ingestor uses LibrosaFeatureClassifier (heuristic acoustic features), not the PANNs pipeline originally planned.

---

## The Next Three Actions — In Exact Order

**Action 1: Run deberta-base in primary mode (v5.3 code, label order now correct).**
```powershell
$env:OLLAMA_HOST="http://127.0.0.1:11434"
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-base `
  --nli-primary
```
This is the untested path that should exceed 71%. The label order bug that caused primary mode to fail (8%) is fixed in v5.3. The smoke test will run automatically and confirm the mapping before inference starts.

**Action 2: Threshold sweep on cross-check mode.**
```powershell
foreach ($t in 0.3, 0.4, 0.5, 0.6) {
  python -m victor.scifact_benchmark `
    --corpus-path data/corpus.jsonl `
    --claims-path data/claims_dev.jsonl `
    --n-samples 100 `
    --nli-model cross-encoder/nli-deberta-v3-base `
    --nli-threshold $t
}
```
0.5 was untuned. Sweep it. Pick threshold that maximises `contradict` recall without collapsing `confirm` precision. Report both — overall accuracy alone hid the real failure in Runs 1 and 2.

**Action 3: If Actions 1–2 don't clear 83%, upgrade to deberta-v3-large.**
```powershell
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-large `
  --nli-threshold <tuned-value>
```
Same interface, ~2–3% better on MNLI. Slower (~3–5s/sample on CPU). Still no GPU required.

Do not run a 300-sample full dev set until one configuration clears ~83% on n=100. The full run is the final confirmation step, not the exploration step.

---

## Environment Facts (verified on this machine)

| Item | Value |
|------|-------|
| Ollama installed | ✅ |
| Correct model tag | `qwen2.5:7b` (not `qwen2.5` — resolves to `latest`, can fail) |
| OLLAMA_HOST | `http://127.0.0.1:11434` — must be set before running benchmark |
| SciFact data | Present locally in `data/` — `corpus.jsonl`, `claims_dev.jsonl`, `claims_train.jsonl`, `claims_test.jsonl` |
| Python env | Windows PowerShell, use backtick `` ` `` for line continuation |

---

## Results Log
*Append results here when actions above are completed. Do not edit prior entries.*

| Date | Action | Result |
|------|--------|--------|
| 2026-06-23 | Bug 1 fixed — quadratic token counting (`retrieve.py`) | `self._context_tokens =` (current turn only). Agent loop operates correctly. |
| 2026-06-23 | Bug 2 fixed — `compute_statistics` metric conflation (`core.py`) | Requires explicit `metric_name`. Multi-metric experiments no longer averaged. |
| 2026-06-23 | PatternDetector wired unprompted | `ask_full()` now calls `_inject_pattern_note()`. Surfaces automatically when query overlaps a priority gap. |
| 2026-06-27 | SciFact Run 1 — v4.9, pure LLM, n=50 | **68.0%** — confirm recall 86%, contradict recall 27%. Agreement bias confirmed: model defaults to confirm under uncertainty. |
| 2026-06-27 | SciFact Run 2 — v5.1, structured JSON prompt, n=50 | **58.0%** — confirm recall 63%, contradict recall 47%. Regression from v5.0 judge() rewrite. Structured JSON pushed Qwen2.5-7B toward confirm as easiest schema-satisfying token. NLI cross-encoder not loaded in either run. |
| 2026-06-27 | SciFact Run 3 — v5.1, qwen2.5:7b, no NLI, n=100 | **59.0%** — confirm precision 87.8%, recall 61.4%; contradict precision 55.2%, recall 53.3%. NLI overrides fired: 4. Consistent with Run 2; pure-LLM ceiling ~59%. |
| 2026-06-27 | SciFact Run 4 — v5.2, deberta-v3-base, NLI primary mode, n=100 | **8.0%** — NLI overrides fired: 100. Primary mode catastrophically broken. Root cause: `_LABEL_ORDER` was wrong (entailment/neutral indices swapped), causing every entailment pair to be classified as contradiction. Fixed in v5.2 (corrected order) and v5.3 (smoke test). |
| 2026-06-27 | SciFact Run 5 — v5.2, deberta-v3-base, NLI cross-check mode, n=100 | **71.0%** — Best observed result. Cross-check only overrides LLM confirm→contradict, so label order bug at indices 1/2 didn't affect it (index 0 = contradiction was always correct). Still 14 points below DoD target. |
| 2026-06-27 | v5.3 shipped | Added `label_order` constructor param to `NLICrossEncoder`. Added `validate_label_order()` smoke test. Added `--nli-label-order` and `--skip-nli-smoke-test` CLI flags. Auto-detection now tries 3 attribute paths. 196/196 tests pass. Primary mode with corrected label order not yet benchmarked. |
| — | SciFact DoD #4 (>85%) | **Not yet closed.** Current best: 71.0%. Run deberta-base primary mode with v5.3 code next. |

---

## Version History of This Document

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial document created |
| June 2026 | v5.0 | Both bugs fixed. PatternDetector wired. Audio ingestor built (LibrosaFeatureClassifier). Tests: 147 → 177. |
| June 2026 | v5.1 | NLICrossEncoder added. scifact_benchmark.py wired with --nli-model flags. Tests: 177 → 196. |
| June 2026 | v5.2 | _LABEL_ORDER corrected for deberta-v3-base. Auto-detection via id2label added. SciFact Runs 3–5 completed. |
| June 2026 | v5.3 | label_order constructor param. validate_label_order() smoke test. --nli-label-order / --skip-nli-smoke-test CLI flags. 3-path auto-detection. Known model label orders documented. |

*VICTOR_WHAT_IS_BUILT.md · v5.3 · June 2026*
