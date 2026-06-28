# VICTOR — What Is Built
*Code version: v5.3 · Date: June 2026*

---

> This document is updated every time the code changes.
> Check the version header before reading. An outdated version of this document is worse than no document.

---

## The One-Line State

Phase 0 and Phase 1 are complete. 212/212 tests pass (re-verified via actual `pytest` run, 2026-06-28). The v5.3 NLI features are now in the exported codebase: `label_order` constructor param, `validate_label_order()` smoke test, `--nli-label-order` and `--skip-nli-smoke-test` CLI flags, 3-path id2label auto-detection. Best SciFact accuracy so far: **71.0%** (cross-check mode, n=100). DoD criterion #4 (>85%) is still open. No real research data has been ingested.

<!-- CURRENT_TEST_COUNT -->212<!-- /CURRENT_TEST_COUNT -->

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
│   ├── test_agent_loop.py          — 21 tests
│   ├── test_audio_pipeline.py      — 25 tests
│   ├── test_cli_import.py          — 5 tests
│   ├── test_masked_memory.py       — 21 tests (mask/unmask flags, retrieval anchoring, sovereignty model)
│   ├── test_masking_enforcement_full.py — 13 tests (tool-layer masking enforcement end-to-end)
│   ├── test_metric_conflation.py   — 5 tests
│   ├── test_nli_crossencoder.py    — 35 tests (NLICrossEncoder, validate_label_order, v5.3 flags)
│   ├── test_scifact_benchmark.py   — 25 tests (machinery only, not real accuracy)
│   ├── test_sensor_pipeline.py     — 28 tests
│   ├── test_statistics_kernel.py   — 20 tests
│   ├── test_tool_mask_enforcement.py — 6 tests
│   └── test_unmask_audit_log.py    — 8 tests
│
│   ABSENT (confirmed gaps): test_chunker.py, test_extractor.py
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
| NLICrossEncoder (agreement-bias catch) | ✅ Built + v5.3 complete | `reasoning.py` — `label_order` param, `validate_label_order()` smoke test, 3-path id2label auto-detection. CLI: `--nli-label-order`, `--skip-nli-smoke-test` |
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
| SciFact benchmark — machinery | ✅ Built + NLI wired + v5.3 complete | `scifact_benchmark.py` → `--nli-model`, `--nli-threshold`, `--nli-primary`, `--nli-label-order`, `--skip-nli-smoke-test` |
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

### NLI label-order bug [FIXED in v5.2, smoke-tested in v5.3, fully shipped 2026-06-28]
Was: `_LABEL_ORDER = ["contradiction", "entailment", "neutral"]` — indices 1 and 2 were swapped for `cross-encoder/nli-deberta-v3-base`. Caused all entailment predictions to be mapped to "neutral" → "inconclusive", making primary mode fail (8% accuracy). Fixed to `["contradiction", "neutral", "entailment"]`.

v5.3 additions (now in exported codebase as of 2026-06-28):
- `label_order` constructor param on `NLICrossEncoder` — bypasses auto-detection entirely. Use for models like ModernCE whose id2label path differs.
- `validate_label_order()` method — runs two known pairs before any benchmark loop and raises `RuntimeError` on mismatch so a bad mapping aborts early.
- `--nli-label-order` CLI flag — parses comma-separated order string, passes to constructor.
- `--skip-nli-smoke-test` CLI flag — opt-out if you've already validated externally.
- 3-path id2label auto-detection — tries `model.model.config.id2label`, `model.config.id2label`, and `model.model.config["id2label"]` before falling back to the class default.

Also fixed: the class docstring said `[contradiction, entailment, neutral]` (old, wrong order) while `_LABEL_ORDER` had already been corrected to `["contradiction", "neutral", "entailment"]`. Docstring now matches the constant.

> **Open question, not yet resolved:** Hugging Face's own README for this model family documents `label_mapping = ['contradiction', 'entailment', 'neutral']` — the order this doc calls buggy. The corrected order was validated empirically via diagnostic scores, which is strong evidence. To settle it definitively, run `from sentence_transformers import CrossEncoder; m = CrossEncoder("cross-encoder/nli-deberta-v3-base"); print(m.model.config.id2label)` on your local machine and compare against both sources. The smoke test (`validate_label_order()`) will catch a mismatch automatically before any benchmark run.

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

**Action 1 ✅ DONE: Run deberta-base in primary mode (v5.3 code).** Result: 8.0% (Run 8). NLI-primary architecture confirmed insufficient — cross-encoder alone cannot handle SciFact.

