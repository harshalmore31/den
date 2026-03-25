"""Zero-LLM memory classification using anchor embeddings."""

from __future__ import annotations

import numpy as np

from den.memory.config import DenMemoryConfig


class AnchorClassifier:
    """Classify text into categories by cosine similarity to anchor centroids."""

    def __init__(self, config: DenMemoryConfig | None = None):
        self.config = config or DenMemoryConfig()
        self._centroids: dict[str, np.ndarray] = {}
        self._initialized = False

    def initialize(self, embed_fn) -> None:
        """Compute anchor centroids from config examples."""
        for category, examples in self.config.anchors.items():
            vecs = [embed_fn(t) for t in examples]
            centroid = np.mean(vecs, axis=0)
            norm = float(np.linalg.norm(centroid))
            if norm > 1e-9:
                centroid = centroid / norm
            self._centroids[category] = centroid
        self._initialized = True

    def classify(self, embedding: np.ndarray) -> tuple[str, float]:
        """Classify an embedding. Returns (category_name, confidence_score)."""
        if not self._initialized:
            return "fact", 0.0

        best_cat = "fact"
        best_score = -1.0

        for cat, centroid in self._centroids.items():
            score = float(np.dot(embedding, centroid))
            if score > best_score:
                best_score = score
                best_cat = cat

        return best_cat, max(best_score, 0.0)
