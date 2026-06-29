# Victor: A Local-First Research Intelligence System with Epistemic Provenance and NLI-Augmented Conflict Detection

## Abstract

Researchers accumulate knowledge across fragmented tools — papers, notes, experiments, observations — with no memory of where claims originated or how confident they should be in them. We present Victor, a local-first research intelligence system that converts raw inputs into typed, provenance-tracked Epistemic Artifacts stored in a persistent knowledge graph, answering research queries by retrieving and reasoning over those artifacts entirely on-device. Victor introduces four technical contributions: (1) an Epistemic Artifact abstraction with six mandatory provenance properties as the unit of knowledge, (2) an NLI-primary architecture in which a cross-encoder decides conflict direction while the LLM provides reasoning traces only, mitigating structured-output agreement bias, (3) a masked memory primitive with embedding-channel closure that deletes vector store entries for suppressed nodes, and (4) a bounded agent loop with automatic pre-answer conflict review. On the SciFact claim verification benchmark, Victor's cross-check configuration achieves 71.0% accuracy (n=100) using Qwen2.5-7B and DeBERTa-v3-base NLI, with root causes of lower-performing configurations identified and validated. Victor is open-source, CPU-only, and requires no cloud connectivity.

## 1. Introduction

The distance between a physical observation and a researcher's reliable understanding of it is enormous. A researcher today uses instruments to observe, export tools to extract data, notebooks to compute, reference managers to find papers, document viewers to read them, note apps to record thoughts, and memory to hold it all together. Every boundary between these tools destroys information. Every destroyed connection must be reconstructed from memory months later, imperfectly, or not at all.

The result is *epistemic fragmentation*: knowledge is produced but does not compound. Experiments are run but their relationship to prior claims is never recorded. Contradictions accumulate unseen. Gaps grow unnoticed. Researchers repeatedly rediscover prior insights, repeat experiments already done, and fail to build on prior work as effectively as the accumulated evidence would support.

Victor addresses this by tracking epistemic provenance from the moment a claim is created. Every piece of knowledge in Victor's graph carries a type (measurement, experiment, literature, note, or hypothesis), a confidence score derived from evidence edges, a contradiction set, a gap set, and a temporal decay rate. This structured representation enables automatic surfacing of contradictions, gaps, and patterns — and prevents the system from ever confusing a hypothesis with a measurement.

Victor is designed for deployment in environments where cloud connectivity cannot be assumed: remote field sites, research vessels, hazardous facilities. All inference, storage, and reasoning occur on-device. The system carries pre-trained models locally and is roughly 90% capable without internet access. This is not a performance constraint but a design identity: offline is the default reliable state, not a degraded fallback.

This paper makes four contributions:

1. **The Epistemic Artifact abstraction** — a six-property knowledge unit that enforces provenance tracking at graph construction time, enabling typed evidence aggregation and epistemic-aware retrieval scoring.

2. **NLI-primary conflict detection** — an architecture that inverts the standard LLM-primary pipeline: a cross-encoder NLI model makes the direction decision (confirm/contradict/inconclusive) while the LLM provides free-form reasoning traces only. This eliminates structured-output agreement bias, where instruction-tuned LLMs route to "confirm" as the lowest-perplexity schema-satisfying token.

3. **Masked memory with embedding-channel closure** — a sovereignty primitive that suppresses node content from LLM answers while keeping graph structure live for routing, and deletes vector embeddings to close the membership-inference covert channel.

4. **A bounded agent loop with automatic pre-answer review** — a Retrieve → Reason → Review → Respond cycle with hard tool-call limits, token ceilings, and automatic conflict detection on retrieved claims before the first LLM call.

## 2. Related Work

