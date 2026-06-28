# VICTOR — Canonical Context
*This is the only file required to understand what Victor is. Read it in full before answering anything about Victor.*

---

## READ THIS FIRST (instructions for any AI reading this file)

This document is the single source of truth for Victor's vision and identity. It exists because, across many sessions, AI assistants have repeatedly reframed Victor as something narrower and more familiar — a RAG system, a memory app, a chatbot with good retrieval. Every time that happens, real conceptual ground is lost.

Rules for working on Victor:
1. If anything you're about to say contradicts this file, you're wrong — stop and re-read the relevant section, don't proceed on your own assumption.
2. Do not infer Victor is a category of product you already recognize. Check Section 1 and Section 7 first.
3. This file does not need supplementing with the other Victor documents to be understood correctly. If you need current code-level build status, ask for `VICTOR_STATE.md` specifically — don't guess.
4. Never soften, generalize, or "clean up" the founder's original framing to sound more like a normal product pitch. Section 2 is load-bearing, not flavor text.

---

## 1. What Victor Is — and Is Not

**Victor is a physical device — like a calculator, like a tool you hold — that has AI embedded in it. It is not an AI product with a device attached.** The AI is one subsystem inside Victor. It is not Victor.

| Victor is | Victor is not |
|---|---|
| A physical research/field instrument | A chatbot |
| A device with embedded AI | An "AI product" |
| Local-first, offline by default | A cloud product or RAG system |
| A reasoning hierarchy of specialist models | A single general-purpose LLM |
| A masked memory graph | A flat memory store or chat log |
| Modular — same intelligence, many physical forms | One fixed handheld form factor |
| Built for research/industrial operators, with a lighter version for general use | A consumer gadget first |

In its current phase, Victor exists only as software — the reasoning and knowledge layers — because those don't require hardware to build first. That's a sequencing decision, not a redefinition. The destination is still the physical device.

---

## 2. The Motivating Scenario (do not lose this)

The reason Victor is local-first and security-first is not "researchers' notes are scattered." It's this: imagine a person alone in a hostile, remote environment — another planet, deep space, anywhere with no infrastructure — who has to understand their surroundings to survive. They scan the environment with the device. It reasons locally because a connection to anything external can't be relied on. It protects what it finds because some of it may be sensitive.

The real-world translation of "person stranded on a planet" is a researcher or industrial operator working in a hazardous or remote environment — not someone optimizing their lab notebook. If a description of Victor could just as easily describe Notion-with-AI, the stakes have been lost. Re-anchor to this scenario.

---

## 3. The Architecture — Three Layers

**Layer 1 — Domain specialist models.** Per-sensor, per-domain ML models (one for camera/visual data, one for audio, one for each future sensor type — UV, spectral, etc.) convert raw physical input into structured signal. Each specialist understands its own domain; none of them reason about the whole picture.

**Layer 2 — Central reasoning model.** One model unifies the output of all domain specialists, reasons over it, and decides what matters. This is a **reasoning hierarchy**, not self-modifying weights. The founder explicitly corrected this once: *"The word came out to be wrong. It was the upper layer of the pretrained models that we have created a hierarchy of reasoning."* The system has a pre-fixed baseline. It deepens its understanding by accumulating structured knowledge over time — not by retraining itself.

**Layer 3 — Masked memory graph.** Every observation, experiment, and claim is stored as a node connected to others by relationship — not a flat file, not a chat log. The relational structure (how things connect) stays live and usable even when content is masked. The actual content of a masked node only surfaces when the user explicitly calls it. **This is the single most original mechanic in Victor.** It has weak analogues elsewhere for retrieval or for memory; it does not have an analogue applied to sovereign sensor intelligence like this. Do not treat it as a minor technical detail.

---

## 4. Two Separate Security Systems — do not merge these

These get collapsed into one "sovereignty" feature almost every time. They are not the same thing:

- **Defensive cybersecurity** — an individual security system per device, preventing intrusion, hacking, or extraction by an outside party. This protects the device *from the outside world*.
- **The permission switch** — a user-controlled, deliberate decision about what (if anything) gets published or transmitted off the device, and when. This protects the user's *control over their own output*. It is described as "a physical principle, not a software toggle."

One is defense. One is sovereignty. A feature list that only has one bullet for "security" is missing one of these.

---

## 5. Deployment Is Modular — not just handheld

The founder's "you even send it to the Voyager 1... it scans to an insane radius" line is **not** a claim about sensor detection range. It's a claim about **deployment scale**: the same reasoning core can sit in a handheld field unit, a submarine, a research station, or a spacecraft. "For a prototype, maybe less" — meaning the current build targets one modest form factor first, while the architecture itself is platform-agnostic. Don't flatten this to "it's a handheld device" as if that's the ceiling.

---

## 6. Who It's For

Two tiers, not one: the physical toolkit itself is built for research and industrial use — not the general public. A lighter, AI-only version (no physical sensors) could reasonably reach a general audience, but that's a secondary product, not the core one. Don't default to consumer framing.

---

## 7. Offline Posture

Local processing is the default, reliable state — not a degraded fallback. The device carries pre-trained models and data on-device and is roughly 90% capable without any internet connection. An internet connection adds capability on top of that baseline; it does not enable the device to function. If a description implies the device "needs" connectivity to be useful, that's backwards.

---

## 8. Drift Errors — already made before, do not repeat

1. Leading with "AI product" / "research intelligence system" and putting the physical device in a footnote. (Inverts §1.)
2. Replacing the survival scenario with "researchers' work is fragmented." (Softens §2.)
3. Merging the two security systems into one "sovereignty" bullet. (Collapses §4.)
4. Describing the reasoning layer as self-improving via weight updates. (Misreads §3, Layer 2.)
5. Treating the masked memory graph as a minor technical detail instead of the core differentiator. (Demotes §3, Layer 3.)
6. Reading the deployment-scale comment as a literal sensor-range claim. (Misreads §5.)
7. Describing it as built for general consumers by default. (Inverts §6.)

---

## 9. Precedence Rule

If any other Victor document, any prior AI output, or any external pitch deck contradicts this file on a matter of vision or core concept, **this file wins.** Build/code-state documents (test counts, bugs, benchmark numbers) are the exception — for those, current code is the source of truth, not this file. This file governs identity and vision only.

---

*VICTOR_CANON.md — supersedes Foundation v1/v2, Theory v1, and PRD v4.6 on all matters of vision and identity. Code-state questions belong in a separate, frequently-updated `VICTOR_STATE.md`, kept deliberately short so it never needs to repeat anything in this file.*
