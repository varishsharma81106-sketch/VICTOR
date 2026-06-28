# VICTOR — Build Sequence
*From current state to physical device · June 2026 · Updated to v5.3*

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

## Current Position

**Phase 0 complete. Phase 1A complete. YOU ARE HERE: Closing DoD #4 (SciFact benchmark ≥85%).**

Phase 0 (software brain, text-only) is complete — both bugs fixed, PatternDetector wired, full test suite passing (196/196).

Phase 1A (audio ingestion) is complete — `AudioIngestor` with `LibrosaFeatureClassifier` ships in v5.0. Note: the build plan called for PANNs/ONNX for audio classification; what shipped is a simpler heuristic classifier using MFCCs and chroma features via librosa. Functional for producing MEASUREMENT nodes from audio; less accurate than PANNs would have been. Phase 1B (sensor fusion) should upgrade this before relying on audio for field research.

The one remaining gate before Phase 1B can open is DoD #4: ConflictDetector accuracy ≥85% on the SciFact full dev set. The NLI cross-encoder is wired and the label-order bug that caused primary mode to fail is fixed in v5.3. Current best: 71.0% (cross-check mode, n=100). Primary mode with corrected label order has not yet been benchmarked.

---

## Phase 0 — Software Brain, Text Only
*Status: ✅ Complete.*

All five tasks done:
- AgenticRetriever quadratic token counting bug fixed (`retrieve.py`)
- `compute_statistics` metric conflation bug fixed (`kernels.py`)
- SciFact benchmark run and documented (5 runs; see VICTOR_WHAT_IS_BUILT.md Results Log)
- `victor gaps` not yet run on real data — this is the one unverified Phase 0 item
- PatternDetector wired to surface unprompted (`core.py`, `cli.py`)

**Status on real data:** no real research document has been ingested yet. Phase 0 exit criteria technically require `victor gaps` to produce useful output on at least one real document. This has not been verified. It is the lowest-effort open item in the entire phase map.

---

## Phase 1 — AI Brain Complete
*Status: ✅ Mostly complete. One DoD gate open.*

**Phase 1A — Audio Ingestion**
*Status: ✅ Complete (simplified). Ships in v5.0.*

`AudioIngestor` class exists in `sensors.py`. `LibrosaFeatureClassifier` performs heuristic acoustic feature extraction (MFCCs, mel spectrogram, chroma features). Produces MEASUREMENT nodes from audio. `victor observe --audio` CLI command exists.

**Correction from original plan:** the build plan called for PANNs (Pretrained Audio Neural Networks) via ONNX Runtime. What shipped is `LibrosaFeatureClassifier` — a simpler heuristic approach. This is a real gap for production audio classification accuracy. When resuming Phase 1 work after DoD #4 closes, the PANNs upgrade is the first task.

**Phase 1 AI reasoning — ConflictDetector accuracy**

This is the one item blocking Phase 1 completion and opening Phase 5 (LoRA fine-tuning).

Current state of the benchmark:

| Run | Config | n | Accuracy | Notes |
|---|---|---|---|---|
| Run 1 | v4.9, pure LLM | 50 | 68.0% | Original unstructured prompt |
| Run 2 | v5.1, pure LLM (JSON rewrite) | 50 | 58.0% | Structured prompt regression |
| Run 3 | v5.2, qwen2.5:7b, no NLI | 100 | 59.0% | Pure LLM ceiling confirmed |
| Run 4 | v5.2, deberta-base, NLI primary | 100 | 8.0% | Label order bug (now fixed in v5.3) |
| Run 5 | v5.2, deberta-base, NLI cross-check | 100 | **71.0%** | Best to date |
| **Target** | — | ≥300 | **>85%** | DoD #4 |

Next benchmark to run: deberta-base primary mode using v5.3 code (label order bug fixed). See `VICTOR_SCIFACT_ACCURACY_PLAN.md` for exact commands and decision gates.

**Definition of done for Phase 1:**
- All reasoning components built ✅
- PatternDetector surfaces unprompted ✅
- ConflictDetector accuracy ≥85% on SciFact full dev set ❌ (current best: 71.0%)

