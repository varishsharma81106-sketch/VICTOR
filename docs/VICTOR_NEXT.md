# VICTOR — What To Build Next

*Written 2026-08-23 against code version v5.4 · 421/421 tests*

---

> `VICTOR_BUILD_SEQUENCE.md` says what order the **phases** go in, and that
> ordering has not changed. This document says what to do **on Monday**. It is
> shorter-horizon, it is allowed to be wrong, and it should be rewritten every
> time a block of work lands.
>
> The invariant rule still governs every item below: *does this improve the
> production, preservation, or compounding of Epistemic Artifacts?* If an idea
> is not on this list, check it against that question before it goes on.

---

## Where we actually are

Three things changed in August that move the position marker:

1. **The core loop works on real data.** A real arXiv paper went in; 13 claims,
   15 concepts, 29 nodes came out; a real question got a correct, cited answer
   with an unprompted gap warning attached. Phase 0's one unverified exit
   criterion is now verified.
2. **The masked-memory idea is implemented as a mechanism, not a flag.** The
   referral layer means the machine walks its own holed memory one point at a
   time, states a reason for each request, and is refused without a human in
   the loop.
3. **The uniqueness claim is smaller than we thought.** Five arXiv papers in
   five months implement a redaction boundary over agent memory. The defensible
   claim is the *live graph anchor*, not the redaction.

What has **not** changed: DoD #4 is open at 71.0%, and it still gates Phase 1B.

---

## The ordered list

Ranked by *(value × confidence) ÷ effort*. Do them top-down. Do not start an
item because it is interesting.

### 1. Close DoD #4 — SciFact ≥85% · **blocks Phase 1B** · days

The three commands in `VICTOR_WHAT_IS_BUILT.md` → "The Next Three Actions" are
still the right three, with one correction: **primary mode with
DeBERTa-v3-base is conclusively ruled out** (Run 8, all 100 samples
inconclusive — MNLI-trained cross-encoders collapse to neutral on 200-word
abstracts). So the live options are, in order:

- **Threshold sweep on cross-check** (0.3 / 0.4 / 0.5 / 0.6). 0.5 was never
  tuned. Cheapest possible experiment. Report contradict-recall *and*
  confirm-precision separately — overall accuracy hid the real failure in Runs
  1 and 2 and it will hide it again.
- **Self-consistency voting** — 3 LLM judgments at temperature 0.3, majority
  wins. Directly attacks the agreement bias that Runs 1–3 all showed.
- **deberta-v3-large** in cross-check mode. Same interface, ~2–3% on MNLI,
  ~3–5s/sample on CPU.
- **Sentence-level NLI** — split the abstract, run NLI per sentence, take the
  max-confidence contradiction. This is the fix that addresses the actual root
  cause (input length), and it is the only one of the four that would also make
  primary mode viable. Highest effort, highest payoff.

Do not run the 300-sample full dev set until one config clears ~83% at n=100.
The full run is confirmation, not exploration.

### 2. Extraction quality · **highest value per hour on this list** · days

421 green tests say nothing about whether the extracted claims are *good*, and
on the one real paper we have, four defects showed up immediately:

| Defect | Fix | Effort |
|---|---|---|
| Duplicates survive dedup — one claim is a literal substring of another | Add a containment check alongside the 0.75 cosine threshold; substring ⇒ keep the longer | hours |
| Section headings absorbed into claim text (`"2.2 Selective Chain-of-thought Medical questions…"`) | Strip leading `N.N Title` patterns in the chunker before extraction | hours |
| Sentence fragments orphaned by chunk boundaries (`"more output tokens, higher latency, and…"`) | Overlap chunks by one sentence, or reject claims that start lowercase / with a conjunction | hours |
| Concepts fragment on surface form — `Selective Chain-of-Thought (Selective CoT)`, `Selective Chain-of-Thought`, `Selective CoT` are three nodes | Canonicalise: strip parentheticals, resolve acronym↔expansion, merge on normalised form | 1–2 days |

The last one matters most. `VICTOR_THEORY_v1` says value scales with connection
density; splitting one concept into three nodes is a direct, measurable tax on
the central thesis. **Add a metric** — mean degree per concept node — and watch
it move. Right now nothing measures the thing the theory is about.

### 3. Fix the mask→unmask data loss · **correctness** · hours

`Victor.mask()` deletes the node's chunks from ChromaDB to close the embedding
covert channel. `Victor.unmask()` does not put them back. A mask→unmask cycle
permanently removes the node from vector search — data loss on an operation
that looks reversible. Re-embed on unmask, and add a test that asserts the node
is findable by vector search afterwards.

### 4. The three carried-over core-loop defects · **correctness** · hours

