"""Embedding service -- local vectors with fastembed or TF-IDF fallback."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np

from den.memory.config import DenMemoryConfig


class EmbeddingService:
    """Compute text embeddings locally. Uses fastembed if available, else TF-IDF."""

    def __init__(self, config: DenMemoryConfig | None = None):
        self.config = config or DenMemoryConfig()
        self._model = None
        self._cache: dict[str, np.ndarray] = {}
        self._use_fastembed = self.config.use_fastembed

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text string. Returns (dim,) unit-normalized vector."""
        key = hashlib.md5(text.encode()).hexdigest()
        if key in self._cache:
            return self._cache[key]
        vec = self._compute_batch([text])[0]
        self._cache[key] = vec
        return vec

    def embed_batch(self, texts: list[str]) -> list[np.ndarray]:
        """Embed multiple texts. Uses cache for duplicates."""
        results: list[np.ndarray | None] = []
        uncached_texts = []
        uncached_indices = []

        for i, t in enumerate(texts):
            key = hashlib.md5(t.encode()).hexdigest()
            if key in self._cache:
                results.append(self._cache[key])
            else:
                results.append(None)
                uncached_texts.append(t)
                uncached_indices.append(i)

        if uncached_texts:
            vecs = self._compute_batch(uncached_texts)
            for idx, vec in zip(uncached_indices, vecs):
                key = hashlib.md5(texts[idx].encode()).hexdigest()
                self._cache[key] = vec
                results[idx] = vec

        return results  # type: ignore[return-value]

    @staticmethod
    def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        dot = float(np.dot(a, b))
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na < 1e-9 or nb < 1e-9:
            return 0.0
        return dot / (na * nb)

    @staticmethod
    def cosine_similarity_matrix(query: np.ndarray, keys: np.ndarray) -> np.ndarray:
        """Cosine similarity of query against each row in keys."""
        if keys.shape[0] == 0:
            return np.array([])
        norms = np.linalg.norm(keys, axis=1)
        norms = np.maximum(norms, 1e-9)
        qnorm = max(float(np.linalg.norm(query)), 1e-9)
        return (keys @ query) / (norms * qnorm)

    @property
    def dim(self) -> int:
        return self.config.embedding_dim

    def _compute_batch(self, texts: list[str]) -> list[np.ndarray]:
        if self._use_fastembed:
            return self._fastembed_batch(texts)
        return self._tfidf_batch(texts)

    def _get_model(self):
        if self._model is None:
            try:
                from fastembed import TextEmbedding

                cache_dir = "/den/memory/.embeddings_cache"
                try:
                    self._model = TextEmbedding(
                        model_name=self.config.embedding_model,
                        cache_dir=cache_dir,
                    )
                except Exception:
                    import os
                    os.environ.pop("HF_HUB_OFFLINE", None)
                    self._model = TextEmbedding(
                        model_name=self.config.embedding_model,
                        cache_dir=cache_dir,
                    )
                self._use_fastembed = True
            except (ImportError, Exception):
                self._use_fastembed = False
                self._model = "tfidf"
        return self._model

    def _fastembed_batch(self, texts: list[str]) -> list[np.ndarray]:
        model = self._get_model()
        if model == "tfidf":
            return self._tfidf_batch(texts)
        embeddings = list(model.embed(texts))
        return [self._normalize(np.array(e, dtype=np.float32)) for e in embeddings]

    def _tfidf_batch(self, texts: list[str]) -> list[np.ndarray]:
        """TF-IDF fallback using numpy with hashing trick."""
        dim = self.config.embedding_dim
        results = []
        for text in texts:
            tokens = self._tokenize(text)
            if not tokens:
                results.append(np.zeros(dim, dtype=np.float32))
                continue
            tf = Counter(tokens)
            vec = np.zeros(dim, dtype=np.float32)
            for token, count in tf.items():
                h = int(hashlib.md5(token.encode()).hexdigest(), 16)
                idx = h % dim
                sign = 1.0 if (h // dim) % 2 == 0 else -1.0
                vec[idx] += sign * (1.0 + math.log(count))
            results.append(self._normalize(vec))
        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower().strip()
        tokens = re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text)
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "to", "of", "in", "for", "on", "with", "at", "by", "it", "this",
            "that", "and", "or", "but", "not", "no", "do", "does", "did",
            "has", "have", "had", "will", "would", "can", "could", "should",
        }
        return [t for t in tokens if len(t) > 1 and t not in stop]

    @staticmethod
    def _normalize(v: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(v))
        if norm < 1e-9:
            return v
        return v / norm
