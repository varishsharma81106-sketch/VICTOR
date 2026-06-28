"""
TextChunker — word-based sliding window.

chunk_size=300 words, overlap=50 words ensures a 30-page paper
becomes ~50 retrievable chunks rather than 1 truncated blob.
"""
from typing import List
from .models import TextChunk


class TextChunker:
    def __init__(self, chunk_size: int = 300, overlap: int = 50):
        self.chunk_size = max(chunk_size, 50)
        self.overlap    = min(overlap, chunk_size // 2)

    def chunk(
        self,
        text:         str,
        source_id:    str,
        source_type:  str,
        source_title: str,
        extra_metadata: dict | None = None,
    ) -> List[TextChunk]:
        words  = text.split()
        chunks = []
        start  = 0
        idx    = 0

        while start < len(words):
            end        = start + self.chunk_size
            chunk_text = " ".join(words[start:end])

            if chunk_text.strip():
                chunks.append(TextChunk(
                    text         = chunk_text,
                    source_id    = source_id,
                    source_type  = source_type,
                    source_title = source_title,
                    chunk_index  = idx,
                    word_start   = start,
                    word_end     = min(end, len(words)),
                    metadata     = extra_metadata or {},
                ))
                idx += 1

            start += self.chunk_size - self.overlap
            if start == 0:
                break

        return chunks

    @staticmethod
    def word_count(text: str) -> int:
        return len(text.split())
