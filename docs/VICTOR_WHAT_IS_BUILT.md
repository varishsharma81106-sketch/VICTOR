# VICTOR — What Is Built
*Code version: v5.4 · Date: August 2026*

---

> This document is updated every time the code changes.
> Check the version header before reading. An outdated version of this document is worse than no document.

---

## The One-Line State

Phase 0 and Phase 1 are complete. 421/421 tests pass (actual `pytest` run, 58s). Best SciFact accuracy so far: **71.0%** (cross-check mode, n=100); DoD criterion #4 (>85%) is still open. **Real research data has been ingested** — see Results Log, 2026-08-23 — and the full retrieve→reason→report loop was exercised end to end against a real arXiv paper on local `qwen2.5:7b`. A web console (`victor serve`) makes the graph and the masked memory mechanism visible, and a **referral layer** (`victor consider`, `/api/deliberate`, the console's Machine view) makes Victor work through its own masked memory without a human clicking anything. A **sensor simulation** (`victor simulate`) runs Victor inside a machine for 40 ticks so the compounding, contradiction, gap and masking claims can be watched instead of asserted. Measured at **20,000 nodes** — see Scale.

<!-- CURRENT_TEST_COUNT -->421<!-- /CURRENT_TEST_COUNT -->

---

## What Exists — Full File Map

