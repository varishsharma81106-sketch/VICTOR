# VICTOR — Build Sequence
*From current state to physical device · June 2026*

---

> This document tells you what to build in what order and why the order matters.
> Every phase is a complete, usable system at its own level before the next phase begins.
> Do not start Phase N+1 until Phase N is verifiably working on real data.

---

## The Invariant Rule

Before adding any new capability, answer this question:

> *Does this improve the production, preservation, or compounding of Epistemic Artifacts?*

If no: do not build it. If yes: find where it fits in the sequence below and build it in order.

---

## Current Position: Phase 0 → Phase 1 transition

Phase 0 (software brain, text-only) is built but has two unfixed bugs and zero real data.
The next action is not building Phase 2. It is finishing Phase 0.

---

## Phase 0 — Software Brain, Text Only
*Status: Built. Two bugs remain. No real data ingested yet.*

**What this phase is:**
The knowledge graph, reasoning layer, ingestion pipeline, and basic sensor pipeline exist. The system can ingest PDFs, extract claims, detect conflicts, find gaps, and answer questions with provenance. One camera modality (CLIP) produces MEASUREMENT nodes.

**What remains before Phase 0 is truly complete:**

| Task | File | Why |
|------|------|-----|
| Fix AgenticRetriever quadratic token counting | `retrieve.py` | Agent loop dies turn 2–3 in real use |
| Fix `compute_statistics` metric conflation | `kernels.py` | StatisticsKernel produces wrong aggregates |
| Run SciFact benchmark, document result in README | `scifact_benchmark.py` | No accuracy number = no basis for claiming ConflictDetector works |
| Ingest one real research document, run `victor gaps` | CLI | First real-world test of whether the system produces useful output |
| Wire PatternDetector to surface unprompted | `core.py`, `cli.py` | PatternDetector computes but never speaks |

**Definition of done for Phase 0:**
- Both bugs fixed
- SciFact result documented: "ConflictDetector accuracy on SciFact: X.X%"
- `victor gaps` produces useful output on at least one real document
- PatternDetector insights appear in answers without user asking for them
- All existing tests pass on a clean clone

---

## Phase 1 — Reality → Artifact Pipeline (Multi-Modal)
*Status: Camera modality built. Audio and spectral not started.*
*Prerequisites: Phase 0 complete.*

**What this phase adds:**
The ability to ingest from sensors directly — not just documents. Every sensor modality becomes a StreamIngestor that produces MEASUREMENT nodes. Phase 0 proved the loop works for one modality (camera). Phase 1 extends it to audio and spectral.

**Build order within Phase 1:**

### Phase 1A — Audio Ingestion (1–2 weeks)
The laptop microphone already exists. No hardware purchase needed.

| Task | What it produces |
|------|-----------------|
| `AudioIngestor` class (subclass of `IngestorBase`) | Microphone capture → acoustic feature extraction |
| librosa integration: MFCCs, mel spectrogram, chroma features | Structured acoustic features |
| PANNs (Pretrained Audio Neural Networks) via ONNX Runtime | Acoustic event classification with confidence |
| MEASUREMENT node creation from audio classification | Audio → EpistemicStatus.MEASUREMENT in the graph |
| `victor observe --audio` CLI command | End-to-end test |
| Tests using MockAudioClassifier | No hardware dependency |

**Definition of done for Phase 1A:**
One microphone capture produces a MEASUREMENT node with all 6 Epistemic Artifact properties. `victor ask "what sounds have I recorded today?"` returns that node with provenance.

### Phase 1B — Sensor Fusion (2–3 weeks, after 1A)
When two or more modalities produce readings from the same physical scan, fuse them into a single higher-confidence artifact.

| Task | What it produces |
|------|-----------------|
| `SensorFusionEngine` | Takes timestamped outputs from N sensors, aligns temporally |
| `EnvironmentSnapshot` node type | Unified multi-modal observation: camera + audio + environment |
| Confidence weighting per sensor | Accounts for sensor reliability in context (acoustic fails in wind, EM fails near interference) |
| Cross-modal similarity (ImageBind embeddings, optional) | Camera reading and text description comparable in same vector space |

