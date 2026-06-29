"""
VictorVectorStore — ChromaDB persistent vector store.

SECURITY NOTE — Embedding covert channel:
  Implemented Option A (2026-06-28): when a node is masked, its embedding
  chunks are deleted from ChromaDB via delete_node_chunks(), called from
  core.py mask(). This closes the membership-inference attack vector —
  masked node embeddings are no longer queryable by cosine similarity.
  On unmask, the node's content should be re-embedded and re-inserted.

  See VICTOR_WHAT_IS_BUILT.md security notes for full discussion.
"""
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

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
        """
        Delete all vector chunks for a given source document.
        Delegates to delete_node_chunks() for consistent error handling.
        """
        self.delete_node_chunks(source_id)

    def delete_node_chunks(self, node_id: str) -> int:
        """
        Delete all vector chunks whose source_id matches node_id.
        Called when a node is masked to close the embedding covert channel —
        masked node embeddings must not remain queryable.

        Returns the count of deleted items (0 if none matched).
        Handles exceptions gracefully so a ChromaDB failure never breaks
        the mask operation.
        """
        try:
            self._init()
            existing = self._collection.get(
                where={"source_id": node_id},
                include=[],
            )
            n_items = len(existing.get("ids", []))
            if n_items > 0:
                self._collection.delete(where={"source_id": node_id})
            return n_items
        except Exception as exc:
            logger.warning("Failed to delete chunks for node %s: %s", node_id, exc)
            return 0

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
