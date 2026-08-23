# VICTOR — What Is Built
*Code version: v5.3 · Date: June 2026*

---

> This document is updated every time the code changes.
> Check the version header before reading. An outdated version of this document is worse than no document.

---

## The One-Line State

Phase 0 and Phase 1 are complete. 264/264 tests pass (actual `pytest` run). Best SciFact accuracy so far: **71.0%** (cross-check mode, n=100); DoD criterion #4 (>85%) is still open. **Real research data has now been ingested** — see Results Log, 2026-08-23 — and the full retrieve→reason→report loop was exercised end to end against a real arXiv paper on local `qwen2.5:7b`. A web console (`victor serve`) now makes the graph and the masked memory mechanism visible.

<!-- CURRENT_TEST_COUNT -->264<!-- /CURRENT_TEST_COUNT -->

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
│   ├── web.py             — Web console: stdlib HTTP server + JSON API. Redaction enforced
│   │                        server-side (VictorAPI._redact / _redact_meta), RevealSession
│   ├── webui/             — index.html, app.js, style.css. Vanilla JS, no CDN, no build step
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
| Web console (HTTP API + UI) | ✅ Built | `web.py` — stdlib `http.server`, no new deps. `victor serve` |
| Graph visualization | ✅ Built | `webui/app.js` — canvas force layout; masked nodes drawn hollow |
| Masked memory made operable | ✅ Built | Vault view, session reveal vs permanent unmask, audit trail |
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

### Masking content leak [FIXED 2026-08-12]
Was: `_anchor_for()` in `tools.py`, `_masked_summary()` in `reasoning.py`, and `_make_anchor()` in `retrieve.py` all leaked up to 40 characters of masked node labels in the anchor text. For example, a masked claim "This is SECRET research finding..." would show `[MASKED — claim 'This is SECRET research finding about quantum ent...' — content withheld]`. The test only checked that the FULL secret wasn't in the string, so it passed even with the truncated leak. Fixed by removing the truncated label from all three methods. Anchors now show `[MASKED — claim — content withheld. Use 'victor unmask <id>']` with no content leakage.

> **Open question, flagged 2026-06-28, not yet resolved:** Hugging Face's own README for this model family documents `label_mapping = ['contradiction', 'entailment', 'neutral']` — the order this doc calls buggy. The order above was validated locally via the smoke test against known pairs, which is good evidence, but it directly contradicts the vendor README. Before relying on a primary-mode deberta-v3 run, print `model.config.id2label` directly and confirm which order the actual checkpoint reports — don't take either source on faith.

Additionally, `dleemiller/ModernCE-large-nli` outputs labels in `["entailment", "neutral", "contradiction"]` order — the inverse of the fallback default. Auto-detection from `id2label` silently fails for this model (attribute path is different). v5.3 adds explicit `--nli-label-order` flag and a `validate_label_order()` smoke test that catches this before the benchmark loop starts. *(Note: this flag/method/param were confirmed local-only, not yet pushed, as of the last code review — push them so the next zip export actually contains them.)*

---

## Divergences From the Original Conception — Masked Memory

*Checked against `VICTOR_ORIGINAL.md` §4, which is the document that wins on
matters of intent. Recorded 2026-08-23.*

`VICTOR_ORIGINAL.md` calls the masked memory graph "the most original idea in the
entire conception" and warns that earlier sessions "dropped [it] as a detail".
Measuring the code against the source text rather than against later PRDs:

| Original framing | Status |
|---|---|
| "every experiment… connects through a relation" — relational anchors stay live | ✅ Masking never touches edges. Verified by test. |
| Content withheld until called | ✅ Enforced at retrieval, in the CLI, and at the API boundary. |
| "one recording only getting through when the user decides to call it" | ⚠️ Partial. `unmask` is a permanent declassification, not a momentary surfacing. The web console adds a **session reveal** that surfaces one node without writing to the graph, which is closer to the original sense. The CLI still only has the permanent verb. |
| Masking as the default posture of memory | ❌ Not built. `is_masked` defaults `False`; you opt in per node. The original describes the inverse — memory that is masked *by nature*, with recall as the act that surfaces it. This is the largest remaining gap, and it is a design decision, not a bug: flipping the default changes every retrieval path. |
| "lets the user decide what the AI has to publish" — sovereign switch | ⚠️ Partial. Masking governs what reaches the LLM; `export` is still unencrypted and has no per-node publish gate. |
| "sovereign cybersecurity model" — defensive system | ❌ Not built. Distinct from the publish switch per §5 of the original; nothing implements it. |

### Masking leaks found and fixed 2026-08-23

Two more instances of the same bug class that was fixed on the anchor path in
August. Both were found by scanning *whole serialised responses* for the secret
rather than checking individual fields — the technique that catches leaks
through fields nobody thought to check.

1. **`victor list-masked` printed 60 characters of every masked node's label.**
   Browsing the vault was a way to read the vault. Now prints `████ content withheld`.
2. **`/api/node` returned raw node metadata for masked nodes.** Claim nodes carry
   the extractor's `metric`/`value`/`direction` fields, so the label was withheld
   while `{"value": "8.70%, -19.0%, -17.6%"}` was published. For a scientific claim
   the metric *is* the content. Fixed with an allowlist (`STRUCTURAL_META_KEYS`),
   not a denylist — a denylist fails open every time the extractor learns a field.

