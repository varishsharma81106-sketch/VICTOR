# VICTOR — Competitive Landscape, Re-Checked

*2026-08-23 · Supersedes section 1 of `VICTOR_STRATEGY.md` (June 2026)*

---

## Why this document exists

`VICTOR_STRATEGY.md` claims Victor has four things "nobody else has", and says
of the flagship one:

> Masked memory — graph structure stays visible for reasoning, content withheld
> from LLM until explicitly unmasked. **No competitor has a redaction/trust
> boundary. Zero.**

That was written on 2026-06-28 and never re-checked. A load-bearing claim about
a fast-moving field, two months stale, asserted with a hard number — this is
precisely the kind of unverified assertion Victor is built to flag. So it got
flagged.

**Method.** `WebSearch` and `WebFetch` are blocked by org policy on this
machine, so the check ran against the arXiv API directly:

```bash
python tools/arxiv_scan.py "agent memory redaction" "LongMemEval" \
    "MemoryAgentBench" "provenance knowledge graph agent memory" \
    "authorization context agent memory boundary"
```

Reproducible, dated, and re-runnable. Every paper below was returned by that
tool; IDs and dates are as arXiv reported them on 2026-08-23. Abstracts were
read; implementations were not. Where this document says "does X", it means the
paper claims X.

---

## 1. The headline claim is false

Five papers in the last five months implement a redaction or trust boundary over
agent memory. Ranked by how directly they overlap Victor's design:

| Paper | arXiv | Date | Overlap with masked memory |
|---|---|---|---|
| **MNC: Scope-Bound Semantic Declassification for Private LLM-Agent Communication** | 2608.01719 | 2026-08-03 | Closest thing to a direct competitor. Governs *what a legitimately informed agent should disclose*, not just what it can read — a policy layer above Victor's binary mask/unmask. |
| **Authorization Before Context: A Model-Neutral Audience Boundary** | 2608.17148 | 2026-08-17 | Authorizes facts per *audience* before they enter the assembled prompt. Victor masks per node, globally; this masks per node, per reader. |
| **Memory Provenance Laundering in LLM Agents** | 2607.29167 | 2026-07-31 | Names the failure where consolidation rewrites a low-trust observation as trusted user history, erasing its source. Victor's `origin` field is exactly the thing that gets laundered, and Victor has no non-amplification check. |
| **BodhiPromptShield** | 2604.05793 | 2026-04-07 | Typed placeholders for sensitive spans, routed across retrieval / memory writes / tool calls / logs. Victor redacts at the node; this redacts at the span and follows it through the pipeline. |
| **Deployment-Time Memorization in Foundation-Model Agents** | 2606.10062 | 2026-06-08 | Frames memory design as a utility-vs-extraction-risk tradeoff. The evaluation frame Victor's masking feature has never been run through. |
| **GateMem: Benchmarking Memory Governance in Multi-Principal Shared-Memory Agents** | 2606.18829 | 2026-06-17 | A *benchmark* for exactly the property Victor claims to own uniquely. Roles, scopes, relationships over a shared memory pool. |

The correct claim is not "zero competitors". It is narrower and still true:

> Victor is the only one of these that combines redaction with a **live graph
> anchor** — the masked node keeps its edges, its type, its degree, and its
> place in reasoning while its content is withheld. The others redact by
> removal, substitution, or gating; Victor redacts by leaving a hole with a
> shape.

That is defensible and worth saying. "Zero" is not.

**The capability Victor is now behind on:** several of these propagate
restriction through derivation. If a masked node contributes to a derived claim,
Victor's derived claim is unmasked. MNC's scope-bound declassification and
the provenance-laundering firewall both address that; Victor does not. This is a
real gap, not a positioning problem — see §5.

---

## 2. The claim that survived, and the one that got a benchmark

**Epistemic status tiers** (MEASUREMENT > EXPERIMENT > LITERATURE > NOTE >
HYPOTHESIS): the probe for `"epistemic status evidence tier retrieval"` returned
**nothing**. Nobody is shipping typed scientific-evidence ladders. This
differentiator holds.

The uncomfortable corollary: it holds because Victor doesn't use it either.
`EpistemicStatus.weight` still has **zero call sites**. Victor owns a
differentiator it has not wired into ranking, retrieval, or belief revision. A
unique feature that changes no output is a unique feature on paper.

Adjacent work has arrived on *temporal* trust, which is the same shelf:

- **TEPA** (2608.07429, 2026-08-07) — revokes stale memories; names "memory
  pollution" as the failure where superseded facts stay retrievable.
- **Caching for the Future** (2608.04746, 2026-08-05) — per-memory,
  type-conditioned temporal decay. Victor has `apply_temporal_decay()`, uniform
  across types. Type-conditioned is strictly better and is what
  `_DEFAULT_IMPORTANCE` is already halfway toward.
- **SodaMem** (2608.08055, 2026-08-08) — evidence-grounded temporal graph
  memory, explicitly for currency + provenance + ordered temporal reasoning.
  The nearest neighbour to Victor's whole architecture.

**Tamper-evident disclosure log**: no direct hit, but MemTxn (2607.27834) builds
a transaction boundary with complete-state recovery, and Springdrift (2604.04660)
ships an append-only auditable substrate with git-backed recovery. Victor's
audit log is not unique in kind, only in what it audits (mask/unmask decisions
with caller provenance). Keep the claim, drop the "no competitor has this".

---

## 3. The paper that attacks Victor's thesis directly

