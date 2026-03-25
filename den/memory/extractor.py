"""Equation-based fact extractor -- no LLM calls.

Uses category prominence, entropy gating, and declarative signal
to extract memorable facts from user input.
"""

from __future__ import annotations

import math
import re

import numpy as np

from den.memory.config import DenMemoryConfig
from den.memory.embeddings import EmbeddingService

_FIRST_PERSON = re.compile(r"^(?:i|my|we|our|i'm|i've|i'd|i'll)\b", re.I)
_COPULA = re.compile(r"\b(?:is|are|was|were|am)\b", re.I)
_POSSESSIVE = re.compile(r"\b(?:'s|name|boss|friend|brother|sister|partner|team)\b", re.I)
_QUESTION_START = re.compile(r"^(?:what|how|why|when|where|who|which|can|could|would|should|do|does|did|is|are|will)\b", re.I)
_IMPERATIVE_START = re.compile(r"^(?:please|help|show|tell|read|write|edit|delete|run|execute|search|find|list|create|make|fix|check|open|close|get|set|add|remove|install|update|start|stop|build)\b", re.I)


def _declarative_signal(sentence: str) -> float:
    """Compute how likely a sentence is a declarative statement (0-1)."""
    s = sentence.strip()
    sl = s.lower()
    score = 0.0

    if _FIRST_PERSON.search(sl): score += 2.0
    if _COPULA.search(sl): score += 1.0
    if _POSSESSIVE.search(sl): score += 1.0
    if len(s) > 15: score += 0.5

    if _QUESTION_START.match(sl): score -= 3.0
    if _IMPERATIVE_START.match(sl): score -= 3.0
    if s.endswith("?"): score -= 2.0
    if len(s) < 10: score -= 1.0

    return 1.0 / (1.0 + math.exp(-(score - 1.0)))


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r'(?<=[.!?])\s+|(?<=\n)', text)
    result = []
    for part in parts:
        if len(part) > 150:
            result.extend(re.split(r'[;]\s*', part))
        else:
            result.append(part)
    return [s.strip() for s in result if s.strip()]


class FactExtractor:
    """Extract memorable facts using classifier confidence, entropy, and declarative signal."""

    def __init__(self, config: DenMemoryConfig | None = None,
                 embedder: EmbeddingService | None = None):
        self.config = config or DenMemoryConfig()
        self.embedder = embedder or EmbeddingService(self.config)
        self._centroids: dict[str, np.ndarray] = {}
        self._n_categories = 0
        self._max_entropy = 1.0
        self._initialized = False
        self.temperature = 5.0
        self.declarative_lambda = 0.3
        self.theta_extract = 0.15

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        for category, examples in self.config.anchors.items():
            vecs = self.embedder.embed_batch(examples)
            centroid = np.mean(vecs, axis=0)
            norm = float(np.linalg.norm(centroid))
            if norm > 1e-9:
                centroid /= norm
            self._centroids[category] = centroid
        self._n_categories = len(self._centroids)
        self._max_entropy = math.log(self._n_categories) if self._n_categories > 1 else 1.0
        self._initialized = True

    def extract(self, user_input: str) -> list[dict]:
        """Extract memorable facts. Returns list of {content, category, confidence}."""
        self._ensure_initialized()
        text = user_input.strip()
        if len(text) < 8:
            return []

        sentences = _split_sentences(text)
        facts = []

        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) < 8:
                continue

            category, score = self._score_sentence(sentence)
            if category and score >= self.theta_extract:
                clean = sentence.strip().rstrip(".")
                if len(clean) >= 8:
                    facts.append({
                        "content": clean,
                        "category": category,
                        "confidence": round(score, 4),
                    })

        return facts

    def _score_sentence(self, sentence: str) -> tuple[str | None, float]:
        if not self._centroids:
            return None, 0.0

        emb = self.embedder.embed(sentence)
        categories = list(self._centroids.keys())
        scores = np.array([float(np.dot(emb, self._centroids[cat])) for cat in categories])

        best_idx = int(np.argmax(scores))
        best_category = categories[best_idx]

        mu = float(np.mean(scores))
        sigma = float(np.std(scores))
        prominence = (float(scores[best_idx]) - mu) / (sigma + 1e-8)

        scaled = scores * self.temperature
        scaled -= np.max(scaled)
        exp_scores = np.exp(scaled)
        probs = exp_scores / np.sum(exp_scores)
        entropy = -float(np.sum(probs * np.log(probs + 1e-10)))
        entropy_norm = entropy / self._max_entropy

        prominence_gate = 1.0 / (1.0 + math.exp(-(prominence - 0.5)))
        semantic_score = prominence_gate * (1.0 - entropy_norm)

        delta = _declarative_signal(sentence)
        declarative_score = delta * self.declarative_lambda

        return best_category, max(semantic_score, declarative_score)
