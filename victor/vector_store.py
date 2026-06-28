"""
VictorVectorStore — ChromaDB persistent vector store.

SECURITY NOTE — Embedding covert channel (future work, not a current threat):
  When a node is masked, its text embedding is still stored in ChromaDB and
  remains queryable by cosine similarity.  An adversarial model that can issue
  many queries and observe which ones produce high-similarity masked-anchor
  results can progressively narrow down what the masked content says without
  ever reading it directly (standard membership-inference attack on the vector
  store).

  This is NOT a threat in the current single-user, trusted-model deployment.
  It becomes relevant when:
    (a) Victor federates across devices and shares a vector store, or
    (b) an untrusted third-party model is introduced (Phase 5+).

  Fix when needed — Option A (simplest, complete):
    On mask:   delete the node's embedding chunks from ChromaDB
               (self.delete_by_node_id(node_id))
    On unmask: re-embed and re-insert the node's content chunks

  Option B (more flexible): separate public/masked ChromaDB collections;
  retriever queries only the public collection; masked collection queried
  only during explicit unmask operations.

  Add a delete_by_node_id() method here when implementing either option.
  See VICTOR_WHAT_IS_BUILT.md security notes for full discussion.
"""
from typing import List, Dict, Any, Optional
from pathlib import Path

from .models import TextChunk, RetrievedChunk
from .embedder import LocalEmbedder


class VictorVectorStore:
    COLLECTION = "victor_chunks"

    def __init__(self, db_path: Path, embedder: LocalEmbedder):
        self.db_path   = db_path
        self.embedder  = embedder
        self._client     = None
        self._collection = None

    def _init(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(path=str(self.db_path))
            self._collection = self._client.get_or_create_collection(
                name=self.COLLECTION,
                metadata={"hnsw:space": "cosine"},
            )

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_chunks(self, chunks: List[TextChunk]):
        if not chunks:
            return
        self._init()

        texts      = [c.text for c in chunks]
        ids        = [c.chunk_id for c in chunks]
        metadatas  = [c.to_chroma_doc()["metadata"] for c in chunks]
        embeddings = self.embedder.embed_batch(texts)

        self._collection.upsert(
            ids=ids, documents=texts, metadatas=metadatas, embeddings=embeddings,
        )

    # ── Read ──────────────────────────────────────────────────────────────────

    def query(
        self,
        query_text:          str,
        top_k:               int = 8,
        filter_source_type:  Optional[str] = None,
    ) -> List[RetrievedChunk]:
        self._init()
        where = {"source_type": filter_source_type} if filter_source_type else None
        q_emb = self.embedder.embed(query_text)

        results = self._collection.query(
            query_embeddings=[q_emb],
            n_results=min(top_k, self._collection.count() or 1),
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        chunks    = []
        docs      = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(docs, metadatas, distances):
            score = max(0.0, 1.0 - float(dist))
            chunks.append(RetrievedChunk(
                text         = doc,
                source_id    = meta["source_id"],
                source_type  = meta["source_type"],
                source_title = meta["source_title"],
                chunk_index  = int(meta["chunk_index"]),
                score        = round(score, 4),
                provenance   = ["vector search"],
            ))
        return chunks

    def get_by_source(self, source_id: str) -> List[RetrievedChunk]:
        self._init()
        results = self._collection.get(
            where={"source_id": source_id},
            include=["documents", "metadatas"],
        )
        chunks = []
        for doc, meta in zip(results["documents"], results["metadatas"]):
            chunks.append(RetrievedChunk(
                text         = doc,
                source_id    = meta["source_id"],
                source_type  = meta["source_type"],
                source_title = meta["source_title"],
                chunk_index  = int(meta["chunk_index"]),
                score        = 1.0,
                provenance   = ["direct fetch"],
            ))
        return chunks

    def delete_source(self, source_id: str):
        self._init()
        self._collection.delete(where={"source_id": source_id})

    def count(self) -> int:
        self._init()
        return self._collection.count()

    def stats(self) -> Dict[str, Any]:
        self._init()
        total  = self._collection.count()
        counts: Dict[str, int] = {}
        for stype in ["paper", "note", "experiment"]:
            try:
                r = self._collection.get(where={"source_type": stype}, include=[])
                counts[stype] = len(r["ids"])
            except Exception:
                counts[stype] = 0
        return {"total_chunks": total, "by_type": counts}