**When Your Agent Opens the Chat App: Agent-Controlled Search over Raw Chat Logs
Rivals Structured Memory** — arXiv 2608.12888v2, 2026-08-13.

ReFind builds **no semantic index, no graph, no summaries**. It gives the agent
a lexical search interface over unmodified history and lets it iterate. Reported
results:

- **58.2 on MemoryAgentBench**, versus HippoRAG 2 at 53.2
- **93.2 ± 3.3 on LongMemEval-S**, **89.3 ± 6.0 on LongMemEval-M**

The question it poses is aimed at Victor's foundations: *how much of the benefit
of structure comes from the structure, and how much from competent retrieval?*

Victor's honest answer today is "we don't know, because we've never measured it
against a no-structure baseline." That is the single most valuable experiment
available right now, and it is cheap: Victor already has a retrieval path and a
graph; running the same queries with graph expansion disabled is a config flag.

Two things soften the blow, and neither is a reason to skip the experiment:

1. ReFind's domain is conversational history. Victor's is papers, measurements,
   and claims with typed relations — the compounding-connections thesis is about
   cross-document links a chat log doesn't have.
2. ReFind has no trust boundary at all. Lexical search over raw logs is the
   *opposite* of masked memory; the two are not substitutable for a user with
   unpublished results.

But "our domain is different" is a hypothesis, not a defence. Measure it.

---

## 4. Benchmarks: Victor is running the wrong race

Victor benchmarks on **SciFact** (currently 71.0%, DoD #4 still open). The
strategy doc already said chasing SciFact accuracy is "optimizing the wrong
thing" and was right for the wrong reason — the problem isn't the target number,
it's that **no one in the memory-systems field reads SciFact results**. The
field standardised while Victor wasn't looking:

| Benchmark | What it measures | Who reports it |
|---|---|---|
| **LongMemEval-S / -M** | Long-horizon recall across sessions | ReFind, CABLE, ArborMem, RippleMem, LycheeMemory V2 |
| **MemoryAgentBench** | Multi-competency agent memory | ReFind, TEPA, Supra Cognitive Modes, TRUSTMEM |
| **LoCoMo** | Long conversational memory | CABLE, ArborMem, V-Mem, the serving-cost study |
| **GateMem** | Memory *governance* — roles, scopes, principals | new, 2026-06 |
| **Total Recall at What Cost?** (2608.11879) | Serving cost of memory systems | benchmarks Mem0, Hindsight, Mastra |

**Recommendation, in priority order:**

1. **GateMem.** It benchmarks the property Victor claims to be best at. If
   masked memory is real, this is where it shows up as a number, against
   competitors, on the field's own terms. Highest value per unit of work.
2. **LongMemEval-S.** The most widely reported figure; a number here makes
   Victor legible to anyone reading this literature.
3. **The ablation from §3** — Victor with and without graph expansion, same
   queries. Not a public benchmark, but it either validates the compounding
   thesis or tells us to stop paying for it.
4. **Serving cost.** Post-scale-work Victor is 1.7 ms/query at 10k nodes and
   11.5 ms at 100k (see `VICTOR_WHAT_IS_BUILT.md`). Against LLM-consolidation
   systems that call a model on every write, this is a genuinely strong number
   and nobody has heard it.

SciFact stays as a regression guard. It stops being a headline.

---

## 5. What to build, given the above

Ordered by (gap that is real) × (work Victor has already done):

1. **Propagate mask restriction through derivation.** If a masked node feeds a
   summary, an extracted claim, or a belief, the product inherits the
   restriction. This is the capability MNC and the provenance-laundering
   firewall have and Victor lacks, and it's the difference between a redaction
   feature and a redaction *boundary*. Victor already has the edges to walk.
2. **Wire `EpistemicStatus.weight` into ranking.** The differentiator nobody
   else has, currently costing zero and returning zero.
3. **Type-conditioned decay** (per *Caching for the Future*). A measurement
   doesn't go stale the way a note does. `_DEFAULT_IMPORTANCE` already asserts
   types differ; decay should agree.
4. **Belief revision under contradiction.** `victor/simulation.py` now
   demonstrates this working — recency-weighted voting that revised the
   atmosphere belief 8 ticks after the ground truth changed. TEPA calls the
   failure it avoids "memory pollution". The mechanism exists in the simulation
   and not in the main graph; promote it.
5. **MCP server.** Unchanged from the June assessment and still the distribution
   gap. Every system in §1 that gets used is reachable from inside an assistant.

---

## 6. Standing correction

`VICTOR_STRATEGY.md` §1 "What Victor Has That Nobody Else Has" should now read:

- ~~1. Masked memory — no competitor. Zero.~~ → **Masked memory with a live
  graph anchor.** Six adjacent systems exist as of 2026-08; Victor's
  distinguishing property is that the withheld node stays structurally present
  and reasoning-visible, not that redaction is novel. Victor is *behind* on
  derivation-restriction propagation.
- 2. Epistemic status tiers — **holds**, unchallenged in the literature.
  Currently unused in Victor's own code.
- 3. Compounding graph — **unmeasured**, and directly contested by ReFind
  (2608.12888). Run the ablation before repeating it.
- ~~4. Tamper-evident disclosure log — no competitor has this.~~ → **Auditable
  by construction, uniquely over disclosure decisions.** Append-only auditable
  runtimes now exist (Springdrift, MemTxn); auditing mask/unmask specifically
  does not.

Re-run `tools/arxiv_scan.py` before quoting any of this after 2026-11.