**Definition of done for Phase 1B:**
One field scan using phone camera + laptop microphone simultaneously produces one `EnvironmentSnapshot` node with fused confidence higher than either individual reading.

### Phase 1C — Spectral / Chemical (future, requires hardware)
*Do not start until 1A and 1B are done and you have access to a spectrometer.*

Raman / near-IR spectrometer → NIST/RRUFF spectral reference database → MEASUREMENT node with chemical identification. This is the modality that makes Victor genuinely powerful for field research. It requires hardware not yet available.

---

## Phase 2 — Computation Kernels
*Status: StatisticsKernel built. Others not started.*
*Prerequisites: Phase 1A complete (at minimum).*

**What this phase adds:**
Victor doesn't just store measurements — it computes over them. Every kernel result is a COMPUTED node with full provenance, uncertainty, and a reproducibility hash.

### Phase 2A — UncertaintyPropagationKernel (1 week)
User specifies a formula. Victor finds the MEASUREMENT nodes for each variable. Computes the result. Propagates uncertainty using standard error propagation formulas.

```
"Given measurement A = 4.2 ± 0.1 and measurement B = 3.7 ± 0.2, what is A×B?"
Victor: "15.54 ± 0.90 (k=1). Dominant uncertainty source: B (82% of total variance)."
```

The result is a COMPUTED node linked to both MEASUREMENT nodes via DERIVED_FROM edges.

### Phase 2B — SignalProcessingKernel (1–2 weeks, after Phase 1A)
For time-series data from acoustic and environmental sensors:
- FFT and spectral analysis
- Peak detection and characterisation
- Baseline subtraction
- Trend extraction and rate-of-change computation

Needs audio input from Phase 1A before it can do anything useful.

### Phase 2C — EstimationKernel (2–3 weeks)
Curve fitting, parameter estimation, Bayesian credible intervals. User provides a model equation and a set of MEASUREMENT nodes. Victor fits the model and stores best-fit parameters as COMPUTED nodes.

**Reproducibility hash on every kernel output:**
Every COMPUTED node carries a deterministic hash of: input node IDs + kernel type + kernel version + parameters. If any input changes, the hash breaks. The system flags which computed results are now stale.

---

## Phase 3 — Model Stack Upgrade
*Status: Ollama used in development, not production-ready for device.*
*Prerequisites: Phase 0 complete. Can run in parallel with Phase 1.*

**What this phase adds:**
Replace Ollama with inference backends appropriate for embedded deployment. No code changes outside the `InferenceClient` interface — everything else stays the same.

### Phase 3A — InferenceClient → llama-cpp-python (1 week)

| Backend | Use case | Why |
|---------|---------|-----|
| `llama-cpp-python` | Production CPU inference | Direct C++ bindings, zero daemon overhead, runs on ARM |
| `mlx-lm` | Apple Silicon only | 2–3x faster than llama.cpp on M-series chips |
| `ONNX Runtime` | Edge/embedded inference | Hardware-agnostic, INT4/INT8 quantization, 1GB RAM devices |
| Ollama | Development only | Keep for dev convenience, remove from production path |

Keep Ollama as the development default. Replace the production inference path. Same interface, different backend.

### Phase 3B — Embedder upgrade (1 week, parallel with 3A)

| From | To | Why |
|------|-----|-----|
| `all-MiniLM-L6-v2` | `nomic-embed-text-v1.5` + `specter2` | MiniLM not trained for scientific retrieval |

Two embedders in parallel: `nomic-embed-text-v1.5` for general text and conversation memory (8192-token context). `allenai/specter2` for scientific literature and claims — trained on academic papers using citation supervision, substantially better at finding semantically related scientific claims.

### Phase 3C — Reasoning model upgrade (1 week, parallel)

| From | To | Why |
|------|-----|-----|
| phi3:mini or similar | Qwen2.5-7B-Instruct (Q4_K_M) | Stronger structured output, scientific reasoning, multilingual |

