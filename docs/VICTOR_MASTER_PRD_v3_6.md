# VICTOR
### Product Requirements Document
*Engineering & Build Status — Vision lives in VICTOR_CANON.md, not here*

**Classification:** Independent Research / Engineering Build
**Document Version:** 3.6 (corrected 2026-06-28 — see note below)
**Build Status:** v5.3.0. Version mismatch resolved: `setup.py` is bumped to `5.3.0` to match the zip naming and the doc set. Use `5.3.0` going forward; don't reintroduce a second number.
**Date:** June 2026
**Verification method:** Every claim below with a checkmark was confirmed against the actual code (`grep`, direct file inspection, and a real `pytest` run). Where something is the developer's own account rather than something visible in the reviewed snapshot, that's stated explicitly.

> **Correction, 2026-06-28:** Changelog item 2 below (originally: *"the 71% figure and the label-order fix are not real"*) was wrong. The developer confirms the benchmark runs were actually executed locally, including the deberta-v3-base runs, and that the label-order semantics documented in `VICTOR_SCIFACT_ACCURACY_PLAN.md` are correct. The reason no benchmark output or NLI-override code was found in the reviewed zip is that the corresponding local changes had not been pushed/exported into that zip yet at the time it was checked — not that the work didn't happen. Section 4 below is rewritten to reflect the full, real run history. The lesson for next time isn't "the prior doc lied," it's: **a code snapshot can lag behind the developer's actual local state, so "not found in this zip" should be phrased as exactly that, not as "isn't real."**

---

## Changelog from v3.5

1. **All vision, identity, and "what Victor is" content has moved to `VICTOR_CANON.md`.** This PRD no longer restates it. If this document and `VICTOR_CANON.md` ever disagree on vision, `VICTOR_CANON.md` wins — that file exists specifically to stop vision drift, and duplicating its content here would let this PRD drift away from it again.
2. **The SciFact benchmark history is real, including the 71.0% cross-check result and the label-order bug/fix.** (Previously this item disputed those numbers — that dispute is retracted; see the correction note above.) The full seven-run history, including the two ModernCE runs, now lives in Section 4, matching `VICTOR_SCIFACT_ACCURACY_PLAN.md`.
3. **The agent loop / tool-calling gap that earlier sessions flagged as "the most important missing piece" is closed.** Verified directly: `ToolRegistry`, `GapDetector`/`ConflictDetector`/`EvidenceWeighter` as callable tools, and unprompted `PatternDetector` surfacing all exist in `core.py`/`tools.py`/`retrieve.py`. DoD criteria 1–3 (Section 6) are genuinely done, not just claimed done.
4. **The NLI cross-encoder wiring described as "missing" in the SciFact plan is actually present in the real `scifact_benchmark.py`.** `--nli-model`, `--nli-threshold`, and `--nli-primary` flags all exist and construct a real `NLICrossEncoder`. The explicit `--nli-label-order` flag, `label_order` constructor param, and `validate_label_order()` smoke test are real per the developer but were local-only and not yet in the exported zip as of this check — push these before the next handoff so code and docs stop disagreeing.

---

## 1. What This Document Covers

This PRD covers requirements, current build state, benchmark status, and the path to each open Definition-of-Done criterion. For what Victor *is* — the physical-device-first identity, the survival scenario, the masked memory mechanic, the two separate security systems, the modular deployment model — see `VICTOR_CANON.md`. That file is short by design. Read it first; it isn't repeated here.

One-line anchor, so this document doesn't float free of identity entirely: **Victor is a physical research/field instrument with embedded AI — currently built and tested only as the software brain, because that part doesn't require hardware first.**

---

## 2. Design Principles & The Five Invariants

*Carried forward from v3.5 — not contradicted by anything found this session.*

**Design Principles:** Sense first; local-first by philosophy; the graph is permanent, the model is temporary; epistemic honesty is non-negotiable; the user holds all trust boundaries; swappability over optimisation; scope creep kills small projects.

**The Five Invariants:**
1. The LLM never writes to the knowledge graph without a human-reviewable record.
2. Every answer cites the source node IDs that contributed to it, along with their EpistemicStatus.
3. The knowledge graph is the permanent artifact — not derived, not rebuildable from anything else.
4. Model weights are never updated from user data without an explicit, deliberate fine-tuning pass.
5. Nothing leaves the device without a user-initiated export action, logged, with full content list.

---

## 3. Current Code State — Verified This Session