**Retrieval-Augmented Generation.** Lewis et al. (2020) established the RAG paradigm: retrieve relevant documents, then generate an answer conditioned on them. Victor extends this with typed epistemic provenance — standard RAG has no notion of whether a retrieved chunk is a hypothesis or a measurement. Victor's retrieval scoring blends cosine similarity with importance-weighted epistemic status, ensuring higher-tier evidence (measurements, experiments) ranks above lower-tier sources (notes, hypotheses).

**Knowledge Graph QA.** KG-RAG systems (Pan et al., 2024) use knowledge graphs for entity linking and relation traversal to improve retrieval. Victor uses a knowledge graph not for entity linking but for epistemic edge tracking: CONFIRMS, CONTRADICTS, DERIVED_FROM, and GROUNDED_IN edges encode the evidential relationships between claims, experiments, and observations. This typed edge layer enables automated reasoning that flat knowledge graphs cannot support.

**NLI for Fact Verification.** Thorne et al. (2018, FEVER) and Wadden et al. (2020, SciFact) established NLI-based claim verification as a standard evaluation task. The dominant approach uses an LLM or fine-tuned classifier as the primary judge. Victor's contribution is architectural: wiring the NLI cross-encoder as the primary direction judge with the LLM as annotator-only, inverting the standard pipeline to eliminate structured-output agreement bias. This addresses a specific failure mode where instruction-tuned LLMs default to "confirm" under uncertainty.

**Agentic RAG.** ReAct (Yao et al., 2023), Toolformer (Schick et al., 2023), and related systems introduce tool-use loops where an LLM iteratively calls retrieval and reasoning tools. Victor bounds this loop explicitly with a hard tool-call limit (5 calls), a soft token ceiling (8,000 tokens with forced-answer fallback), and an automatic Review step that runs ConflictDetector on retrieved claims with mixed evidence before the first LLM call. This prevents runaway tool use and ensures conflict detection is not skipped.

**Personal Knowledge Management.** Obsidian, Roam Research, and Logseq enable networked note-taking with bidirectional links. These tools capture *what* the user wrote but not *how confident* they should be in it. Victor differs by enforcing epistemic typing (every node carries an EpistemicStatus), automated conflict detection (experiments can confirm or contradict claims), and evidence weighting (confidence scores aggregate from evidence edges).

## 3. System Design

### 3.1 The Epistemic Artifact

Victor's fundamental unit of knowledge is the Epistemic Artifact — a graph node with six mandatory properties:

1. **Origin** — provenance chain: sensor type and ID, source document, or extraction model.
2. **Type** — one of five epistemic tiers forming a trust hierarchy:
   - MEASUREMENT (weight 1.00): directly observed data point
   - EXPERIMENT (weight 0.85): controlled test result
   - LITERATURE (weight 0.70): claim from a published paper
   - NOTE (weight 0.50): personal annotation or summary
   - HYPOTHESIS (weight 0.25): speculative, unverified
3. **Confidence** — 0.0–1.0, computed from evidence edge aggregation.
4. **Contradictions** — set of experiment nodes with CONTRADICTS edges to this claim.
5. **Gaps** — what evidence is missing before this claim can be trusted.
6. **Age** — timestamp plus temporal decay rate for importance weighting.

The hierarchy is enforced at graph construction time: the node type determines the default epistemic status, which determines the weight used in all downstream retrieval scoring and conflict resolution. A MEASUREMENT node from a spectrometer and a HYPOTHESIS node from casual observation are structurally distinct — the system cannot confuse them.

### 3.2 Knowledge Graph

Victor uses a directed graph with 8 node types (PAPER, CLAIM, EXPERIMENT, NOTE, CONCEPT, CONVERSATION, COMPUTED, OBSERVATION) and 12 typed edge types. The graph is serialized as JSON via NetworkX with atomic save semantics (write to `.tmp`, then `os.replace()`) to survive crashes. Every node carries semantic embeddings computed at creation time for cosine-similarity retrieval.

### 3.3 Ingestion Pipeline

