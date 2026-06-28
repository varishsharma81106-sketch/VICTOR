"""
VictorEvaluator — measures retrieval quality.

Eval file format (JSON):
[
  {
    "query": "What was the baseline score?",
    "expected_source": "paper_title_substring",
    "expected_keywords": ["keyword1", "keyword2"]
  }
]

Metrics: precision@k, hit@k, MRR
"""
import json
from pathlib import Path
from typing import List, Dict, Any

from .retrieve import HybridRetriever
from .models import RetrievedChunk


class VictorEvaluator:
    def __init__(self, retriever: HybridRetriever):
        self.retriever = retriever

    def load_queries(self, filepath: Path) -> List[Dict[str, Any]]:
        return json.loads(filepath.read_text())

    def is_relevant(self, chunk: RetrievedChunk, query_item: Dict) -> bool:
        text_lower  = chunk.text.lower()
        title_lower = chunk.source_title.lower()

        expected_source = query_item.get("expected_source", "").lower()
        if expected_source and expected_source not in title_lower:
            if expected_source not in text_lower:
                return False

        keywords = query_item.get("expected_keywords", [])
        if keywords:
            return all(kw.lower() in text_lower for kw in keywords)

        return bool(expected_source)

    def evaluate(self, queries: List[Dict[str, Any]], k: int = 5) -> Dict[str, Any]:
        if not queries:
            return {}

        precisions:       List[float] = []
        reciprocal_ranks: List[float] = []
        hits:             List[int]   = []
        per_query:        List[Dict]  = []

        for item in queries:
            query  = item["query"]
            chunks = self.retriever.retrieve(query)[:k]

            relevant_mask = [self.is_relevant(c, item) for c in chunks]
            n_relevant    = sum(relevant_mask)

            prec = n_relevant / k if k > 0 else 0.0
            precisions.append(prec)
            hits.append(1 if n_relevant > 0 else 0)

            rr = 0.0
            for rank, is_rel in enumerate(relevant_mask, 1):
                if is_rel:
                    rr = 1.0 / rank
                    break
            reciprocal_ranks.append(rr)

            per_query.append({
                "query":       query,
                "precision":   round(prec, 3),
                "hit":         bool(n_relevant),
                "rr":          round(rr, 3),
                "top_sources": [f"{c.source_title} ({c.score:.2f})" for c in chunks],
            })

        n = len(queries)
        return {
            f"precision@{k}": round(sum(precisions) / n, 4),
            f"hit@{k}":       round(sum(hits) / n, 4),
            "MRR":            round(sum(reciprocal_ranks) / n, 4),
            "n_queries":      n,
            "per_query":      per_query,
        }