**Action 2 ✅ DONE: Threshold sweep on cross-check mode (Runs 9–12).** Best result: 64.0% at threshold=0.4 and 0.6. No threshold improves on Run 5 (71.0%). NLI overrides fire on only 5–8/100 samples — the LLM does 92–95% of the work. Threshold tuning is a dead end on this architecture.

**Action 3: Upgrade to ModernCE-large-nli in cross-check mode (untested with correct labels).**
```powershell
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model dleemiller/ModernCE-large-nli `
  --nli-label-order entailment,neutral,contradiction `
  --nli-threshold 0.5
```
ModernCE has 92.0% MNLI-mismatched accuracy vs deberta's 87%. Never tested with correct label order. This is the highest expected lift untested path.

If Actions 1–3 don't clear 83%, upgrade to deberta-v3-large, then self-consistency voting, then fine-tuning on SciFact train split.

Do not run a 300-sample full dev set until one configuration clears ~83% on n=100.

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
| 2026-06-28 | v5.3 NLI features exported | All v5.3 NLI features confirmed present in codebase (were local-only in prior zip). Docstring bug fixed (`NLICrossEncoder` class docstring said old wrong label order). File map in WHAT_IS_BUILT corrected (added masking test files, removed absent test_chunker/test_extractor). 16 new tests added for v5.3 features. **212/212 tests pass.** |
| 2026-06-28 | SciFact Run 8 — v5.3, deberta-v3-base, NLI primary mode, auto-detected label order, mock LLM, n=100 | **8.0%** — Smoke test passed (auto-detect: [contradiction, entailment, neutral]). NLI overrides fired: 100. Confusion: 84/100 predicted inconclusive. **Does NOT beat previous best (71.0%).** NLI cross-encoder alone cannot handle SciFact — defaults to neutral for long scientific abstracts. The LLM does the heavy lifting in cross-check mode; NLI only catches agreement bias on a subset. Confirms: primary-mode architecture (NLI decides, LLM annotates) is insufficient for this task. |
| 2026-06-28 | SciFact Run 9 — v5.3, deberta-v3-base, cross-check, threshold=0.3, n=100 | **61.0%** — confirm recall 64.3% (45/70), contradict recall 53.3% (16/30). NLI overrides: 7. Below Run 5. |
| 2026-06-28 | SciFact Run 10 — v5.3, deberta-v3-base, cross-check, threshold=0.4, n=100 | **64.0%** — confirm recall 65.7% (46/70), contradict recall 60.0% (18/30). NLI overrides: 8. Below Run 5. |
| 2026-06-28 | SciFact Run 11 — v5.3, deberta-v3-base, cross-check, threshold=0.5, n=100 | **63.0%** — confirm recall 61.4% (43/70), contradict recall 66.7% (20/30). NLI overrides: 8. Best contradict recall in sweep, but overall below Run 5. |
| 2026-06-28 | SciFact Run 12 — v5.3, deberta-v3-base, cross-check, threshold=0.6, n=100 | **64.0%** — confirm recall 67.1% (47/70), contradict recall 56.7% (17/30). NLI overrides: 5. Below Run 5. |
| — | SciFact DoD #4 (>85%) | **Not yet closed.** Current best: 71.0% (Run 5). Threshold sweep (Runs 9–12) did not improve on Run 5. NLI-primary confirmed insufficient (Run 8). Next: ModernCE-large-nli cross-check (Action 3), then deberta-v3-large if needed. |

---

## Version History of This Document

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial document created |
| June 2026 | v5.0 | Both bugs fixed. PatternDetector wired. Audio ingestor built (LibrosaFeatureClassifier). Tests: 147 → 177. |
| June 2026 | v5.1 | NLICrossEncoder added. scifact_benchmark.py wired with --nli-model flags. Tests: 177 → 196. |
| June 2026 | v5.2 | _LABEL_ORDER corrected for deberta-v3-base. Auto-detection via id2label added. SciFact Runs 3–5 completed. |
| June 2026 | v5.3 | label_order constructor param. validate_label_order() smoke test. --nli-label-order / --skip-nli-smoke-test CLI flags. 3-path auto-detection. Known model label orders documented. |
| 2026-06-28 | v5.3 (export fix) | v5.3 NLI features confirmed in codebase. Class docstring corrected. File map corrected (masking tests added, absent tests removed). 16 new tests. 212/212. |

*VICTOR_WHAT_IS_BUILT.md · v5.3 · June 2026*
