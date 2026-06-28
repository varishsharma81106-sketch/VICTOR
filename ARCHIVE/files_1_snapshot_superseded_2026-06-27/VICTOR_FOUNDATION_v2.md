# VICTOR FOUNDATION
## Project Constitution · v2 · June 2026

---

> **Victor is not an AI product.**
> Victor is a research instrument that contains AI.

---

## 1. What Victor Is

Victor is a **local-first physical research toolkit** — a device a researcher carries into any environment to acquire, process, understand, and accumulate knowledge from physical reality.

It contains sensors, domain-specific models, scientific computation, a persistent knowledge graph, strong security, and a user-controlled publication switch. AI is one subsystem among these. It is not the product.

The device operates fully offline by default. It processes data on-device. It accumulates understanding over time. It never transmits anything without an explicit, deliberate action by the researcher.

In its current form, Victor is the software brain of that device — the knowledge construction and reasoning layers — built first because they require no hardware. The software brain is not Victor. It is the part of Victor that can be built now.

---

## 2. What Victor Is Not

Victor is **not a chatbot.** The conversational interface is one way to query the system. It is not what the system is.

Victor is **not a memory product.** Memory is one subsystem. The product is the full pipeline from physical reality to reliable understanding.

Victor is **not a RAG system.** Retrieval-augmented generation is one mechanism inside the retrieval layer. It is not the architecture. A RAG system retrieves documents and passes them to a language model. Victor additionally extracts structured claims, links experimental results to those claims, tracks epistemic status of every piece of knowledge, maintains a typed graph of relationships, and computes over accumulated knowledge. These are categorically different operations.

Victor is **not a general AI assistant.** It has no access to external knowledge beyond what has been deliberately ingested. Its intelligence is bounded by the researcher's accumulated work. This is a feature, not a limitation. An AI assistant is a replacement for thinking; Victor is augmentation of thinking.

Victor is **not a cloud product.** There is no telemetry. There is no sync that the system initiates. There is no remote inference. The cloud exists only as an optional output channel the researcher explicitly opens.

Victor is **not a note-taking app.** It is built for structured scientific work: measurements, experiments, claims, evidence, uncertainty, provenance. Notes can be ingested. Notes are not the point.

Victor is **not the AI.** This cannot be stated too many times. The LLM reads the graph and produces language. The intelligence lives in the graph, not the model.

Victor is **not a hardware startup.** The physical device is one implementation. It is not the deepest layer. The deepest layer is the principle in `VICTOR_THEORY_v1.md`.

---

## 3. Why Victor Exists

The distance between a physical observation and a researcher's reliable understanding of it is enormous. Current tools increase that distance by fragmenting it.

A researcher today uses: instruments to observe, export tools to extract data, notebooks to compute, reference managers to find papers, document viewers to read them, note apps to record thoughts, and memory to hold it all together. Every boundary between these tools destroys information. Every destroyed connection must be reconstructed from memory six months later, imperfectly, or not at all.

The result is **epistemic fragmentation**: knowledge is produced but does not compound. Experiments are run but their relationship to prior claims is never recorded. Contradictions accumulate, unseen. Gaps grow, unnoticed. Researchers repeatedly rediscover prior insights, repeat experiments already done, and fail to build on prior work as effectively as the accumulated evidence would support.

Victor exists to close this gap — not by replacing the researcher's judgment, but by providing a unified substrate where observations, computations, literature claims, experimental results, and their relationships are all preserved in one place, with full provenance, so that understanding can compound across time instead of resetting with each session.

The motivating scenario is not office research. It is a person alone in a hostile or unknown environment — a remote facility, a research vessel, an extreme field site, or in the original conception, another planet entirely — who needs to understand their surroundings to make decisions that matter. The stakes are physical, not organizational. Victor is a survival-grade research instrument before it is an efficiency tool.

---

## 4. The Core Principles

**Reality first.** Victor starts from physical observation, not from text. Sensors and instruments are the primary inputs. Documents and notes are secondary inputs. This order is not cosmetic. It determines every architectural decision.

**Human sovereignty.** The researcher owns all data, all knowledge, all discoveries. Victor never decides what leaves the device. The permission switch is not a software toggle. It is a physical principle. Two distinct features serve this: a defensive security system that prevents intrusion and unauthorized data extraction, and a separate user-controlled publication switch that governs what the researcher chooses to share.

**Local-first by philosophy, not constraint.** Victor must function fully offline — not as a degraded fallback, but as the complete product. The device carries pre-trained models and dataset flows on local storage. Offline is the default reliable state. Connectivity improves capability. It is never required for operation.

**Knowledge over data.** Victor does not accumulate files. It accumulates structured knowledge: typed claims, experiments, measurements, relationships, epistemic status, and uncertainty. A stored fact with no provenance is nearly worthless. A fact connected to the experiment that confirmed it, the claim it tests, and the uncertainty it carries is worth compounding.

**AI is a tool.** The LLM reads the graph and produces language. It does not write to the graph without human review. It does not update its weights without an explicit, deliberate fine-tuning pass the researcher initiates and can roll back. The intelligence lives in the graph, not the model.

**Epistemic honesty.** Every piece of knowledge has a type, an uncertainty, and a provenance chain. The system surfaces disagreement rather than suppressing it. An answer that hides a contradiction is worse than an answer that shows one.

**Swappability over optimisation.** Every model, storage backend, and inference engine is behind an abstract interface. The right choice today is not the right choice in two years. Victor's knowledge outlasts any specific implementation. A model upgrade never invalidates past knowledge.

**The theory is the drift detector.** If a proposed feature does not improve the production, preservation, or compounding of Epistemic Artifacts, it does not belong in Victor. No exceptions.

