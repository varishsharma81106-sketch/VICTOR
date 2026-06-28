"""
Smoke test — exercises the full Victor pipeline end-to-end without needing
network access to download embedding models. LocalEmbedder is monkeypatched
to return small deterministic hash-based vectors instead of real ones; the
LLM runs in mock mode. This validates wiring/control-flow correctness, not
embedding quality or LLM answer quality.
"""
import sys
import hashlib
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from victor.embedder import LocalEmbedder


def _fake_encode(self, text, normalize_embeddings=True, batch_size=64):
    """Deterministic 32-dim fake embedding from a hash of the text."""
    if isinstance(text, str):
        texts = [text]
        single = True
    else:
        texts = list(text)
        single = False
    vecs = []
    for t in texts:
        h = hashlib.sha256(t.encode()).digest()
        v = np.frombuffer(h, dtype=np.uint8).astype(np.float32)[:32]
        v = v / (np.linalg.norm(v) + 1e-8)
        vecs.append(v)
    arr = np.array(vecs)
    return arr[0] if single else arr


class _FakeModel:
    encode = _fake_encode


LocalEmbedder._load = lambda self: setattr(self, "_model", _FakeModel()) if self._model is None else None


# ── In-memory vector store stub (avoids chromadb dependency) ─────────────────
class _FakeCollection:
    def __init__(self, name):
        self.name = name
        self._docs = {}
        self._embeddings = {}
        self._metadatas = {}

    def count(self):
        return len(self._docs)

    def upsert(self, ids, documents, metadatas, embeddings):
        for i, doc_id in enumerate(ids):
            self._docs[doc_id] = documents[i]
            self._embeddings[doc_id] = embeddings[i]
            self._metadatas[doc_id] = metadatas[i]

    def query(self, query_embeddings, n_results, where=None, include=None):
        if not self._docs:
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}
        # Cosine similarity over our fake vectors
        q = np.array(query_embeddings[0])
        scores = {}
        for doc_id, emb in self._embeddings.items():
            d = np.array(emb)
            denom = np.linalg.norm(q) * np.linalg.norm(d)
            sim = float(np.dot(q, d) / denom) if denom > 0 else 0.0
            scores[doc_id] = 1.0 - sim  # distance = 1 - similarity

        sorted_ids = sorted(scores, key=scores.get)[:n_results]
        return {
            "documents": [[self._docs[did] for did in sorted_ids]],
            "metadatas": [[self._metadatas[did] for did in sorted_ids]],
            "distances": [[scores[did] for did in sorted_ids]],
        }

    def get(self, where=None, include=None):
        matched = {}
        for doc_id, meta in self._metadatas.items():
            if where:
                ok = all(meta.get(k) == v for k, v in where.items())
                if not ok:
                    continue
            matched[doc_id] = {"document": self._docs[doc_id], "metadata": meta}
        return {
            "documents": [m["document"] for m in matched.values()],
            "metadatas": [m["metadata"] for m in matched.values()],
            "ids": list(matched.keys()),
        }

    def delete(self, where=None):
        to_remove = []
        for doc_id, meta in self._metadatas.items():
            if where:
                ok = all(meta.get(k) == v for k, v in where.items())
                if ok:
                    to_remove.append(doc_id)
        for doc_id in to_remove:
            self._docs.pop(doc_id, None)
            self._embeddings.pop(doc_id, None)
            self._metadatas.pop(doc_id, None)


class _FakeChromaClient:
    def __init__(self, path):
        self._collections = {}

    def get_or_create_collection(self, name, metadata=None):
        if name not in self._collections:
            self._collections[name] = _FakeCollection(name)
        return self._collections[name]


import victor.vector_store as _vs_module
_vs_module.chromadb = type("FakeChromaDB", (), {
    "PersistentClient": _FakeChromaClient,
})()

# Patch VictorVectorStore._init to use our fake chromadb
_original_vs_init = None

def _patch_vector_store():
    global _original_vs_init
    _original_vs_init = _vs_module.VictorVectorStore._init

    def _fake_init(self):
        if self._client is None:
            self._client = _FakeChromaClient(str(self.db_path))
            self._collection = self._client.get_or_create_collection(
                name="victor_chunks",
                metadata={"hnsw:space": "cosine"},
            )

    _vs_module.VictorVectorStore._init = _fake_init


# ── Also mock sentence_transformers import path ──────────────────────────────
import types
_fake_st = types.ModuleType("sentence_transformers")
_fake_st.SentenceTransformer = lambda *a, **k: _FakeModel()
sys.modules["sentence_transformers"] = _fake_st


def main():
    _patch_vector_store()
    from victor.config import VictorConfig
    from victor.core import Victor

    tmp = tempfile.mkdtemp(prefix="victor_smoke_")
    config = VictorConfig(home_dir=tmp)
    config.use_mock_llm = True

    v = Victor(config=config)
    print("[1] Victor constructed OK. Ingestor extensions registered:",
          sorted(v._ingestors_by_ext.keys()))

    # ── Ingest a markdown note ───────────────────────────────────────────────
    note_path = Path(tmp) / "note.md"
    note_path.write_text(
        "# Catalyst Notes\n\n"
        "The reaction yield improved to 92% under higher temperature.\n"
        "This claim has not yet been tested experimentally.\n"
    )
    r1 = v.ingest_file(note_path)
    print("[2] Ingested note:", r1["type"], r1["n_chunks"], "chunks,", r1["n_claims"], "claims")
    assert r1["type"] == "note"

    # ── Ingest an experiment JSON ────────────────────────────────────────────
    exp_path = Path(tmp) / "exp1.json"
    exp_path.write_text(
        '{"name": "yield_test_1", "description": "Measured yield at 80C",'
        ' "results": {"yield_pct": 91.5},'
        ' "claims_tested": ["The reaction yield improved to 92% under higher temperature"]}'
    )
    r2 = v.ingest_file(exp_path)
    print("[3] Ingested experiment:", r2["type"], r2["n_chunks"], "chunks,",
          len(r2["linked_claims"]), "linked claims")
    assert r2["type"] == "experiment"

    # ── Ask a question (exercises retriever + LLM mock chain) ───────────────
    answer = v.ask_full("What was the yield result?")
    print("[4] ask_full() returned answer, provider:", answer.provider_used)

    # ── Reasoning layer ──────────────────────────────────────────────────────
    gaps = v.gaps()
    print("[5] gaps():", len(gaps), "unconfirmed claims")

    stats = v.stats()
    print("[6] stats():", stats["graph"])

    # ── StatisticsKernel ─────────────────────────────────────────────────────
    from victor.kernels import StatisticsKernel
    sk = StatisticsKernel()
    result = sk.compute([91.5, 92.0, 90.8, 91.2])
    print("[7] StatisticsKernel.compute():", result.outputs)
    assert "mean" in result.outputs and "ci_low" in result.outputs

    # ── Node deduplication ───────────────────────────────────────────────────
    # (placeholder — NodeDeduplicator not yet in codebase, skip gracefully)
    print("[8] Node deduplication — placeholder (module not yet in codebase)")

    # ── Faithfulness scoring ─────────────────────────────────────────────────
    # (placeholder — score_faithfulness not yet in evaluate.py, skip gracefully)
    print("[9] score_faithfulness — placeholder (not yet in evaluate.py)")

    print("\nALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()
