"""Den Memory Manager -- the agent's persistent brain."""

from __future__ import annotations

import time
from datetime import datetime

import numpy as np

from den.memory.classifier import AnchorClassifier
from den.memory.config import DenMemoryConfig
from den.memory.embeddings import EmbeddingService
from den.memory.extractor import FactExtractor
from den.memory.store import MemoryStore
from den.utils import sigmoid


class MemoryManager:
    """Den agent's memory -- persistent, semantic, always-on.

    Features: fact extraction, auto-classification, novelty gating,
    contradiction detection, context vector, graph-activated recall,
    response-alignment feedback, and rich prompt injection.
    """

    def __init__(self, config: DenMemoryConfig | None = None):
        self.config = config or DenMemoryConfig()
        self.embedder = EmbeddingService(self.config)
        self.store = MemoryStore(self.config)
        self.classifier = AnchorClassifier(self.config)
        self.extractor = FactExtractor(self.config, self.embedder)

        self._context_vector: np.ndarray | None = None
        self._last_recalled: list[dict] = []

        self.classifier.initialize(self.embedder.embed)

    def close(self) -> None:
        self.store.close()

    def process_conversation(
        self,
        user_input: str,
        ai_output: str = "",
        namespace: str = "global",
        source_task: str = "_conversation",
    ) -> list[dict]:
        """Extract and store memorable facts from a conversation turn."""
        self.update_context(user_input)

        facts = self.extractor.extract(user_input)
        results = []

        for fact in facts:
            result = self.remember(
                content=fact["content"],
                category=fact["category"],
                namespace=namespace,
                source_task=source_task,
                ai_output_text=ai_output,
            )
            results.append(result)

        return results

    def remember(
        self,
        content: str,
        category: str | None = None,
        namespace: str = "global",
        source_task: str = "",
        force: bool = False,
        ai_output_text: str = "",
    ) -> dict:
        """Store a memory if it passes novelty and output-aware gates."""
        content = content.strip()
        if not content or len(content) < 10:
            return {"action": "filtered", "reason": "too short"}

        embedding = self.embedder.embed(content)

        if category is None:
            category, _ = self.classifier.classify(embedding)

        if not force:
            ids, matrix = self.store.get_all_embeddings(namespace=namespace)

            if len(ids) > 0:
                sims = EmbeddingService.cosine_similarity_matrix(embedding, matrix)
                best_idx = int(np.argmax(sims))
                best_sim = float(sims[best_idx])

                # Near-duplicate: strengthen existing instead of re-storing
                if best_sim >= 0.85:
                    self.store.increment_access(ids[best_idx])
                    return {"action": "strengthened", "existing_id": ids[best_idx]}

                # Contradiction detection
                if best_sim >= self.config.contradiction_key_threshold:
                    old_mem = self.store.get(ids[best_idx])
                    if old_mem and old_mem.get("embedding") is not None:
                        value_sim = float(EmbeddingService.cosine_similarity(embedding, old_mem["embedding"]))
                        if value_sim < self.config.contradiction_value_threshold:
                            mid = self.store.add(
                                content, category, namespace, embedding,
                                source_task=source_task,
                            )
                            self.store.supersede(ids[best_idx], mid)
                            return {"action": "superseded", "memory_id": mid,
                                    "superseded_id": ids[best_idx], "category": category}

                # Output-aware gating: penalize if content overlaps with AI output
                output_penalty = 0.0
                if ai_output_text:
                    ai_emb = self.embedder.embed(ai_output_text[:500])
                    output_overlap = float(EmbeddingService.cosine_similarity(embedding, ai_emb))
                    if output_overlap > 0.90:
                        return {"action": "filtered", "reason": "output overlap (AI retrieving, not learning)"}
                    output_penalty = max(0, output_overlap - 0.5) * 0.3

                novelty = 1.0 - best_sim - output_penalty
                gate = sigmoid(self.config.beta_gate * (novelty - self.config.theta_gate))

                if gate < 0.15:
                    self.store.increment_access(ids[best_idx])
                    return {"action": "filtered", "reason": "not novel", "similarity": round(best_sim, 3)}

        importance = self.config.category_importance.get(category, 1.0)
        strength = self.config.initial_strength * importance

        mid = self.store.add(
            content, category, namespace, embedding,
            strength=strength, source_task=source_task,
        )

        self._create_edges(mid, embedding, namespace)
        return {"action": "stored", "memory_id": mid, "category": category}

    def update_context(self, user_input: str) -> None:
        """Update running conversation context vector (EMA of inputs)."""
        emb = self.embedder.embed(user_input)
        lam = 0.7
        if self._context_vector is None:
            self._context_vector = emb.copy()
        else:
            self._context_vector = lam * self._context_vector + (1.0 - lam) * emb
            norm = float(np.linalg.norm(self._context_vector))
            if norm > 1e-9:
                self._context_vector = self._context_vector / norm

    def recall(
        self,
        query: str,
        namespace: str | None = None,
        top_k: int | None = None,
    ) -> list[dict]:
        """Semantic recall with context vector blending and graph activation."""
        top_k = top_k or self.config.top_k
        query_emb = self.embedder.embed(query)

        ids, matrix = self.store.get_all_embeddings(namespace=namespace)
        if len(ids) == 0:
            return []

        effective_query = self._get_effective_query(query_emb, ids, matrix)
        sims = EmbeddingService.cosine_similarity_matrix(effective_query, matrix)

        results = []
        seen_ids = set()
        for i, sim in enumerate(sims):
            if sim >= self.config.min_relevance:
                mem = self.store.get(ids[i])
                if mem:
                    strength = mem.get("strength", 1.0)
                    compressed = strength ** 0.3
                    mem["relevance"] = round(float(sim) * compressed, 3)
                    results.append(mem)
                    seen_ids.add(ids[i])
                    self.store.increment_access(ids[i])

        # Graph activation: spread from top matches to neighbors
        top_seeds = sorted(results, key=lambda m: m["relevance"], reverse=True)[:5]
        for seed in top_seeds:
            seed_id = seed.get("id")
            if not seed_id:
                continue
            neighbors = self.store.get_neighbors(seed_id)
            for neighbor_id, weight in neighbors:
                if neighbor_id in seen_ids:
                    continue
                if weight < 0.2:
                    continue
                mem = self.store.get(neighbor_id)
                if mem:
                    mem["relevance"] = round(seed["relevance"] * weight * 0.3, 3)
                    mem["_via_graph"] = True
                    results.append(mem)
                    seen_ids.add(neighbor_id)

        results.sort(key=lambda m: m["relevance"], reverse=True)
        self._last_recalled = results[:top_k]
        return self._last_recalled

    def _get_effective_query(self, query_emb: np.ndarray, ids: list, matrix: np.ndarray) -> np.ndarray:
        """Blend raw query with context vector based on self-sufficiency."""
        if self._context_vector is None or len(ids) == 0:
            return query_emb

        sims = EmbeddingService.cosine_similarity_matrix(query_emb, matrix)
        sigma_self = float(np.max(sims)) if len(sims) > 0 else 0.0

        alpha = sigmoid(8.0 * (sigma_self - 0.4))
        q_eff = alpha * query_emb + (1.0 - alpha) * self._context_vector
        norm = float(np.linalg.norm(q_eff))
        if norm > 1e-9:
            q_eff = q_eff / norm
        return q_eff

    def recall_for_task(self, task_name: str, task_description: str) -> list[dict]:
        """Recall memories relevant to a specific task."""
        memories = self.recall(task_description, top_k=self.config.top_k)
        history = self.store.get_task_history(task_name, limit=5)
        if history:
            for h in history:
                memories.append({
                    "content": f"[Task History] {h['task_name']}: {h['status']} "
                               f"({h['iterations']} iterations) -- {h['summary']}",
                    "category": "task_result",
                    "relevance": 0.8,
                    "source": "task_history",
                })
        return memories

    def format_for_prompt(self, memories: list[dict], max_tokens: int = 500) -> str:
        """Format recalled memories as rich context for LLM injection."""
        if not memories:
            return ""

        now = time.time()
        lines = [f"[Agent Memory -- {len(memories)} relevant entries, {datetime.now().strftime('%Y-%m-%d %H:%M')}]"]

        char_budget = max_tokens * 4
        chars_used = len(lines[0])

        for mem in memories:
            content = mem.get("content", "")[:200]
            category = mem.get("category", "fact")
            strength = mem.get("strength", 1.0)
            created = mem.get("created_at", 0)
            access_count = mem.get("access_count", 0)
            via_graph = mem.get("_via_graph", False)

            age = ""
            if created:
                age_secs = now - created
                if age_secs < 3600:
                    age = f"{int(age_secs / 60)}m ago"
                elif age_secs < 86400:
                    age = f"{int(age_secs / 3600)}h ago"
                else:
                    age = f"{int(age_secs / 86400)}d ago"

            graph_tag = " [linked]" if via_graph else ""
            line = f"  [{category}] {content} ({age}, strength:{strength:.2f}, used:{access_count}x{graph_tag})"

            if chars_used + len(line) > char_budget:
                break

            lines.append(line)
            chars_used += len(line)

        return "\n".join(lines)

    def feedback_from_response(self, ai_output: str) -> None:
        """After AI responds, strengthen memories it actually used."""
        if not self._last_recalled or not ai_output:
            return

        ai_emb = self.embedder.embed(ai_output[:500])

        for mem in self._last_recalled:
            mem_emb = mem.get("embedding")
            mem_id = mem.get("id")
            if mem_emb is None or mem_id is None:
                continue

            alignment = float(EmbeddingService.cosine_similarity(ai_emb, mem_emb))

            if alignment >= 0.20:
                current_strength = mem.get("strength", 1.0)
                new_strength = min(current_strength + 0.08, 2.0)
                self.store.update_strength(mem_id, new_strength)

    def decay(self) -> None:
        self.store.decay_all()

    def record_task(self, task_name: str, status: str, iterations: int = 0,
                    summary: str = "", phase_data: str = "") -> str:
        return self.store.add_task_record(task_name, status, iterations, summary, phase_data)

    def get_stats(self) -> dict:
        return self.store.stats()

    def _create_edges(self, memory_id: str, embedding: np.ndarray, namespace: str) -> None:
        ids, matrix = self.store.get_all_embeddings(namespace=namespace)
        if len(ids) == 0:
            return
        sims = EmbeddingService.cosine_similarity_matrix(embedding, matrix)
        for i, sim in enumerate(sims):
            if sim >= self.config.edge_threshold and ids[i] != memory_id:
                self.store.add_edge(memory_id, ids[i], float(sim))