### Known asymmetry — not yet fixed

`Victor.mask()` deletes the node's chunks from ChromaDB to close the embedding
covert channel. `Victor.unmask()` does **not** re-embed them. A mask→unmask cycle
therefore permanently removes the node from vector search; it survives only as a
graph node reachable by semantic query and hop expansion. This is data loss on a
reversible-looking operation.

---

## What Is NOT Built (Confirmed Absent)

- Spectral ingestion — no spectrometer pipeline.
- Authentication on the web console — it binds loopback only and has no login. Do not bind it to `0.0.0.0`.
- Masking as the *default* memory posture — `is_masked` defaults to `False` and
  masking is opt-in per node. `VICTOR_ORIGINAL.md` §4 describes memory as masked
  by default with content surfacing only on explicit call. See "Divergences".
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
| 2026-08-12 | Masking leak fixed | Removed 40-char label leak from `tools.py`, `reasoning.py`, `retrieve.py`. Anchors now show `[MASKED — claim — content withheld]` with no content leakage. 212/212 tests pass. |
| 2026-08-12 | SciFact Run 6 — v5.3, deberta-v3-base, NLI primary mode (label order fixed), n=100 | **8.0%** — All 100 samples predicted "inconclusive" (neutral). Label order smoke test PASSED. Root cause: DeBERTa-v3-base NLI fine-tuned on MNLI (short sentence pairs) cannot handle long scientific text (200-word abstracts). Cross-encoder defaults to neutral on every input. Confirms cross-check architecture is the correct approach for this model. |
| — | SciFact DoD #4 (>85%) | **Not yet closed.** Current best: 71.0% (cross-check mode). Primary mode conclusively ruled out for DeBERTa-v3-base on long text. Next: self-consistency voting, threshold sweep, or fine-tuning. |
| 2026-08-23 | Four core-loop defects fixed (`8ce0541`) | Masked nodes crashed `answer_full()` (`epistemic_status=None` → `.upper()`); gap ranking read `importance_score` at the wrong nesting level so every gap scored 0.0; `top_queried_sources` was never written *and* emitted dicts against tuple-unpacking consumers; Ollama sampling temperature was the daemon's 0.8, not Victor's. +19 regression tests, 17 of which fail on the pre-fix tree. |
| 2026-08-23 | **First real-document ingest** | `data/arxiv_selective_cot_medical_qa.txt` → 4 chunks, **13 claims, 15 concepts, 29 nodes / 28 edges** in 2m49s on an RTX 4050 (6 GB) with `qwen2.5:7b`. Answers PRD v3.6 §5's "most important unresolved question": Victor does produce usable structure from a real paper. Extraction quality notes below. |
| 2026-08-23 | Real query through the full loop | *"How much does Selective CoT reduce inference time, and what does it cost in accuracy?"* → correct, grounded, cited answer in 1m40s, **and the PatternDetector fired unprompted** to flag that the underlying claim has no experimental confirmation. The epistemic layer earns its place: the system answered *and* qualified the answer. |
| 2026-08-23 | Web console shipped | `victor serve` — stdlib-only HTTP server, canvas graph view, gaps, vault, audit. 33 tests, centred on the redaction boundary. Two masking leaks found and fixed in the process (see Divergences). |

### Extraction quality — observed on the first real paper

Worth recording because the numbers above say nothing about whether the claims
are *good*. From the 13 extracted:

- **Duplicates survive dedup.** `"wall-clock time drops by approximately 13-45%"`
  is a literal substring of a longer extracted claim, and both were kept.
  `claim_similarity_threshold` is 0.75 cosine, which does not catch containment.
- **Section headings contaminate claims.** One claim begins
  `"2.2 Selective Chain-of-thought Medical questions can be broadly grouped…"` —
  the heading was absorbed into the claim text.
- **Sentence fragments.** One claim starts mid-sentence: `"more output tokens,
  higher latency, and…"`, orphaned from its subject by a chunk boundary.
- **Concept nodes fragment on surface form.** `Selective Chain-of-Thought (Selective CoT)`,
  `Selective Chain-of-Thought`, and `Selective CoT` are three separate nodes for
  one concept; likewise `computational cost` / `computational costs`. This
  directly suppresses the connection density that `VICTOR_THEORY_v1` says the
  value scales with.

None of these are crashes, which is why 264 green tests say nothing about them.
They are the next real work.

---

## Version History of This Document

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial document created |
| June 2026 | v5.0 | Both bugs fixed. PatternDetector wired. Audio ingestor built (LibrosaFeatureClassifier). Tests: 147 → 177. |
| June 2026 | v5.1 | NLICrossEncoder added. scifact_benchmark.py wired with --nli-model flags. Tests: 177 → 196. |
| June 2026 | v5.2 | _LABEL_ORDER corrected for deberta-v3-base. Auto-detection via id2label added. SciFact Runs 3–5 completed. |
| June 2026 | v5.3 | label_order constructor param. validate_label_order() smoke test. --nli-label-order / --skip-nli-smoke-test CLI flags. 3-path auto-detection. Known model label orders documented. |

*VICTOR_WHAT_IS_BUILT.md · v5.3 · Updated 2026-08-12*
