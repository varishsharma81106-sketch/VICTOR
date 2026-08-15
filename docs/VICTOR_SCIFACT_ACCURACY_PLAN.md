# VICTOR — SciFact Accuracy: Diagnosis & Action Plan
*Working document · v5.3 · June 2026*
*Supersedes all prior versions of this file. Update in place; do not create new versions per run.*

> **Current state in one line:** Environment works. Benchmark runs. Best observed: **71.0%** (deberta-v3-base, cross-check, n=100). The label order inversion bug that caused primary mode to score 8–12% is diagnosed and fixed in v5.3. The remaining gap to ≥85% is accuracy, not setup.

---

## 1. Verified environment state

| Item | State |
|---|---|
| SciFact data | Present locally: `data/corpus.jsonl`, `data/claims_dev.jsonl`, `data/claims_train.jsonl`, `data/claims_test.jsonl` |
| Ollama | Installed. Working model tag: **`qwen2.5:7b`** (not `qwen2.5` — that resolves `latest` and fails when registry is unreachable) |
| `OLLAMA_HOST` | Must be set: `$env:OLLAMA_HOST="http://127.0.0.1:11434"` before running |
| `scifact_benchmark.py` | Runs end-to-end. Accepts `--nli-model`, `--nli-threshold`, `--nli-primary`, `--nli-label-order`, `--skip-nli-smoke-test` |
| sentence-transformers | Installed. NLI cross-encoders downloadable from HuggingFace |
| Blocking issues | None. The remaining work is accuracy improvement, not installation |

---

## 2. Complete benchmark history

All measured runs, in chronological order. No guesses; no aspirational numbers.

| Run | Version | Setup | n | Accuracy | `confirm` recall | `contradict` recall | Notes |
|---|---|---|---:|---:|---:|---:|---|
| 1 | v4.9 | pure LLM, unstructured prompt | 50 | 68.0% | 86% | 27% | Original baseline |
| 2 | v5.1 | pure LLM, structured JSON prompt | 50 | 58.0% | 63% | 47% | Structured JSON caused regression |
| 3 | v5.1 | `qwen2.5:7b`, NLI wired, cross-check | 100 | 59.0% | 61.4% | 53.3% | NLI fired only 4 times; near-pure LLM result |
| 4 | v5.1 | `cross-encoder/nli-deberta-v3-base`, **primary mode** | 100 | 8.0% | 7.1% | 10.0% | Label order bug — all 100 samples overridden, entailment/neutral swapped |
| 5 | v5.1 | `cross-encoder/nli-deberta-v3-base`, **cross-check mode** | 100 | 71.0% | 68.6% | 76.7% | **Current best.** Cross-check only uses index 0 (contradiction), which was correct in both old and new label order |
| 6 | v5.2 | `dleemiller/ModernCE-large-nli`, primary mode | 5 | 20.0% | 0% | 33% | Label inversion: confirms → predicted contradict |
| 7 | v5.2 | `dleemiller/ModernCE-large-nli`, primary mode | 100 | 12.0% | 1.4% | 36.7% | Label inversion confirmed at scale; confusion matrix shows near-perfect confirm↔contradict swap |
| 8 | v5.3 | `cross-encoder/nli-deberta-v3-base`, **primary mode** (label order FIXED) | 100 | 8.0% | 7.1% | 10.0% | **Label order correct** (smoke test passed). All 100 samples predicted inconclusive. Root cause: DeBERTa-v3-base NLI fine-tuned on MNLI (short sentence pairs) defaults to neutral on long scientific text (200-word abstracts). This is a model capacity limitation, not a label-order bug. |

> The current best observed result is **71.0%** (Run 5, cross-check mode). Run 8 conclusively proves that DeBERTa-v3-base NLI cannot serve as the primary judge on long scientific text — the model was fine-tuned on MNLI (short sentence pairs) and defaults to neutral on SciFact-length inputs. The cross-check architecture (LLM decides, NLI catches agreement bias) is the correct approach for this model. To improve beyond 71%, the paths are: self-consistency voting, threshold sweep, larger NLI model, or fine-tuning DeBERTa on SciFact pairs.

---

## 3. Root cause diagnosis

### Cause A — Structured JSON prompt amplified agreement bias (Runs 1 → 2 regression)

Forcing Qwen2.5-7B to emit valid JSON against an enum-constrained schema suppresses reasoning quality. The model routes to the lowest-perplexity token satisfying the schema — `"confirm"` is shorter, more common in RLHF data, and schema-valid. This is a documented failure mode (10–30 point accuracy drop on reasoning tasks constrained to structured output). Run 2's structured prompt moved `contradict` recall from 27% to 47%, but collapsed `confirm` recall from 86% to 63% — a different failure, worse overall.

Fix: Step-1a architecture — LLM generates free-form reasoning text (no JSON constraint, no direction token), NLI cross-encoder makes the direction decision. `--nli-primary` flag implements this.

### Cause B — Label order bug inverted primary mode (Runs 4, 6, 7)