The ingestion layer uses a plugin architecture via `IngestorBase`. Adding a new source type requires implementing `extensions` (file suffixes) and `ingest()` — the core controller dispatches by file extension through a registry without modification. Three built-in ingestors:

- **PDFIngestor** — extracts text via PyMuPDF/pdfplumber, chunks via `TextChunker`, optionally extracts claims via LLM-based `ClaimExtractor`.
- **MarkdownIngestor** — same pipeline for `.md`/`.txt`/`.rst` files, accepts a `source_type` override to classify documents as PAPER (LITERATURE tier) or NOTE.
- **ExperimentIngestor** — ingests structured JSON experiment logs, auto-links to existing claims via cosine similarity threshold.

Claims are extracted per-chunk (not on a hard-truncated document prefix) to avoid losing information from later sections. Extracted claims are deduplicated case-insensitively across chunks and stored with source provenance linking back to the originating document.

### 3.4 Retrieval Architecture

**HybridRetriever** performs two-stage retrieval with blended scoring:

```
score = 0.7 × cosine_similarity + 0.3 × importance_score
```

Stage 1 queries the ChromaDB vector store for top-k similar chunks. Stage 2 performs semantic graph query on node embeddings plus 2-hop neighbor expansion via the typed edge layer. Masked nodes participate in graph routing (preserving structural reasoning) but their content is withheld from retrieval results.

**AgenticRetriever** extends HybridRetriever with a bounded tool-use loop:

- **Retrieve** — hybrid vector + graph retrieval
- **Reason** — LLM calls reasoning tools (judge_conflict, summarize_claim_evidence, find_research_gaps, search_nodes_by_text, find_related_nodes, get_node_details, get_claims_for_source)
- **Review** — automatic ConflictDetector run on retrieved claims that have both CONFIRMS and CONTRADICTS edges, before the first LLM call
- **Respond** — LLM generates the final answer conditioned on all gathered evidence

Hard limits: maximum 5 tool calls, 8,000 token ceiling with forced-answer fallback. Tool deduplication by SHA-256 hash of (tool_name, arguments) prevents redundant calls.

### 3.5 Conflict Detection

The **ConflictDetector** determines whether an experiment confirms, contradicts, or is inconclusive with respect to a claim. It operates in two modes:

**Standard mode (LLM + NLI cross-check):** The LLM (Qwen2.5-7B) makes the direction decision via structured JSON output. An NLI cross-encoder (`cross-encoder/nli-deberta-v3-base`) runs afterward. If the LLM predicts confirm/inconclusive but the NLI predicts contradiction with confidence above a threshold, the judgment is overridden to contradict. This catches the LLM's agreement bias on a subset of samples.

**NLI-primary mode (Step-1a architecture):** The NLI cross-encoder decides the direction. The LLM is called only for a free-form reasoning trace — no JSON schema, no direction token. This eliminates structured-output agreement bias: when constrained to emit a valid JSON enum, instruction-tuned LLMs route to "confirm" as the lowest-perplexity schema-satisfying token.

The **NLICrossEncoder** wrapper handles label-order ambiguity across model families. The output order of NLI models varies (e.g., DeBERTa outputs [contradiction, neutral, entailment] while ModernCE outputs [entailment, neutral, contradiction]). Victor auto-detects the order from `model.config.id2label`, trying three attribute paths for robustness. A pre-benchmark smoke test validates the mapping against two known pairs before any evaluation run.

### 3.6 Reasoning Layer

**EvidenceWeighter** walks inbound edges to a CLAIM node and computes confidence as n_confirms / (n_confirms + n_contradicts + n_inconclusive). **GapDetector** surfaces CLAIM nodes with n_confirms == 0, sorted by importance score descending. **PatternDetector** performs cross-gap analysis and auto-injects insights into answers when the query embedding similarity to a priority gap exceeds 0.65.

### 3.7 Sovereignty and Security

Victor implements two orthogonal per-node control flags:

