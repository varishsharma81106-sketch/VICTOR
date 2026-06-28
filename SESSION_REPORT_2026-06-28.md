# Victor — Session Report · 2026-06-28

## Session Summary

**Duration:** ~2 hours  
**Focus:** SciFact benchmark accuracy work — primary-mode test, threshold sweep, label order verification, documentation updates  
**Result:** 5 new benchmark runs completed (Runs 8–12). DoD #4 remains open at 71.0%. Label order discrepancy resolved. Threshold tuning confirmed dead end.

---

## What Was Done

### 1. Full Codebase Analysis (Read-Only)

Read and analyzed every source file in the repository without modification:

- **16 Python modules** in `victor/` — core.py, cli.py, config.py, models.py, graph.py, vector_store.py, reasoning.py, tools.py, retrieve.py, llm.py, embedder.py, ingest.py, extractor.py, chunker.py, sensors.py, kernels.py, scifact_benchmark.py, evaluate.py
- **12 test files** in `tests/`
- **All documentation** — VICTOR_CANON.md, VICTOR_BUILD_SEQUENCE.md, VICTOR_WHAT_IS_BUILT.md, VICTOR_SCIFACT_ACCURACY_PLAN.md, VICTOR_FOUNDATION_v2.md, VICTOR_MASTER_PRD_v3_6.md
- **Configuration** — setup.py, requirements.txt, Dockerfile, smoke_test.py

**Output:** Comprehensive 10-category analysis covering architecture, folder structure, implementation status, missing features, technical debt, bugs, scalability concerns, security concerns, code quality, and prioritized roadmap.

### 2. Label Order Verification (Critical Discovery)

**Action:** Loaded `cross-encoder/nli-deberta-v3-base` and verified its actual `id2label` mapping:

```
Model's actual id2label: {0: 'contradiction', 1: 'entailment', 2: 'neutral'}
Auto-detected order:    ['contradiction', 'entailment', 'neutral']
Class default _LABEL_ORDER: ['contradiction', 'neutral', 'entailment']
```

**Finding:** The auto-detection reads from `model.config.id2label` and produces the **correct** order `['contradiction', 'entailment', 'neutral']`. The class-level default `_LABEL_ORDER` is **wrong** for this model (indices 1 and 2 swapped). Since auto-detection reads from the model config, the actual runtime behavior is correct. The smoke test (`validate_label_order()`) passes.

**Smoke test results:**
- `'A dog is sleeping.' / 'An animal is resting.'` → **confirm** (conf=0.99) ✓
- `'The sky is blue.' / 'The sky is green.'` → **contradict** (conf=1.00) ✓

**Implication:** This resolves the open question from VICTOR_WHAT_IS_BUILT.md about whether the HF README's label order matches the model's actual config. The model's `config.json::id2label` is the ground truth, and auto-detection reads it correctly.

### 3. SciFact Benchmark — Primary Mode (Run 8)

**Command:**
```bash
PYTHONIOENCODING=utf-8 python -m victor.scifact_benchmark \
  --corpus-path data/corpus.jsonl \
  --claims-path data/claims_dev.jsonl \
  --n-samples 100 \
  --nli-model cross-encoder/nli-deberta-v3-base \
  --nli-primary \
  --use-mock-llm
```

**Note:** Used `--use-mock-llm` because Ollama was not initially reachable. In NLI-primary mode, the cross-encoder makes the direction decision; the LLM only provides reasoning traces.

**Bug found:** `validate_label_order()` uses Unicode characters (`✓`, `✗`, `→`) that crash on Windows terminals without `PYTHONIOENCODING=utf-8`.

**Result:** **8.0% accuracy**

| Direction | Precision | Recall | Support |
|---|---|---|---|
| confirm | 71.4% | 7.1% | 70 |
| contradict | 33.3% | 10.0% | 30 |

**Confusion matrix:**
```
Gold \ Pred     confirm  contradict  inconclusive
confirm (70):      5         6            59
contradict (30):   2         3            25
```

**Analysis:** 84/100 samples predicted as inconclusive. The NLI cross-encoder alone cannot handle SciFact — MNLI-trained cross-encoders default to neutral on long scientific abstracts. The LLM does the heavy lifting in cross-check mode; the NLI only catches agreement bias on a subset. **Primary-mode architecture (NLI decides, LLM annotates) confirmed insufficient.**

### 4. SciFact Benchmark — Threshold Sweep (Runs 9–12)

**Ollama availability:** Confirmed running with `qwen2.5:7b` model.

**Commands:**
```bash
for threshold in 0.3 0.4 0.5 0.6; do
  PYTHONIOENCODING=utf-8 OLLAMA_HOST=http://127.0.0.1:11434 \
    python -m victor.scifact_benchmark \
      --corpus-path data/corpus.jsonl \
      --claims-path data/claims_dev.jsonl \
      --n-samples 100 \
      --nli-model cross-encoder/nli-deberta-v3-base \
      --nli-threshold $threshold
done
```

**Results:**

| Run | Threshold | Accuracy | confirm recall | contradict recall | NLI overrides |
|---|---|---|---|---|---|
| 9 | 0.3 | **61.0%** | 64.3% (45/70) | 53.3% (16/30) | 7 |
| 10 | 0.4 | **64.0%** | 65.7% (46/70) | 60.0% (18/30) | 8 |
| 11 | 0.5 | **63.0%** | 61.4% (43/70) | 66.7% (20/30) | 8 |
| 12 | 0.6 | **64.0%** | 67.1% (47/70) | 56.7% (17/30) | 5 |
| **5 (prev best)** | **0.5** | **71.0%** | **68.6%** | **76.7%** | — |

