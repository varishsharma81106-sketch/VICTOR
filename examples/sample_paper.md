# Retrieval-Augmented Generation with Agentic Query Decomposition

## Abstract

We evaluate an agentic retrieval strategy that decomposes complex research queries into sub-queries, executes each against a vector knowledge base, and synthesizes results before final answer generation. The approach is tested against a single-pass retrieval baseline using two open-source language models.

## Experiment Setup

The evaluation was conducted on the SciFact validation set, comprising 200 evidence-seeking queries. Each query requires identifying supporting or refuting evidence from a corpus of 5,000 scientific abstracts. We compare two retrieval approaches:

- **Baseline**: Single-pass dense retrieval using nomic-embed-text-v1.5 embeddings with top-8 cosine similarity selection.
- **Agentic**: A multi-step agent that decomposes the query into 2-3 sub-queries, retrieves evidence for each, re-ranks results using cross-encoder scoring, and selects the top-10 chunks for final generation.

Both approaches feed retrieved context into a local language model (Qwen2.5-7B, Q4_K_M quantization) for answer generation.

## Results

The agentic approach improved Precision@5 from 0.62 to 0.78 (+16 points) and Recall@10 from 0.45 to 0.68 (+23 points). Mean Reciprocal Rank (MRR) increased from 0.55 to 0.72. The gains were most pronounced on multi-hop queries requiring evidence from two or more documents, where the baseline frequently missed critical supporting passages.

Notably, the agentic approach incurred approximately 3x higher latency per query (1.8s vs 0.6s) and required an average of 2.4 LLM calls per query compared to 1.0 for the baseline. However, the improvement in factual accuracy substantially outweighed the latency cost for research-assistant use cases where correctness matters more than speed.

## Conclusion

Agentic query decomposition with iterative retrieval significantly outperforms single-pass dense retrieval on evidence-seeking tasks. The approach is particularly effective for complex, multi-faceted queries. Future work will explore caching sub-query results and parallelizing retrieval steps to reduce latency.