Known, unfixed, each small:

- `retrieve()` calls `record_retrieval()` per chunk rather than per node, so
  retrieval counts are inflated by chunk fan-out.
- `top_src_ids = list(seen.values())[:3]` is "first three inserted", not
  "top three by score". The variable name is a lie.
- `reasoning.py::_masked_summary()` hardcodes `gap = True`, so a masked node
  always reports as a gap regardless of its actual edges.

### 5. Incremental persistence · **the scale ceiling** · 1 week

Every save rewrites the whole graph JSON atomically. Measured: 12.1 MB at 20k
nodes. At 200k that is a ~120 MB rewrite per save, and the compounding thesis
explicitly assumes a graph allowed to grow for months. Options, cheapest first:

- **Append-only journal + periodic compaction.** Keeps the atomic-replace
  safety property, turns the common case into an append. Least invasive.
- **SQLite for nodes/edges, NetworkX built on load.** Well-trodden, gives
  indexed queries for free, loses the "one readable file" property.
- **Sharded JSON by node type.** Cheap, but only buys a constant factor.

Recommendation: the journal. It preserves the crash-survival property that
`VICTOR_FOUNDATION_v2` treats as irreducible.

Also cache `/api/overview` — it walks every node and grows linearly (1.5 → 6.6
→ 35.7 ms across 1k → 5k → 20k). Not urgent at 20k; a one-line problem at 200k.

### 6. Answer the competitors on their own terms · 1–2 weeks

`VICTOR_COMPETITIVE_2026-08.md` names five overlapping papers. Two of them
describe capabilities Victor genuinely lacks, and both are natural extensions
of the referral layer rather than new subsystems:

- **Per-audience authorization** (arXiv 2608.17148). Victor masks per node,
  globally. Make `ReferralDesk.authority` take a *principal*, not just a node
  id, and the mask becomes per-reader. The plumbing already exists — the
  `authority` callable is a single injection point.
- **Non-amplification / provenance laundering** (arXiv 2607.29167). Victor
  records `origin` and never re-verifies it, which is exactly the failure that
  paper names: consolidation quietly rewrites a low-trust observation as
  trusted history. Add a check that a node's epistemic tier can never *rise*
  through derivation. `EpistemicStatus.weight` now has a call site, so the
  comparison is one line.
- **GateMem** (arXiv 2606.18829) is a *benchmark* for exactly the property
  Victor claims. Running against it would convert an assertion into a number.
  Worth doing before any paper submission.

### 7. Make the simulation prove something falsifiable · days

`victor simulate` currently *shows* compounding, contradiction, gaps and
masking. It does not yet *measure* them. Add an assertion-style report:

- belief confidence on a stable entity is monotonically non-decreasing;
- the entity that changes state at tick 18 has its belief flip within N ticks;
- the late-degrading entity ends flagged as underevidenced;
- the sensitive reading never appears in clear text in any tick record.

The last one is already tested. The first three would turn the simulation from
a demo into a regression test for the theory itself — which is the only form in
which the compounding claim can actually fail.

---

## Deliberately not doing yet

| Idea | Why not yet |
|---|---|
| LoRA fine-tuning | Correctly gated on DoD #4 + real accumulated data. Nothing has changed. |
| Spectral ingestion | Phase 1C, needs hardware. The simulated `spectrometer` sensor is not an ingestion path. |
| Auth on the web console | It binds loopback and holds unpublished research. Auth is the *wrong* fix for "don't expose it"; not binding `0.0.0.0` is the right one. Revisit only if remote access becomes a real requirement. |
| Multi-user / federation | Out of scope until single-user is solid. Note that per-audience authorization (item 6) is *not* this — it is one user with several readers. |
| Encryption on export | Real gap, but `export` is rarely used and item 2 affects every ingest. Ordering, not dismissal. |
| Graph-wide masked-by-default | Changes every retrieval path. The simulation now demonstrates masked-on-arrival for one path; get evidence from that before flipping the global default. |

---

## The honest risk

The largest risk to this project is not any item above. It is that the
compounding thesis — value scales with connection density — has never been
measured. Every doc asserts it; no test, benchmark, or metric checks it.

Item 2 adds mean-degree-per-concept. Item 7 adds monotonicity assertions. Those
two together are the cheapest available test of whether the central claim is
true. If they can be done in a week, they should be done before anything on
this list that assumes the answer is yes.

---

*Rewrite this file when a numbered item lands. Move the outcome — including
"tried it, didn't work" — into `VICTOR_WHAT_IS_BUILT.md`'s Results Log, which
is append-only and is the audit trail.*

*VICTOR_NEXT.md · v5.4 · 2026-08-23*
