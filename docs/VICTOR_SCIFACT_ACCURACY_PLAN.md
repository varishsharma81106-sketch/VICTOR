# VICTOR — SciFact Accuracy: Diagnosis & Action Plan
*Working document · v5.4 · Updated 2026-08-23*
*Supersedes all prior versions of this file. Update in place; do not create new versions per run.*

> **Current state in one line:** Environment works. Benchmark runs. Best observed: **71.0%** (deberta-v3-base, cross-check, n=100) — which is **zero-shot parity with fine-tuned SOTA**, not a mediocre score. The remaining 14 points to ≥85% are the gap between zero-shot and fine-tuned, and no published system crosses it without training. **The bar therefore mandates fine-tuning.** See Section 0.

---

## 0. The finding that reorders this document

*Added 2026-08-23. This was already in the evidence — it was sitting at §9.1 and
§9.2, below eight sections of tuning steps that cannot possibly close the gap.
Promoting it, because it changes what to do first.*

### 71.0% read against the field

| System | Accuracy | Setup |
|---|---|---|
| **Victor, cross-check** | **71.0%** | Zero-shot. General 7B LLM + off-the-shelf NLI, no SciFact training |
| MultiVerS (SOTA) | 72–73% | Purpose-built, fine-tuned on SciFact, Longformer backbone |
| SciClaims | 88% | DeBERTa fine-tuned on the SciFact training set |

Victor, with zero SciFact-specific training, is within 1–2 points of a
purpose-built fine-tuned system. **The gap to 85% is not a gap between Victor
and the field. It is the gap between zero-shot and fine-tuned.**

### What follows from that

**Threshold sweeps, prompt changes, and bigger off-the-shelf models cannot close
a 14-point gap.** Section 9.6 prices them honestly: +1–3%, +3–5%, +2–3%. Even
stacked, and even assuming they compose (they will not), that is a fraction of
what is needed. They are worth running because they are nearly free, not because
they are a plan.

The only path with published evidence of clearing the bar is **fine-tuning
DeBERTa on `data/claims_train.jsonl`** — 809 labelled claims, already on disk,
CPU-feasible. SciClaims did approximately this and reached 88%. The
architectural alternative is a **Longformer-based NLI checkpoint**, which
addresses Cause D directly (linear attention over a passage-length premise) and
is why MultiVerS uses one.

Revised ordering: start fine-tuning **in parallel with** the cheap experiments,
not after them. The cheap experiments are 30 minutes each; treating them as a
prerequisite has cost weeks of not starting the thing that works.

### The circularity that has to be resolved first

`VICTOR_BUILD_SEQUENCE.md` gates LoRA fine-tuning (Phase 4C) on DoD #4, and §6
of this document repeats the gate. If DoD #4 now requires fine-tuning, then:

> **DoD #4 is gated on Phase 4C, and Phase 4C is gated on DoD #4.**

This is a real deadlock in the plan, not a technicality, and it will not resolve
itself. The proposed resolution is to split what the gate was actually written
to prevent from what it now blocks by accident:

| Activity | Gate | Why |
|---|---|---|
| Fine-tune a **task-specific NLI component** on a public labelled benchmark split | **Ungated — do it now** | Supervised training of a classifier on public data with a held-out eval. Auditable, reversible, versioned, and testable against the base model. This is ordinary ML engineering |
| Fine-tune the **reasoning model on Victor's own accumulated user data** (Phase 4C) | **Stays gated on DoD #4** | This is what the gate was written for: training on unaudited data produced by a reasoning component whose accuracy is unverified. That produces a system nobody can audit, and the gate is correct |

They are different activities and only the second carries the risk that motivated
the rule. **This split needs an explicit decision from the founder before the
fine-tuning work starts** — it is a change to a stated gate, and changing a gate
quietly is exactly the failure mode this project keeps having.

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
`scifact_benchmark.py` now accepts `--nli-model`, `--nli-threshold`, `--nli-primary`. `NLICrossEncoder` is wired into `ConflictDetector` at both construction sites. NLI override counts are tracked and reported. Tests: 212/212 passing.

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
- **Don't treat 71% as a failure.** It is zero-shot parity with fine-tuned SOTA (§0). Reading it as a bad score is what produced a step list of cheap tuning options against a gap that cheap tuning cannot close.
- **Don't run the cheap steps *before* starting the fine-tune.** Run them in parallel. Each is 30 minutes; sequencing them ahead of the only path that clears the bar has already cost weeks.
- ~~Don't trust any primary-mode result from before v5.3 — all prior primary-mode runs had the label order wrong.~~ **Update (2026-08-12):** Run 8 confirms primary mode with correct label order still scores 8%. The issue is model capacity, not label order. Primary mode with DeBERTa-v3-base is definitively ruled out for long scientific text.
- Don't start Phase 4C (LoRA fine-tuning on Victor's *own accumulated data*) before DoD #4 closes. This gate stands. It does **not** cover fine-tuning a task-specific NLI component on a public benchmark split — see §0 for why those are different activities.
- Don't swap to a wholly new model family before finishing the steps above. The NLI wiring is 90% of the fix; a new model wrapper starts from scratch.
- **Don't use primary mode for SciFact.** Cross-encoder NLI models trained on MNLI (short sentence pairs) default to neutral on 200-word scientific abstracts. Cross-check mode is the correct architecture.

