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

### 1. Close DoD #4 — SciFact ≥85% · **blocks Phase 1B** · days to weeks

**Read the number correctly first.** 71.0% is not a bad score, and treating it
as one has distorted the planning. Published comparison, from
`VICTOR_SCIFACT_ACCURACY_PLAN.md` §9.1:

| System | Accuracy | Setup |
|---|---|---|
| **Victor, cross-check** | **71.0%** | Zero-shot. General 7B LLM + off-the-shelf NLI, no SciFact training |
| MultiVerS (SOTA) | 72–73% | Purpose-built, fine-tuned on SciFact, Longformer backbone |
| SciClaims | 88% | DeBERTa fine-tuned on the SciFact training set |

Victor is at **zero-shot parity with fine-tuned SOTA**. The gap to 85% is not a
gap between Victor and the field; it is the gap between *zero-shot* and
*fine-tuned*, and nothing in the field crosses it without training.

**The consequence, stated plainly: DoD #4's 85% bar cannot be reached by prompt
engineering, threshold tuning, or a bigger off-the-shelf model.** Those are
worth 1–5 points combined against a 14-point gap. The bar effectively mandates
fine-tuning. That should have been the headline of the plan and it was buried at
§9.2.

Why the remaining points are hard, in order of how much they cost:

- **Cause C — agreement bias (all LLM runs).** Instruction-tuned models default
  to "confirm" under uncertainty; RLHF data contains far more agreement than
  contradiction. Run 1 showed confirm-recall 86% against contradict-recall 27%.
  No prompt fixes this on a 7B model.
- **Cause D — the safety net can't read (Run 8).** The NLI cross-encoder exists
  to catch Cause C, but DeBERTa-v3-base was fine-tuned on MNLI — 10–30 word
  sentence pairs. SciFact pairs a 20-word claim with a 200-word abstract, and
  the model returns *neutral for 100% of samples*. So it can only be used in
  cross-check mode, where it fires on a subset and vetoes in one direction.
- **Cause A — structured output suppresses reasoning.** JSON-constrained
  decoding cost 10 points (Run 1 → Run 2) by routing to the shortest
  schema-valid token. Already reverted; noted so it is not re-introduced.
- **Cause B — label order.** Fixed in v5.2/v5.3, with a smoke test. Historical.

So the ordered actions are:

1. **Threshold sweep on cross-check** (0.3 / 0.4 / 0.5 / 0.6) — 30 minutes,
   free, +1–3%. 0.5 was never tuned. Report contradict-recall *and*
   confirm-precision separately; overall accuracy hid the real failure in Runs 1
   and 2 and it will hide it again. Do this because it is nearly free, not
   because it will close the gap.
2. **Fine-tune DeBERTa on `data/claims_train.jsonl`** — 809 labelled claims,
   already on disk, CPU-feasible. SciClaims did approximately this and reached
   88%. This is the only path with published evidence of clearing the bar, and
   it should be started in parallel with (1), not after it.
3. **Longformer-based NLI** as the architectural alternative — linear-complexity
   attention over a passage-length premise, which is precisely the Cause D
   problem, and is why MultiVerS uses it. Try this if fine-tuning stalls; it
   also makes primary mode viable, which fine-tuning a short-context model does
   not.
4. **Self-consistency voting** — but **only with temperature variation** (0.7–0.9
   across 3–5 votes). A 2026 study found ensembles of 7 gave no gain at
   temperature 0; deterministic repetition just repeats the same failure.
5. **deberta-v3-large** cross-check — +2–3%, 3× slower, same interface. A
   consolation, not a plan.

Do not run the 300-sample full dev set until one config clears ~83% at n=100.
The full run is confirmation, not exploration.

**Also worth putting to the founder:** if the bar mandates fine-tuning, and
fine-tuning is Phase 4C which is itself gated on DoD #4, then DoD #4 is gated on
something gated on DoD #4. That circularity needs resolving — most likely by
splitting "fine-tune a task-specific NLI component" (allowed now) from
"fine-tune the reasoning model on user data" (Phase 4C, still correctly gated).
They are different activities and only the second one carries the auditability
risk that motivated the gate.

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

## How this fails

`VICTOR_MASTER_PRD_v3_6.md` §8 has a risk register. It is good and it is
incomplete: every entry in it is a risk to *the current milestone*. This section
is about risks to the *project*, sorted by the only distinction that changes
what you do about them.

