# VICTOR — SciFact Accuracy: Diagnosis & Action Plan
*Working document · June 2026 · Updated with the latest verified benchmark runs and Ollama state*

> This file tracks the actual SciFact benchmark facts as observed in the current v5.2 / v5.1 toolchain, not the aspirational PRD wording. The important distinction is now clear:
> - **Ollama is installed and working**
> - **`qwen2.5:7b` is the local model tag**
> - **`scifact_benchmark.py` runs end-to-end**
> - **the remaining problem is accuracy / routing, not basic execution**

---

## 1. Current verified state

### 1.1 Dataset
The SciFact release data is present locally:

- `data/claims_dev.jsonl`
- `data/claims_train.jsonl`
- `data/claims_test.jsonl`
- `data/corpus.jsonl`

### 1.2 Ollama
Current verified Ollama facts:

- `ollama list` shows `qwen2.5:7b`
- `ollama run qwen2.5` tries to resolve `latest` and fails when the registry is unreachable
- `ollama run qwen2.5:7b` works and returns a normal chat response
- `OLLAMA_HOST=http://127.0.0.1:11434` is set in the session before running the benchmark

### 1.3 Benchmark status
`python -m victor.scifact_benchmark` now executes successfully. The benchmark is no longer blocked by missing files or missing Ollama connectivity.

---

## 2. What has actually been measured

| Run | Setup | n | Accuracy | `confirm` recall | `contradict` recall | Notes |
|---|---|---:|---:|---:|---:|---|
| Run 1 | v4.9, pure LLM | 50 | 68.0% | 86% | 27% | Original unstructured `judge()` prompt |
| Run 2 | v5.1, pure LLM | 50 | 58.0% | 63% | 47% | Structured JSON prompt, regression confirmed |
| Run 3 | v5.1, `qwen2.5:7b`, no NLI | 100 | 59.0% | 61.4% | 53.3% | `NLI overrides fired: 4` |
| Run 4 | v5.1, `cross-encoder/nli-deberta-v3-base`, primary mode | 100 | 8.0% | 7.1% | 10.0% | `NLI overrides fired: 100`; primary routing is misaligned |
| Run 5 | v5.1, `cross-encoder/nli-deberta-v3-base`, cross-check mode | 100 | 71.0% | 68.6% | 76.7% | Best observed so far; still below target |

### 2.1 Confusion matrices that matter

#### Run 3 — `qwen2.5:7b` only
- `confirm`: precision 87.8%, recall 61.4%
- `contradict`: precision 55.2%, recall 53.3%

#### Run 4 — NLI primary mode
The system overrode nearly everything to `inconclusive`, which indicates the current primary-mode mapping is not usable as-is for this benchmark.

#### Run 5 — NLI cross-check mode
This is the first configuration that materially improved over the pure LLM baseline, but it still leaves a large gap to the >85% target.

---

## 3. Diagnosis — what the latest runs imply

### Cause 1 — Pure LLM scoring still has agreement bias
The qwen2.5-only run still favors `confirm` under uncertainty. That is consistent with the earlier 68% → 58% regression story.

### Cause 2 — The NLI primary path is currently miswired
`cross-encoder/nli-deberta-v3-base` is not the problem by itself. The problem is the way Victor currently interprets or applies its outputs in `primary` mode. A direct toy check on the same cross-encoder returns a nontrivial 3-way score vector, so the model is producing usable logits; the current benchmark routing is what collapses in primary mode.

### Cause 3 — Cross-check mode is promising, but not enough yet
Cross-check mode with the base NLI model improves the observed number to 71%, which is the best result captured so far in the current session. That still does not close DoD #4.

### Cause 4 — Model tag hygiene matters
Use the exact local tag:

```powershell
qwen2.5:7b
```

not:

```powershell
qwen2.5
```

The shorter name attempts to pull `latest`, which is not what is installed locally in this setup.

---

## 4. Action plan — current, practical order

### Step 1 — Keep the benchmark pinned to the working local Ollama tag
Use `qwen2.5:7b` explicitly in any benchmark path that invokes Ollama. Do not rely on the unqualified `qwen2.5` name.

### Step 2 — Fix NLI label routing before trusting primary mode
The primary-mode behavior is not credible yet. Inspect the label-order / override logic in `reasoning.py` and `scifact_benchmark.py` before interpreting any more primary-mode scores.

### Step 3 — Treat 71% as the current baseline
The current best observed benchmark number is 71.0% on the 100-sample dev subsample with cross-check mode. That is the floor for the next iteration.

### Step 4 — Only after routing is fixed, do a threshold sweep
Once the NLI outputs map correctly, sweep the threshold on the dev set and compare `confirm` vs `contradict` recall.

### Step 5 — Full 300-sample dev run after the routing is stable
Do not close DoD #4 on n=50 or n=100. Run the full `claims_dev.jsonl` set only after the best configuration is stable.

---

## 5. Updated benchmark commands

### 5.1 Pure Ollama baseline
```powershell
$env:OLLAMA_HOST="http://127.0.0.1:11434"
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model none `
  --nli-primary
```

### 5.2 Cross-check NLI baseline
```powershell
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-base `
  --nli-threshold 0.5
```

### 5.3 Primary-mode test
```powershell
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-base `
  --nli-primary
```

---

## 6. Definition of done for the SciFact workstream

- [ ] `qwen2.5:7b` is the explicit local Ollama target
- [ ] `scifact_benchmark.py` runs end-to-end with `OLLAMA_HOST` set
- [ ] NLI primary routing is corrected or removed
- [ ] Cross-check mode is re-evaluated after routing is corrected
- [ ] A full 300-sample dev run lands at or above 85%
- [ ] The benchmark log in the PRD is updated with the real final number

---

## 7. Bottom line

The current SciFact story is now clear:

- The environment works.
- The benchmark runs.
- The local model works.
- The best observed score so far is **71.0%**.
- The remaining gap is in **routing / label mapping / benchmark integration**, not in basic installation.

*Update this file in place as new runs finish; do not branch into a fresh diagnosis document unless the benchmark architecture changes again.*