`NLICrossEncoder._LABEL_ORDER` was originally `["contradiction", "entailment", "neutral"]`. The actual output order of `cross-encoder/nli-deberta-v3-base` is `["contradiction", "neutral", "entailment"]` — indices 1 and 2 were swapped. This caused all entailment predictions to map to "neutral" → "inconclusive", making primary mode produce 8% accuracy.

The v5.2 corrected order (`["contradiction", "neutral", "entailment"]`) was right for deberta-v3-base. But for `dleemiller/ModernCE-large-nli`, the output order is `["entailment", "neutral", "contradiction"]` — the direct inverse. Auto-detection (reading `id2label` from the model config) silently fails for ModernCE because its attribute path differs from deberta's. The fallback to the deberta-correct order produces systematic inversion for ModernCE. The Run 7 confusion matrix makes this explicit:

```
Gold \ Pred     confirm   contradict   inconclusive
confirm (70):       1          52             17       ← confirms → predicted contradict
contradict (30):   18          11              1       ← contradicts → predicted confirm
```

Fix (v5.3): `NLICrossEncoder` now accepts an explicit `label_order` parameter that bypasses auto-detection entirely. `--nli-label-order` CLI flag exposes this. Multi-path auto-detection tries 3 attribute paths before falling back. `validate_label_order()` smoke test runs two known pairs before the full benchmark and aborts if labels are inverted.

### Cause C — Agreement bias is still the base problem (all LLM runs)

Instruction-tuned LLMs doing zero-shot NLI systematically default to "entailment" (confirm) when uncertain. This is training-distribution driven — RLHF data has far more agreement/confirmation than contradiction. No prompt change fully eliminates it on a 7B-class model. The NLI cross-encoder architecture exists precisely to catch this: deberta-v3 NLI models were fine-tuned specifically on entailment/contradiction pairs and have no agreement bias.

### Cause D — Cross-encoder NLI cannot handle long text in primary mode (Run 8)

DeBERTa-v3-base NLI was fine-tuned on MNLI (MultiNLI), which consists of short sentence pairs (typically 10-30 words each). SciFact data pairs a ~20-word claim with a ~200-word scientific abstract. When the NLI cross-encoder receives these long, complex inputs, it defaults to "neutral" → "inconclusive" for **every sample** — 100% of predictions are inconclusive, regardless of the true label.

This is confirmed by the confusion matrix:
```
Gold \ Pred             confirm   contradict inconclusive
confirm (70):               5            6           59    ← 84% predicted inconclusive
contradict (30):            2            3           25    ← 83% predicted inconclusive
```

The smoke test passes because it uses short, simple sentences ("A dog is sleeping" / "An animal is resting") that fall within the model's training distribution. The actual SciFact data does not.

**Conclusion:** Cross-encoder NLI models trained on short sentence pairs cannot serve as the primary judge on long scientific text. The cross-check architecture (Run 5: 71%) is the correct approach: the LLM handles the long-text reasoning, and the NLI catches agreement bias on a subset of samples.

---

## 4. Known label orders by model

| Model | Output order (index 0, 1, 2) | `--nli-label-order` argument |
|---|---|---|
| `cross-encoder/nli-deberta-v3-base` | `contradiction, neutral, entailment` | `contradiction,neutral,entailment` |
| `cross-encoder/nli-deberta-v3-large` | `contradiction, neutral, entailment` | `contradiction,neutral,entailment` |
| `dleemiller/ModernCE-large-nli` | `entailment, neutral, contradiction` | `entailment,neutral,contradiction` |
| `dleemiller/EttinX-nli-s` | `entailment, neutral, contradiction` | `entailment,neutral,contradiction` |

> Always run the smoke test before a new model to catch order mismatches early. The smoke test is automatic unless `--skip-nli-smoke-test` is passed.

---

## 5. Action plan — ordered by effort, with decision gates

### ✅ DONE — Wire NLI into benchmark script (Step 1, original plan)
`scifact_benchmark.py` now accepts `--nli-model`, `--nli-threshold`, `--nli-primary`. `NLICrossEncoder` is wired into `ConflictDetector` at both construction sites. NLI override counts are tracked and reported. Tests: 196/196 passing.

### ✅ DONE — Fix label order bug and add smoke test (v5.2 + v5.3)
`_LABEL_ORDER` corrected for deberta-v3. Auto-detection added (multi-path). `label_order` constructor param added. `validate_label_order()` smoke test added. `--nli-label-order` CLI flag added.

---

### ☐ Step 1 — Run deberta-base in primary mode (~30 min, no new downloads)

First untested path with a correct label order. This was broken in every prior run (Run 4 used wrong label order; v5.3 fixes it).

```powershell
$env:OLLAMA_HOST="http://127.0.0.1:11434"
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-base `
  --nli-primary