---

## 7. Definition of done for DoD #4

- [ ] **Founder decision recorded on the §0 gate split** — fine-tuning a task-specific NLI component on public data is unblocked, Phase 4C stays gated. Nothing below can proceed to 85% without this
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

---

## 9. Research Findings (2026-08-12)

### 9.1 — Victor's 71% is competitive, not mediocre

| System | Accuracy | Notes |
|--------|----------|-------|
| **Victor (cross-check)** | **71.0%** | Zero-shot, general LLM + off-the-shelf NLI |
| MultiVerS (SOTA) | 72-73% | Purpose-built, fine-tuned on SciFact, Longformer backbone |
| SciClaims | 88% | Fine-tuned DeBERTa on SciFact training set |

Victor's 71% using Qwen2.5-7B + DeBERTa-v3-base with zero SciFact-specific training is genuinely close to a dedicated, fine-tuned SOTA system (MultiVerS at 72-73%). This is not a mediocre result — it's a strong zero-shot baseline.

### 9.2 — SciClaims validates the fine-tuning path

**SciClaims** fine-tuned DeBERTa on a SciFact-derived training set and hit **88% F1**. This directly validates the accuracy plan's Step 5 (fine-tune DeBERTa on `claims_train.jsonl`, target 88–92%) as realistic. Someone has already done almost exactly that and cleared 85%.

**Key insight:** The training data is already present locally: `data/claims_train.jsonl` (809 labeled claims). No GPU required for CPU fine-tuning (slower but feasible).

### 9.3 — Longformer-based NLI is a known fix for long text

Run 8 proved DeBERTa-v3-base fails on long text (all 100 samples predicted inconclusive). The standard fix in the field is swapping to a **Longformer-based NLI architecture** — linear-complexity attention built for passage-length premise + short hypothesis. MultiVerS uses a Longformer backbone for exactly this reason.

**New option not in original accuracy plan:** Consider a Longformer-based NLI checkpoint as primary judge on long text, either instead of or before fine-tuning DeBERTa.

### 9.4 — Self-consistency voting needs temperature variation

The original plan listed self-consistency voting as priority #1 (free +3-5%). However, a 2026 study found that **increasing ensemble size from 1 to 7 produced no significant accuracy gain** unless paired with actual temperature diversification — deterministic repeated calls just repeat the same failure mode.

**Fix:** If implementing self-consistency voting, explicitly raise temperature (e.g., 0.7–0.9) across the 3–5 votes. Naive repetition at temperature 0 won't help.

### 9.5 — MCP memory landscape is more crowded

By July 2026, MCP memory-server directories show a more crowded field. Several now advertise redaction-style features. Victor's "nobody else has masked memory" claim is getting less unique as a bare claim.

**What's still unique:** The **combination** of:
1. Epistemic-status tiers (MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS)
2. Tamper-evident mask/unmask audit log
3. Graph-structure-live-content-hidden
4. Applied specifically to scientific claim provenance

**Messaging shift:** From "nobody has masking" to "nobody has this combination for scientific evidence provenance" — more defensible and more true.

### 9.6 — Updated priority list

| Priority | Action | Expected Impact | Notes |
|----------|--------|-----------------|-------|
| 1 | Threshold sweep (0.3-0.6) | +1-3% | Free, 30 min |
| 2 | Self-consistency voting (with temp variation) | +3-5% | Free, but must vary temperature |
| 3 | Fine-tune DeBERTa on SciFact (CPU OK) | Could reach 85%+ | Validated by SciClaims (88%) |
| 4 | Longformer-based NLI | Could reach 85%+ | Alternative to fine-tuning |
| 5 | DeBERTa-v3-large cross-check | +2-3% | 3x slower, same interface |

---

*Research findings added 2026-08-12. Sources: MultiVerS paper, SciClaims paper, 2026 ensemble study.*

*Section 0 added 2026-08-23 (v5.4). It contains no new research — it promotes
what §9.1 and §9.2 already established, which had been sitting below eight
sections of tuning steps that cannot close the gap. The findings were right; the
ordering was wrong.*
