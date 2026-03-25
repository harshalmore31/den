"""Tests for Den memory system."""

import os
import tempfile

import pytest

from den.memory.config import DenMemoryConfig
from den.memory.manager import MemoryManager
from den.memory.store import MemoryStore


@pytest.fixture
def tmp_db():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield os.path.join(tmpdir, "test_memory.db")


@pytest.fixture
def config(tmp_db):
    return DenMemoryConfig(db_path=tmp_db, use_fastembed=False)


@pytest.fixture
def store(config):
    s = MemoryStore(config)
    yield s
    s.close()


@pytest.fixture
def manager(config):
    m = MemoryManager(config)
    yield m
    m.close()


class TestMemoryStore:
    def test_add_and_get(self, store):
        mid = store.add("Python is a programming language", category="fact")
        assert mid is not None
        mem = store.get(mid)
        assert mem is not None
        assert mem["content"] == "Python is a programming language"
        assert mem["category"] == "fact"

    def test_count(self, store):
        assert store.count() == 0
        store.add("fact one")
        store.add("fact two")
        assert store.count() == 2

    def test_search_text(self, store):
        store.add("Python is great for AI")
        store.add("JavaScript runs in browsers")
        results = store.search_text("Python")
        assert len(results) == 1
        assert "Python" in results[0]["content"]

    def test_delete(self, store):
        mid = store.add("temporary memory")
        assert store.count() == 1
        store.delete(mid)
        assert store.count() == 0

    def test_supersede(self, store):
        old_id = store.add("The API uses v1")
        new_id = store.add("The API uses v2")
        store.supersede(old_id, new_id)
        old = store.get(old_id)
        assert old["superseded_by"] == new_id

    def test_task_history(self, store):
        tid = store.add_task_record(
            "weekly-report", "SUCCESS", iterations=2, summary="Generated report"
        )
        history = store.get_task_history("weekly-report")
        assert len(history) == 1
        assert history[0]["status"] == "SUCCESS"
        assert history[0]["iterations"] == 2

    def test_stats(self, store):
        store.add("fact one", category="fact")
        store.add("preference one", category="preference")
        stats = store.stats()
        assert stats["total"] == 2
        assert "fact" in stats["by_category"]

    def test_graph_edges(self, store):
        id1 = store.add("memory one")
        id2 = store.add("memory two")
        store.add_edge(id1, id2, 0.8)
        neighbors = store.get_neighbors(id1)
        assert len(neighbors) == 1
        assert neighbors[0][0] == id2


class TestMemoryManager:
    def test_remember_stores(self, manager):
        result = manager.remember("Den is a sandbox runtime for AI agents")
        assert result["action"] == "stored"
        assert "memory_id" in result

    def test_remember_filters_short(self, manager):
        result = manager.remember("hi")
        assert result["action"] == "filtered"
        assert result["reason"] == "too short"

    def test_remember_handles_duplicate(self, manager):
        manager.remember("Den uses Docker for isolation")
        result = manager.remember("Den uses Docker for isolation")
        # Near-duplicate: strengthens existing memory instead of re-storing
        assert result["action"] in ("filtered", "strengthened")

    def test_recall_semantic(self, manager):
        manager.remember("Python is used for machine learning", category="fact")
        manager.remember("JavaScript is used for web development", category="fact")
        results = manager.recall("AI and machine learning")
        assert len(results) > 0
        # Python/ML memory should be more relevant
        assert "machine learning" in results[0]["content"].lower() or \
               "python" in results[0]["content"].lower()

    def test_recall_empty(self, manager):
        results = manager.recall("anything")
        assert results == []

    def test_force_store(self, manager):
        manager.remember("same thing")
        result = manager.remember("same thing", force=True)
        assert result["action"] == "stored"

    def test_task_recording(self, manager):
        tid = manager.record_task("test-task", "SUCCESS", iterations=3, summary="Done")
        assert tid is not None

    def test_recall_for_task(self, manager):
        manager.remember("Market analysis requires Reuters data", source_task="weekly-report")
        manager.record_task("weekly-report", "SUCCESS", summary="Generated report")
        results = manager.recall_for_task("weekly-report", "Generate a market report")
        assert len(results) > 0

    def test_stats(self, manager):
        manager.remember("A fact about something interesting")
        stats = manager.get_stats()
        assert stats["total"] >= 1