---

## Phase 1B — Sensor Fusion (after DoD #4 closes)
*Prerequisites: Phase 1A complete AND DoD #4 closed.*

When two or more modalities produce readings from the same physical scan, fuse them into a single higher-confidence artifact.

| Task | What it produces |
|------|-----------------| 
| `SensorFusionEngine` | Takes timestamped outputs from N sensors, aligns temporally |
| `EnvironmentSnapshot` node type | Unified multi-modal observation: camera + audio + environment |
| Confidence weighting per sensor | Accounts for sensor reliability in context |
| PANNs upgrade for audio | Replace LibrosaFeatureClassifier with PANNs/ONNX for production-grade audio classification |

**Definition of done for Phase 1B:**
One field scan using phone camera + laptop microphone simultaneously produces one `EnvironmentSnapshot` node with fused confidence higher than either individual reading.

---

## Phase 1C — Spectral / Chemical (future hardware)
*Do not start until 1A and 1B are done and you have access to a spectrometer.*

Raman / near-IR spectrometer → NIST/RRUFF spectral reference database → MEASUREMENT node with chemical identification. Requires hardware not yet available.

---

## Phase 2 — Computation Kernels
*Status: StatisticsKernel built. Others not started.*
*Prerequisites: Phase 1A complete (at minimum).*

**Phase 2A — UncertaintyPropagationKernel (1 week)**
User specifies a formula. Victor finds the MEASUREMENT nodes for each variable. Computes the result. Propagates uncertainty using standard error propagation. Every computation produces a COMPUTED node with provenance and uncertainty.

**Phase 2B — SignalProcessingKernel (1–2 weeks, after Phase 1A)**
FFT, spectral analysis, peak detection, baseline subtraction, trend extraction. Needs audio input from Phase 1A before it can do anything useful.

**Phase 2C — EstimationKernel (2–3 weeks)**
Curve fitting, parameter estimation, Bayesian credible intervals. User provides a model equation and a set of MEASUREMENT nodes. Victor fits the model.

**Reproducibility hash on every kernel output:** every COMPUTED node carries a deterministic hash of: input node IDs + kernel type + kernel version + parameters. If any input changes, the hash breaks. The system flags which computed results are stale.

---

## Phase 3 — Model Stack Upgrade
*Status: Ollama used in development. Can run in parallel with Phase 1B.*
*Prerequisites: Phase 0 complete.*

Replace Ollama with inference backends appropriate for embedded deployment. No code changes outside the `InferenceClient` interface.

### Phase 3A — InferenceClient → llama-cpp-python (1 week)

| Backend | Use case |
|---------|---------|
| `llama-cpp-python` | Production CPU inference — direct C++ bindings, zero daemon overhead, runs on ARM |
| `mlx-lm` | Apple Silicon only — 2–3× faster than llama.cpp on M-series |
| `ONNX Runtime` | Edge/embedded — hardware-agnostic, INT4/INT8, 1GB RAM devices |
| Ollama | Development only |

### Phase 3B — Embedder upgrade (1 week)
From `all-MiniLM-L6-v2` to `nomic-embed-text-v1.5` + `allenai/specter2`. nomic for general text; specter2 for scientific literature (trained on citation supervision — substantially better at finding semantically related scientific claims).

### Phase 3C — Reasoning model upgrade (1 week)
From phi3:mini to Qwen2.5-7B-Instruct (Q4_K_M). For ConflictDetector specifically: consider `DeepSeek-R1-Distill-Qwen-7B` — it produces explicit step-by-step reasoning chains that can be stored as provenance in the graph.

### Phase 3D — ModelRegistry (2 weeks)
Four hardware tiers, auto-detected at startup:

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

### Phase 4A — Conversation Memory as Graph Nodes (2 weeks)
Already partially implemented. Every Q&A session becomes a CONVERSATION node linked via GROUNDED_IN edges to source nodes.

### Phase 4B — Proactive Pattern Detection (2 weeks, after 4A)
PatternDetector (built) surfaces insights without being asked: topics with many queries but weak evidence, claims referenced often but never experimentally confirmed, recurring anomalies, temporal trends. Already wired to surface unprompted — this phase completes the proactive triggering logic.

