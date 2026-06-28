# VICTOR — What Is Built
*Code version: v4.6 · Date: June 2026*

---

> This document is updated every time the code changes.
> Check the version header before reading. An outdated version of this document is worse than no document.

---

## The One-Line State

The knowledge graph, reasoning layer, ingestion pipeline, and camera sensor pipeline are built and tested. Two bugs remain that break real usage. The SciFact benchmark has not been run. No real research data has been ingested.

---

## What Exists — Full File Map

```
victor/
├── victor/
│   ├── models.py          — EpistemicStatus (5-tier), ObservationResult, ConflictResult, all dataclasses
│   ├── graph.py           — VictorKnowledgeGraph, add_observation(), freeze/unfreeze, atomic save, temporal decay
│   ├── core.py            — Victor controller, ingestion, query, patterns, stats, AgenticRetriever wired
│   ├── cli.py             — Full Rich CLI: ingest, ask, gaps, observe, inspect, stats
│   ├── sensors.py         — CameraIngestor, CLIPClassifier, MockClassifier (Reality → Artifact pipeline)
│   ├── reasoning.py       — ConflictDetector (LLM-based), EvidenceWeighter, GapDetector, PatternDetector
│   ├── retrieve.py        — HybridRetriever + AgenticRetriever (bounded agent loop)
│   ├── llm.py             — Ollama + OpenAI + Mock fallback chain
│   ├── ingest.py          — PDF, Markdown, Experiment JSON ingestors, IngestorBase plugin arch
│   ├── extractor.py       — LLM-based claim extraction
│   ├── embedder.py        — sentence-transformers LocalEmbedder (nomic-embed-text primary)
│   ├── vector_store.py    — ChromaDB wrapper
│   ├── tools.py           — ToolRegistry for agent loop
│   ├── kernels.py         — StatisticsKernel, Cohen's d, confidence intervals, reproducibility hashes
│   ├── chunker.py         — TextChunker
│   ├── evaluate.py        — VictorEvaluator
│   ├── scifact_benchmark.py — SciFact eval harness (built, never run)
│   └── config.py          — VictorConfig
├── tests/
│   ├── test_agent_loop.py
│   ├── test_scifact_benchmark.py
│   ├── test_statistics_kernel.py
│   └── test_sensor_pipeline.py   — MockClassifier tests, no GPU required
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
| EvidenceWeighter | ✅ Built | `reasoning.py` |
| GapDetector | ✅ Built | `reasoning.py` |
| PatternDetector | ✅ Built, not surfaced unprompted | `reasoning.py` |
| Weighted retrieval (0.7 × cosine + 0.3 × importance) | ✅ Built | `retrieve.py` |
| Temporal decay | ✅ Built | `graph.py` |
| Conversation memory as graph nodes | ✅ Built | `core.py` |
| Model-agnostic InferenceClient | ✅ Built | `llm.py` → Ollama / OpenAI / Mock |
| StatisticsKernel | ✅ Built | `kernels.py` |
| Reality → Artifact pipeline (camera) | ✅ Built | `sensors.py` → CameraIngestor + CLIP |
| Agent loop (agentic retrieval) | ⚠️ Partial | Skeleton exists, quadratic token counting breaks it |
| SciFact benchmark result | ❌ Not done | `scifact_benchmark.py` exists, never run |
| FastAPI endpoint | ❌ Not built | No web interface |
| Graph visualization | ❌ Not built | No browser view |
| Audio ingestion | ❌ Not started | Layer 1, Phase 2 |
| Spectral ingestion | ❌ Not started | Layer 1, Phase 2 |

---

## Known Bugs — Priority Order

### Bug 1 — AgenticRetriever quadratic token counting [HIGH]
**File:** `retrieve.py`, line ~418
**What it does:** `self._context_tokens += _estimate_tokens(prompt) + _estimate_tokens(llm_result.text)` — `prompt` is rebuilt from accumulated context every turn. Token count grows quadratically. Agent loop exits by turn 2–3 in real use.
**Effect:** Agent loop effectively non-functional on any real query that needs more than two reasoning steps.
**Fix:** Count only the delta added each turn, not the full accumulated prompt.

### Bug 2 — `compute_statistics` conflates metrics [MEDIUM]
**File:** `kernels.py`, lines ~526–529
**What it does:** Loops `for k, v in results_dict.items()` and appends every numeric field indiscriminately. An experiment with `{"precision": 0.87, "recall": 0.72, "f1": 0.80}` averages all three together as if they are the same measurement.
**Effect:** StatisticsKernel produces incorrect aggregates for multi-metric experiments.
**Fix:** Require explicit metric specification. Don't auto-aggregate all numeric fields.

---

## What Is NOT Built (Confirmed Absent)

These are not partial or buggy — they genuinely do not exist in the codebase.

- `api.py` — no FastAPI or any web endpoint. CLI only.
- Graph visualization — no browser view of the knowledge graph.
- Audio ingestion — `AudioIngestor` does not exist. Librosa/PANNs not integrated.
- Spectral ingestion — no spectrometer pipeline.
- Encryption on export — `export` command exists but output is unencrypted.
- LoRA fine-tuning pipeline — not started. Requires 500+ real conversation turns first.
- Multi-user or federation — out of scope until single-user is solid.
- SciFact accuracy number — harness exists, has never been run.

---

## The Next Three Actions — In Exact Order

**Action 1: Fix the quadratic token counting bug.**
File: `retrieve.py`. One fix, one test. Until this is fixed, the agent loop cannot be used in production and the retrieval layer is not actually working correctly.

**Action 2: Run the SciFact benchmark.**
```bash
python -m victor.scifact_benchmark --samples 200
```
This produces the only real number that tells you whether ConflictDetector works. The README should not claim anything about Victor's conflict detection capability until this number exists.

**Action 3: Ingest one real research document and run `victor gaps`.**
```bash
victor ingest your_paper.pdf --extract-claims
victor ask "what does this say about X?"
victor gaps
```
This is the actual test of whether Victor works on real data. Everything else is testing infrastructure. `gaps` output is what makes Victor different from any other RAG system. If that output is useful, the system is working.

Do not build anything new until these three actions are complete and their results documented at the bottom of this file.

---

## Results Log
*Append results here when actions above are completed. Do not edit prior entries.*

| Date | Action | Result |
|------|--------|--------|
| 2026-06-23 | Bug 1 fixed — quadratic token counting (`retrieve.py` line ~418) | Changed `self._context_tokens +=` to `self._context_tokens =`. Token budget now tracks current turn size (linear) rather than re-summing all prior turns (quadratic). Agent loop no longer exhausted after 2–3 turns. |
| 2026-06-23 | Bug 2 fixed — `compute_statistics` metric conflation (`core.py` lines ~526–529) | `results_dict` loop now extracts only the key matching `metric_name` instead of appending every numeric field. Multi-metric experiments (e.g. `{"precision": 0.87, "recall": 0.72, "f1": 0.80}`) no longer produce a meaningless average across unrelated measurements. |
| 2026-06-23 | PatternDetector wired — automatic surfacing in `ask_full` | `ask_full()` now calls `_inject_pattern_note()` on every answer. No flag needed; pattern insights appear automatically when query overlaps a priority gap (cosine > 0.65). `ask_with_patterns()` retained as alias for back-compat. CLI `--show-patterns` default changed to `True`; use `--no-show-patterns` to suppress. |
| — | SciFact benchmark | Not yet run — requires network access + Ollama/OpenAI. Run locally: `python -m victor.scifact_benchmark --samples 200`. Write result here. |

---

## Version History of This Document

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial document created |

*VICTOR_WHAT_IS_BUILT.md · v4.6 · June 2026*