For ConflictDetector and GapDetector specifically: consider `DeepSeek-R1-Distill-Qwen-7B` — it produces explicit step-by-step reasoning chains that can be stored as provenance in the graph. The reasoning trace becomes a node.

### Phase 3D — ModelRegistry (2 weeks)

```python
class ModelRegistry:
    reasoning:  LLMBase         # text reasoning and Q&A
    vision:     VisionBase      # image understanding
    audio:      AudioBase       # acoustic analysis
    embedder:   EmbedderBase    # text and multi-modal embeddings
    classifier: ClassifierBase  # fast on-device classification
```

Victor auto-detects hardware tier at startup and loads appropriate models. Swapping a model is a config change, not a code change. Four hardware tiers:

| Tier | Hardware | RAM | Reasoning | Vision | Embedder |
|------|---------|-----|-----------|--------|---------|
| 0 — minimal | Raspberry Pi / ARM | 4GB | smolLM2-1.7B (Q4) | moondream2 (Q4) | bge-small-en |
| 1 — standard | Modern CPU laptop | 8–16GB | Qwen2.5-7B (Q4_K_M) | Florence-2-base | nomic-embed-text |
| 2 — performance | Apple Silicon / GPU | 16–32GB | Qwen2.5-14B (Q6) | PaliGemma-3B | specter2 |
| 3 — research | High-end workstation | 32GB+ | DeepSeek-R1-Distill-7B | Full vision pipeline | ImageBind |

---

## Phase 4 — Self-Learning (Domain Adaptation)
*Status: Not started. Requires real accumulated data from Phases 0–1.*
*Prerequisites: Phase 0 complete AND at minimum 3 months of real usage with real data.*

**What this phase adds:**
Victor gets better at your specific domain from your own accumulated work. Three sub-phases in strict order.

### Phase 4A — Conversation Memory as Graph Nodes (2 weeks)
Every Q&A session becomes a new node in the graph:
```
node type: CONVERSATION
fields: query, answer, provider_used, sources_cited, timestamp
edges: GROUNDED_IN → source nodes used
```
The model doesn't change. The graph gets richer from usage alone. This is already partially implemented. Completing it means: next time you ask a related question, previous Q&A surfaces as context alongside source documents.

### Phase 4B — Proactive Pattern Detection (2 weeks, after 4A)
PatternDetector (already built) surfaces insights without being asked:
- Topics with many queries but weak evidence (gaps the user keeps bumping into)
- Claims referenced often but never experimentally confirmed
- Recurring anomalies across multiple field sessions
- Temporal trends in measurement data

When a user asks about a topic with unconfirmed claims, the answer prepends: *"Pattern insight: You've asked about this 4 times and it has no experimental confirmation in your graph."*

### Phase 4C — LoRA Fine-Tuning (months, after 4A + 4B + real data)
Actual weight updates to the reasoning model from accumulated domain knowledge.

**Hard prerequisites before starting:**
- Minimum 500 conversation turns of real usage data in the graph
- Phase 4A and 4B both working and producing useful output
- Fine-tuning pipeline: LoRA + PEFT + datasets library
- Eval harness to test the fine-tuned model against the base model before deployment
- Model versioning: keep baseline, deploy fine-tuned, rollback if worse

**What it does:**
Improves claim extraction from domain-specific documents, improves conflict detection reasoning in the domain, improves gap detection relevance.

**What it does not do:**
Update weights from individual conversations without user review. Replace the knowledge graph. Run unsupervised. The fine-tuning is always opt-in, auditable, and reversible.

The knowledge graph approach (Phases 4A + 4B) is stronger for most research use cases than weight fine-tuning. The knowledge is inspectable, correctable, and doesn't suffer from catastrophic forgetting. Do not rush to 4C.

---

## Phase 5 — Field Prototype (Hardware)
*Status: Not started. Requires all software phases stable.*
*Prerequisites: Phases 0, 1, 2, 3 complete and tested on real data.*

