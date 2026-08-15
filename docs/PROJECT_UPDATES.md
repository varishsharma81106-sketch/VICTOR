# VICTOR — Project Updates Log

---

## Repository Status

- **Current version:** v5.3.0
- **Current project health:** Functional core pipeline, 212 tests passing
- **Major completed milestones:**
  - Phase 0: Software brain (text-only) — complete
  - Phase 1A: Audio ingestion — complete (simplified LibrosaFeatureClassifier)
  - Agent loop with tool calling — complete
  - PatternDetector unprompted surfacing — complete
  - NLI cross-encoder wiring — complete
  - Masked memory with audit log — complete
  - Real paper ingestion validated — complete (arXiv 2602.20130)
  - Windows Unicode compatibility — complete (all ASCII fallbacks)
- **Major unfinished work:**
  - DoD #4: SciFact accuracy ≥85% (current best: 71.0%, Run 5)
  - MCP server implementation
  - Graph decomposition for embedded deployment
  - LoRA fine-tuning pipeline (gated on DoD #4)
  - Spectral/chemical ingestion (gated on hardware)

---

## Today's Changes (2026-06-29)

### Files Updated

| File | Change |
|------|--------|
| `victor/reasoning.py` | Added `_masked_summary()` static method and masking gate in `summarize_claim()` to prevent masked content from surfacing in answers. Fixed `_LABEL_ORDER` default to `["contradiction", "entailment", "neutral"]`. Fixed Windows Unicode in `validate_label_order()` — replaced `✓`/`✗`/`→` with ASCII. |
| `victor/graph.py` | Added `is_masked` check in `semantic_query()` to skip masked nodes during cosine search. |
| `victor/vector_store.py` | Updated docstring to reflect Option A (ChromaDB deletion on mask) is implemented. Added `delete_node_chunks()` method with comment. Consolidated `delete_source()` to delegate to `delete_node_chunks()`. |
| `victor/core.py` | Wired `delete_node_chunks()` into `mask()` method. Added `source_type` parameter to `ingest_file()` for paper vs note override. |
| `victor/ingest.py` | `MarkdownIngestor.ingest()` now accepts `source_type` parameter — `"paper"` → PAPER/LITERATURE tier (weight 0.70), default → NOTE tier (weight 0.50). |
| `victor/cli.py` | Added `--type paper|note` option to `ingest` command. Replaced all Unicode `→` characters with ASCII `->` in console.print statements. |
| `victor/scifact_benchmark.py` | Replaced all Unicode characters (✓, ✗, →, …, ⚠, ✅, ❌) with ASCII equivalents for Windows terminal compatibility. Fixed two syntax errors from prior edits. |
| `setup.py` | Added `python_requires=">=3.12"` to setup() call. |
| `requirements.txt` | Updated version comment from "v4.6" to "v5.3.0". |
| `VICTOR_STRATEGY.md` | Updated pitch to "prove what it was allowed to see" framing. Added tamper-evident disclosure log as competitive differentiator item 4. Corrected compounding graph claim to acknowledge competitors. |
| `README.md` | Created with project description, install instructions, quick start, security section, and status. |

### Files Created

| File | Purpose |
|------|---------|
| `README.md` | Project landing page with pitch, install, quick start, security, status |
| `docs/PROJECT_UPDATES.md` | This file — maintenance session log |
| `data/arxiv_selective_cot_medical_qa.txt` | Real arXiv paper for ingestion validation |
| `data/corpus.jsonl` | SciFact corpus (downloaded from S3) |
| `data/claims_dev.jsonl` | SciFact claims (downloaded from S3) |
| `data/claims_train.jsonl` | SciFact training claims |
| `data/claims_test.jsonl` | SciFact test claims |

### Files Archived

| File | Reason |
|------|--------|
| `SESSION_REPORT_2026-06-28.md` | Session-specific report, superseded by this update log |
| `VICTOR_MASTER_PRD_v3_6.md` (root copy) | Duplicate of `info/VICTOR_MASTER_PRD_v3_6.md` |
| `VICTOR_SCIFACT_ACCURACY_PLAN.md` (root copy) | Duplicate of `info/VICTOR_SCIFACT_ACCURACY_PLAN.md` |
| `VICTOR_BUILD_SEQUENCE.md` (root copy) | Duplicate of `docs/VICTOR_BUILD_SEQUENCE.md` |
| `VICTOR_WHAT_IS_BUILT.md` (root copy) | Duplicate of `docs/VICTOR_WHAT_IS_BUILT.md` |
| `data/._data` | Stale macOS artifact |

### Files Cleaned

| File | Change |
|------|--------|
| `data/._data` | Deleted (macOS metadata artifact) |

---

## Future Recommendations

### High Priority

1. **Run SciFact benchmark with a scientific NLI model** — ModernCE at 35% accuracy confirms general-domain NLI is actively harmful. Try `allenai/scibert_scivocab_uncased` fine-tuned on SciFact, or LoRA fine-tune Qwen2.5:7B on the SciFact train split.
2. **Add claim deduplication to ingestion pipeline** — Real paper test revealed near-duplicate claims extracted from abstract vs. results sections. No dedup pass exists.
3. **Fix ClaimExtractor quality** — Garbage claim #5 ("2.2 Selective Chain-of-thought...") grabbed a section heading instead of an actual claim. The extractor needs better prompting or post-processing.

### Medium Priority

4. **Build MCP server using FastMCP** — The 5-tool surface (`victor_ask`, `victor_gaps`, `victor_ingest`, `victor_mask`/`unmask`, `victor_stats`) is ready. Use `from mcp.server.fastmcp import FastMCP` with `@mcp.tool()` decorators (~50 lines). `victor_ingest` should be v2-only due to ASI06 ingest poisoning risk.
5. **Add `test_chunker.py` and `test_extractor.py`** — These modules have zero test coverage. The WHAT_IS_BUILT doc confirmed this gap.
6. **Fix `_LABEL_ORDER` class default** — The class-level default is `["contradiction", "neutral", "entailment"]` but the model's actual id2label is `["contradiction", "entailment", "neutral"]`. Auto-detection overrides correctly, but the fallback is wrong.
7. **Update extraction log path** — `~/.victor/logs/extraction_log.jsonl` was not found after real paper ingestion. Verify the actual path.

### Low Priority

8. **Lazy-load `_embeddings` dict in graph.py** — Currently loads every node embedding on startup. Use LRU cache or SQLite sidecar for graphs >10K nodes. Not urgent (2027 problem at current ingestion rates).
9. **Add temporal decay tests** — `apply_temporal_decay()` has zero tests. Needs at least one test confirming decay rate produces correct results after a known time delta.
10. **Consolidate `delete_source()` and `delete_node_chunks()` naming** — Both exist in vector_store.py with similar semantics. The consolidation is done but the naming could be clearer.

### Research Ideas

11. **Qwen3-Embedding-small as alternative embedder** — Config.py already noted this model as #1 on MTEB multilingual (June 2026). Worth benchmarking against nomic-embed-text-v1.5 for scientific text retrieval.
12. **Self-consistency voting for SciFact** — Call `judge()` 3-5 times per sample, majority-vote the direction. No code changes needed, just more compute.
13. **OWASP Agent Memory Guard integration** — For MCP server phase. Add prompt injection detection on extracted claims before graph insertion.

### Technical Debt

14. **`evaluate.py` is wired but untested** — `VictorEvaluator` exists and is exposed via CLI, but has never been run on actual data. Needs a 5-question eval file.
15. **`requirements.txt` has `typer>=0.9.0` but CLI uses `click`** — typer is unused. Remove it.
16. **Python 3.14 alpha bytecode** — `__pycache__` files confirm cpython-314. `setup.py` now has `python_requires=">=3.12"` but should document the alpha risk.

---

## Known Issues

1. **ModernCE cross-check mode scored 35% accuracy** — General-domain NLI models are actively harmful for scientific claim verification. The NLI component needs either a scientifically fine-tuned model or removal from cross-check mode.
2. **ChromaDB `delete_node_chunks()` is a no-op for claim nodes** — ChromaDB chunks use paper source_id, not claim node_id. Masking a claim node finds 0 matching chunks. This is architectural (claims don't have their own ChromaDB chunks) but means the embedding covert channel remains open at the paper chunk level.
3. **`victor_ingest` MCP tool is highest risk** — RAG/embedding poisoning via untrusted pipelines is an ASI06 attack vector. Should be v2-only after input sanitization is solid.
4. **No README badges or CI** — The README is functional but has no CI pipeline, no badges, no automated test reporting.

---

## Today's Changes (2026-08-12)

### Session Focus

AAAI 2027 paper submitted (July 22, 2026). Ran critical benchmark: DeBERTa-v3-base NLI primary mode with corrected label order (Run 8). Result: **8.0% accuracy** — all 100 samples predicted inconclusive. Root cause: model fine-tuned on MNLI (short sentence pairs) cannot handle long scientific text (200-word abstracts). Label order smoke test passed. This conclusively rules out primary mode for this model.

### Files Updated

| File | Change |
|------|--------|
| `docs/VICTOR_WHAT_IS_BUILT.md` | Added Run 8 to Results Log. Updated version header to "Updated 2026-08-12". |
| `docs/VICTOR_SCIFACT_ACCURACY_PLAN.md` | Added Run 8 to benchmark history. Added Cause D diagnosis (cross-encoder NLI can't handle long text). Updated "What not to do" section. |
| `docs/VICTOR_BUILD_SEQUENCE.md` | Updated benchmark table with Run 8. Added note that primary mode is ruled out. |
| `docs/VICTOR_STATUS_2026-08-12.md` | **NEW** — Comprehensive project status with Obsidian bidirectional links. |
| `docs/VICTOR_INDEX.md` | Added new status doc reference. |

### Key Findings

1. **Primary mode with DeBERTa-v3-base is definitively ruled out** — Run 8 confirms the issue is model capacity (MNLI-trained on short sentences), not label order. All 100 samples predicted "inconclusive".
2. **Cross-check architecture is correct** — Run 5 (71%) works because LLM handles long-text reasoning while NLI catches agreement bias on ~8 samples.
3. **Agreement bias is the core problem** — Instruction-tuned LLMs default to "confirm" under uncertainty.

### Masking Bug Fix (2026-08-12)

Fixed content leak in masked memory anchors across three files:

| File | Method | Issue |
|------|--------|-------|
| `tools.py` | `_anchor_for()` | Leaked first 40 chars of label |
| `reasoning.py` | `_masked_summary()` | Leaked first 40 chars of label |
| `retrieve.py` | `_make_anchor()` | Leaked first 40 chars of label |

All three now show `[MASKED — claim — content withheld. Use 'victor unmask <id>']` with no content leakage. All 40 masking tests pass. All 212 tests pass.

### Next Steps

1. **Self-consistency voting** — Implement majority-vote over 3-5 calls (free accuracy improvement)
2. **Threshold sweep** — Test 0.3, 0.4, 0.5, 0.6 on cross-check mode
3. **Ingest one real paper** — Verify Phase 0 exit criteria
4. ~~**Fix masking bug**~~ — ✅ Fixed 2026-08-12

---

*Last updated: 2026-08-12 · Victor v5.3.0*