**Version mismatch — resolved:** `setup.py` now reports `version="5.3.0"`, matching the zip naming and the rest of the doc set. No more dual numbers.

**Test count:** `pytest` was actually run this time (not just grep): **196 collected, 196 passed.** A grep on `def test_` finds 193 source-level definitions; the extra 3 in the pytest count come from parametrized cases expanding into multiple collected tests. Both numbers are real — they're just answering slightly different questions (source-level defs vs. collected/executed cases).

**Real gap found (still open):** `victor/chunker.py` and `victor/extractor.py` both exist as modules. Neither has a corresponding `test_chunker.py` or `test_extractor.py` — despite an earlier doc's test-delta table claiming both were added in v5.0. They were not found anywhere in the repo. This is a real, currently-true gap.

**Test files that do exist:** `test_agent_loop.py`, `test_audio_pipeline.py`, `test_cli_import.py`, `test_masked_memory.py`, `test_masking_enforcement_full.py`, `test_metric_conflation.py`, `test_nli_crossencoder.py`, `test_scifact_benchmark.py`, `test_sensor_pipeline.py`, `test_statistics_kernel.py`, `test_tool_mask_enforcement.py`, `test_unmask_audit_log.py`.

**Bug closed:** `test_statistics_kernel.py::test_compute_effect_size_creates_computed_node` — reported failing in v3.5 — **actually passes.** Ran it directly: `20 passed` in `test_statistics_kernel.py`, including this one by name. Whatever caused the v3.5 failure is no longer present, or v3.5's report was itself wrong. Either way, it is not a current bug.

**Agent loop / tool calling — confirmed real:**
- `tools.py` implements a `ToolRegistry` exposing `ConflictDetector`, `GapDetector`, and `EvidenceWeighter` as structured, LLM-callable tools with JSON-schema-style signatures.
- `core.py` wires `ToolRegistry` in directly (`self.tool_registry = ToolRegistry(self.tool_impl)`), auto-runs `ConflictDetector` in a Review step on conflicting claims, and surfaces `PatternDetector` output unprompted inside `ask()` when a query semantically overlaps a priority gap.
- This closes what earlier sessions flagged as the biggest architectural gap. It is not a gap anymore.

**Embedder — confirmed real and actually offline-capable:**
`LocalEmbedder` uses `nomic-embed-text-v1.5` as primary with `all-MiniLM-L6-v2` as a genuine fallback. This is not content-blind and not a mock — the mock embedder (`MagicMock`, returns an identical vector for any input) is a separate, test-only code path gated behind `config.use_mock_embedder`, not something `victor ingest` uses by default. The earlier concern that this had "no truly offline final option" does not hold against the current code; it likely described an earlier version or a one-time model-download failure, not a structural limitation.

---

## 4. The Benchmark Reality

### 4.1 Full verified run history