**What this phase adds:**
Victor moves from a laptop software system to a portable, field-deployable device.

### Hardware target: Raspberry Pi 5 + modules
- Raspberry Pi 5 (8GB) — main compute
- Camera module v3 — primary vision sensor
- BME688 environmental sensor — temperature, pressure, humidity, gas
- USB sound card + omnidirectional microphone — acoustic input
- 128GB NVMe SSD — knowledge graph storage
- LiPo battery + management board — field power
- Ruggedized enclosure

This runs Tier 0 models (smolLM2-1.7B, moondream2, bge-small-en) comfortably. The ModelRegistry from Phase 3D means no code changes — just a different config file.

### Software changes for the device:
- CLI becomes daemon-first: sensor → domain model → graph → reasoning runs continuously in background without human typing queries
- SQLite-vec replaces ChromaDB for embedded deployment (lighter, no server process)
- `sensors.py` gains GPIO bindings for BME688
- Power management: graceful shutdown with knowledge snapshot on low battery

### Definition of done for Phase 5:
One complete field session: power on device, scan environment with camera + microphone + environmental sensor, ingest results, run `victor gaps`, power off. All knowledge preserved in graph. Same graph queryable on laptop after transferring storage.

---

## Phase 6 — Multi-Sensor Unit (Advanced Hardware)
*Status: Not started. Requires Phase 5 validated.*

**What this phase adds:**
Jetson Orin Nano replaces Raspberry Pi. Spectrometer and LIDAR added. Runs Tier 1–2 models. Sensor fusion produces `EnvironmentSnapshot` nodes across 4+ simultaneous modalities.

This is the device that matches the original vision most closely — modular, deployable in submarines or spacecraft, running full sensor fusion intelligence locally.

Do not design Phase 6 hardware before Phase 5 is working in the field.

---

## What to Never Build (In Any Phase)

**LangChain / LlamaIndex / Haystack / DSPy** — these add abstraction layers over the LLM calls that make debugging harder and provide orchestration that Victor's own graph architecture already does better. Victor's knowledge graph is its own orchestration layer. Adding a framework mediating between the graph and inference layer means building two retrieval systems and reconciling them.

**Ungated autonomous weight updates** — the AI must not update its own weights from user interactions without explicit user-initiated fine-tuning with review and rollback. This is not a philosophical constraint only; it is a safety requirement for a device used in research contexts where trust in the system's outputs matters.

**Cloud-first features** — any feature that requires internet connectivity to function degrades Victor's offline capability from "complete product offline" to "degraded fallback offline." That is a different product.

**General-purpose features** — if a feature would be equally at home in Notion or Obsidian, it does not belong in Victor. Victor is built specifically for the structure of scientific and technical reasoning. Generality is scope creep.

---

## Build Sequence Summary

```
Phase 0 — Software brain, text only          ← YOU ARE HERE (2 bugs remain)
    ↓
Phase 1A — Audio ingestion                   ← First new capability
    ↓
Phase 1B — Sensor fusion                     ← Multi-modal
    ↓
Phase 2A — UncertaintyPropagationKernel      ← Can run parallel with Phase 1
Phase 3A–D — Model stack upgrade             ← Can run parallel with Phase 1
    ↓
Phase 4A — Conversation memory               ← After 3+ months real usage
Phase 4B — Proactive pattern detection
    ↓
Phase 5 — Field prototype (hardware)         ← After all software phases stable
    ↓
Phase 6 — Multi-sensor unit                  ← After Phase 5 validated in field
Phase 4C — LoRA fine-tuning                  ← After 500+ real turns and Phase 4A+B
    ↓
Phase 1C — Spectral/Chemical ingestion       ← Requires hardware not yet available
```

---

*VICTOR_BUILD_SEQUENCE.md · June 2026*
*For current bugs and next immediate action, see VICTOR_WHAT_IS_BUILT.md.*
*For the principle every phase implements, see VICTOR_THEORY_v1.md.*