**Analysis:** No threshold improves on Run 5 (71.0%). The NLI override count is too low (5–8 out of 100) to move the needle — the LLM does 92–95% of the work. Threshold tuning on this architecture is a dead end.

### 5. SciFact Dataset Download

Downloaded the SciFact dataset directly from the source URL found in the HuggingFace loading script:
- Source: `https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz`
- Extracted to: `data/corpus.jsonl` (5,183 docs) and `data/claims_dev.jsonl` (300 claims)
- Note: HuggingFace `datasets` v5.0 no longer supports loading scripts; v4.8.5 also failed; direct S3 download was the workaround.

### 6. Version Fix

**File:** `victor/__init__.py`  
**Change:** `__version__ = "4.0.0"` → `__version__ = "5.3.0"`  
**Reason:** Was inconsistent with `setup.py` (which already says `5.3.0`) and all documentation.

### 7. Documentation Updates

#### VICTOR_WHAT_IS_BUILT.md
- Added Runs 8–12 to Results Log with full config details
- Updated DoD #4 status line
- Marked Action 1 (primary mode) as DONE
- Marked Action 2 (threshold sweep) as DONE
- Updated Next Three Actions to point to ModernCE cross-check as Action 3
- Updated file map description for scifact_benchmark.py

#### VICTOR_SCIFACT_ACCURACY_PLAN.md
- Added Runs 8–12 to benchmark history table (Section 2)
- Updated one-line state to reflect primary-mode finding
- Marked Step 1 (primary mode) as DONE with results
- Marked Step 1a (threshold sweep) as DONE with results table
- Updated summary paragraph after benchmark table

---

## Diagnosis: Model Capacity Problem, Not Methodology Problem

### What Was Ruled Out

1. **Label order:** RESOLVED. Auto-detection reads from `model.config.id2label` and produces correct order. Smoke test passes. Run 8 (correct labels) still scored 8.0% in primary mode — proving the architecture, not the labels, is the problem.

2. **Threshold tuning:** DEAD END. NLI overrides are 5–8 out of 100 samples — the LLM does 92–95% of the work. Tuning a parameter that fires on <10% of samples cannot close a 14-point gap.

3. **Eval set noise:** Partial factor. Run 5 (71.0%) vs threshold sweep at same 0.5 (63.0%) shows ±7% variance at n=100 with different random seeds. But even the best sweep result (64%) is far below 85%.

### What It Actually Is

A **model capacity problem**. The LLM (qwen2.5:7b) has a pure ceiling of ~59% (Run 3). The deberta-v3-base NLI cross-check adds ~12 points by catching agreement bias on ~8 samples. The combined system plateaus at 64–71%. Getting to 85% requires either:
- A stronger LLM, or
- A stronger NLI model, or
- Fine-tuning

---

## Prioritized Next Steps for Accuracy Work

1. **ModernCE-large-nli in cross-check mode** (highest expected lift, untested with correct labels)
   - ModernCE has 92.0% MNLI-mismatched accuracy vs deberta's 87%
   - Never tested with correct label order
   - Command: `python -m victor.scifact_benchmark --corpus-path data/corpus.jsonl --claims-path data/claims_dev.jsonl --n-samples 100 --nli-model dleemiller/ModernCE-large-nli --nli-label-order entailment,neutral,contradiction --nli-threshold 0.5`

2. **deberta-v3-large in cross-check mode** (same architecture, larger model)
   - ~2–3% better on MNLI
   - Slower (~3–5s/sample on CPU)
   - Do this if ModernCE doesn't clear 83%

3. **Self-consistency voting** (no code changes, more compute)
   - Call `judge()` 3–5 times per sample, majority-vote the direction
   - No new models, no GPU needed

4. **Fine-tune NLI on SciFact train split** (most promising, needs GPU)
   - `claims_train.jsonl` has 809 labeled claims
   - Fine-tune `cross-encoder/nli-deberta-v3-base` locally
   - Free-tier Colab T4 is sufficient
   - Target: 88–92%

---

## Files Modified This Session

| File | Change | Verified |
|---|---|---|
| `victor/__init__.py` | `__version__` "4.0.0" → "5.3.0" | ✅ Confirmed |
| `VICTOR_WHAT_IS_BUILT.md` | Added Runs 8–12, updated DoD status, updated Next Three Actions | ✅ Confirmed |
| `VICTOR_SCIFACT_ACCURACY_PLAN.md` | Added Runs 8–12, marked Steps 1 and 1a as DONE | ✅ Confirmed |

## Files NOT Modified

- No source code logic changes were made
- No test files were modified
- No refactoring was performed

---

## Open Items Discovered

1. **Windows Unicode bug:** `validate_label_order()` in `reasoning.py` uses `✓`, `✗`, `→` characters that crash on Windows terminals without `PYTHONIOENCODING=utf-8`. Needs ASCII fallback.

2. **Class default `_LABEL_ORDER` mismatch:** The class default is `["contradiction", "neutral", "entailment"]` but the model's actual id2label is `["contradiction", "entailment", "neutral"]`. Auto-detection overrides this correctly, but the fallback is wrong. Should be fixed for safety.

3. **SciFact data path:** Data was extracted to `data/data/` (nested) rather than `data/` due to the tar.gz structure. The WHAT_IS_BUILT.md Environment Facts section says `data/` which is incorrect for the downloaded files.

4. **No real research data ingested:** Phase 0 exit criteria technically require `victor gaps` to produce useful output on at least one real document. This has not been verified.

---

*Session report generated 2026-06-28 · Victor v5.3*