---

## 5. The System Layers

These are the layers of Victor. Each is distinct. None of them is Victor alone.

```
LAYER 0 — Reality Acquisition
  Sensors, instruments, cameras, EM detectors,
  spectrometers, acoustic sensors, environmental monitors.
  Purpose: acquire raw information from physical reality.
  Status: one modality (camera via sensors.py) built in v4.6.

LAYER 1 — Domain Intelligence
  Per-modality models: vision, acoustic, spectral, chemical, environmental.
  Purpose: convert raw measurements into structured information.
  Each modality has its own model. No raw data goes directly to the LLM.
  Status: CLIP/Florence-2 vision pipeline built. Audio and spectral not started.

LAYER 2 — Scientific Computation
  Statistics, uncertainty propagation, signal processing, estimation.
  Purpose: transform structured information into computed knowledge.
  Every computation produces a typed node with provenance and uncertainty.
  Status: StatisticsKernel built. UncertaintyPropagation not started.

LAYER 3 — Knowledge Construction  ← core of current implementation
  Typed knowledge graph, EpistemicStatus on every node,
  typed edges, claim extraction, provenance linking.
  Purpose: transform information into structured knowledge.
  Status: implemented and tested.

LAYER 4 — Reasoning
  ConflictDetector, GapDetector, EvidenceWeighter, PatternDetector.
  Purpose: surface what the accumulated knowledge implies —
  contradictions, gaps, patterns, confidence assessments.
  Status: all four implemented. PatternDetector not yet surfaced unprompted.

LAYER 5 — Research Intelligence
  LLM synthesis over accumulated knowledge.
  Agent loop: Retrieve → Reason → Review → Respond.
  Purpose: answer questions grounded in the accumulated graph.
  Status: implemented, agent loop has known quadratic token counting bug.

LAYER 6 — Sovereignty & Publication
  Permission switch, encrypted export, transmission log.
  Purpose: the researcher controls everything that leaves the device.
  Status: basic export exists, encryption not implemented.
```

The architecture is designed so that each layer can be added without restructuring the ones below it.

---

## 6. The Irreducible Components

Remove any of these and Victor becomes something else:

**EpistemicStatus on every node.** A spectrometer measurement and a speculative hypothesis must not be structurally identical. The trust model breaks without this. Everything downstream — ConflictDetector, EvidenceWeighter, GapDetector — requires it.

**The graph as permanent artifact.** Not a session context. Not an index that can be rebuilt. The graph is the memory of the device across model upgrades, hardware replacements, and years of use. It is the one irreplaceable output of the system.

**Typed edges with direction.** CONFIRMS, CONTRADICTS, DERIVED_FROM, GROUNDED_IN are not decoration. They are the semantic layer that makes reasoning possible. Flat storage with semantic search is not Victor.

**Offline capability.** The device must function in full in environments with no internet. This is not a performance requirement. It is a design identity requirement. A device that requires connectivity is a different product.

**User-controlled permission switch.** Nothing leaves the device without deliberate researcher action. This is non-negotiable across every phase.

**Provenance on everything.** Every piece of knowledge in the graph carries a record of where it came from. An answer that cannot be traced to a source node is a failure mode, not a feature.

**Accumulation over time.** A single session of Victor is not Victor. Victor is the system that makes a researcher's understanding compound over months and years. Without persistence and compounding, it is just another AI tool.

**Masked memory graph.** Relational anchors between knowledge nodes stay live and active. The full content of a specific node surfaces only when the user explicitly calls it. This mechanic — applied to sovereign sensor intelligence — is the most original idea in Victor's conception and the primary differentiator from all existing products.

---

## 7. The Long-Term North Star

A researcher alone in an unknown environment — remote facility, research vessel, extreme fieldwork, or a thought experiment of another planet entirely — carries one device.

The device scans. It understands what it scans. It connects what it finds today to what was found six months ago. It surfaces the contradictions, the gaps, the patterns the researcher has not noticed. It tells the researcher what remains unconfirmed. It protects its knowledge. It never phones home without permission.

Over years of use, in the specific domain of that researcher's work, it becomes a genuine expert in that domain — not from the internet, not from other users' data, but from that researcher's own accumulated measurements, experiments, and reasoning.

The model is swappable. The hardware is upgradeable. The knowledge graph is permanent.

That is Victor.

---

## 8. Competitive Position

The pieces that make up Victor exist separately in other products. Nobody has assembled this specific combination.

What exists elsewhere: multi-sensor detection hardware (L3Harris, FLIR, Smiths Detection), edge AI inference (Edge Impulse, Qualcomm), vector memory systems (Mem0, Cognee, Zep), data sovereignty tools, platform-agnostic software.

What nobody has built as one thing: the masked memory graph mechanic — relational anchors live, full content masked until explicitly called — applied to sovereign sensor intelligence across any platform. That specific combination, as a licensable intelligence layer, does not exist as a product.

The market it addresses is real: handheld multi-sensor field detection was $3.6–6.2B in 2025–2026, growing at 8–10% CAGR, dominated by defense and industrial buyers with high data sovereignty requirements.

The correct entry strategy is not hardware competition against L3Harris. It is building the software intelligence layer — masked memory, domain fusion pipeline, the security model — as something existing sensor hardware manufacturers can embed. B2B software inside a hardware market. Lower capital requirement, faster to revenue, original innovation intact.

---

*Victor Foundation Document · v2 · June 2026*
*Supersedes VICTOR_FOUNDATION_v1.md.*
*This document is the constitutional reference. For current code state, see VICTOR_WHAT_IS_BUILT.md. For build order, see VICTOR_BUILD_SEQUENCE.md.*
