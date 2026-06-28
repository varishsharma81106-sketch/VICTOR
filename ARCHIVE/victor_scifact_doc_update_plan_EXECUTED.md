# Victor SciFact Doc Update Plan

## Goal
Make the SciFact and PRD markdown files reflect the real current state of the Victor benchmark work, without stale assumptions or aspirational language.

## Files to treat as live
- `VICTOR_SCIFACT_ACCURACY_PLAN.md`
- `VICTOR_MASTER_PRD_v3_5.md`

## Files to treat as archived or secondary
- Older PRD versions
- Older build-sequence / what-is-built versions
- Any benchmark note that still assumes the old baseline or old routing behavior

---

## 1. What the live SciFact file should say at the top

The first section should state, plainly:

1. `qwen2.5:7b` is the verified local Ollama model tag.
2. `qwen2.5` is not the correct alias in this setup; it resolves to `latest` and can fail.
3. `scifact_benchmark.py` runs end-to-end.
4. The current problem is **accuracy and routing**, not installation, not dataset availability, and not basic execution.
5. Primary mode is currently misaligned; cross-check mode is the better observed path.

---

## 2. What the benchmark history section should contain

Keep the real measured runs, in chronological order:

- Run 1: v4.9, pure LLM, 50 samples, 68.0%
- Run 2: v5.1, pure LLM, 50 samples, 58.0%
- Run 3: v5.1, `qwen2.5:7b`, 100 samples, 59.0%
- Run 4: v5.1, `cross-encoder/nli-deberta-v3-base`, primary mode, 100 samples, 8.0%
- Run 5: v5.1, `cross-encoder/nli-deberta-v3-base`, cross-check mode, 100 samples, 71.0%

Add one sentence under the table:

> The current best observed result is 71.0% in cross-check mode, but it is still below the target and the routing behavior still needs correction.

---

## 3. What the failure analysis should say

Split the failure into three separate causes:

### A. Agreement bias
The local LLM tends to prefer `confirm` under uncertainty.

### B. Routing bug
Primary mode is not behaving as a stable benchmark baseline.

### C. Label semantics
Any NLI model swap must preserve the exact label order expected by the benchmark code. That should be explicitly checked before trusting a run.

Add a short smoke-test rule:

> Before any full benchmark run, verify the model’s label mapping on a tiny test input and confirm that the benchmark interprets the logits in the intended order.

---

## 4. What the PRD should say instead of the old promise

In `VICTOR_MASTER_PRD_v3_5.md`, rewrite the SciFact lever so it says:

- Step 1 is a real code integration step, not a no-code claim.
- The benchmark script must accept `--nli-model` and `--nli-threshold`.
- The NLI model must be wired explicitly into the detector used by the benchmark.
- Only after that should the benchmark claims be treated as evidence.

Remove or replace any wording that says:
- the fix already exists in the benchmark path if it was never actually wired there
- the target is reachable without any code changes
- the benchmark number is a settled number

---

## 5. Recommended structure for the live benchmark doc

Use this sequence:

### Current verified state
What is installed, what runs, what is confirmed.

### Actual measured runs
Only the real benchmark numbers, no guesses.

### Root cause
Why the benchmark is underperforming.

### Next experiment
The next thing to try, with one command.

### Decision gate
A hard condition for whether to continue or change direction.

### Fallback path
If the current model family tops out, move to the next model or fine-tuning step.

---

## 6. What to move out of the main body

Move these into a short appendix or remove them from the live narrative:

- old version headers
- stale “zero new code” language
- any claim that `qwen2.5` is the correct alias
- any benchmark number not from the latest verified run
- any text that implies primary mode is already the stable baseline

---

## 7. Suggested wording for the live file

Use wording like this:

> The benchmark now runs reliably. The remaining issue is model routing and classification accuracy, not setup. The best current observed score is 71.0% in cross-check mode, and the next work item is to repair the routing logic and re-evaluate on the same dev set.

---

## 8. Suggested wording for the PRD

Use wording like this:

> The SciFact benchmark is no longer blocked by environment setup. The current limitation is predictive quality and NLI routing. The next step is to wire the benchmark to the intended NLI model path and re-run the dev set under a stable configuration.

---

## 9. Practical editing order

1. Update the SciFact accuracy plan first.
2. Update the PRD second.
3. Leave older documents untouched except for archive labels.
4. Re-run the benchmark only after the docs match the code path again.

---

## 10. Final rule
No benchmark number should remain in the live documents unless it has all of the following:

- the exact model tag
- the exact routing mode
- the sample size
- the date or run label
- a short note on what changed since the previous run

