# VICTOR — Strategic Analysis
*Generated 2026-06-28 · Session synthesis of competitive research, technical planning, and startup framing*

---

## 1. Competitive Landscape (as of June 2026)

### Category 1: Scientific Claim-Verification Agents
- **PaperQA2** (FutureHouse) — built specifically for dense, jargon-heavy scientific literature. Exceeds human performance on QA, summarization, contradiction detection. Frontier-model-backed.
- **OpenScholar** — synthesizes from 45M papers, outperforms GPT-4o by 5% on ScholarQABench.
- **Valsci** — similar category.
- **Victor cannot win head-to-head on raw literature QA accuracy.** That's not the right battle. Chasing NLI-primary accuracy toward 85% on SciFact is optimizing the wrong thing.

### Category 2: Local-First PKM / Second Brain Apps
- **Obsidian** — 1.5M+ users, 22% YoY growth.
- **Mem, Tana, Reflect, Rowboat, Cortex** — Rowboat builds typed knowledge graphs from emails/meetings. Cortex exposes 10 MCP tools (remember, recall, forget, search, etc.) for Claude Desktop.
- **None have epistemic status tiers or statistics kernel.** They're built for "remember my work," not "track evidence quality."

### Category 3: AI Agent Memory / MCP Servers (Most Important)
- **Anthropic official Memory MCP server** — local knowledge graph of entities, relations, observations. Ships with Claude.
- **Zep Graphiti** — graph-backed memory, connects to Claude/Cursor via MCP.
- **mem0** — memory layer for AI agents.
- **Cortex** — personal knowledge graph with MCP tools.
- **This is the distribution mechanism Victor is missing.** The pattern — expose knowledge graph as MCP server → get used inside Claude/Cursor for free — is now the default for this category. Victor is CLI-only.

### What Victor Has That Nobody Else Has
1. **Masked memory** — graph structure stays visible for reasoning, content withheld from LLM until explicitly unmasked. No competitor has a redaction/trust boundary. Zero.
2. **Epistemic status hierarchy** — MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS. No competitor tracks evidence quality tiers. Generic numeric confidence (which the industry now considers table stakes) is not the same as typed scientific-evidence ladders.
3. **Compounding graph** — after 6 months of use, Victor knows your domain better than any fresh instance. Network effect inside one user's knowledge base. Not a feature — accumulated state.
4. **Tamper-evident disclosure log** — every mask/unmask decision is recorded with caller provenance. When a published paper is challenged, Victor can produce a log of exactly what the AI assistant was permitted to see and when. No competitor has this. It maps directly to OWASP ASI06 compliance ("redact-at-rest / hydrate-on-return") and to research integrity requirements that are becoming standard in computational fields.

---

## 2. MCP Server Plan — Critique and Corrected Design

### What Claude's Original Plan Got Right
- 1:1 core.py wrapping (thin transport layer, no reimplemented logic)
- MCP as optional extra (`pip install victor[mcp]`)
- Masking enforcement as primary concern
- Path validation on ingest
- No raw graph escape hatch

### What Was Wrong — 4 Masking Bugs (Real, Verified Against Code)

**Bug 1: `find_gaps()` / `summarize_claim()` in reasoning.py leak masked content**
```python
# reasoning.py, summarize_claim() — called by both gaps() and evidence()
claim_text = claim_node.get("label", "")   # no is_masked check
```
The project already found and patched this exact leak at ONE call site (`_inject_pattern_note()` in core.py) with an explicit masking gate. But the fix never propagated to `find_gaps()` / `summarize_claim()` / `summarize_all_claims()` themselves. **Gaps, evidence, and patterns still leak masked claim text for every caller — CLI included.**