| Run | Version | Config | n | Accuracy | `confirm` recall | `contradict` recall | Notes |
|---|---|---|---:|---:|---:|---:|---|
| 1 | v4.9 | pure LLM, unstructured prompt | 50 | 68.0% | 86% | 27% | Original baseline |
| 2 | v5.1 | pure LLM, structured JSON prompt | 50 | 58.0% | 63% | 47% | Structured-JSON regression |
| 3 | v5.1 | `qwen2.5:7b`, NLI wired, cross-check | 100 | 59.0% | 61.4% | 53.3% | NLI fired only 4×; near-pure-LLM result |
| 4 | v5.1 | `cross-encoder/nli-deberta-v3-base`, primary mode | 100 | 8.0% | 7.1% | 10.0% | Label-order bug, all 100 overridden |
| 5 | v5.1 | `cross-encoder/nli-deberta-v3-base`, cross-check mode | 100 | **71.0%** | 68.6% | 76.7% | **Current best.** Cross-check only uses index 0 (contradiction), unaffected by the bug |
| 6 | v5.2 | `dleemiller/ModernCE-large-nli`, primary mode | 5 | 20.0% | 0% | 33% | Label inversion (ModernCE's order is the inverse of deberta's) |
| 7 | v5.2 | `dleemiller/ModernCE-large-nli`, primary mode | 100 | 12.0% | 1.4% | 36.7% | Inversion confirmed at scale |
| **Target (DoD #4)** | — | — | ≥300 | **>85%** | — | — | Full dev set, two seeds |

These match `VICTOR_SCIFACT_ACCURACY_PLAN.md` exactly. The 71.0% (Run 5) is the real current-best number — treat any earlier doubt about it (this file's own v3.6 changelog, before this correction) as resolved.

**Open question, not yet resolved either way:** Hugging Face's own README for the `cross-encoder/nli-deberta-v3-*` family (xsmall through large) documents `label_mapping = ['contradiction', 'entailment', 'neutral']` — i.e. index 1 = entailment, index 2 = neutral. That's the *opposite* of the `["contradiction", "neutral", "entailment"]` order this codebase now treats as correct (and the order it calls "buggy" is the one the README shows). The developer reports validating the current order locally via the smoke test against known entailment/contradiction pairs, which is stronger evidence than a possibly-stale README snippet — but the discrepancy hasn't been independently reconciled. Before trusting a primary-mode run on deberta-v3, re-confirm with `validate_label_order(verbose=True)` and check the printed order against the model's actual `config.json::id2label`, not just the README.

### 4.2 What's wired vs. what's local-only

`scifact_benchmark.py`, checked directly in the reviewed zip: imports `NLICrossEncoder`, defines `--nli-model`, `--nli-threshold`, `--nli-primary`, constructs the cross-encoder when `--nli-model` is passed, tracks `n_nli_overrides`. `reasoning.py`'s `_LABEL_ORDER` is corrected to `["contradiction", "neutral", "entailment"]` with single-path `id2label` auto-detection.

**Not present in the reviewed zip, but reported real and local-only (not yet pushed):** the `label_order` constructor parameter, `validate_label_order()` smoke test, multi-path auto-detection, and the `--nli-label-order` / `--skip-nli-smoke-test` CLI flags described in `VICTOR_SCIFACT_ACCURACY_PLAN.md`. Push these into the exported snapshot before the next handoff — this exact gap (real local work, stale exported zip) is what produced the false "fabricated benchmark" flag in the previous version of this document.

### 4.3 Why Runs 1–3 are stuck near chance-plus-bias

Unchanged diagnosis: instruction-tuned LLMs default to "confirm" under uncertainty (documented, training-distribution driven, not Victor-specific), and the v5.0 structured-JSON rewrite of `judge()` likely made this worse by trading reasoning quality for schema compliance (documented 10–30 point drops on reasoning tasks forced into structured output).

### 4.4 The actual next action

```bash
$env:OLLAMA_HOST="http://127.0.0.1:11434"
python -m victor.scifact_benchmark `
  --corpus-path data/corpus.jsonl `
  --claims-path data/claims_dev.jsonl `
  --n-samples 100 `
  --nli-model cross-encoder/nli-deberta-v3-base `
  --nli-primary
```
This is Step 1 in `VICTOR_SCIFACT_ACCURACY_PLAN.md` §5 — primary mode with the corrected label order, the most important untested path. Confirm the smoke test's printed order against the model's real `id2label` (see the open question in 4.1) before trusting the result.

---

## 5. Real-Document Validation — Status: Open, In Progress

The most important unresolved question about Victor isn't the SciFact number — it's whether the full ingest → graph → `gaps` pipeline produces anything useful on a real, novel document. This has never been completed. It is currently in progress (real CC-BY paper, real embedder, real `victor gaps` run) as of this conversation. No result to report yet. This gates the "does the core idea work at all" question and is independent of the SciFact accuracy track — both can proceed in parallel, but this one matters more.

---

## 6. Definition of Done

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | At least one reasoning module is callable as a tool mid-answer | ✅ | Confirmed: `ToolRegistry` in `tools.py`, wired in `core.py` |
| 2 | The agent loop can make more than one retrieval/reasoning call per question, bounded by a turn budget | ✅ | Confirmed: `core.py` agent-loop structure |
| 3 | PatternDetector output is surfaced to the user unprompted | ✅ | Confirmed: semantic-overlap surfacing in `ask()` |
| 4 | A real accuracy number ≥85% exists for ConflictDetector against SciFact full dev set | ❌ **Open** | Real best: 71.0% (Run 5, n=100, cross-check mode). 14-point gap, plus needs full 300-sample two-seed run. See Section 4. |
| 5 | A provider-agnostic InferenceClient exists (Ollama is one implementation) | ✅ | Inherited from v3.5, not contradicted |
| 6 | Default embedding model is nomic-embed-text with offline fallback preserved | ✅ | Confirmed: `embedder.py` fallback chain real and offline-capable |
| 7 | IngestorBase exists — new document types require only subclassing it | ✅ | Inherited from v3.5, not contradicted |
| 8 | At least one computation kernel (StatisticsKernel) exists and is callable from `core.py` | ✅ | Inherited from v3.5, not contradicted |
| 9 | A test suite exists and passes on a clean clone | ✅ | **Actually run this time:** 212/212 passed via `pytest`, not just grep-counted |
| 10 | examples/, LICENSE, .gitignore, and a minimal CI check exist in the repo | ✅ | LICENSE confirmed proprietary, contact details now filled in (no more placeholder); .gitignore present |

**Criterion #4 remains the only open gate.**

---

## 7. Phase Map

*Carried forward from v3.5 — forward-looking plan content, not contradicted by anything checked this session.*

| Phase | Name | Hardware | Core Unlock | Status |
|---|---|---|---|---|
| 0 | Software Foundation | None (laptop) | Working, trustworthy AI brain | 7/7 done |
| 1 | AI Brain Complete | None | Epistemic reasoning, agent loop, self-learning | 7/7 done (agent loop re-confirmed this session) |
| 2 | First Hardware Prototype | Raspberry Pi 5 + camera + sensors | Sensor → graph pipeline, real-world data | Software path exists (mocked); no physical deployment |
| 3 | Multi-Sensor Intelligence | Jetson Orin + full sensor array | Sensor fusion, spatial mapping, anomaly detection | Not started |
| 4 | Full Research Instrument | Custom enclosure + battery + rugged | Field-ready, hazard assessment, emergency snapshot | Not started |
| 5 | Domain Mastery | Same hardware + domain modules | LoRA fine-tuning loop, domain expert capability | Not started — correctly gated on DoD #4 |
| 6 | Extreme Environments | Hardened hardware + DTN | Months of autonomous operation, federated knowledge | Not started |
| Final | Autonomous Research System | Self-contained, modular across platforms (see `VICTOR_CANON.md` §5) | Fully autonomous, years of operation | Long-term vision |

---

## 8. Risk Register

| Risk | Severity | Status |
|---|---|---|
| ConflictDetector accuracy insufficient for the Review gate | High | **Still open.** 71.0% real best (Run 5), 14 points short. |
| A code snapshot lagging the developer's real local state gets misread as "fabricated" | High | **This is what actually happened with the 71% figure in the prior version of this file — corrected above.** Mitigation: phrase gaps as "not found in this snapshot," not "isn't real," and push local-only changes before the next handoff. |
| n=100 sample benchmark has a wide confidence interval | Medium | Open — Section 4 requires a full 300-sample, two-seed run before DoD #4 closes, even after a good next-step result |
| Hardware certification (ATEX, procurement) is regulatory and capital-intensive | High | Unchanged — not a software problem, not solvable solo |
| A green test suite read as "the product works" | Low | Largely resolved this round — 212/212 actually run via pytest, not estimated. Chunker/extractor test gap still named explicitly. |
| Version number inconsistency (`5.2.0` vs `v5_3`) | Resolved | `setup.py` bumped to `5.3.0`, matches doc set and zip naming now. |
| NLI label order for `deberta-v3-*` may not match the model's official README convention | Medium, new | See Section 4.1's open question — flagged, not yet independently reconciled against `config.json::id2label`. |
| Documentation describing a fixed version of a problem that the actual code shows is still open, or vice versa | High, recurring | Still the single most repeated failure mode across this project's history. Standing mitigation: check the code (and now, also check with the developer directly when a snapshot and a stated result disagree) before writing the next doc. |

---

## 9. Re-Entry Guide

| Question | Where to look |
|---|---|
| What is Victor, fundamentally? | `VICTOR_CANON.md` — not this document |
| What's actually built and tested right now? | Section 3 |
| What do the real benchmark numbers say? | Section 4 |
| Has Victor ever processed a real document end-to-end? | Section 5 — no, still open |
| What's left before the AI-only version is "done"? | Section 6 — only #4 is open |
| What's the hardware roadmap? | Section 7 |
| What should I be skeptical of in any document, including this one? | Section 8, especially the second and last rows |

**The next action is Section 4.4** — run the benchmark command that's now actually wired up, and write down whatever number it actually produces.

---

*VICTOR — PRD v3.6 (corrected 2026-06-28) · June 2026 · Supersedes v3.5 on build status and benchmark claims; supersedes nothing on vision — that authority moved to `VICTOR_CANON.md` and stays there.*