### Phase 4C — LoRA Fine-Tuning (months, after 4A + 4B + real data)

**Hard prerequisites:**
- Minimum 500 conversation turns of real usage data in the graph
- Phase 4A and 4B both working and producing useful output
- Fine-tuning pipeline: LoRA + PEFT + datasets library
- Eval harness to test fine-tuned model against base model before deployment
- Model versioning: keep baseline, deploy fine-tuned, rollback if worse

**Correctly gated on DoD #4.** Do not start Phase 4C before ConflictDetector accuracy ≥85%. Fine-tuning on top of an unverified reasoning component produces an unauditable system.

---

## Phase 5 — Field Prototype (Hardware)
*Status: Not started.*
*Prerequisites: Phases 0, 1, 2, 3 complete and tested on real data.*

**Hardware target: Raspberry Pi 5 (8GB) + modules**
Camera module v3, BME688 environmental sensor, USB omnidirectional microphone, 128GB NVMe SSD, LiPo battery + management board, ruggedized enclosure.

Runs Tier 0 models (smolLM2-1.7B, moondream2, bge-small-en). ModelRegistry from Phase 3D means no code changes — just a different config file.

**Software changes for the device:**
- CLI becomes daemon-first: sensor → model → graph → reasoning runs continuously in background
- SQLite-vec replaces ChromaDB for embedded deployment
- `sensors.py` gains GPIO bindings for BME688
- Power management: graceful shutdown with knowledge snapshot on low battery

---

## Phase 6 — Multi-Sensor Unit (Advanced Hardware)
*Status: Not started. Requires Phase 5 validated in the field.*

Jetson Orin Nano replaces Raspberry Pi. Spectrometer and LIDAR added. Runs Tier 1–2 models. Sensor fusion produces `EnvironmentSnapshot` nodes across 4+ simultaneous modalities. This matches the original vision most closely.

---

## What to Never Build (In Any Phase)

**LangChain / LlamaIndex / Haystack / DSPy** — Victor's knowledge graph is its own orchestration layer. Adding a framework creates two retrieval systems that must be reconciled.

**Ungated autonomous weight updates** — model weights must never update from user interactions without explicit, user-initiated fine-tuning with review and rollback capability. Non-negotiable.

**Cloud-first features** — any feature that requires internet connectivity to function degrades offline capability from "complete product" to "degraded fallback." That is a different product.

**General-purpose features** — if a feature would be equally at home in Notion or Obsidian, it does not belong in Victor. Generality is scope creep.

---

## Build Sequence Summary

```
Phase 0 — Software brain, text only             ✅ COMPLETE
    ↓
Phase 1A — Audio ingestion                      ✅ COMPLETE (LibrosaFeatureClassifier)
    ↓
    ← YOU ARE HERE: Close DoD #4 (SciFact ≥85%)
    ← Then: ingest one real document, run `victor gaps`
    ↓
Phase 1B — Sensor fusion + PANNs audio upgrade   ← Next new capability
    ↓
Phase 2A — UncertaintyPropagationKernel          ← Can run parallel with Phase 1B
Phase 3A–D — Model stack upgrade                 ← Can run parallel with Phase 1B
    ↓
Phase 4A — Conversation memory                   ← After 3+ months real usage
Phase 4B — Proactive pattern detection
    ↓
Phase 5 — Field prototype (hardware)             ← After all software phases stable
    ↓
Phase 6 — Multi-sensor unit                      ← After Phase 5 validated in field
Phase 4C — LoRA fine-tuning                      ← After 500+ real turns + Phase 4A+B
    ↓
Phase 1C — Spectral/Chemical ingestion           ← Requires hardware not yet available
```

---

*VICTOR_BUILD_SEQUENCE.md · June 2026 · Updated to v5.3*
*For current bugs and next immediate action, see VICTOR_WHAT_IS_BUILT.md.*
*For the principle every phase implements, see VICTOR_THEORY_v1.md.*
*For the SciFact benchmark path specifically, see VICTOR_SCIFACT_ACCURACY_PLAN.md.*