```
victor/
├── victor/
│   ├── models.py          — EpistemicStatus (5-tier), ObservationResult, ConflictResult, ConflictJudgment
│   ├── graph.py           — VictorKnowledgeGraph, add_observation(), freeze/unfreeze, atomic save, temporal decay, mask/unmask
│   ├── core.py            — Victor controller, ingestion, query, patterns, stats, AgenticRetriever wired
│   ├── cli.py             — Full Rich CLI: ingest, ask, gaps, observe, inspect, stats, mask, unmask,
│   │                        consider (referral pass), simulate (sensor run), serve
│   ├── referral.py        — ReferralPoint / ReferralTable / ReferralDesk / Dereference /
│   │                        DeliberateReasoner / PolicyChooser / Fragment / ReferralLedger.
│   │                        The machine's own path through masked memory, one point at a time
│   ├── simulation.py      — SimulatedSensor (real StreamIngestorBase), Scenario, WorldState,
│   │                        STRANDED_SITE, per-tick belief telemetry, fragments() → referral
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
│   │                        server-side (VictorAPI._redact / _redact_meta), RevealSession.
│   │                        /api/search, /api/deliberate (+ sensor fragments, redacted)
│   ├── webui/             — index.html, app.js, style.css. Vanilla JS, no CDN, no build step.
│   │                        Views: Graph, Ask, Machine, Gaps, Vault, Audit
│   └── config.py          — VictorConfig
├── tests/                               — 421 tests total
│   ├── test_web_console.py          — 90  API, redaction boundary, search, /api/deliberate
│   ├── test_referral.py             — 46  referral table, ledger, chooser, loop, fragments
│   ├── test_nli_crossencoder.py     — 35
│   ├── test_sensor_pipeline.py      — 28
│   ├── test_simulation.py           — 26  scenario determinism, belief revision, masking
│   ├── test_scifact_benchmark.py    — 25  (machinery only, not real accuracy)
│   ├── test_core_loop_regressions.py— 25  17 of these fail on the pre-fix tree
│   ├── test_audio_pipeline.py       — 25
│   ├── test_scale_persistence.py    — 22  large-graph behaviour, save/load, slicing
│   ├── test_masked_memory.py        — 21
│   ├── test_agent_loop.py           — 21
│   ├── test_statistics_kernel.py    — 20
│   ├── test_masking_enforcement_full.py — 13
│   ├── test_unmask_audit_log.py     — 8
│   ├── test_tool_mask_enforcement.py— 6
│   ├── test_metric_conflation.py    — 5
│   └── test_cli_import.py           — 5
├── tools/
│   ├── bench_scale.py               — scale harness: build/save/load/query at 1k–20k+ nodes
│   └── arxiv_scan.py                — arXiv API competitor scan (WebSearch is policy-blocked here)
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
| Referral point — a handle that publishes what memory *is*, not what it says | ✅ Built | `referral.py` → `ReferralPoint`, `ReferralTable` |
| "One point at a time" — serialised dereference with a stated reason | ✅ Built | `referral.py` → `DeliberateReasoner`, budget-bounded |
| Real-time fragmentation joining the same processing stage | ✅ Built | `referral.py` → `Fragment`; `simulation.py` → `Simulation.fragments()` |
| Every request logged, grants and refusals alike | ✅ Built | `referral.py` → `ReferralLedger` (JSONL, `content` popped before write) |
| The machine does the understanding, not the operator | ✅ Built | `victor consider`, `/api/deliberate`, console **Machine** view. Nobody clicks "reveal" |
| EpistemicStatus hierarchy actually *used* in ranking | ✅ Built | `EpistemicStatus.weight` → `ReferralPoint.tier_weight`. Had zero call sites before v5.4 |
| Reality → Artifact loop run for longer than one frame | ✅ Built | `simulation.py` → `victor simulate --ticks 40` |
| Scale measured rather than assumed | ✅ Built | `tools/bench_scale.py`; 22 tests in `test_scale_persistence.py`. See Scale |
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
| "one recording only getting through when the user decides to call it" | ⚠️ Partial. `unmask` is a permanent declassification, not a momentary surfacing. The web console adds a **session reveal** that surfaces one node without writing to the graph, which is closer to the original sense. The referral layer adds the *serialised* half — one point dereferenced at a time, each with a stated reason. The CLI's `unmask` is still the permanent verb. |
| Masking as the default posture of memory | ⚠️ Partial as of v5.4. `is_masked` still defaults `False` for the graph in general, so for ingestion it remains opt-in. But `Scenario.sensitive` in `simulation.py` masks a reading **on arrival**, before it is ever readable, which is the original framing implemented for one path. Flipping the graph-wide default still changes every retrieval path, so it stays a design decision rather than a bug. |
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

## The Referral Layer — built 2026-08-23

*`victor/referral.py`, 46 tests in `tests/test_referral.py`.*

This is the diagram of the holed slab, implemented. Memory is a slab with holes
in it; every line out of it — through a hole or not — converges on one **referral
point**; from there it goes to data processing and then to the reasoning model;
a single hard constraint says **one point at a time**; and real-time readings are
fragmented and fed into the same stage.

| Piece of the diagram | Class | What it actually does |
|---|---|---|
| The holed slab | `ReferralDesk.offer()` | Builds a table over graph nodes *and* live fragments. Masked nodes are re-added structurally, because `semantic_query` skips them (`graph.py:753`) |
| The referral point | `ReferralPoint` | Publishes id, type, epistemic standing, confidence, degree, age, relevance and a descriptor. For a masked node the descriptor is `REDACTED`. Never carries content |
| One point at a time | `DeliberateReasoner.run()` | A serialised loop: choose one ref, state a reason, ask, get content or a refusal, repeat until the budget is spent |
| Data processing → reasoning model | `PolicyChooser` / an LLM chooser | Either can drive the loop. `PolicyChooser` runs with no model at all, so the mechanism is testable without inference |
| Real-time fragmentation | `Fragment`, `Simulation.fragments()` | A live reading enters the *same* table and competes on the same properties as a two-year-old paper |
| The audit line | `ReferralLedger` | One JSONL line per request, grants and refusals alike. `content` is popped before write, so the ledger is not a back door |

### The property that makes it a boundary and not a delay

A masked point's relevance is **inherited from a visible anchor × 0.6** — it is
never computed from its own text. That is deliberate and it is the whole
security argument. If a masked node were ranked by matching the query against
its hidden content, then ranking *is* an oracle: an attacker asks a thousand
questions, watches the node rise and fall, and reconstructs the content one
query at a time. Test
`test_naming_the_secret_carries_no_extra_information` probes with four query
wordings — including the secret's verbatim label — and asserts the masked/anchor
ratio stays exactly 0.6 in all four. What the attacker learns is the anchor's
relevance, which was already published.

### Where you can see it

```bash
victor consider "what do we know about the catalyst?" --budget 3 --sensors 10
```

and the **Machine** tab of `victor serve`, which renders three panels: what was
offered, what the machine did with each point, and what it concluded. Grants and
refusals get equal visual weight on purpose — a machine that renders what it was
denied in muted grey is telling you it got everything it wanted.

The only unmask authority the endpoint has is `RevealSession.is_revealed`; the
default is refuse-all. A reasoning pass that could silently unmask would not be
a trust boundary, it would be a delay.

**Two real defects were found by exercising this rather than reading it:**

1. `DeliberateReasoner._final()` returned `""` whenever there was no LLM, so a
   policy pass that spent its whole budget ended with an empty answer and no
   account of what had been refused. Fixed by deferring to `chooser.conclude()`.
2. Live fragments took all three anchor slots (a fragment has no neighbourhood),
   so during a busy sensor tick — exactly when stored context matters most —
   masked memory stopped being offered at all and the table went quiet about it.
   Anchors are now restricted to points that are actually in the graph.

Both have regression tests.

---

## The Simulation — Victor inside a machine

*`victor/simulation.py`, 26 tests. `victor simulate --scenario stranded-site --ticks 40`.*

`VICTOR_CANON` describes Victor as a physical research device. Only the software
brain existed, and `sensors.py` had never run for longer than a single frame — so
every claim that depends on *accumulation* was unobservable. This runs the loop.

`STRANDED_SITE` is a survey unit alone at a remote site with no uplink. Four
instruments of stated reliability (0.68 to 0.94), each with named confusions and
named blind spots, watch four things: the air, the shelter, the power cell, and a
commercially sensitive sample. Two of the four **change state partway through**,
so the run shows Victor revising a belief rather than merely piling up agreement.
Same seed, same run — no hardware, no network, no LLM.

What each thesis looks like when you watch it:

- **Compounding** — `belief` firms up and `margin` widens tick over tick.
- **Contradiction** — `mic-array` at 0.68 reliability argues with `spectrometer`
  at 0.94, and the disagreement is visible rather than averaged away.
- **Gaps** — `power-cell` degrades at tick 26, so a 40-tick run ends with a
  belief that is correct and *underevidenced*, and says so.
- **Masking as default posture** — `palladium-rich matrix` is masked **on
  arrival**, not after the fact. This is the one place in the codebase where
  `VICTOR_ORIGINAL.md` §4's actual framing is implemented.

`SimulatedSensor` implements the real `StreamIngestorBase` and its output travels
the real `add_observation()` path, so a bug there fails here too. A simulation
that used a private shortcut would prove nothing about shipping code.

`Simulation.fragments()` is the join to the referral layer: the freshest reading
per entity, offered as `Fragment`s. A reading of a sensitive reading is masked on
arrival, so it reaches the table as a handle with no content — the machine can
see a live observation exists and is relevant, ask for it, and be refused.

---

## Scale — measured, 2026-08-23

Every performance number Victor had ever reported about itself came from a graph
of a few dozen nodes. `python tools/bench_scale.py 1000 5000 20000`, on this
machine:

| nodes | edges | build s | save s | load s | JSON MB | query ms | 2-hop ms | /api/overview ms | /api/graph ms |
|---|---|---|---|---|---|---|---|---|---|
| 1,000 | 1,331 | 0.09 | 0.04 | 0.06 | 0.6 | 0.7 | 0.2 | 1.5 | 5.5 |
| 5,000 | 6,665 | 0.34 | 0.19 | 0.22 | 3.0 | 1.9 | 0.1 | 6.6 | 5.8 |
| 20,000 | 26,667 | 1.09 | 0.59 | 0.61 | 12.1 | 2.8 | 0.1 | 35.7 | 18.5 |

Reading it honestly:

- **Nothing here is the bottleneck at 20k.** Load is 0.6s, a semantic query over
  the whole graph is under 3ms, and 2-hop expansion is flat because it is local.
- **`query ms` excludes embedding.** The harness uses a deterministic
  hash-seeded embedder so it times Victor's code, not a model download. In real
  use, one `LocalEmbedder.embed()` call dominates this column by two orders of
  magnitude. The graph is not what makes queries slow.
- **`/api/overview` is the one growing linearly** — 1.5 → 6.6 → 35.7ms. It walks
  every node to compute statistics. Fine at 20k, worth caching before 200k.
- **The JSON file is the real ceiling.** 12.1 MB at 20k nodes, whole-file
  rewritten atomically on every save. At 200k that is a ~120 MB rewrite per
  save. This is the thing that will need to change first, and it is a storage
  decision, not a tuning one.

---

## What Is NOT Built (Confirmed Absent)

- Spectral ingestion — no spectrometer pipeline. (`simulation.py` has a
  `spectrometer` *sensor spec* at 0.94 reliability; that is a simulated
  instrument, not an ingestion path for real spectra.)
- Authentication on the web console — it binds loopback only and has no login. Do not bind it to `0.0.0.0`.
- Masking as the *graph-wide default* memory posture — `is_masked` defaults to
  `False` and masking is opt-in per node on the ingestion paths. The simulation
  masks on arrival; nothing else does. See "Divergences".
- Per-audience authorization — the mask is global, not per reader. Two of the
  papers in `VICTOR_COMPETITIVE_2026-08.md` do this and Victor does not.
- Non-amplification / provenance-laundering checks — `origin` is recorded but
  never re-verified, which is the exact failure arXiv 2607.29167 names.
- Incremental graph persistence — every save rewrites the whole JSON file. See Scale.
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
| 2026-08-23 | Competitive claim re-checked and **found false** | `VICTOR_STRATEGY.md`'s "no competitor has a redaction/trust boundary. Zero." was two months stale. `tools/arxiv_scan.py` found five papers in five months that implement one. Corrected claim, narrower and still true: Victor is the only one combining redaction with a **live graph anchor** — the masked node keeps its edges, type, degree and place in reasoning. See `VICTOR_COMPETITIVE_2026-08.md`. |
| 2026-08-23 | Scale measured for the first time | 1k / 5k / 20k nodes via `tools/bench_scale.py`. Load 0.61s and query 2.8ms at 20k; `/api/overview` grows linearly (35.7ms); the 12.1 MB whole-file atomic rewrite is the real ceiling. +22 tests in `test_scale_persistence.py`. See Scale. |
| 2026-08-23 | Sensor simulation shipped | `victor simulate` — `STRANDED_SITE`, four instruments of stated reliability, two entities that change state mid-run, one reading masked on arrival. Runs the real `StreamIngestorBase` → `add_observation()` path. 26 tests. Makes compounding / contradiction / gaps / masking watchable instead of asserted. |
| 2026-08-23 | Referral layer shipped | `victor/referral.py` + `victor consider` + `/api/deliberate` + console **Machine** view. The machine works through its own masked memory one point at a time and states a reason for each request; nobody clicks "reveal". 46 tests. `EpistemicStatus.weight` finally has a call site. Two real defects found by exercising it: an empty policy conclusion, and live fragments starving stored masked memory out of the anchor slots. |
| 2026-08-23 | Test-suite integrity repair | Two duplicate class names in `test_web_console.py` (`TestSearchIsNotAnOracle`, `TestGraphSlicing`) were silently shadowing **11 tests** — Python keeps the last definition. Merged and renamed. One un-shadowed test then failed and was correct to: its own comment asserted "paper1 outranks the claims", but CLAIM is 0.70 and PAPER is 0.65. The code was right and the assertion had never run to say otherwise. |
| 2026-08-23 | Full suite green at v5.4 | **421 passed** in 58s, 1 unrelated `chromadb`/`asyncio` DeprecationWarning. Up from 264. |

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

None of these are crashes, which is why 421 green tests say nothing about them.
They are the next real work — and they are still open at v5.4.

---

## Version History of This Document

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial document created |
| June 2026 | v5.0 | Both bugs fixed. PatternDetector wired. Audio ingestor built (LibrosaFeatureClassifier). Tests: 147 → 177. |
| June 2026 | v5.1 | NLICrossEncoder added. scifact_benchmark.py wired with --nli-model flags. Tests: 177 → 196. |
| June 2026 | v5.2 | _LABEL_ORDER corrected for deberta-v3-base. Auto-detection via id2label added. SciFact Runs 3–5 completed. |
| June 2026 | v5.3 | label_order constructor param. validate_label_order() smoke test. --nli-label-order / --skip-nli-smoke-test CLI flags. 3-path auto-detection. Known model label orders documented. |
| Aug 2026 | v5.3.1 | Four core-loop defects fixed. Web console shipped (`victor serve`); two masking leaks found and closed. Tests: 196 → 264. |
| Aug 2026 | v5.4 | Referral layer (`referral.py`, `victor consider`, `/api/deliberate`, Machine view). Sensor simulation (`simulation.py`, `victor simulate`). Scale harness and first real scale numbers to 20k nodes. Competitive claim re-checked against arXiv and corrected. 11 shadowed tests recovered. Tests: 264 → **421**. |

*VICTOR_WHAT_IS_BUILT.md · v5.4 · Updated 2026-08-23*