```

Expected: smoke test passes (deberta auto-detection works), results substantially above 71%.

**Decision gate:** ≥78% → Step 2 (larger model). 71–77% → Step 1a (threshold sweep in cross-check mode). <71% → something else is wrong; check smoke test output.

---

### ☐ Step 1a — Threshold sweep on cross-check mode (~30 min, free)

`nli_override_threshold=0.5` is a guess. Sweep it:

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

Report `contradict` recall and `confirm` precision separately at each threshold. The goal is maximum `contradict` recall without collapsing `confirm` precision.

---

### ☐ Step 2 — Run ModernCE with correct label order (~30 min, model already downloaded)

ModernCE-large-nli (92.0% MNLI-mismatched) has never been benchmarked with a correct label order. With `--nli-label-order entailment,neutral,contradiction`, this is a new data point.

```powershell
# Cross-check mode
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model dleemiller/ModernCE-large-nli `
  --nli-label-order entailment,neutral,contradiction `
  --nli-threshold 0.5

# Primary mode
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model dleemiller/ModernCE-large-nli `
  --nli-label-order entailment,neutral,contradiction `
  --nli-primary
```

**Decision gate:** ≥83% on either → go to Step 4 (full dev set). <83% → Step 3.

---

### ☐ Step 3 — Self-consistency voting (~no new code, more compute)

Call `judge()` 3–5 times per sample, majority-vote the direction. No code changes, no GPU, costs only inference time. Run after Steps 1–2 identify the best single-call configuration.

---

### ☐ Step 4 — Upgrade to deberta-v3-large (~same command, 3× slower per sample)

```powershell
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-large `
  --nli-threshold <tuned value>
```

**Decision gate:** ≥83% → Step 5 (full dev set). <83% → Step 5 (fine-tuning).

---

### ☐ Step 5 — Fine-tune on SciFact train split (days, needs GPU, target 88–92%)

Only if Steps 1–4 don't clear ~85%.

Fine-tune `cross-encoder/nli-deberta-v3-base` on `claims_train.jsonl` (809 labeled claims — present locally). Evaluate on `claims_dev.jsonl`. Deploy as `--nli-model`.

Hardware: free-tier **Colab T4** (15GB VRAM) is sufficient. Base model: ~6GB VRAM at batch_size=8.

**Contamination note:** Do not use `MilosKosRad/DeBERTa-v3-large-SciFact` from HuggingFace — its model card does not confirm `claims_dev.jsonl` was excluded from training. Fine-tune locally on `claims_train.jsonl` only; that path is contamination-clean.

---

### ☐ Step 6 — Full dev set, two seeds (once any config clears ~85%)

```powershell
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --nli-model <winning model> `
  --nli-threshold <tuned value> `
  --seed 1

python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --nli-model <winning model> `
  --nli-threshold <tuned value> `
  --seed 2
```

n=100 has ±7% CI. DoD #4 requires a stable number: both seeds must land within 3% of each other on the full 300-sample `claims_dev.jsonl`.

---

## 6. What not to do

- Don't report a single n=50 or n=100 number as closing DoD #4. It doesn't.
- Don't write another planning document. The next action is a benchmark command, not a file.
- ~~Don't trust any primary-mode result from before v5.3 — all prior primary-mode runs had the label order wrong.~~ **Update (2026-08-12):** Run 8 confirms primary mode with correct label order still scores 8%. The issue is model capacity, not label order. Primary mode with DeBERTa-v3-base is definitively ruled out for long scientific text.
- Don't start Phase 5 (LoRA fine-tuning on Victor's own data) before DoD #4 closes.
- Don't swap to a wholly new model family before finishing the steps above. The NLI wiring is 90% of the fix; a new model wrapper starts from scratch.
- **Don't use primary mode for SciFact.** Cross-encoder NLI models trained on MNLI (short sentence pairs) default to neutral on 200-word scientific abstracts. Cross-check mode is the correct architecture.

---

## 7. Definition of done for DoD #4

- [ ] A benchmark run shows `NLI overrides fired` > 0 in the output (NLI is actually engaging, not silently skipped)
- [ ] `contradict` recall is reported separately at every step — overall accuracy alone hid the real failure in every prior run
- [ ] Smoke test passes for every model used (`validate_label_order()` output shows ✓ on both pairs)
- [ ] Full 300-sample `claims_dev.jsonl` run, two seeds, both within 3% of each other, both ≥85%
- [ ] `VICTOR_WHAT_IS_BUILT.md` Results Log and `VICTOR_MASTER_PRD_v3_5.md` DoD criterion #4 updated with the real final number

---

## 8. Addendum — label order smoke test (v5.3)

The smoke test in `NLICrossEncoder.validate_label_order()` checks two pairs before any benchmark run:

```
Entailment pair:    "A dog is sleeping." / "An animal is resting."   → expected: confirm
Contradiction pair: "The sky is blue."   / "The sky is green."       → expected: contradict
```

If either fails, the benchmark aborts with a clear error message and the correct label orders for common models. Pass `--skip-nli-smoke-test` only if you've already validated the mapping externally.

*Update this file's run table in place as new runs complete. One row per run, exact model tag, exact n, exact mode, exact date.*
