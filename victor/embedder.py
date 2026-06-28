"""
LocalEmbedder — wraps sentence-transformers.
Everything runs offline; no API calls beyond the one-time model download
(handled by sentence-transformers/huggingface_hub itself, cached locally
after first use).

v4.3: accepts a fallback chain. If `model_name` can't be loaded (no network
on first run, model name typo, out of memory on a small device), tries each
entry in `fallback_models` in order before giving up. This is what makes the
nomic-embed-text-v1.5 default (DoD item #6) safe to ship — a machine with no
internet access still gets a working embedder via the all-MiniLM-L6-v2 fallback,
which sentence-transformers ships pre-cached in most installs.
"""
from typing import List, Optional, Sequence
import numpy as np


class LocalEmbedder:
    def __init__(
        self,
        model_name: str = "nomic-embed-text-v1.5",
        fallback_models: Optional[Sequence[str]] = ("all-MiniLM-L6-v2",),
    ):
        self.model_name      = model_name
        self.fallback_models = list(fallback_models or [])
        self._model          = None
        self._active_model   = None   # which name actually loaded, for introspection

    def _load(self):
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        last_exc: Optional[Exception] = None
        for candidate in [self.model_name, *self.fallback_models]:
            try:
                kwargs = {}
                # nomic models require trust_remote_code for their custom
                # pooling/rotary implementation; harmless to pass for others.
                if "nomic" in candidate.lower():
                    kwargs["trust_remote_code"] = True
                self._model = SentenceTransformer(candidate, **kwargs)
                self._active_model = candidate
                return
            except Exception as exc:
                last_exc = exc
                continue

        raise RuntimeError(
            f"LocalEmbedder: could not load '{self.model_name}' or any fallback "
            f"{self.fallback_models}. Last error: {last_exc}"
        )

    def embed(self, text: str) -> List[float]:
        self._load()
        vec = self._model.encode(text, normalize_embeddings=True)
        return vec.tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        self._load()
        vecs = self._model.encode(texts, normalize_embeddings=True, batch_size=64)
        return vecs.tolist()

    @staticmethod
    def cosine(a: List[float], b: List[float]) -> float:
        a, b  = np.array(a), np.array(b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0
