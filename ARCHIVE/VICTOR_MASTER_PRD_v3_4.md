# VICTOR

### Product Requirements Document

*A Local-First Research Intelligence System*

**Classification:** Independent Research / Engineering Build
**Document Version:** 3.4 — Master PRD, corrected against verified codebase and direct test execution; extended with a researched technical lever for closing DoD criterion #4
**Build Status:** v4.9 shipped. Phase 0 at 7/7 *(corrected v3.4: repo scaffolding confirmed present, not absent)*. Phase 1 at 7/7 (masked memory graph added — not in v3.1 scope). CLI was broken on every invocation path from v4.6 through v4.8 (see Section 5); fixed in v4.9.
**Date:** June 2026
**Architecture:** Sense → Fuse → Structure → Reason → Compound

*"Every other AI resets. Victor compounds — and shows you why."*

> **What changed from v3.1:** the vision, principles, invariants, and hardware phase map (Sections 2–4, 9, 12–13) did not change — they were already right. What changed is Section 5 onward: several "Not done" items were actually done, one major system (masked memory) wasn't in v3.1 at all, and the real remaining gap turned out to be a benchmark, not a feature. Every status mark below was checked against the actual `victor_v4.6` codebase — 40 files, 142 passing tests, run from a clean extraction — not against a prior summary document.
>
> **What changed in v3.3:** this version corrects three numeric errors that survived the v3.2 "verified" pass (44 files → 40; 16 of 41 features → 16 of 40; 23 not-started → 22 not-started), fixes an internal contradiction in the EpistemicStatus tier count (Section 5 said 5 tiers and matched the code; Section 10 said 6 tiers and didn't), and documents a CLI import bug that made `victor/cli.py` fail on every invocation path — `python -m victor.cli`, `from victor import cli`, and the installed console script — from v4.6 through v4.8, undetected because no test in the 142-test suite ever imported it. All of the above were found by actually running the code and the test suite, not by re-reading the document. A new Section 24 addresses competitive and market-positioning gaps that no prior version of this document covered at all.
>
> **What changed in v3.4:** the 68.0% SciFact baseline referenced throughout this document as "not yet run" has now been run once (see `SCIFACT_BENCHMARK_RESULTS.md`) and diagnosed as an agreement bias — the model under-calls `contradict`. `ConflictDetector.judge()` has since been rewritten (structured JSON output, reasoning-before-label, explicit definitions, worked example) and re-verified end-to-end (176/177 tests pass; the one failure is the pre-existing, unrelated `compute_effect_size` bug noted in Section 17). A real re-run number is still pending — that part of criterion #4 has not changed. What's new in this version is Section 22's tech-stack table gaining one row, and Section 24 gaining 24.5–24.6: a researched, zero-new-dependency technical lever (an NLI cross-encoder already reachable through the existing `sentence-transformers` dependency) that targets the exact agreement-bias failure mode found in the SciFact diagnosis, plus a hardware-requirements note for the eventual LoRA phase. Neither addition moves a DoD checkbox; both are documented here so the next session doesn't have to re-derive them.

---

## 1. Executive Summary

Victor is a local-first research intelligence system — eventually a physical device with embedded sensors, right now a software brain. The AI reads from an accumulated, structured knowledge graph of papers, experiments, claims, and notes. Every answer is traceable to a source node. The graph is permanent; the model is swappable.

The original vision goes further: a researcher carries one device into any environment. It scans with multiple sensors simultaneously. The AI processes locally, reasons over everything accumulated from this researcher's own work, and gives answers with full provenance. Nothing leaves the device without the user's explicit permission. It gets smarter from the researcher's own usage, not from the internet.

This document is the single source of truth. It supersedes all prior PRDs, assessments, strategy documents, and framing documents. Pick it up at any time and have everything needed to resume.

| What it looks like on the surface | What it actually is | Why this matters |
|---|---|---|
| An AI research assistant | A knowledge graph with a reasoning loop on top | Intelligence lives in the graph, not the model |
| A clever answer | A traceable answer — citation matters more than fluency | Every claim cites the source node that generated it |
| Continuous self-learning | Accumulated structured context; model weights never update unsupervised | Growth is inspectable and reversible |
| A chatbot or document reader | A local-first research instrument | Offline-first by philosophy, not constraint |
| *(new, v4.6)* A static knowledge store | A graph with relational anchors that stay live while content stays hidden until called | The masked memory mechanic — implemented and well-tested, but not a unique market position; see Section 24 |

---

## 2. The Real Vision

Pulled from the original framing, stripped of all other context, the AI-specific part in plain terms:

*"Instead of what a normal LLM is based on, we fine-tune it… it tries to understand itself and enhance its own mind throughout the user's chats and knowledge. Instead of doing multiple amount of data sources, it has a pre-fixed baseline. After that, the user provides info… and it tries to learn itself and enhance itself even further without even the user telling it."*

Three concrete requirements are in there. Everything in this document serves these three things and nothing else:

1. **A baseline model** — fixed starting point, not retrained from scratch per user.
2. **It grows from the user's own accumulated material** — not from scraping the internet, from this user's chats, papers, and notes specifically.
3. **It enhances itself from usage without being explicitly told to** — the growth is a side effect of normal use, not a separate training chore the user runs.

The broader device vision: a researcher in a lab, on a vessel, in a hazardous facility, or on another planet carries one device. It scans the environment with multiple sensors simultaneously. It understands what it is looking at, not just what it measured. It stores everything locally, with full provenance. It connects what it finds today to what it found three months ago. It tells the researcher what is missing from their knowledge. It never phones home. It never forgets. Over time, in the specific domain of that researcher's work, it gets smarter.

The document ingestion and note analysis that exists in v4+ is the first input channel — the cheapest one to build because it needs no hardware. Every architectural decision in v3 through v4.6 was made to ensure that when sensors are connected, the system can absorb their output without rebuilding anything. That is the design constraint that governs every decision in this document.

---

## 3. What Victor Is and Is Not

### Victor is

- A local-first research intelligence system built for a single technical user — researcher, engineer, serious practitioner.
- A physical research instrument with embedded AI (eventually) — a tool, not a service.
- A structured knowledge graph that accumulates from sensors, experiments, literature, and conversations.
- A provenance engine: every answer cites the specific knowledge nodes that contributed to it.
- A claim-to-evidence linker: connects what the literature says to what experiments found.
- A self-improving domain expert: gets better at its specific domain from the researcher's own work.
- A computation engine: performs statistics, uncertainty propagation, and signal processing over accumulated knowledge.
- A safety system (Phase 4+): assesses hazards, protects its own data, never transmits without permission.
- *(new, v4.6)* A sovereignty mechanism: knowledge nodes can be masked — relational anchors stay live, content stays hidden until the user explicitly calls it, with every mask/unmask action audit-logged.

### Victor is not

- A chatbot. The conversational interface is the query surface; the product is the graph and the citation trail.
- A second-brain or note-taking app. Victor ingests structured research artifacts, not arbitrary notes.
- A self-learning system in the naive sense. Model weights do not update from conversations unsupervised.
- A multi-user or collaborative platform. Single researcher, single device, through Phase 4 at minimum.
- A cloud product. No telemetry, no sync, no remote inference. Nothing leaves the device without explicit user action.
- A hardware device or sensor platform right now. The physical toolkit is Phase 2+; only the software-side ingestion path for one sensor type (camera) currently exists, and only in mocked/CLIP-classifier form — no physical deployment.
- AGI-adjacent or unrestricted self-improvement. This is a bounded, inspectable retrieval and reasoning tool.

---

## 4. Design Principles & The Five Invariants

### Design Principles

- **Sense first, understand second.** Raw sensor data is not knowledge. It becomes knowledge when structured, linked, and epistemically stamped.
- **Local-first by philosophy, not constraint.** The system must function entirely offline — not as a degraded fallback, but as the full product.
- **The graph is permanent; the model is temporary.** Knowledge accumulated over years must survive a model upgrade, a hardware replacement, a decade of continued use.
- **Epistemic honesty is non-negotiable.** Every piece of knowledge has a type, an uncertainty, and a provenance chain.
- **The user holds all trust boundaries.** The system never decides what leaves the device, what gets published, or what gets shared.
- **Swappability over optimisation.** Every model, storage backend, and inference engine is behind an interface. The right choice today is not the right choice in two years.
- **Scope creep kills small projects.** Features that require cloud infrastructure or multi-user support are deferred until the single-device offline loop is validated.

### The Five Invariants

These five rules hold across every phase and every version. Any feature that violates one is out of scope, regardless of how useful it seems.

1. The LLM never writes to the knowledge graph without a human-reviewable record. Claim extraction is logged. The user can inspect and delete any extracted node.
2. Every answer cites the source node IDs that contributed to it, along with their EpistemicStatus. An unsourced confident answer is a bug.
3. The knowledge graph is the permanent artifact. Vector indexes and model outputs are derived and can be rebuilt. The graph cannot be rebuilt from anything else — it is the source of truth.
4. Model weights are never updated from user data without an explicit, deliberate fine-tuning pass that the user initiates, reviews, and can roll back.
5. Nothing leaves the device without a user-initiated export action. The permission switch is not a software toggle the system can override — it is a deliberate user action, logged, with the full list of what was exported stored in the graph. *(v4.6 note: this invariant is now partially mechanized, not just policy — the masked memory system is the first concrete enforcement layer for it, with `mask()`/`unmask()`/`list_masked()` and an immutable audit log on every call.)*

---

## 5. Current State — What's Actually Built

Based on a direct read of the v4.6 codebase, with v4.9 corrections noted inline where the v4.9 audit found the v4.6–v4.8 status to be wrong. Test counts and CLI status reflect v4.9. June 2026.

### Phase 0 — Software Foundation: 7 of 7 done *(corrected v3.4 — was 6/7; repo scaffolding confirmed present)*

| | Feature | Status | Location |
|---|---|---|---|
| ✅ | Fix confirms/contradicts heuristic — uses ConflictDetector | Done | graph.py |
| ✅ | EpistemicStatus on every node (MEASUREMENT, EXPERIMENT, LITERATURE, NOTE, HYPOTHESIS) | Done | models.py, graph.py |
| ✅ | Importance-weighted retrieval (0.7×cosine + 0.3×importance) | Done | retrieve.py |
| ✅ | Temporal memory decay (90-day threshold, 0.02/30-day, floored at 0.1) | Done | graph.py |
| ⚠️ | CLI — 23 commands incl. subgroups (inspect, delete, freeze, export, patterns, evidence, mask, unmask) | **Built, but broken on import v4.6–v4.8** — fixed in v4.9 | cli.py |
| ✅ | InferenceClient (provider-agnostic LLM backend) | **Done** *(was: not done)* | llm.py — `InferenceClient(ABC)` → `OllamaClient`, `LlamaCppClient`, `MLXClient` |
| ✅ | Embedder defaults to nomic-embed-text-v1.5, offline fallback to all-MiniLM-L6-v2 | **Done** *(was: not done)* | embedder.py, config.py |
| ✅ | Repo scaffolding — LICENSE, .gitignore, CI config, Dockerfile | **Done** *(corrected 2026-06-27 — LICENSE was MIT, which conflicts with the B2B-OEM licensing model in Foundation v2; now Proprietary/All Rights Reserved. .gitignore, Dockerfile, .github/workflows/ci.yml unaffected)* | repo root |

### Phase 1 — AI Brain: 7 of 7 done

| | Feature | Status | Location |
|---|---|---|---|
| ✅ | ConflictDetector — LLM-based, replaces keyword heuristic | Done | reasoning.py |
| ✅ | GapDetector — finds claims with no experimental backing | Done | reasoning.py |
| ✅ | EvidenceWeighter — confidence per claim weighted by EpistemicStatus | Done | reasoning.py |
| ✅ | Conversation memory nodes — every Q&A stored as a graph node | Done | graph.py, retrieve.py |
| ✅ | PatternDetector — surfaces recurring weak topics and unconfirmed claims | Done | reasoning.py |
| ✅ | PatternDetector output **surfaced**, not just computed | **Done** *(was: computed, not surfaced)* | core.py `ask_with_patterns()`, cli.py `--show-patterns`, `victor patterns` digest |
| ✅ | IngestorBase abstract class | **Done** *(was: not done)* | ingest.py — `IngestorBase(ABC)` → `PDFIngestor`, `MarkdownIngestor`, `ExperimentIngestor` |
| ✅ | StatisticsKernel — first computation kernel (mean/variance/CI) | **Done** *(was: not done)* | kernels.py — `ComputationKernelBase(ABC)` → `StatisticsKernel`, reproducibility hash included |
| ✅ | Bounded agent loop (Retrieve → Reason → Review → Respond) | **Done** *(was: not done — this was the central gap in v3.1 Section 6)* | retrieve.py — `AgenticRetriever(HybridRetriever)` |
| ✅ | *(new, not in v3.1 scope)* Masked memory graph + audit log | Done | core.py `mask()`/`unmask()`/`list_masked()`, `_write_mask_audit()` |

### Test suite — 147 tests, not zero

9 test files, 147 passing assertions on a clean extraction: `test_masked_memory.py`, `test_agent_loop.py`, `test_scifact_benchmark.py` *(harness logic only — not a benchmark run)*, `test_unmask_audit_log.py`, `test_statistics_kernel.py`, `test_masking_enforcement_full.py`, `test_sensor_pipeline.py`, `test_tool_mask_enforcement.py`, `test_cli_import.py` *(new in v4.9 — see below)*. Masking alone accounts for ~1,100 lines across 4 dedicated files — clearly the most heavily defended subsystem in the repo, at 48 of the 147 tests.

**A green suite does not mean a working product.** Until v4.9, `cli.py` — the only user-facing entry point into everything else in this table — was unimportable due to a bare-import bug (`from config import VictorConfig` instead of `from .config import VictorConfig`), and crashed identically whether invoked as `python -m victor.cli`, `from victor import cli`, or through the installed console script. None of the 142 tests at the time touched `cli.py`, so the suite stayed green while the product's primary surface was completely broken. `test_cli_import.py` (5 tests) closes that specific gap; it does not guarantee no other module has zero coverage. Treat "tests passing" as evidence about the modules the tests actually import, not as evidence about the product as a whole.

### Repo Scaffolding — Still mostly zero

`examples/` and `.env.example` are restored (were lost between v3 and v4, per v3.1). LICENSE, `.gitignore`, CI config, and a Dockerfile are now also present *(corrected v3.4 — previously described as "genuinely absent"; confirmed in repo root)*. This is now a folder of trustworthy, tested modules that a stranger can clone with confidence about licensing and CI gates.

---

## 6. The AI Vision Gap — What Was Missing, and What's Closed Now

v3.1 described one structural gap: the pipeline ran once per question — vector search → fixed graph expansion → one LLM call → done — with no loop, no mid-answer tool calls, and a PatternDetector that computed insights nobody saw. **That gap is closed in v4.6.**

| Stage | Name | v3.1 status | v4.6 status |
|---|---|---|---|
| 1 | Retrieve | Done — vector + graph search | Done, unchanged |
| 2 | Reason | Missing — skipped to generation | **Done** — `AgenticRetriever` makes bounded tool calls before answering |
| 3 | Review | Missing — no consistency check | **Done** — ConflictDetector is callable mid-loop, not just at ingestion |
| 4 | Respond | Done — single LLM call | Done — now the terminal step of a multi-call loop, not the only step |

The PatternDetector gap — "computes findings, nothing acts on them" — is also closed: `ask_with_patterns()` injects a PatternDetector insight whenever a query semantically overlaps a known weak topic (cosine similarity > 0.65), and the CLI exposes both an on-by-default inline nudge and an explicit `victor patterns` digest.

**What this means for the original three-part AI vision (Section 2):** requirement 3 — "enhances itself from usage without being told to" — now has a real, working, non-weight-touching implementation. The system surfaces unprompted "you've asked about this 4 times and it's still unconfirmed" findings. This was the single most direct, lowest-risk implementation path available, and it's built.

**What is genuinely still missing from the AI vision**, now that the loop exists:

- No real accuracy number for the Review step. ConflictDetector runs inside the agent loop, but its trustworthiness as a Review gate has never been measured against a labeled dataset (SciFact). Wiring an unmeasured judge into an automated loop is exactly the risk the Risk Register (Section 17) already calls out.
- No fine-tuning loop yet — by design. Section 8's own gate says this shouldn't start until the rest is measured and stable. That gate is closer to satisfied now than it was, but criterion #4 (below) is still open.

**Honest cost, unchanged from v3.1:** multi-step reflection loops typically cost 3–10x the tokens of a single-shot pipeline. The loop now exists; what hasn't been measured is whether its iteration budget and stop condition behave well on real usage volume, since the test suite exercises correctness, not cost under load.

---

## 7. What to Build — Status of the Original Plan

### Step 1 — Expose reasoning modules as tools — ✅ Done

GapDetector, EvidenceWeighter, ConflictDetector, and graph traversal are callable mid-answer through `AgenticRetriever`, not invoked in a fixed Python order.

### Step 2 — Replace fixed pipeline with bounded agent loop — ✅ Done

`AgenticRetriever(HybridRetriever)` implements the turn-budgeted loop. The original warning — *design the stop condition before building the loop, or it runs away on cost* — should be re-verified against real usage now that the loop is live; passing tests confirm correctness of the bound, not necessarily that the chosen budget is the right one in practice.

### Step 3 — Wire PatternDetector to the surface — ✅ Done

`ask_with_patterns()` plus the `victor patterns` CLI digest.

### Step 4 — Close Phase 0 and Phase 1 remaining items — ✅ Done

InferenceClient, nomic-embed-text default, IngestorBase, and StatisticsKernel all exist as specified.

### Step 5 — Make the repo real — ⚠️ Partially done

| Sub-item | Status |
|---|---|
| pytest suite (ingest → graph → retrieve → answer, ConflictDetector, GapDetector) | ✅ Done — 147 tests (142 + 5 added in v4.9 closing the cli.py coverage gap) |
| Run ConflictDetector against SciFact for a real accuracy number | ⚠️ **Run once, below threshold** — harness executed against the real dataset, 68.0% accuracy on n=50 vs. the 85% target (see `SCIFACT_BENCHMARK_RESULTS.md`); `ConflictDetector.judge()` has since been rewritten to address the diagnosed agreement bias, but a real post-rewrite number is still pending (Section 6, Section 17 risk, Section 8 criterion #4, and Section 24.5 for a candidate accuracy lever) |
| Restore examples/ + sample experiment JSON | ✅ Done |
| LICENSE, .gitignore, CI workflow, .env.example | ✅ all four confirmed present *(corrected v3.4 — was "the other three still don't exist")* |

### Step 6 — LoRA fine-tuning — Correctly still not started

Per the original plan, this should not begin before Steps 1–5 are fully closed. Step 5 is not fully closed (SciFact) *(corrected v3.4 — repo scaffolding is no longer a blocker here; confirmed present)*. **This gate is still correctly holding.**

### Embedder, reranker, and retrieval upgrades — Partially evaluated

- Embedder: nomic-embed-text-v1.5 is now the default, matching the recommendation. Qwen3-Embedding-small was suggested as an alternative — not adopted; not necessarily wrong, just unevaluated.
- Reranker (BAAI/bge-reranker-v2-m3): not present in the codebase. Still an open upgrade.
- PageRank-weighted graph traversal (HippoRAG-style): not present — current traversal is still the simpler naive-hop expansion referenced in v3.1.
- Semantic Scholar ingestion benchmark: not adopted; `examples/sample_paper.md` is a single hand-picked document, not a Semantic Scholar pull.
- SciFact / Matter-of-Fact claim verification benchmark: SciFact harness exists, unrun. Matter-of-Fact: not present at all.

---

## 8. Definition of Done

The AI version is done when all ten of the following are true. Not before.

| # | Criterion | Category | Status |
|---|---|---|---|
| 1 | At least one v4+ reasoning module is callable as a tool mid-answer | Agent loop | ✅ |
| 2 | `answer_full()` can make more than one retrieval/reasoning call per question, bounded by an explicit turn budget | Agent loop | ✅ |
| 3 | PatternDetector output is surfaced to the user unprompted | Agent loop | ✅ |
| 4 | A real accuracy number exists for ConflictDetector against SciFact | Benchmark | ❌ **Open** |
| 5 | llm.py exposes a provider-agnostic InferenceClient; Ollama is one implementation | Phase 0 | ✅ |
| 6 | Default embedding model is nomic-embed-text with offline fallback preserved | Phase 0 | ✅ |
| 7 | IngestorBase exists — new document type requires only subclassing it | Phase 1 | ✅ |
| 8 | At least one computation kernel (StatisticsKernel) exists and is callable from core.py | Phase 1 | ✅ |
| 9 | A test suite exists and passes on a clean clone | Repo | ✅ (147/147 — was 142/142; +5 in v4.9 closing the cli.py coverage gap) |
| 10 | examples/, LICENSE, .gitignore, and a minimal CI check exist in the repo | Repo | ✅ *(corrected v3.4 — was "Half"; LICENSE, .gitignore, Dockerfile, and .github/workflows/ci.yml all confirmed present in repo root)* |

**9 of 10 fully true, 1 open** *(corrected v3.4 — previous text said "7 of 10 fully true, 1 half-true, 2 open," which didn't match its own table even before this correction: the table only ever marked one criterion ❌ Open (#4); recounting after fixing #10 gives 9 ✅ + 1 ❌ = 10)*. Fine-tuning work must not start before all ten are true — and per this scorecard, that gate is still correctly closed. The one real remaining blocker is the benchmark run (#4); repo hygiene (#10) is closed.

---

## 9. Phase Map

Each phase is a complete, usable product at its own level. Phase 2 is useful without Phase 3. The phases are dependencies, not a forced sequence.

| Phase | Name | Hardware | Core Unlock | Status |
|---|---|---|---|---|
| 0 | Software Foundation | None (laptop) | Working, trustworthy AI brain | **7/7 done** *(corrected v3.4 — was 6/7)* |
| 1 | AI Brain Complete | None | Epistemic reasoning, agent loop, self-learning | **7/7 done** |
| 2 | First Hardware Prototype | Raspberry Pi 5 + camera + sensors | Sensor → graph pipeline, real-world data | Software path for camera exists (mocked); no physical deployment |
| 3 | Multi-Sensor Intelligence | Jetson Orin + full sensor array | Sensor fusion, spatial mapping, anomaly detection | Not started |
| 4 | Full Research Instrument | Custom enclosure + battery + rugged | Field-ready, hazard assessment, emergency snapshot | Not started |
| 5 | Domain Mastery | Same hardware + domain modules | LoRA fine-tuning loop, domain expert capability | Not started — correctly gated |
| 6 | Extreme Environments | Hardened hardware + DTN | Months of autonomous operation, federated knowledge | Not started |
| Final | Autonomous Research System | Self-contained | Fully autonomous, years of operation, no external input | Long-term vision |

Phase 1 crossing to 7/7 means the prerequisite for Phase 2 stated in Section 10 below ("Phase 0 + Phase 1 fully done — not 5/7, not mostly done") is **fully** satisfied: Phase 1 is fully done, and Phase 0 is now also 7/7 *(corrected v3.4 — repo scaffolding, the one item left, is confirmed present)*.

---

## 10. Phase 0 — Software Foundation

Goal: make the existing codebase trustworthy. Phase 0 is pure fixes and backend swaps — not new capability. Phase 1 cannot build correctly on corrupted data.

**P0-F001 — Fix confirms/contradicts heuristic [DONE].** The direction of claim→experiment edges was decided by keyword matching. Fixed: now uses ConflictDetector — one LLM call per link with structured output `{direction, confidence, reason}`. The reason field is stored as provenance on the edge.

**P0-F002 — EpistemicStatus on every node [DONE].** Every node carries an epistemic type at creation: MEASUREMENT (device directly observed) > EXPERIMENT (controlled test result) > LITERATURE (claimed in a paper) > NOTE (personal annotation) > HYPOTHESIS (speculation). Every retrieval result surfaces it. *(Corrected in v3.3 — prior versions of this section listed a sixth "COMPUTATION" tier between EXPERIMENT and LITERATURE that does not exist in the code; `models.py`'s `EpistemicStatus` enum has exactly five members and a five-entry `.weight` table, matching Section 5's table, not this one. `NodeType.COMPUTED` exists as a separate concept — a node type for kernel outputs — and is not an EpistemicStatus tier. This document's two sections disagreed with each other for at least one full version; only the five-tier version is real.)*

**P0-F003 — Importance-weighted retrieval [DONE].** Retrieval score = 0.7 × cosine_similarity + 0.3 × importance_score. Starting importance: experiments = 0.8, claims = 0.7, chunks = 0.5. Importance increases 0.05 per retrieval.

**P0-F004 — Temporal memory decay [DONE].** Nodes not retrieved in 90 days decay at 0.02 per additional 30 days, floored at 0.1. Computed lazily at retrieval time.

**P0-F005 — InferenceClient (provider-agnostic backend) [DONE — corrected from v3.1].** `InferenceClient(ABC)` exists with `OllamaClient`, `LlamaCppClient`, and `MLXClient` as concrete backends. Ollama remains the default.

**P0-F006 — Swap embedder to nomic-embed-text [DONE — corrected from v3.1].** Default embedder is `nomic-embed-text-v1.5`. `all-MiniLM-L6-v2` retained as the offline/test fallback, exactly as specified.

**P0-F007 — CLI completeness [DONE, with a corrected history].** 23 commands wired across the root group plus the `list` and `compute` subgroups: ingest, ask, evaluate, gaps, evidence, patterns, decay, inspect, freeze/unfreeze, delete, export, stats, mask, unmask, observe, list (claims/papers/experiments/conversations/masked), compute (stats/effect). Output via rich. `--mock-llm` flag for full offline operation. *(v3.3 correction: this was marked "[DONE]" and "functional" in v3.1 and v3.2, but `cli.py` had a bare-import bug that crashed it on every invocation form — `python -m victor.cli`, `from victor import cli`, and the installed console script — from v4.6 through v4.8. It was never run as part of verifying this PRD; it was only read. Fixed in v4.9, with 5 new regression tests added specifically because none of the prior 142 tests imported this module. The lesson, not just the bug: "wired" and "functional" are different claims, and this document conflated them.)*

**P0-F008 — Repo scaffolding [DONE — corrected v3.4, was "NOT DONE — unchanged from v3.1"].** LICENSE, `.gitignore`, CI config (`.github/workflows/ci.yml`), and a Dockerfile are all confirmed present in the repo root, alongside the already-present `.env.example` and `examples/`. No longer open.

**Phase 0 exit, revised:** precision@5 measurement, EpistemicStatus coverage, and codebase openness are achievable now. The remaining blocker for a clean "Phase 0 exit" is publishing the repo with proper licensing and a CI gate — a packaging task, not an engineering one.

---

## 11. Phase 1 — AI Brain Complete

Goal: build the reasoning layer that makes Victor a research intelligence system, not just a smart document store. Phase 1 does not require any hardware. It completes the software product and unlocks Phase 2.

**P1-F001 — ConflictDetector [DONE].** LLM-based reasoning over two nodes to determine genuine conflict. Produces typed output: CONTRADICTS, CONSISTENT_WITH, or INCONCLUSIVE, with confidence and a reasoning trace stored as a REASONING node.

**P1-F002 — GapDetector [DONE].** Finds CLAIM nodes with no experimental confirmation. Ranks gaps by priority: frequency retrieved, contradiction-resolving potential, or foundational dependency.

**P1-F003 — EvidenceWeighter [DONE].** Aggregates CONFIRMS/CONTRADICTS edges pointing to a CLAIM node, weighted by source EpistemicStatus. Produces a confidence score per claim.

**P1-F004 — Conversation Memory Nodes [DONE].** Every Q&A session becomes a CONVERSATION node with GROUNDED_IN edges to source nodes. Retrieved as context on related future queries.

**P1-F005 — PatternDetector [DONE — surfacing now closed, corrected from v3.1].** Analyses accumulated CONVERSATION and MEASUREMENT nodes for recurring weak topics, unconfirmed-but-frequently-retrieved claims, and temporal trends. v3.1 noted this *computed but did not surface* findings. v4.6 closes this: `ask_with_patterns()` injects findings inline (similarity > 0.65 trigger) and `victor patterns` exposes a full digest on demand.

**P1-F006 — IngestorBase abstract class [DONE — corrected from v3.1].** `IngestorBase(ABC)` defines `ingest(source, config) → IngestResult` plus `source_type` and `default_epistemic_status` properties. `PDFIngestor`, `MarkdownIngestor`, and `ExperimentIngestor` all subclass it. `core.py` does not need to change when a new document-type ingestor is added.

**P1-F007 — StatisticsKernel [DONE — corrected from v3.1].** `ComputationKernelBase(ABC)` → `StatisticsKernel`: mean, standard deviation, confidence intervals over EXPERIMENT/MEASUREMENT nodes. Outputs carry a reproducibility hash, satisfying the original spec's requirement that stale computations be detectable if an input node is later deleted.

**P1-F008 — *(new, not in v3.1)* Masked memory graph [DONE].** Relational anchors between knowledge nodes stay live and traversable; the full content of a node surfaces only when the user explicitly calls `unmask()`. Every `mask()`/`unmask()`/`list_masked()` call is audit-logged via `_write_mask_audit()`. This is the most heavily tested subsystem in the repo (4 dedicated test files, ~1,100 lines) and the most direct mechanism so far for Invariant 5 ("nothing leaves the device without a user-initiated action, logged").

**Phase 1 exit, revised:** GapDetector, ConflictDetector, EvidenceWeighter, and conversation memory are all live and tested on synthetic data. The one item from the original exit criteria still open is *"ConflictDetector accuracy number published from SciFact run"* — everything else in the original Phase 1 exit bar is met.

---

## 12. Phase 2 — First Hardware Prototype

Goal: connect the software brain to the physical world. Phase 2 is deliberately minimal — one compute platform, one camera, basic sensors. The goal is to validate that the sensor → StreamIngestor → graph pipeline works end-to-end before adding complexity.

**Hardware target (unchanged):** Raspberry Pi 5 (8GB) + Pi Camera 3 + BME688 environmental sensor (temperature, pressure, humidity, gas resistance) + USB microphone.

**Prerequisite (unchanged):** Phase 0 + Phase 1 fully done. Not mostly done — fully done. Per Section 9, both phases now are *(corrected v3.4 — Phase 0's one remaining item, repo scaffolding, is confirmed present, not open)*.

| Feature | Original status | Verified status |
|---|---|---|
| P2-F001 StreamIngressor base class | Not done | **Partially done.** `sensors.py` has `StreamIngestorBase(ABC)` — a sensor-equivalent base class exists, narrower in scope than the full spec but structurally present |
| P2-F002 CameraIngressor | Not done | **Software path done.** `CameraIngestor(StreamIngestorBase)` exists with `VisionClassifierBase(ABC)` → `CLIPClassifier` / `MockClassifier`. Florence-2 (the originally specified model) is not what's wired — CLIP is. No physical Pi Camera integration. `core.py` raises `NotImplementedError` for every sensor type except `'camera'` |
| P2-F003 EnvironmentalIngressor | Not done | Not done |
| P2-F004 AcousticIngressor | Not done | Not done |
| P2-F005 ScanSession node type | Not done | Not done |
| P2-F006 Voice interface (whisper.cpp) | Not done | Not done |

**Phase 2 exit:** unchanged from v3.1 — still not met. The camera ingestion path existing in mocked/CLIP form on a laptop is meaningfully different from "Victor on Raspberry Pi 5 ingests camera, environmental, and acoustic data in a real field session." Phase 2 is not close to its exit criteria; one of six features has a software stub.

---

## 13. Phases 3–6 — Overview

*(Unchanged from v3.1 — nothing in the verified codebase touches Phase 3 and beyond. Reproduced here for document completeness.)*

### Phase 3 — Multi-Sensor Intelligence

Hardware additions: NVIDIA Jetson Orin (16GB), Raman spectrometer module, Intel RealSense D435 depth/lidar, EM field sensor, optional GPS. Key systems: SensorFusionEngine, SpectrometerIngressor (RRUFF/NIST matching), SpatialMapper (lidar occupancy + revisit diff), EMIngressor, ImageBind multi-modal embeddings, real-time AnomalyDetector. Exit: 3+ simultaneous sensor fusion; spectrometer identifies 5 known RRUFF materials on-device; anomaly detected within 500ms.

### Phase 4 — Full Research Instrument

Goal: field-ready, not new AI capability. UncertaintyPropagationKernel, Safety AI Layer (HAZARD_ASSESSMENT nodes, non-deletable USER_OVERRIDE nodes), Emergency Knowledge Snapshot, Field-Ready Enclosure (IP67, -20°C–60°C, drop test, 8h battery, physical hardware permission switch). Exit: real field session by a domain expert, drop test passed, 8h battery, emergency snapshot tested end-to-end.

### Phase 5 — Domain Mastery

Self-Labeling Loop (50+ label events triggers on-device retraining), Domain Dataset Integration (Materials Project, NIST Chemistry, RRUFF, PubChem, UCR), LoRA Fine-Tuning Pipeline (prepare → run → eval → deploy → rollback, base model never modified, minimum 200 Q&A pairs + 100 label events), Research Paper Export. Exit: domain head outperforms base model on researcher's own data; LoRA pipeline runs end-to-end; paper draft produced from accumulated data.

### Phase 6 — Extreme Environments and Federation

Extended Autonomous Operation (solar, duty-cycling, graph pruning, self-diagnosis), Delay-Tolerant Networking, Federated Knowledge — opt-in, typed-node-only, never raw data — Hardened Hardware (-40°C–85°C, 10 krad, MIL-STD-810G). Exit: 90 days autonomous, DTN sync with simulated windows, two-device federation test.

---

## 14. Technical Stack by Phase

*(Largely unchanged from v3.1; corrected where the actual codebase diverges from the spec.)*

| Layer | Phase 0–1 (spec) | Phase 0–1 (actual) | Phase 2–3 | Phase 4–5 | Phase 6 |
|---|---|---|---|---|---|
| Inference | Ollama (dev) / llama-cpp-python (prod) | **Matches** — `InferenceClient` with Ollama, LlamaCpp, MLX backends | llama-cpp-python / mlx-lm | llama-cpp-python + ONNX Runtime | llama-cpp-python + fallback tiers |
| LLM model | Qwen2.5-7B-Instruct Q4_K_M | **Matches** — `ollama_model: "qwen2.5:7b"` in config | Qwen2.5-7B Q4_K_M | Domain LoRA adapter | Fine-tuned adapter v3–5 |
| Vision | — | CLIP (mock/real classifier in `sensors.py`) — spec called for Florence-2 | Florence-2-base (ONNX, CPU) — not yet adopted | Florence-2 + PaliGemma-3B | Domain-adapted Florence-2 head |
| Audio | — | Not present | whisper.cpp + PANNs | PANNs + ROCKET | Domain-adapted acoustic head |
| Embeddings | nomic-embed-text-v1.5 + specter2 | **Mostly matches** — nomic-embed-text-v1.5 default, MiniLM fallback; specter2 not present | nomic-embed-text + specter2 | ImageBind | ImageBind + domain head |
| Vector store | ChromaDB (dev) / sqlite-vec (prod) | **Matches dev side** — ChromaDB wrapper in `vector_store.py`; sqlite-vec swap not done | sqlite-vec | sqlite-vec | sqlite-vec |
| Graph | NetworkX + JSON | **Matches** — `graph.py` uses NetworkX with atomic JSON save | NetworkX (write) + DuckDB (read) | NetworkX + DuckDB | + cold archive |
| Signal proc. | scipy + numpy | **Matches** | librosa + scipy | + RDKit | Same |
| Fine-tuning | — | Correctly absent | — | transformers + PEFT (LoRA) | transformers + PEFT |
| Compute | Laptop/server CPU | **Matches** — this is where it runs today | Raspberry Pi 5 (8GB) | Jetson Orin (16GB) | Jetson Orin (hardened) |

---

## 15. Feature Master List

| ID | Feature | Phase | Priority | v3.1 Status | Verified Status |
|---|---|---|---|---|---|
| F001 | Fix confirms/contradicts heuristic | 0 | P0 | ✅ Done | ✅ Done |
| F002 | EpistemicStatus on all nodes | 0 | P0 | ✅ Done | ✅ Done |
| F003 | Importance-weighted retrieval | 0 | P0 | ✅ Done | ✅ Done |
| F004 | Temporal memory decay | 0 | P1 | ✅ Done | ✅ Done |
| F005 | InferenceClient (backend-agnostic) | 0 | P1 | ❌ Not done | ✅ **Done** |
| F006 | nomic-embed-text + specter2 embedders | 0 | P1 | ❌ Not done | ✅ **Mostly done** (specter2 absent) |
| F007 | CLI: all 19+ commands | 0 | P1 | ✅ Done | ✅ Done |
| F008 | ConflictDetector (LLM-based) | 1 | P0 | ✅ Done | ✅ Done |
| F009 | GapDetector | 1 | P0 | ✅ Done | ✅ Done |
| F010 | EvidenceWeighter | 1 | P1 | ✅ Done | ✅ Done |
| F011 | Conversation memory nodes | 1 | P0 | ✅ Done | ✅ Done |
| F012 | PatternDetector (compute + surface) | 1 | P1 | ⚠️ Computed, not surfaced | ✅ **Done** |
| F013 | IngestorBase abstract class | 1 | P1 | ❌ Not done | ✅ **Done** |
| F014 | StatisticsKernel | 1 | P1 | ❌ Not done | ✅ **Done** |
| F015 | Agent loop (Retrieve→Reason→Review→Respond) | 1 | P0 | ❌ Not done | ✅ **Done** |
| F040 | *(new)* Masked memory graph + audit log | 1 | P0 | *not listed* | ✅ **Done** |
| F016 | StreamIngressor base class | 2 | P0 | ❌ Not done | ⚠️ **Partial** — base class exists, narrower scope |
| F017 | CameraIngressor (vision) | 2 | P0 | ❌ Not done | ⚠️ **Partial** — software path with CLIP, no hardware, not Florence-2 |
| F018 | EnvironmentalIngressor (BME688) | 2 | P0 | ❌ Not done | ❌ Not done |
| F019 | AcousticIngressor (PANNs + librosa) | 2 | P0 | ❌ Not done | ❌ Not done |
| F020 | ScanSession node type | 2 | P1 | ❌ Not done | ❌ Not done |
| F021 | Voice interface (whisper.cpp) | 2 | P1 | ❌ Not done | ❌ Not done |
| F022 | SensorFusionEngine | 3 | P0 | ❌ Not done | ❌ Not done |
| F023 | SpectrometerIngressor | 3 | P0 | ❌ Not done | ❌ Not done |
| F024 | SpatialMapper (lidar) | 3 | P1 | ❌ Not done | ❌ Not done |
| F025 | EMIngressor | 3 | P1 | ❌ Not done | ❌ Not done |
| F026 | ImageBind multi-modal embeddings | 3 | P0 | ❌ Not done | ❌ Not done |
| F027 | Real-time AnomalyDetector | 3 | P0 | ❌ Not done | ❌ Not done |
| F028 | UncertaintyPropagationKernel | 4 | P0 | ❌ Not done | ❌ Not done |
| F029 | Safety AI Layer | 4 | P0 | ❌ Not done | ❌ Not done |
| F030 | Emergency Knowledge Snapshot | 4 | P1 | ❌ Not done | ❌ Not done |
| F031 | SignalProcessingKernel | 4 | P1 | ❌ Not done | ❌ Not done |
| F032 | EstimationKernel | 4 | P1 | ❌ Not done | ❌ Not done |
| F033 | Self-Labeling Loop | 5 | P0 | ❌ Not done | ❌ Not done |
| F034 | Domain Dataset Integration | 5 | P1 | ❌ Not done | ❌ Not done |
| F035 | LoRA Fine-Tuning Pipeline | 5 | P0 | ❌ Not done | ❌ Not done |
| F036 | Research Paper Export | 5 | P2 | ❌ Not done | ❌ Not done |
| F037 | Extended Autonomous Operation | 6 | P0 | ❌ Not done | ❌ Not done |
| F038 | Delay-Tolerant Networking | 6 | P1 | ❌ Not done | ❌ Not done |
| F039 | Federated Knowledge (Opt-In) | 6 | P2 | ❌ Not done | ❌ Not done |

**Score:** 16 of 40 features done (was 11 of 39 in v3.1), 2 partial, 22 not started — all 22 correctly concentrated in Phase 2 and beyond, where hardware is the gating factor, not software design. *(v3.3 correction: this row previously read "16 of 41... 23 not started." A direct count of every row in the table above gives 40 total — 16 done [including F006 and F040] + 2 partial [F016, F017] + 22 not-done [F018–F039] = 40. There is no 41st feature in this table; both numbers in the old line were off by one.)*

---

## 16. Success Metrics by Phase

*(Unchanged from v3.1 in structure, but corrected v3.4: ConflictDetector accuracy has now been run — 68.0% (n=50), below the threshold below — so this is no longer "never run," it's "run and failing the gate." precision@5 (Phase 0's other gating metric) genuinely remains unmeasured.)*

| Phase | Primary Metric | Secondary Metric | Threshold |
|---|---|---|---|
| 0 | precision@5 on eval set | ConflictDetector accuracy (SciFact) | p@5 > 0.80, ConflictDetector accuracy > 0.85 |
| 1 | GapDetector actionability rate | EvidenceWeighter calibration | >70% of surfaced gaps confirmed useful by researcher |
| 1 | Agent loop answer quality vs. single-shot | Token cost ratio | Improved precision@5; cost ratio < 5x single-shot |
| 2 | Sensor-to-node pipeline latency | Anomaly detection recall | <2s sensor read to node; >80% recall on staged anomalies |
| 3 | Cross-modal retrieval accuracy | Fusion vs. single-sensor accuracy | Fusion +15% over best single sensor on material ID |
| 4 | Field session duration without failure | UncertaintyPropagation accuracy | 8h continuous; <5% error vs. manual calculation |
| 5 | Domain head accuracy vs. base model | Fine-tuned LLM eval harness score | Domain head +20%; fine-tuned LLM +10% on eval harness |
| 6 | Autonomous operation duration | DTN transmission success rate | 90 days continuous; >95% transmission success |

---

## 17. Risk Register

| Risk | Phase | Severity | Mitigation | Status note |
|---|---|---|---|---|
| Agent loop cost runs away without a stop condition | 1 | High | Design the iteration budget and stop condition before building the loop. Explicit token ceiling per query. | **Loop now exists** — this risk is live in practice, not theoretical; budget behavior under real usage is untested |
| Fine-tuning started before the loop exists — trains on incomplete behaviour | 5 | High | Section 8 DoD: fine-tuning cannot start before all 10 criteria true | Gate correctly still closed (7/10 + 1 half) |
| ConflictDetector accuracy insufficient for Review step to be trustworthy | 1 | High | Run SciFact benchmark before wiring ConflictDetector into the agent loop as a Review tool | **Materialized as planned, not yet mitigated** — ConflictDetector *is* wired into the loop already, and the benchmark that was supposed to precede that wiring still hasn't run |
| Florence-2 accuracy insufficient for domain material ID in Phase 2 | 2 | Medium | Domain fine-tuning head in Phase 5 | Moot for now — CLIP is wired, not Florence-2; re-evaluate when Florence-2 is actually adopted |
| Raman spectrometer module unavailable or too expensive | 3 | Medium | Defer to Phase 4 | Unchanged |
| LoRA fine-tuning degrades base model general capability | 5 | Medium | Mandatory eval harness comparison; rollback always available | Unchanged — not yet relevant |
| Sensor fusion latency too high for real-time on Raspberry Pi | 2 | High | Jetson Orin is the target for full fusion | Unchanged |
| Federated knowledge creates privacy exposure | 6 | High | Opt-in at node granularity; legal review before deployment | Unchanged |
| Narrative inflation outpaces code: documents grow, doable features stall | All | High | This document is the last planning document until Section 8 DoD is fully checked. Next deliverable is code. | **Partially inverted this cycle** — the codebase outpaced the *previous* status document. Still worth tracking in both directions: an inaccurate status doc is a risk whether it's too pessimistic or too optimistic |
| *(new, v3.3)* A green test suite is read as "the product works," but coverage gaps are invisible from the pass/fail count alone | All | High | Treat "N tests passing" as a claim about the modules actually imported by those tests, not about the product. When adding a new module, add at minimum one test that imports it the way a real user would invoke it (CLI: subprocess, not just `from X import Y`) | **Materialized once already** — `cli.py` shipped broken behind 142/142 green for at least two versions (v4.6–v4.8) because no test imported it. Fixed in v4.9 with `test_cli_import.py`. No other module has been audited this way yet; absence of a known bug elsewhere is not evidence of absence |
| *(new, v3.3)* LLM arbiter (ConflictDetector) and deterministic sensor matching (RRUFF/NIST, Beer-Lambert, Phase 3) end up reasoning over the same node without a clear boundary | 1, 3 | Medium | State explicitly, before Phase 3 ships: ConflictDetector judges claim-text vs. experiment-text relationships; it must never be the thing that turns a spectral/sensor reading into a hazard verdict. Confirmed true of the current code (`ConflictDetector.judge()` takes `claim_text`/`result_text`, not raw sensor output) — the risk is this boundary eroding as Phase 3 is built, not that it's wrong today | Currently fine by construction; worth a one-line invariant now while it's free, rather than an incident report later |
| *(new, v3.4, corrected)* `compute_effect_size()`'s explicit-`metric_name` requirement (the Bug 2 fix) breaks a test that predates that fix | 1 | Low | `test_statistics_kernel.py::test_compute_effect_size_creates_computed_node` doesn't pass `metric_name` and its fixture stores the metric under `"score"`, not the function's default `"value"` — confirmed by direct pytest run (176/177, this is the one failure). Either add `metric_name="score"` to the test call or retire it if `test_metric_conflation.py` already covers the same path | **Open, not yet fixed.** This row didn't exist before the v3.4 changelog cited it — the citation was added a version before the row was. Corrected here so Section 17 actually contains what line 19 claims it does. |

---

## 18. Re-Entry Guide

Picking this up after a break. Read only what is needed.

| Question | Where to look |
|---|---|
| What is Victor? | Sections 2, 3, 4 |
| What is built right now? | Section 5 (tables) |
| What's actually closed vs. still open in the AI vision? | Section 6 |
| What's left of the original build plan? | Section 7 |
| How do I know when the AI version is done? | Section 8 (7/10 true, 1 half, 2 open) |
| What is the hardware roadmap? | Sections 9, 12, 13 |
| What are all the features across all phases? | Section 15 (16/40 done) |
| What model/stack should I use at each phase? | Section 14 |
| Is anyone else building this? Should that change priorities? | Section 24 |

**The next action is not another document.** It is closing Section 8 criterion #4: get `corpus.jsonl` + `claims_dev.jsonl` from the official SciFact source onto a machine that can reach it, patch `scifact_benchmark.py`'s loader to accept local files, and run it. That single benchmark run is the last thing standing between "the agent loop and reasoning layer are built" and "the agent loop and reasoning layer are measured." *(Corrected v3.4 — this paragraph previously listed repo scaffolding as a second open item; it's confirmed done and is no longer a blocker.)*

---

## 19. Roadmap Expansion — How Victor Moves Forward

*(Unchanged from v3.1 — the build-order logic doesn't shift based on what's done; it shifts based on what's left.)*

| Phase | Build focus | What becomes true | Main risk |
|---|---|---|---|
| 0 | Foundation cleanup | Stable local inference, storage, tests, packaging, provenance discipline | Repo hygiene and integration debt — **this is now the only open Phase 0 item** |
| 1 | Reasoning loop | Tool calling, bounded agent loop, conflict/gap detection, pattern surfacing | Cost runaway and brittle prompting — **built, unmeasured under load** |
| 2 | Local app + sync base | Usable desktop/mobile surface, account model, encrypted export/sync primitives | Identity, key management, merge logic |
| 3 | Knowledge engine | Graph traversal, reranking, evidence weighting, analytics, evaluation harness | Bad retrieval poisoning answers |
| 4 | Physical sensing | Camera, audio, environmental sensors, scan sessions, timestamped ingestion | Calibration and sensor drift |
| 5 | Domain adaptation | User-specific fine-tuning, label loops, higher precision in one domain | Training on unstable architecture |
| 6 | Federation and DTN | Opt-in device-to-device sync, delayed sync, selective sharing | Conflict resolution and privacy |
| Final | Research instrument | Local research system that syncs what the user allows, across devices, with auditability | Everything above |

---

## 20. Local-First, But Sync-Ready

*(Unchanged from v3.1.)* The actual vision is not "static forever." It is local-first, sync-capable, and permissioned.

1. Local device is the source of truth during normal work.
2. All writes land in an append-only event log or graph mutation log.
3. Sync is an opt-in replication layer, not the core storage layer.
4. Only selected node types are allowed to sync: exports, confirmed claims, public notes, user-approved summaries.
5. Raw sensor streams, private chat history, and sensitive notes stay local unless explicitly exported.
6. Conflicts are resolved by type: notes use CRDT-style merge; claims and evidence use human review or deterministic resolution.

Sync must never become a hidden back door. Visible, logged, reversible, scoped by node type.

| Layer | Local behaviour | Sync behaviour | Policy |
|---|---|---|---|
| Graph / claims | Stored locally with provenance | Sync only confirmed/approved items | Human-review or deterministic merge |
| Notes / annotations | Editable immediately | CRDT-style merge | User-controlled sharing scope |
| Sensor raw data | Kept on device by default | Usually not synced | Export only when needed |
| Summaries / reports | Generated locally | Can sync | Signed and timestamped |
| Model weights | Remain local unless deliberate training | Usually not synced | Explicit opt-in only |

---

## 21. Software Skills Needed Beyond Scanning and Physical Hardware

*(Unchanged from v3.1.)*

| Skill area | What you need to learn | Why it matters |
|---|---|---|
| Backend engineering | Python packaging, APIs, async execution, clean modules, config handling | Maintainability and testability |
| Information retrieval | Chunking, embeddings, reranking, retrieval evaluation, citation grounding | Bad retrieval breaks the whole brain |
| Graph systems | Node/edge schema, provenance, traversal, deduplication, graph mutations | Victor is fundamentally a graph, not a chatbot |
| Agent orchestration | Tool calling, bounded loops, stop conditions, planner-executor patterns | Multi-step reasoning without runaway cost |
| Local inference | Quantization, GGUF/ONNX deployment, llama.cpp, device-aware backends | Local-first, practical |
| Data engineering | Schema design, analytics, event logs, DuckDB/SQLite, reproducibility | Makes evidence and experiments queryable |
| Sync architecture | CRDTs, replication, conflict resolution, event sourcing, permissions | Required once you move beyond one machine |
| Evaluation | Test harnesses, benchmarks, accuracy metrics, failure analysis | Prevents narrative inflation — **see Section 6/17, this is the current bottleneck** |
| Security | Encryption at rest, key management, signed exports, access control | Sync without security is a liability |
| Product/UI | Fast local UI, keyboard flow, search, filters, feedback surfaces | A strong system still fails if unusable |

If you focus on only one software line for the next build cycle: **evaluation** has overtaken "retrieval + graph + tool calling + tests" as the bottleneck, since all four of those are now built and evaluation is the thing not yet done.

---

## 22. Tech Stack Improvements to Prioritize

| Area | Suggested direction | Status |
|---|---|---|
| Inference | llama.cpp / llama-cpp-python with GGUF models | ✅ Adopted — `LlamaCppClient` exists |
| Embeddings | Qwen3-Embedding small for quality; nomic-embed-text as fallback | ⚠️ Partially adopted — nomic-embed-text is the default; Qwen3 not evaluated |
| Reranking | BAAI/bge-reranker-v2-m3 or ONNX equivalent | ❌ Not adopted |
| Storage | SQLite + sqlite-vec; DuckDB for analytics | ⚠️ ChromaDB in place of sqlite-vec; DuckDB not adopted |
| Sync | Automerge / CouchDB / ElectricSQL for approved data | ❌ Not adopted — no sync layer exists yet, correctly (Phase 2+ item) |
| App shell | Tauri or lightweight desktop client; CLI as control surface | ❌ CLI only, as expected at this phase |
| Testing | pytest + benchmark fixtures + golden files | ✅ pytest adopted (147 tests, up from 142 — see Section 5); SciFact "golden" benchmark not yet run |
| Conflict detection (NLI) | `sentence-transformers` `CrossEncoder` NLI model (e.g. `cross-encoder/nli-deberta-v3-base`) as an ensemble cross-check inside `ConflictDetector.judge()` | ❌ Not adopted — zero new dependencies, since `sentence-transformers` is already required by `embedder.py`; see Section 24.5 |

### What I would still warn about

- Sync is still the hardest feature in the list, and still correctly untouched.
- Fine-tuning too early is wasted effort if retrieval and schema are still unstable — schema is stable now; the open question is whether the agent loop's behavior under real load is stable, which hasn't been tested.
- Sensor fusion will create calibration and timing problems quickly — still true, still ahead of where the codebase is.
- A bigger model is not automatically a better system — retrieval quality and provenance still matter more, and that priority order is reflected in what's actually built.
- **If the answer is not testable, it will drift into narrative.** This is the principle that produced this very document — the previous status table had drifted, in the safe direction, but drift either way is the thing to keep checking.

---

## 23. Version Contract — Current Versions vs Final Form

| Version / phase | What it is | Local? | Sync? | What is missing | Final target relative to it |
|---|---|---|---|---|---|
| Early v1–v3 | Idea and early PRD | Mostly implied | No | Stable graph, reasoning loop, test harness, clear storage contract | Becomes the documented baseline only |
| v4.6 current | Local-first research brain with graph, provenance, bounded agent loop, and masked memory | Yes | No | Benchmark validation, repo packaging, sensor hardware | Becomes the fully-validated software foundation |
| Phase 1 | Reasoning-capable AI brain | Yes | No / export only | Rigorous benchmarks (SciFact), real-usage cost validation | **Nearly here** — loop and surfacing exist; benchmark is the gap |
| Phase 2 | First hardware prototype | Yes | Maybe approved summaries only | Sensor session handling, voice/UI polish, calibration, physical hardware | Adds physical-world ingress — one of six features has a software stub |
| Phase 3 | Multi-sensor intelligence | Yes | Selective | Fusion robustness, timing alignment, cross-modal retrieval | Goes from input capture to interpretation |
| Phase 4 | Field-ready instrument | Yes | Selective | Ruggedness, uncertainty propagation, safety layer | Turns into a trusted tool |
| Phase 5 | Domain mastery | Yes | Yes, but controlled | Stable fine-tuning pipeline, evaluation gates, rollback | Learns from the user's domain |
| Phase 6 | Federated / DTN system | Yes | Yes, opt-in | Conflict rules, privacy review, selective replication | Can sync without losing local control |
| Final vision | Autonomous local-first research system | Yes | Yes, user-controlled | Nothing essential; it is the integrated whole | This is the end state |

**Final principle, unchanged:** the final version is not "cloud-first with local mode." It is local-first with selective, explicit sync on top.

---

*Victor Project — Master PRD v3.4 · June 2026 · Status corrected against the verified v4.9 codebase (40 files, 147 passing tests, executed from a clean extraction, including direct execution of the full pytest suite and the CLI entry point — not just inspection of test names). v3.4 adds the real-but-below-threshold SciFact run, the post-diagnosis `ConflictDetector` rewrite, and a researched NLI-cross-encoder lever (Section 24.5) for closing it. Next deliverable: a real post-rewrite SciFact benchmark run, not another document.*

---

## 24. Competitive & Market Reality — New in v3.3, extended in v3.4

No prior version of this document named a single competitor or asked whether the hardware roadmap's barriers are technical or regulatory. Both are gaps in the document, not in the code, and they don't move any DoD checkbox — they change what "done" should be optimizing toward.

**24.1 — The masked memory mechanic is real and well-tested, not uncontested.** Zep ships temporal knowledge-graph memory with built-in access control, retention policies, and audit trails today — SOC 2 Type 2, HIPAA, and GDPR certified, in production, 24K+ GitHub stars. A project marketed specifically as local-first/data-sovereign memory under EU AI Act framing also already exists, open-source, benchmarked. "Relational anchors stay live, content masked until called, audit-logged" is not an unclaimed idea — it's the category a funded, certified competitor already occupies. Section 1's table has been softened accordingly (was: "the project's actual differentiator"). The masking implementation itself is not the problem — it's genuinely the most heavily tested subsystem in the repo — the problem is treating "well-built" and "differentiated" as the same claim.

**24.2 — A single SciFact number, once run, will not be as decisive as Section 8 criterion #4 implies.** Zep and Mem0 are in an open public dispute over the same benchmark family (LoCoMo): one claimed 84%, the other disputed it to 58%, the first counter-claimed 75%. A single SciFact run on one local model will produce a number with the same fragility — easy to report, easy to contest, not on its own load-bearing evidence that the Review step is trustworthy in production. Still worth running; just don't let it close criterion #4 as if it were a court ruling rather than a data point.

**24.3 — The hardware roadmap's hardest barrier isn't in the Risk Register, and it isn't software.** Sections 9, 12, and 13 describe Phases 2–4 as an engineering sequence — sensors, fusion, ruggedization. The competitive set in that eventual market (908 Devices' MX908, Smiths Detection's LCD4, ChemProX) is MIL-STD-810/461 and ATEX-certified, sold through NATO procurement, backed by 30+ years of institutional trust. None of Section 17's hardware risks mention certification cost, hazardous-location testing, or procurement relationships — every listed risk is technical (latency, fusion accuracy, sensor cost). Getting from a Raspberry Pi prototype to anything competitive in that specific market is gated by capital and regulatory time, which clean agent-loop code does not shorten. This doesn't block Phase 2–3 (a researcher's desk instrument doesn't need ATEX certification); it specifically blocks treating Phase 4's "field-ready instrument" framing as a software-distance-away goal.

**24.4 — The interaction model may not match the eventual buyer.** A field operator in the hazmat/CBRN space wants "sarin, 94% confidence, alarm" in under a second — literally what MX908 and ChemProX are built to do. Victor's whole interaction model — MEASUREMENT > EXPERIMENT > LITERATURE provenance chains, citation-per-answer — is a researcher's-desk UX, not a field-detection UX. Sections 12–13 add sensors underneath that same interaction model without resolving that handheld field detection and desk-based research synthesis may be different products for different buyers with different decision-speed requirements. Not a reason to drop either direction — a reason to decide, before Phase 4, which buyer Phase 4 is actually for.

**24.5 — A specific, zero-new-dependency technical lever exists for closing criterion #4, found by checking what the field actually uses for this exact task.** SciFact's own original baseline (VERISCI, Wadden et al. 2020) frames confirm/contradict/inconclusive as textual entailment (NLI), not free-form LLM judgment — the published baseline fine-tunes RoBERTa-large for that specific 3-way label prediction, and a 2024 follow-up reports 88% F1 on SciFact by fine-tuning DeBERTa for the same task. `sentence-transformers` — already a `requirements.txt` dependency via `embedder.py`'s `LocalEmbedder`, not a new library — ships ready-to-use NLI cross-encoders (`cross-encoder/nli-deberta-v3-base`, ~90% accuracy on MNLI mismatched) whose three native output labels (contradiction / entailment / neutral) map directly onto Victor's confirm/contradict/inconclusive taxonomy. The vision-aligned use is not replacing the LLM call but cross-checking it inside `ConflictDetector.judge()`: when the LLM says confirm or inconclusive and the cross-encoder says contradiction, that is the exact agreement-bias failure mode the SciFact run diagnosed (see `SCIFACT_BENCHMARK_RESULTS.md` — 27% recall on `contradict` at baseline), caught instead of silently passed through, with both judgments kept as edge provenance rather than one overwriting the other — Section 4's "the system surfaces disagreement rather than suppressing it" principle applied to Victor's own pipeline, not just to what it stores about the world. One caveat that matters specifically for criterion #4's number: a SciFact-domain-finetuned checkpoint exists (`MilosKosRad/DeBERTa-v3-large-SciFact`, the model behind the 88% F1 figure), but its public model card does not state whether `claims_dev.jsonl` was excluded from its own fine-tuning data — using it without independently confirming that split would import the same train/test-contamination risk into Victor's benchmark number that 24.2 already warns the field is prone to. The generic, never-trained-on-SciFact `cross-encoder/nli-deberta-v3-base` is the contamination-free default if criterion #4 needs to survive scrutiny rather than just produce a high number.

**24.6 — The eventual LoRA fine-tuning phase has a hardware requirement the current local-first framing doesn't yet surface.** Inference (Ollama, `qwen2.5:7b`) runs CPU-only on the laptop-class hardware Phase 0–1 targets. Training does not: the current standard local LoRA/QLoRA stack (Unsloth, on top of `peft`/`transformers`) needs a CUDA GPU with roughly 8–12GB VRAM even for 4-bit QLoRA on a 7B model — a Raspberry Pi field unit can run a fine-tuned adapter but cannot produce one. This doesn't conflict with the architecture (training was always going to happen on a researcher's workstation, with only the resulting adapter shipping to the field device), but Phase 5 planning should state that explicitly rather than inherit Phase 0–1's offline-laptop framing by default. Separately: the agreement-bias pattern in 24.5 and Section 8 criterion #4 has a named, actively-studied 2025–2026 literature behind it ("sycophancy bias"), and the field's heavy-duty fix is fine-tuning on synthetic contrastive-disagreement data — real, published, not a Victor-specific workaround, but squarely inside the fine-tuning gate Section 8 correctly keeps closed until all ten criteria are true. Useful to know the failure mode has a name and a literature; not yet actionable here.

**What this section does not change:** none of 24.1–24.6 move any Section 8 DoD checkbox, any Phase exit criterion, or the Phase 0/1 software audit. 24.5 documents a candidate technical lever for *how* criterion #4's number might improve — it does not close criterion #4 itself; only a real benchmark run does that. They're additions to the picture this document gives of *why* to build the next thing, not corrections to *what* has been built.