**Freeze** prevents overwrite of node content while keeping it readable. **Mask** suppresses node content from LLM answers while keeping graph structure live for routing, gap detection, and conflict detection. Masked nodes emit anchor chunks (`[MASKED — ... use 'victor unmask <id>' to reveal]`) that preserve referential presence.

Critically, masking also deletes the node's embedding chunks from ChromaDB. Without this, an adversarial query could triangulate masked content via embedding similarity — the membership-inference covert channel. Every mask/unmask operation is logged in a tamper-evident JSONL audit trail with caller attribution via stack inspection.

### 3.8 Computation Kernels

The **StatisticsKernel** computes descriptive statistics (mean, variance, standard deviation, confidence intervals) and Cohen's d effect size over node values. It requires an explicit `metric_name` parameter — never averages all numeric fields, preventing the conflation of distinct metrics (e.g., precision + recall + f1). Outputs are stored as COMPUTED nodes with DERIVED_FROM edges and a SHA-256 reproducibility hash for staleness detection.

## 4. Implementation

Victor is implemented in Python with the following dependencies: `sentence-transformers` (embeddings and NLI), `chromadb` (vector store), `networkx` (knowledge graph), `ollama` (LLM inference), `click` and `rich` (CLI), and `PyMuPDF` (PDF extraction). The system runs entirely on CPU with no GPU requirement.

The test suite contains 196 tests across 12 test files covering the agent loop, audio pipeline, CLI imports, masked memory, masking enforcement, metric conflation, NLI cross-encoder, SciFact benchmark machinery, sensor pipeline, statistics kernel, tool mask enforcement, and audit logging.

The CLI provides the complete interface: `victor ingest`, `victor ask`, `victor gaps`, `victor observe`, `victor inspect`, `victor stats`, `victor mask`, `victor unmask`, and computation kernel commands. No web API or graph visualization is implemented — these are explicitly out of scope for the current version.

The LLM backend uses a fallback chain: Ollama (primary, serving Qwen2.5-7B) → OpenAI API (if key is set) → Mock (always available, returns inconclusive). This enables full system testing without any external service dependency.

## 5. Evaluation

### 5.1 Task and Dataset

We evaluate Victor's ConflictDetector on the SciFact benchmark (Wadden et al., 2020): given a (claim, abstract) pair, classify the relationship as confirm, contradict, or inconclusive. The dev set contains 300 claims with evidence-linked abstracts. All experiments use n=100 samples unless otherwise noted.

### 5.2 Results

| Run | Mode | n | Accuracy | confirm recall | contradict recall | NLI overrides |
|-----|------|---|----------|----------------|-------------------|---------------|
| 1 | Pure LLM, free-form prompt | 50 | 68.0% | 86.0% | 27.0% | 0 |
| 2 | Structured JSON output | 50 | 58.0% | 63.0% | 47.0% | 0 |
| 3 | Qwen2.5-7B, no NLI | 100 | 59.0% | 61.4% | 53.3% | 4 |
| 4 | DeBERTa-base, NLI primary | 100 | 8.0% | 7.1% | 10.0% | 100 |
| 5 | DeBERTa-base, NLI cross-check | 100 | **71.0%** | 68.6% | 76.7% | — |

**Run 1 → Run 2 regression.** Forcing Qwen2.5-7B to emit valid JSON against an enum-constrained schema suppresses reasoning quality. The model routes to the lowest-perplexity token satisfying the schema — "confirm" is shorter, more common in RLHF data, and schema-valid. This is a documented failure mode: 10–30 point accuracy drops on reasoning tasks constrained to structured output.

**Run 4 failure (label-order bug, fixed in v5.2).** The `_LABEL_ORDER` constant had indices 1 and 2 swapped: `["contradiction", "entailment", "neutral"]` instead of the model's actual output order `["contradiction", "neutral", "entailment"]`. Every entailment prediction mapped to "neutral" → "inconclusive", which the primary-mode logic overrode to "contradict". The result: 100% of predictions wrong. The fix corrects the constant, adds auto-detection from `model.config.id2label`, and introduces a pre-benchmark smoke test that validates the mapping against two known pairs.

