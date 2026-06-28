# VICTOR — Document Index
*Last updated: June 2026 · Code version: v4.6*

---

## Read This First

This file is the only entry point. Every other document has a single job.
If you are starting a new session, read this file, then read only the document that answers your question.
Do not read all documents. They will contradict each other on version-specific details and you will get confused.

---

## The Living Documents

| Document | Answers | Do not use it for |
|----------|---------|-------------------|
| `VICTOR_THEORY_v1.md` | What is Victor, fundamentally? What is the unit of value? What is the one job? | Implementation details, code, build order |
| `VICTOR_FOUNDATION_v2.md` | What are the design principles? What are the irreducible components? What are the layers? | Current code state, bug list, build steps |
| `VICTOR_WHAT_IS_BUILT.md` | What exists in the code right now? What is broken? What is the next action? | Philosophy, long-term vision, hardware plans |
| `VICTOR_BUILD_SEQUENCE.md` | What gets built in what order, from current state to physical device? | Current bugs, philosophy |
| `VICTOR_ORIGINAL.md` | What did Varish actually say when he conceived this? | Technical decisions, build plans |

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
Read `VICTOR_ORIGINAL.md`. If the idea contradicts what Varish said in his own words, flag it.

---

## Version History of This Index

| Date | Code version | What changed |
|------|-------------|--------------|
| June 2026 | v4.6 | Initial index created. Six living documents defined. Assessment and handbook docs archived. |

*Update this table every time a living document is revised or a new code version ships.*