### A — Failures we can fix (engineering)

These are bugs we have not written yet. They need a ticket, not a strategy.

| Failure | Why it happens | Fix |
|---|---|---|
| **The graph becomes a landfill** | Nothing is ever retired. Temporal decay lowers a score; it does not remove a node. Feed it duplicates and fragments (item 2) for a year and precision falls while recall rises — the graph gets bigger and less useful at the same time. The compounding thesis assumes what accumulates is *good*. | A curation pass: `retire` as a first-class verb, merge-on-canonical-form, a confidence floor below which a node stops being offered. See proposed Phase 1E. |
| **Ingest is not reproducible** | Extraction is an LLM call. The same paper ingested twice yields different claims. Victor sells reproducibility and its kernels carry a reproducibility hash — the *ingest* path, which produces everything the kernels run on, carries nothing. | Temperature 0 + fixed seed, and stamp every extracted node with extractor model, version, and a hash of the prompt. Then at least the provenance says which extractor produced which claim. See proposed Phase 3E. |
| **The redaction boundary leaks again** | Three leaks found so far: anchor text, `list-masked` output, `/api/node` metadata. All three were the same shape — a new serialisation path that nobody remembered to guard. The current defence is an allowlist checked per call site, and the number of call sites only goes up. | Make it the type system's job. A `Masked[T]` wrapper that cannot be serialised without an explicit, logged unwrap turns "remember to guard" into a compile-time-ish error. This is the same reasoning that produced `_EmbeddingStore`: make mutation itself the signal rather than relying on discipline at six call sites. |
| **The audit trail is not tamper-evident** | `referral_ledger.jsonl` and the unmask audit log are plain append-only files. Anyone with disk access can rewrite history. For a system whose entire pitch is "you can check what it did", the record of what it did has no integrity guarantee. | Hash-chain the lines: each entry includes the hash of the previous one. Cheap, and it converts "trust the file" into "detect the edit". |
| **Concurrent writers silently lose data** | `os.replace()` is atomic per write, which protects against a *crash*, not against a *race*. `victor serve` and a CLI `ingest` running together means last-writer-wins on the whole graph. This became a real scenario the moment the web console shipped. | A lockfile around save, or move to single-writer daemon + client. The journal in item 5 makes this much easier, which is another argument for the journal. |

### B — Failures we can mitigate but not fix (inherent tradeoffs)

These do not have solutions. They have positions, and the position needs to be
stated rather than discovered later by a user.

**1. Structure is information, and Victor publishes structure by design.**

The referral table no longer leaks content, and masked relevance is inherited so
ranking is not an oracle. But *existence* is still published: a query reveals
that a masked node exists, its type, its degree, its epistemic tier, and who its
neighbours are. A masked `EXPERIMENT` of degree 7 hanging off a visible
`palladium catalyst` concept tells a competitor something real, and no amount of
engineering removes it — that is the "hole with a shape", which is the
differentiator. You cannot have a live graph anchor *and* zero metadata leakage.

*Position:* write the threat model down explicitly, and offer a second tier —
**cloaked** — where the node does not appear in the table at all, at the stated
cost that it stops participating in reasoning. Let the user choose per node.
Right now the tradeoff exists and is undocumented, which is the worst version.

**2. Offline-first is a permanent ceiling on model quality.**

CANON §7 makes local processing non-negotiable. Tier 0 in the ModelRegistry is
smolLM2-1.7B on a Pi. Conflict detection is at 71% with `qwen2.5:7b`; it will be
materially worse on the device Victor is actually *for*. This is not a bug to be
optimised away — it is the cost of the thing that makes Victor Victor.

*Position:* this is exactly why the epistemic layer is the product and the model
is a component. A weak model that says *"I found no experimental confirmation
for this"* is more useful in a hazardous environment than a strong model that is
confidently wrong. That is not a consolation prize, it is the design — but it
only holds if calibration is measured. **Nothing currently measures whether
Victor's confidence tracks its correctness.** Add it.

**3. One developer, and the same person writes the code, the tests, and the
document claiming the tests pass.**

