# PROMPT FOR AI ASSISTANTS
## Working with Victor v5.4

---

## Quick Start

**Read this file first.** Then read `docs/VICTOR_STATUS_2026-08-12.md` for current state.

---

## What Is Victor?

Victor is a **local-first research intelligence system** with epistemic provenance and NLI-augmented conflict detection. It runs entirely on your machine — no cloud required.

**Key features:**
1. Epistemic Artifact abstraction (6 provenance properties)
2. NLI-primary conflict detection (cross-encoder decides, LLM annotates)
3. Masked memory with embedding-channel closure
4. Bounded agent loop (5 calls, 8K tokens)

---

## Current State (2026-08-12)

| Item | Status |
|------|--------|
| **AAAI 2027 Paper** | ✅ Submitted (July 22, 2026) |
| **Decision** | ⏳ Expected ~October 2026 |
| **Codebase** | v5.4.0, 421/421 tests passing |
| **SciFact Benchmark** | 71.0% (cross-check mode, n=100) |
| **DoD #4 (85%)** | ❌ Not yet met |
| **Primary Mode** | ❌ Conclusively ruled out (8%) |

---

## Project Structure

```
victor/
├── victor/           # Core Python package
├── tests/            # 421 tests (16 files)
├── docs/             # Documentation (Obsidian-compatible)
├── data/             # SciFact benchmark data
├── paper/            # AAAI 2027 paper
├── paper 22july/     # Submission files
├── examples/         # Sample files
└── scripts/          # Verification scripts
```

---

## Reading Order

### For Quick Overview (5 min)
1. `docs/VICTOR_INDEX.md` — Document index
2. `docs/VICTOR_STATUS_2026-08-12.md` — Current state

### For Code Understanding (15 min)
1. `docs/VICTOR_WHAT_IS_BUILT.md` — What exists, what's broken
2. `victor/core.py` — Main controller
3. `victor/reasoning.py` — ConflictDetector + NLICrossEncoder

### For Benchmark Context (10 min)
1. `docs/VICTOR_SCIFACT_ACCURACY_PLAN.md` — Full benchmark history
2. `victor/scifact_benchmark.py` — Benchmark harness

---

## Key Commands

```bash
# Install
pip install -e .

# Run benchmark (cross-check mode - current best)
OLLAMA_HOST=http://127.0.0.1:11434 python -m victor.scifact_benchmark \
  --corpus-path data/corpus.jsonl \
  --claims-path data/claims_dev.jsonl \
  --n-samples 100 \
  --nli-model cross-encoder/nli-deberta-v3-base \
  --nli-threshold 0.5

# Run tests
pytest tests/ -v

# Ingest a paper
victor ingest paper.pdf --type paper

# Ask a question
victor ask "What evidence supports this claim?"
```

---

## What Needs To Be Done

### Immediate (This Week)
1. **Self-consistency voting** — Implement majority-vote over 3-5 calls
2. **Threshold sweep** — Test 0.3, 0.4, 0.5, 0.6 on cross-check mode
3. **Ingest one real paper** — `victor ingest data/arxiv_selective_cot_medical_qa.txt --type paper`
4. **Fix masking bug** — `find_gaps()` leaks masked content

### Medium Term (Aug-Oct 2026)
1. **Close DoD #4** — SciFact ≥85% accuracy
2. **Build MCP server** — 5-tool surface for Claude Desktop/Cursor
3. **Prepare for camera-ready** — If AAAI accepted

### Long Term (2027+)
1. **Sensor fusion** — Multi-modal observations
2. **Hardware prototype** — Raspberry Pi 5
3. **LoRA fine-tuning** — After 500+ real turns

---

## Critical Learnings

1. **Primary mode with DeBERTa-v3-base is ruled out** — Run 8 (8%) proved the model can't handle long scientific text. Cross-check mode (71%) is the correct architecture.

2. **Agreement bias is the core problem** — LLMs default to "confirm" under uncertainty. NLI cross-check catches this on ~8 samples.

3. **Label order matters** — DeBERTa outputs [contradiction, neutral, entailment]. ModernCE outputs [entailment, neutral, contradiction]. Always run smoke test first.

4. **Masking is critical** — `find_gaps()` still leaks masked content. Fix before MCP server.

---

## Environment Requirements

| Item | Value |
|------|-------|
| Python | 3.12+ |
| Ollama | Running on `http://127.0.0.1:11434` |
| Model | `qwen2.5:7b` (Q4_K_M) |
| NLI | `cross-encoder/nli-deberta-v3-base` |
| Embedder | `nomic-embed-text-v1.5` |
| SciFact data | Present in `data/` |

---

## Obsidian Documentation

The `docs/` folder is Obsidian-compatible with bidirectional links.

**To use:**
1. Open Obsidian
2. Open folder as vault: `docs/`
3. Enable "Use [[Wikilinks]]" in Settings
4. Open Graph view to see connections

**Key documents:**
- `VICTOR_INDEX.md` — Entry point
- `VICTOR_STATUS_2026-08-12.md` — Current state
- `VICTOR_WHAT_IS_BUILT.md` — Code state
- `VICTOR_BUILD_SEQUENCE.md` — Build order
- `VICTOR_SCIFACT_ACCURACY_PLAN.md` — Benchmark history
- `VICTOR_LINKS.md` — Bidirectional link map

---

## AI Assistant Guidelines

When working with Victor:

1. **Always read `docs/VICTOR_INDEX.md` first** — It tells you which document answers your question.

2. **Never read all documents** — They contradict each other on version-specific details.

3. **Check test count** — Current: 421/421. If tests fail, something broke.

4. **Run benchmark with OLLAMA_HOST set** — `export OLLAMA_HOST=http://127.0.0.1:11434`

5. **Use cross-check mode, not primary mode** — Primary mode is ruled out for DeBERTa-v3-base.

6. **Fix masking before MCP** — `find_gaps()` leaks masked content.

7. **Commit frequently** — Paper files are currently untracked.

---

## ZIP Contents

This ZIP contains the complete Victor project as of 2026-08-12:

- `victor/` — Core Python package
- `tests/` — 421 tests (16 files)
- `docs/` — Documentation (Obsidian-compatible)
- `data/` — SciFact benchmark data
- `paper/` — AAAI 2027 paper
- `paper 22july/` — Submission files
- `examples/` — Sample files
- `scripts/` — Verification scripts

**Total size:** ~18MB

---

## Questions?

- **For code questions:** Read `docs/VICTOR_WHAT_IS_BUILT.md`
- **For benchmark questions:** Read `docs/VICTOR_SCIFACT_ACCURACY_PLAN.md`
- **For strategy questions:** Read `docs/VICTOR_STRATEGY.md`
- **For current state:** Read `docs/VICTOR_STATUS_2026-08-12.md`

---

*Created: 2026-08-12 · Updated 2026-09-05 · Victor v5.4.0*