**Bug 2: `inspect()` and `list_masked()` — NOT actually bugs (disagreement with Claude's critique)**
These are CLI tools for humans who need to see masked content to decide whether to unmask. The fix is NOT in `core.py` (which would break legitimate CLI usage). The fix is in the MCP layer: **do not expose `inspect` or `list_masked` to LLM agents in v1.** The trust boundary is "is the caller an LLM or a human," not "does this function return masked content."

### Corrected v1 Tool Surface (5 tools, not 12)

| MCP tool | Wraps | Notes |
|---|---|---|
| `victor_ask` | `Victor.ask_full(query)` | Primary tool. Returns answer + provenance + epistemic status. |
| `victor_gaps` | `Victor.gaps(min_importance)` | After masking fix in reasoning.py. Genuine differentiator. |
| `victor_ingest` | `Victor.ingest_file(path)` | Path validation required. |
| `victor_mask` / `victor_unmask` | `Victor.mask(node_id)` / `unmask(node_id)` | Human confirmation pattern. Audit log fires through MCP. |
| `victor_stats` | `Victor.stats()` | Graph size/health snapshot. |

**NOT in v1:** `victor_inspect`, `victor_list_masked`, `victor_compute_statistics`, `victor_compute_effect_size`. These can be added in v2 once the trust boundary is clear.

### Prerequisite: Fix Masking in reasoning.py (Before Building MCP Server)
Add masking gate to `find_gaps()` / `summarize_claim()` / `summarize_all_claims()` in `reasoning.py`. This is not optional — it's the foundation the MCP server sits on.

---

## 3. OWASP / Security Validation

### Memory Privacy Is Now a Formal Security Category
- **OWASP LLM08** (2025): "Vector and Embedding Weaknesses"
- **OWASP ASI06** (2026): "Memory and Context Poisoning"
- **AMP (Agent-Memory Protocol)** — published AAAI paper defining redact-at-rest / pack-for-purpose / hydrate-on-return. Almost exactly what Victor does.
- **MEXTRA attack** — empirical proof that LLM agent memory is vulnerable to targeted black-box extraction. Real-world deployments affected (ChatGPT/SpAIware, ElizaOS).

### Practical Implication
- "Implements OWASP ASI06-aligned memory redaction" is a true, checkable claim for pitches/docs.
- The embedding-coerten-channel issue in `vector_store.py` (docstring says "not a threat in current single-user, trusted-model deployment") becomes a real concern once MCP server exposes Victor to external LLMs. Should be addressed before MCP ship.
- "Redact at rest / hydrate on return" is good, citable, non-marketing language from the AMP paper worth borrowing.

---

## 4. Startup Viability — Two Paths

### Path A: B2B Intelligence Layer (Original Vision's Entry Strategy)
- License the software brain to sensor hardware manufacturers (Smiths Detection, L3Harris, Rapiscan)
- They build hardware; Victor provides the intelligence layer
- Revenue: B2B licensing, annual contracts
- Timeline: 1-2 years to revenue, but high value per customer
- This is what the CANON doc describes as the primary path

### Path B: AI-Only Version (Original Voice Note's "General Public" Path)
- MCP server → Claude Desktop/Code/Cursor
- Free → paid managed hosting → B2B for research teams
- Timeline: weeks to external users
- Lower ceiling but faster validation
- This is what the voice note explicitly imagined: "general public could use the AI versions"

### Recommended: Path B First, Then Path A
1. Ship MCP server (weeks) → get external users → validate the "masked memory" pitch
2. Use that traction to approach hardware manufacturers (Path A) with proof the intelligence layer works
3. The MCP server is the demo; the B2B licensing is the business

### The Pitch (From Original Voice Note)
> "It tries to understand itself and enhance its own mind throughout the user's chats and knowledge."

One-sentence version:
> **"Victor is the only research AI that can prove what it was allowed to see — and what it wasn't."**

### What Makes This Defensible
- **The compounding graph.** After 6 months, Victor knows your domain better than any new instance. Not a feature — accumulated state. Competitors can't copy this without the same time investment.
- **Masked memory.** Nobody else has it. The AMP paper describes the theory; Victor has the implementation.
- **Epistemic status hierarchy.** Generic confidence scores are table stakes. MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS with evidence weighting is not.

---

## 5. Prioritized Roadmap (Immediate)

| Priority | Action | Effort | Impact |
|---|---|---|---|
| 1 | Fix masking bug in reasoning.py (find_gaps, summarize_claim) | 1-2 hours | Unblocks MCP server |
| 2 | Build MCP server (mcp_server.py + cli subcommand + tests) | 2-3 weeks | Distribution — first external users |
| 3 | Write positioning doc / landing page | 1 week | "Masked memory for AI agents" |
| 4 | Ingest one real research paper, run `victor gaps` | 1 day | Proves the core idea on real data |
| 5 | ModernCE cross-check benchmark (Action 3 in accuracy plan) | 1 hour | May improve accuracy, but not blocking |
| 6 | Approach hardware manufacturers with whitepaper + MCP demo | Ongoing | Path A revenue |

**What NOT to do:**
- Don't chase SciFact accuracy past 71% until after MCP server ships
- Don't build a web UI before MCP server (MCP is higher leverage)
- Don't start hardware prototype before software has external users

---

*This document captures the strategic thinking from the 2026-06-28 session. Update as decisions are made.*