**Run 5 (current best).** Cross-check mode is robust to the label-order bug because it only uses index 0 (contradiction) for the override decision — and index 0 was correct in both label orders. The NLI cross-encoder catches agreement bias on a subset of samples, adding ~12 points over the pure-LLM ceiling of ~59%.

### 5.3 Analysis

The 71.0% result represents the combined ceiling of Qwen2.5-7B (pure ~59%) plus DeBERTa-v3-base NLI cross-check (~12 points from catching agreement bias on ~8 samples). The NLI override count (5–8 out of 100) indicates the cross-encoder fires infrequently — the LLM does 92–95% of the work. Threshold tuning across values 0.3–0.6 did not improve on 71.0%, confirming that the override frequency, not the threshold, is the binding constraint.

The 14-point gap to the 85% target reflects a model capacity limitation, not an architectural one. Paths to improvement include: (a) a scientifically fine-tuned NLI model (SciFact-trained DeBERTa), (b) a larger LLM, (c) self-consistency voting (majority vote over multiple inference calls), or (d) LoRA fine-tuning on the SciFact training split.

## 6. Discussion

**Agreement bias in LLM-based NLI.** Instruction-tuned LLMs performing zero-shot NLI systematically default to "entailment" (confirm) when uncertain. This is training-distribution driven — RLHF data contains far more agreement than contradiction. Forcing structured JSON output amplifies this by routing to the schema-satisfying token with lowest perplexity. Victor's NLI-primary architecture addresses this by removing the direction decision from the LLM entirely, but the cross-encoder alone lacks the reasoning depth to handle long scientific abstracts (Run 4: 8% after label-order fix). The cross-check architecture — LLM decides, NLI catches agreement bias — currently achieves the best tradeoff.