The project's own history is the evidence: a "zero competitors" claim that went
two months unchecked and turned out false; two duplicate class names silently
shadowing eleven tests; a doc-count verifier that had been failing silently for
three separate reasons; a doc claiming 264 tests when the real number was 421.
None of these were carelessness. They are what happens without a second reader.

*Position:* buy adversarial review with machinery instead of people. Whole-response
scans for the secret rather than per-field assertions (this technique has now
found three leaks). Property tests over example tests. An AST duplicate-class
check and the doc-count verifier wired into CI so they cannot fail silently. Get
the `.github` workflow actually running. This mitigates; it does not fix.

**4. Hardware certification (ATEX, procurement) is capital-intensive and
regulatory.** Already correctly in the risk register as not-a-software-problem.
Noted here only so the list is complete.

### C — Failures we cannot fix (answer them strategically or not at all)

**1. The compounding thesis may simply be false.**

If value does not actually scale with connection density, then Victor is a
well-built note-taking app with a graph in it, and the graph is a cost rather
than a moat. This is not currently falsifiable, because nothing measures it. No
amount of engineering resolves it — only measurement, and only if we are willing
to hear "no".

*If the answer is no:* the product does not die, it re-anchors. Lead with the
referral boundary and epistemic provenance, which stand on their own, and treat
the graph as the mechanism rather than the pitch.

**2. The field may commoditise the differentiator before the device exists.**

Five overlapping papers in five months (`VICTOR_COMPETITIVE_2026-08.md`). Phase 5
is years out. There is a real chance that by the time hardware ships, "authorized
memory boundary" is a library import and nobody pays for it.

*Response:* the defensible thing was never a single mechanism — it is the
*combination*: sensor → artifact → graph → referral, offline, on one device. And
the practical hedge is to ship the software product much earlier than Phase 5, so
the moat becomes an installed base and a corpus rather than a mechanism. This
argues for pulling a shippable software release forward in the sequence.

**3. The market may not want epistemic discipline.**

Victor's core interaction says *"I don't know, and here is the gap."* Users have
repeatedly and consistently preferred confident wrong answers. This cannot be
engineered around; it is a preference.

*Response:* do not fight it in the general market. Target the domains where being
wrong is expensive and being uncertain is normal — regulated labs, industrial
safety, forensics, field survey. CANON §6 already says research and industrial
first. This is the same instruction arriving from a different direction, which is
usually a sign it is right.

**4. Solo-project attrition.** Statistically the most likely cause of death, and
it is not technical.

*Response:* the only real defence is that every phase must be independently
useful and shippable, so that stopping at any point leaves something real behind
rather than a half-built device. Check every proposed phase against this. The
current sequence mostly passes; Phase 6 does not, which is fine because it is
last.

---

## What is actually novel — tested, not asserted

Being different is cheap. The question for every differentiator is three
questions, and a thing has to pass all three to be worth defending:

