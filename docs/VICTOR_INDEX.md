# VICTOR — Document Index
*Last updated: 2026-06-28 · Code version: v5.3.0*

---

## Read This First

This file is the only entry point. Every other document has a single job.
If you are starting a new session, read this file, then read only the document that answers your question.
Do not read all documents. They will contradict each other on version-specific details and you will get confused.

---

## The Living Documents

| Document | Answers | Do not use it for |
|----------|---------|-------------------|
| `VICTOR_CANON.md` | What is Victor, fundamentally, when this disagrees with any other document? The motivating scenario, the architecture layers, the two security systems, modular deployment, who it's for. **This is the top authority on vision/identity** — it explicitly supersedes `VICTOR_FOUNDATION_v2.md` and `VICTOR_THEORY_v1.md` on those specific questions. | Code state, bug list, build steps |
| `VICTOR_THEORY_v1.md` | What is the unit of value? What is the one job? | Implementation details, code, build order. If it ever conflicts with `VICTOR_CANON.md` on vision, CANON wins. |
| `VICTOR_FOUNDATION_v2.md` | What are the design principles? What are the irreducible components? What are the layers? | Current code state, bug list, build steps. If it ever conflicts with `VICTOR_CANON.md` on vision, CANON wins. |
| `VICTOR_WHAT_IS_BUILT.md` | What exists in the code right now? What is broken? What is the next action? | Philosophy, long-term vision, hardware plans |
| `VICTOR_BUILD_SEQUENCE.md` | What gets built in what order, from current state to physical device? | Current bugs, philosophy |
| `VICTOR_ORIGINAL.md` | What did Varish actually say when he conceived this? | Technical decisions, build plans |
| `VICTOR_MASTER_PRD_v3_6.md` | What's the Definition of Done? What's the risk register? What does the benchmark data say? What's the sequenced path to 90%+? | Long-term philosophy (see CANON / THEORY_v1), day-to-day current code state (see WHAT_IS_BUILT) |
| `VICTOR_SCIFACT_ACCURACY_PLAN.md` | What exactly happened in each benchmark run? What is the diagnosed root cause? What is the ordered checklist to close DoD #4? | Philosophy, hardware, anything not directly about the SciFact benchmark |

---

## The Archived Documents

These are accurate for the version they were written against. They are not current references.
Do not use them to decide what to build. Do not contradict the living documents with them.

| Document | Why archived | Written against |
|----------|-------------|-----------------|
| `victor_ai_assessment_v3.md` | EpistemicStatus and ConflictDetector bugs it flagged are fixed in v4.5+ | v3 codebase |
| `victor_layers_1cr.md` | Code state section is v2-era. Strategy section is still valid but belongs in a business doc | v2 codebase |
| `victor_ai_full_vision_extended.md` | Replaced by `VICTOR_BUILD_SEQUENCE.md` which adds ordering | No specific version |
| `victor_handbook_p1.md` | Philosophy sections absorbed into FOUNDATION v2. Implementation sections were stale | v2 codebase |
| `VICTOR_PRD_v4.6` | Build plan and DoD are correct. Theory sections superseded by THEORY v1 and FOUNDATION v2. Implementation audit superseded by WHAT_IS_BUILT | v4.5 codebase |
| `VICTOR_MASTER_PRD_v3_3.md` | Superseded by v3.4 → v3.5 → v3.6. Kept as audit trail of benchmark regression discovery. | v5.0 codebase |
| `VICTOR_MASTER_PRD_v3_4.md` | Superseded by v3.5 → v3.6. First version to record the 68% SciFact run and NLI cross-encoder diagnosis. | v4.9–v5.0 codebase |
| `VICTOR_MASTER_PRD_v3_5.md` | Superseded by v3.6. Recorded the 58% regression and wired concrete 4-step plan. v3.6 adds Runs 3–5, v5.2/v5.3 label-order fix, current best 71.0%. | v5.1 codebase |

---

## How to Use This Set in a New Session

**Starting fresh after a container reset:**
Read `VICTOR_WHAT_IS_BUILT.md` only. It tells you the current code state and the next action.
Then read `VICTOR_THEORY_v1.md` if you need to remember what you're building toward.

**Designing a new feature:**
Read `VICTOR_THEORY_v1.md`. Ask: does this feature improve production, preservation, or compounding of Epistemic Artifacts? If no, don't build it.

**Deciding build order:**
Read `VICTOR_BUILD_SEQUENCE.md`. Find where you are. Do the next step.

**Explaining Victor to someone new:**
Give them `VICTOR_FOUNDATION_v2.md`. It is complete, honest, and does not require prior knowledge.

**Checking if an idea is true to the original vision:**
Read `VICTOR_CANON.md` first — it's the top authority and lists the exact drift errors to avoid. Read `VICTOR_ORIGINAL.md` for Varish's own words if you need the unfiltered source.

**Investigating the SciFact benchmark specifically:**
Read `VICTOR_SCIFACT_ACCURACY_PLAN.md`. It has every run's exact numbers, root cause diagnosis, and the specific commands to run next.

---

## Version History of This Index

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial index created. Six living documents defined. Assessment and handbook docs archived. |
| June 2026 | v5.0 | Header bumped to v5.0. Added `VICTOR_MASTER_PRD_v3_4.md` to living documents — had been maintained through four versions but was never tracked here. |
| June 2026 | v5.3 | Header bumped to v5.3. Added `VICTOR_SCIFACT_ACCURACY_PLAN.md` as a living document (working diagnosis + ordered checklist for DoD #4). Replaced PRD v3.5 entry with v3.6 (Runs 3–5, label-order fix, v5.3 NLI smoke-test infrastructure). Archived PRD v3.3, v3.4, and v3.5 with explanatory notes. |
| 2026-06-28 | v5.3.0 (version string now matches across code and docs) | **`VICTOR_CANON.md` added to the living documents table — it existed and was being treated as authoritative elsewhere but was never actually listed here.** Cross-references added so THEORY_v1/FOUNDATION_v2 explicitly defer to CANON on vision questions. PRD v3.6 corrected: the 71.0% SciFact figure and label-order fix are real (developer-confirmed), not fabricated — the earlier doubt was a stale-snapshot problem, not a fabrication problem. `VICTOR_WHAT_IS_BUILT.md` Bug 3 closed (re-ran the test directly; it passes). Test count confirmed via real `pytest` run: 196/196.

*Update this table every time a living document is revised or a new code version ships.*