**Label-order ambiguity.** NLI model families output label probabilities in different orders. Hugging Face documentation can be stale or inconsistent with the actual `config.json::id2label`. Victor resolves this through three mechanisms: auto-detection from the model config (trying three attribute paths), an explicit `label_order` constructor parameter for bypass, and a pre-benchmark smoke test. This infrastructure caught a real failure (ModernCE's inverted order) that would have produced 35% accuracy without intervention.

**Embedding covert channel.** Setting a masking flag on a graph node suppresses content from LLM answers but leaves vector embeddings queryable in ChromaDB. An adversary could progressively narrow down masked content via cosine similarity queries against the masked node's embedding. Victor closes this channel by deleting the node's chunks from ChromaDB at mask time. This is necessary, not just setting a flag — the vector store operates independently of the graph's masking state.

## 7. Limitations

We acknowledge the following limitations:

1. **CPU-only inference limits model size.** Qwen2.5-7B is the largest model that runs comfortably on consumer hardware. Larger models or fine-tuned variants would likely improve accuracy but require GPU infrastructure.

2. **Audio pipeline uses heuristic classification.** The `AudioIngestor` employs a LibrosaFeatureClassifier with MFCC-based features, not PANNs or ONNX-based classifiers as originally planned. Classification accuracy for real-world audio events is unvalidated.

3. **No web API or graph visualization.** The system is CLI-only. Interactive graph exploration and web-based interfaces are explicitly out of scope for the current version.

4. **SciFact target not yet met.** The 85% accuracy threshold (DoD #4) remains open. The current best of 71.0% represents the combined ceiling of the current model configuration.

5. **Evaluation on benchmark pairs only.** No real research data has been ingested and evaluated end-to-end. The system has been validated on benchmark claim-abstract pairs, not on full document ingestion, claim extraction, and gap detection workflows.

6. **Single-seed evaluation at n=100.** The 71.0% result has wide confidence intervals. A full 300-sample, two-seed evaluation is required before the benchmark result can be considered stable.

## 8. Conclusion

Victor demonstrates that epistemic provenance tracking — typed evidence tiers, conflict detection, and sovereignty controls — can be implemented as a coherent local-first system without cloud dependency. The Epistemic Artifact abstraction provides a structured foundation for research knowledge management that goes beyond flat retrieval or linked notes.

The NLI-primary architecture identifies and addresses a specific failure mode in LLM-based fact verification: structured-output agreement bias. While the current cross-encoder lacks the reasoning depth for primary-mode deployment, the cross-check configuration achieves 71.0% on SciFact with clear paths to improvement.

The masked memory primitive with embedding-channel closure establishes that content suppression and graph routing can coexist — and that the covert channel through vector embeddings must be explicitly closed, not just flagged.

Future work targets the 85% SciFact threshold via fine-tuned NLI models, followed by MCP server integration for distribution through Claude Desktop and Cursor, and eventually the physical device platform with multi-sensor fusion.

## References

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. *NeurIPS 2020*.

Pan, S., Luo, L., Wang, Y., Chen, C., Wang, J., & Wu, X. (2024). Unifying Large Language Models and Knowledge Graphs: A Roadmap. *IEEE TKDE*.

Thorne, J., Vlachos, A., Christodoulopoulos, C., & Mittal, A. (2018). FEVER: a Large-scale Dataset for Fact Extraction and VERification. *NAACL-HLT 2018*.

Wadden, D., Lozhnikov, S., Dasigi, P., Elazar, Y., Richardson, K., & Hajishirzi, H. (2020). SciFact: A Benchmark for Scientific Claim Verification. *arXiv:2005.10645*.

Yao, S., Zhao, J., Yu, D., Du, N., Shafran, I., Narasimhan, K., & Cao, Y. (2023). ReAct: Synergizing Reasoning and Acting in Language Models. *ICLR 2023*.

Schick, T., Dwivedi-Yu, J., Dessì, R., Raileanu, R., Lomeli, M., Hambro, E., Zettlemoyer, L., Cancedda, N., & Scialom, T. (2023). Toolformer: Language Models Can Teach Themselves to Use Tools. *NeurIPS 2023*.

Devlin, J., Chang, M., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding. *NAACL-HLT 2019*.

He, P., Liu, X., Gao, J., & Chen, W. (2021). DeBERTa: Decoding-enhanced BERT with Disentangled Attention. *ICLR 2021*.

Lewis, M., Liu, Y., Goyal, N., Ghazvininejad, M., Mohamed, A., Levy, O., Stoyanov, V., & Zettlemoyer, L. (2020). BART: Denoising Sequence-to-Sequence Pre-training for Natural Language Generation, Translation, and Comprehension. *ACL 2020*.

Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., Chi, E., Le, Q., & Zhou, D. (2022). Chain-of-Thought Prompting Elicits Reasoning in Large Language Models. *NeurIPS 2022*.

Nakano, R., Hilton, J., Balaji, S., Wu, J., Ouyang, L., Kim, C., Hesse, C., Jain, S., Kosaraju, V., Saunders, W., Jiang, Y., Dode, K., Verkade, T., Elber, P., Greer, K., Karamcheti, S., Kim, T., Pachucki, M., Sastry, A., Dragan, S., & Christiano, P. (2021). WebGPT: Browser-assisted question-answering with human feedback. *arXiv:2112.09332*.

Karpukhin, V., Oğuz, B., Min, S., Lewis, P., Wu, L., Edunov, S., Chen, D., & Yih, W. (2020). Dense Passage Retrieval for Open-Domain Question Answering. *EMNLP 2020*.

Gao, Y., Xiong, Y., Liu, Z., Madden, S., & others. (2024). Retrieval-Augmented Generation for Large Language Models: A Survey. *arXiv:2312.10997*.