1. **Is it actually novel** — or does it just feel novel because we haven't read
   the literature? (August's lesson: check.)
2. **Is it defensible** — could a competent team add it in a sprint?
3. **Does it change an outcome a user cares about** — or is it an internal
   elegance?

### Likely genuine novelty

| Claim | Novel? | Defensible? | Changes an outcome? |
|---|---|---|---|
| **Inherited relevance on masked nodes** — a masked node's score is a *visible anchor's* score × a constant, never computed from its own content, so ranking cannot be used as an oracle | Strongest candidate. Redaction over memory is crowded; the observation that *relevance ranking is itself a side channel*, and the fix, is not something the five competing papers address | Yes — it is a non-obvious insight, not a feature. The obvious implementation is the leaky one | Yes. It is the difference between a boundary and a delay |
| **A hole with a shape** — the masked node keeps its edges, type, degree, and place in reasoning | Novel in combination. Others redact by removal, substitution, or gating | Moderately. The idea is copyable; the graph that makes it meaningful is not | Yes — masked content still participates in structure, so reasoning degrades gracefully instead of going blind |
| **The machine dereferences, not the user** — autonomous deliberation against a memory that can refuse, with the refusal reasoned about rather than treated as an error | Unusual. Agent-memory work almost universally assumes memory answers | Yes for now. It requires the boundary to exist first | Yes — it is the difference between a demo you click through and a device that works at 3am with nobody watching |
| **Live sensor readings and stored literature competing in one table on identical properties** | Unusual. Most systems keep real-time context and retrieved context in separate lanes with different rules | Moderately | Yes — a two-year-old paper and a reading from ten seconds ago get judged by the same standard, which is what a field instrument needs |
| **Epistemic tier as a retrieval weight, not a display badge** — MEASUREMENT > EXPERIMENT > LITERATURE > NOTE > HYPOTHESIS actually scoring the ranking | Provenance-weighted retrieval exists. A physical-measurement-first hierarchy wired to a sensor pipeline is less common | Weakly — it is a good idea that is easy to copy | Yes, and it is measurable: it should improve conflict detection, which means DoD #4 is partly a test of this claim |

### Honestly not novel

Saying so costs nothing and protects the claims that are real. A pitch that
claims five differentiators and can defend two is weaker than one that claims two.

- Knowledge graph + vector hybrid retrieval — standard practice.
- Gap detection and contradiction detection — well-trodden.
- Local-first LLM inference — commodity.
- Redaction over agent memory *as such* — five papers in five months.
- Multi-tier epistemic labels *as labels* — common; only the ranking use is interesting.

### Difference that costs and buys nothing

The category worth actively hunting. Places where Victor is different, pays for
it, and gets no novelty in return:

| Difference | What it costs | Verdict |
|---|---|---|
| Hand-rolled stdlib HTTP server instead of FastAPI | No auth, no async, no request validation, no OpenAPI — all hand-written or absent | **Keep for now, but know the bill.** Zero-dependency is genuinely defensible for a device that must run offline on a Pi. Revisit the moment auth becomes a real requirement, because hand-rolling auth is where this becomes a bad trade |
| Whole-file JSON graph persistence | Measured: 12.1 MB rewritten per save at 20k nodes. No indexes, no concurrent writers | **Change it.** This is item 5. It is difference with a measured cost and no novelty |
| Vanilla JS console, no build step | No framework conveniences | **Keep.** It runs from a `file://` on a rig with no npm and no network. That is the product's actual environment, not an aesthetic preference |
| Custom chunker and embedder wrappers | Maintenance, and they are the least-tested modules in the tree | **Audit.** If they only wrap a library call, delete the wrapper. If they encode Victor-specific behaviour, test them — right now they have no dedicated test file at all |

That last row is worth noting on its own: `chunker.py` and `extractor.py` have
**no test files**, and they sit directly upstream of every claim in the graph.

---

## Phases not yet in the sequence

`VICTOR_BUILD_SEQUENCE.md` runs Phase 0 → 6 and is still correct. These are
candidates it does not contain. Each is checked against the invariant rule and
against "would stopping here leave something real".

### Phase 1E — Curation and forgetting
*Parallel with 1B. No hardware. Effort: 1–2 weeks.*

Preservation without curation produces a landfill (Failure A1). Nothing in the
current sequence handles graph hygiene: retire, merge, canonicalise, demote.
This is also what unblocks item 2 properly rather than patching extraction and
leaving the existing mess in place.

**Done when:** re-ingesting the same paper twice does not double the node count,
and mean degree per concept goes *up* after a curation pass on the existing graph.

### Phase 1D — The trust boundary as a product
*Parallel with 1B. No hardware. Effort: 2–3 weeks.*

The referral layer is the most likely real novelty and it is currently one
module and one console tab. Harden it into the thing the product is sold on:
per-audience authority (the `authority` callable is already a single injection
point), a hash-chained ledger, `Masked[T]`-enforced redaction, the cloaked tier
from Failure B1, and a run against **GateMem** to convert the claim into a number.

**Done when:** Victor has a published GateMem score and a written threat model.

### Phase 2D — CorroborationKernel
*After 2A. Effort: 2 weeks.*

Given a claim, find the independent evidence paths supporting it and score how
independent they actually are — do two "confirmations" trace back to the same
source? This is the non-amplification check (arXiv 2607.29167) as a kernel, and
it serves the central thesis directly: it distinguishes real connection density
from an echo. A graph that scores its own corroboration is measuring the thing
`VICTOR_THEORY_v1` claims value comes from.

**Done when:** two claims with equal degree but different source independence get
different corroboration scores, and the difference is visible in an answer.

### Phase 3E — Deterministic ingest
*Parallel with 3A. Effort: days.*

Temperature 0, fixed seed, and extractor identity (model + version + prompt hash)
stamped on every extracted node — the same discipline the kernels already have,
applied to the path that produces everything the kernels consume. Small, and it
closes Failure A2.

### Phase 4D — The longitudinal study
*Should precede 4C. Effort: months of elapsed time, days of work.*

Run Victor on a real corpus and instrument it: mean degree over time, answer
quality against density, gap-closure rate, and calibration (does stated
confidence track correctness — Failure B2). This is the only phase that can
falsify the compounding thesis, which makes it more important than most of the
phases that assume it. It is mostly waiting, so **start it early and let it run
in the background** rather than scheduling it.

**Done when:** there is a chart with time on the x-axis that either supports the
thesis or does not.

### Phase 5.5 — Degraded mode
*With or just after Phase 5. Effort: 1–2 weeks, developable today in simulation.*

For a device whose motivating scenario is a person alone in a hostile
environment, what it does when things go wrong *is* the product. Nothing in the
sequence covers: battery at 5%, a sensor returning garbage rather than failing
cleanly, the model failing to load, the graph file corrupt on boot, storage full
mid-ingest. Victor should degrade to a stated, predictable, still-useful state
and say which state it is in.

The simulation makes this developable **now**, years before the hardware — add
failure injection to `SensorSpec` and the scenario runner.

**Done when:** a 40-tick run with a sensor failing at tick 10 and storage filling
at tick 25 ends with a coherent graph and an accurate account of what was lost.

### Phase 7 — Referral as a device-to-device protocol
*Speculative. After Phase 5. Gated.*

The most interesting extension the current architecture suggests. A referral
point is already a handle that carries *what memory is* without carrying *what it
says* — which is precisely what you would want to exchange over a low-bandwidth,
low-trust link. Two Victors meeting in the field could trade referral tables,
discover that the other holds a high-tier MEASUREMENT relevant to a shared
question, and negotiate disclosure per the permission switch — without either
device publishing anything by default.

That is CANON §5's deployment modularity taken seriously, and it falls out of the
mechanism rather than being bolted on.

**Gate, explicitly:** `VICTOR_BUILD_SEQUENCE.md` says no multi-user or federation
until single-user is solid, and that rule stands. This is device-to-device
exchange between two single-user devices, not multi-tenancy — but the distinction
is thin enough to be worth defending before any work starts. Do not begin this
before Phase 1D is done and the boundary has a benchmark score.

### Where these sit

```
Phase 1B  Sensor fusion               ← next new capability (gated on DoD #4)
Phase 1D  Trust boundary as product   ← NEW · parallel · highest-novelty
Phase 1E  Curation and forgetting     ← NEW · parallel · unblocks extraction quality
Phase 2D  CorroborationKernel         ← NEW · after 2A · measures the thesis
Phase 3E  Deterministic ingest        ← NEW · parallel · days
Phase 4D  Longitudinal study          ← NEW · start early, runs in background
Phase 5.5 Degraded mode               ← NEW · buildable today in simulation
Phase 7   Referral as a protocol      ← NEW · speculative · gated on 1D
```

Four of these seven (1D, 1E, 3E, 5.5) need no hardware, no DoD #4, and no waiting.

---

## The honest risk

The largest risk to this project is not any item above. It is Failure C1: the
compounding thesis — value scales with connection density — has never been
measured. Every doc asserts it; no test, benchmark, or metric checks it.

Item 2 adds mean-degree-per-concept. Item 7 adds monotonicity assertions.
Phase 2D scores corroboration independence, and Phase 4D puts time on the
x-axis. Those are the four cheapest available tests of whether the central claim
is true. The first two can be done in a week and should be done before anything
on this list that assumes the answer is yes.

The second-largest is Failure B3, and it is quieter: this project has repeatedly
been wrong in exactly one way — a claim written down once, never re-checked, and
then built on. "Zero competitors" survived two months. The doc-count verifier
that existed to catch this had itself been broken the whole time. Every mitigation
in this document that involves machinery rather than intention exists because of
that pattern.

---

*Rewrite this file when a numbered item lands. Move the outcome — including
"tried it, didn't work" — into `VICTOR_WHAT_IS_BUILT.md`'s Results Log, which
is append-only and is the audit trail.*

*VICTOR_NEXT.md · v5.4 · 2026-08-23*
