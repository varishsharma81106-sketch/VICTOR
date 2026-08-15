# VICTOR — Project Status
*Session: 2026-08-12 · Code version: v5.3.0*

---

> **TL;DR:** AAAI 2027 paper submitted (July 22, 2026). Decision ~October 2026. Primary mode benchmark conclusively failed (8%). Cross-check mode at 71% is the correct architecture. Next: self-consistency voting, threshold sweep, or fine-tuning to close DoD #4 (85%).

---

## Current Phase

**Phase 1 — AI Brain (mostly complete)**
- Phase 0: ✅ Complete
- Phase 1A: ✅ Complete (LibrosaFeatureClassifier)
- DoD #4: ❌ Open — SciFact ≥85% (current best: 71.0%, cross-check mode)
- Phase 1B: ⏳ Blocked on DoD #4

**You are here:** Closing DoD #4 → then ingest one real document → then Phase 1B (sensor fusion)

---

## AAAI 2027 Submission Status

| Item | Status | Details |
|------|--------|---------|
| **Paper** | ✅ Submitted | Abstract-only on OpenReview |
| **Decision** | ⏳ Pending | Expected ~October 2026 |
| **Title** | Victor: A Local-First Research Intelligence System with Epistemic Provenance and NLI-Augmented Conflict Detection | |
| **Topics** | KRR, Graph ML, Neuro-Symbolic Reasoning | |
| **License** | CC BY 4.0 | MIT for code |
| **Submission files** | `paper/`, `paper 22july/` | ⚠️ Untracked in git |

---

## SciFact Benchmark — Complete History

| Run | Version | Mode | n | Accuracy | Status | Notes |
|-----|---------|------|---|----------|--------|-------|
| 1 | v4.9 | Pure LLM | 50 | 68.0% | Baseline | Agreement bias confirmed |
| 2 | v5.1 | Structured JSON | 50 | 58.0% | Regression | Schema amplifies bias |
| 3 | v5.1 | No NLI | 100 | 59.0% | LLM ceiling | Pure-LLM ceiling ~59% |
| 4 | v5.2 | DeBERTa primary (WRONG label order) | 100 | 8.0% | Bug | Label order bug |
| 5 | v5.2 | DeBERTa cross-check | 100 | **71.0%** | **Best** | LLM decides, NLI catches bias |
| 6 | v5.2 | ModernCE primary (WRONG label order) | 5 | 20.0% | Bug | Label inversion |
| 7 | v5.2 | ModernCE primary (WRONG label order) | 100 | 12.0% | Bug | Systematic inversion |
| 8 | v5.3 | DeBERTa primary (CORRECT label order) | 100 | 8.0% | **Conclusive** | NLI can't handle long text |

### Key Findings

1. **Primary mode with DeBERTa-v3-base is definitively ruled out** — Run 8 confirms the issue is model capacity (MNLI-trained on short sentences), not label order. All 100 samples predicted "inconclusive".

2. **Cross-check architecture is correct** — Run 5 (71%) works because LLM handles long-text reasoning while NLI catches agreement bias on ~8 samples.

3. **Agreement bias is the core problem** — Instruction-tuned LLMs default to "confirm" under uncertainty. NLI cross-check catches this on a subset.

### Path to 85%+

| Priority | Action | Expected Impact | Effort |
|----------|--------|-----------------|--------|
| 1 | Self-consistency voting (3-5 calls, majority vote) | +3-5% | Free |
| 2 | Threshold sweep (0.3, 0.4, 0.5, 0.6) | +1-3% | 30 min |
| 3 | DeBERTa-v3-large cross-check | +2-3% | 30 min |
| 4 | Fine-tune DeBERTa on SciFact train split | Could reach 85%+ | Days (GPU) |

---

## Codebase State

| Metric | Value |
|--------|-------|
| Version | v5.3.0 |
| Tests | 196/196 passing |
| Test files | 12 |
| Python | 3.14 (alpha) |
| LLM | Qwen2.5-7B (Ollama) |
| NLI | DeBERTa-v3-base |
| Embedder | nomic-embed-text-v1.5 |
| Vector store | ChromaDB |
| Graph | NetworkX + JSON |

### Core Components Built

| Component | Status | File |
|-----------|--------|------|
| Knowledge graph | ✅ | `graph.py` |
| Ingestion pipeline | ✅ | `ingest.py` |
| Agent loop | ✅ | `retrieve.py` |
| ConflictDetector | ✅ | `reasoning.py` |
| NLICrossEncoder | ✅ | `reasoning.py` |
| Masked memory | ✅ | `core.py`, `graph.py` |
| StatisticsKernel | ✅ | `kernels.py` |
| Camera ingestor | ✅ | `sensors.py` |
| Audio ingestor | ✅ (simplified) | `sensors.py` |
| CLI | ✅ | `cli.py` |
| SciFact benchmark | ✅ | `scifact_benchmark.py` |

### Known Issues

1. **`find_gaps()` leaks masked content** — Masking gate not propagated to `reasoning.py` `find_gaps()`. Blocks MCP server.
2. **Primary mode fails on long text** — DeBERTa-v3-base NLI defaults to neutral on 200-word abstracts.
3. **No real research data ingested** — Phase 0 exit criteria require `victor gaps` on at least one real document.
4. **Paper files untracked** — `paper/`, `paper 22july/`, `victor_aaai27.pdf` not in git.

---

## Build Sequence Progress

```
Phase 0 — Software brain, text only             ✅ COMPLETE
    ↓
Phase 1A — Audio ingestion                      ✅ COMPLETE
    ↓
    ← YOU ARE HERE: Close DoD #4 (SciFact ≥85%)
    ← Then: ingest one real document, run `victor gaps`
    ↓
Phase 1B — Sensor fusion + PANNs audio upgrade   ← Next new capability
Phase 2A — UncertaintyPropagationKernel          ← Can run parallel
Phase 3A–D — Model stack upgrade                 ← Can run parallel
Phase 4A — Conversation memory                   ← After 3+ months
Phase 4B — Proactive pattern detection           ← After 3+ months
Phase 5 — Field prototype (hardware)             ← After software stable
Phase 6 — Multi-sensor unit                      ← After Phase 5
Phase 4C — LoRA fine-tuning                      ← After 500+ turns
Phase 1C — Spectral/Chemical ingestion           ← Requires hardware
```

---

## Immediate Next Steps (This Week)

1. **Git hygiene** — Commit untracked paper files
2. **Self-consistency voting** — Implement majority-vote over 3-5 calls
3. **Threshold sweep** — Test 0.3, 0.4, 0.5, 0.6 on cross-check mode
4. **Ingest one real paper** — `victor ingest data/arxiv_selective_cot_medical_qa.txt --type paper`
5. **Run `victor gaps`** — Verify Phase 0 exit criteria on real data

---

## Obsidian Vault Links

### Core Documents
- [[VICTOR_CANON]] — Vision/identity
- [[VICTOR_THEORY_v1]] — Unit of value
- [[VICTOR_FOUNDATION_v2]] — Design principles
- [[VICTOR_WHAT_IS_BUILT]] — Code state + next action
- [[VICTOR_BUILD_SEQUENCE]] — Build order

### Technical Documents
- [[VICTOR_SCIFACT_ACCURACY_PLAN]] — Benchmark history + diagnosis
- [[VICTOR_MASTER_PRD_v3_6]] — DoD + risk register
- [[VICTOR_STRATEGY]] — Competitive landscape + roadmap
- [[PROJECT_UPDATES]] — Session logs

### Reference Documents
- [[VICTOR_ORIGINAL]] — Original conception
- [[VICTOR_INDEX]] — Document index
- [[PAPER_AAAI_2027_Victor]] — Paper content

### Related Files
- `victor/scifact_benchmark.py` — Benchmark harness
- `victor/reasoning.py` — ConflictDetector + NLICrossEncoder
- `victor/core.py` — Victor controller
- `victor/cli.py` — Command-line interface

---

## Environment Quick Reference

| Item | Value |
|------|-------|
| Ollama | Running on `http://127.0.0.1:11434` |
| Model | `qwen2.5:7b` (Q4_K_M) |
| NLI | `cross-encoder/nli-deberta-v3-base` |
| SciFact data | `data/corpus.jsonl`, `data/claims_dev.jsonl` |
| Python | 3.14 (alpha) |
| OS | Windows 11 |

---

*Last updated: 2026-08-12 · Victor v5.3.0*
*For the latest code state, see [[VICTOR_WHAT_IS_BUILT]]*
*For the benchmark path, see [[VICTOR_SCIFACT_ACCURACY_PLAN]]*
