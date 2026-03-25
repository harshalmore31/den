"""Tests for the Den Loop Engine."""

import os
import tempfile

import pytest

from den.agentfile.schema import (
    EvaluationConfig,
    LoopConfig,
    PhaseConfig,
    TaskConfig,
    QuestionConfig,
)
from den.core.loop_engine import (
    LoopEngine,
    LoopResult,
    LoopStatus,
    TaskResult,
)
from den.memory.config import DenMemoryConfig
from den.memory.manager import MemoryManager


# ---------------------------------------------------------------------------
# Mock agent executor
# ---------------------------------------------------------------------------


class MockAgentExecutor:
    """Simulates an agent that produces configurable outputs."""

    def __init__(self, outputs: list[dict] | None = None):
        self.outputs = outputs or []
        self.call_count = 0

    def execute(self, context: dict) -> dict:
        idx = min(self.call_count, len(self.outputs) - 1)
        self.call_count += 1
        if idx < 0 or not self.outputs:
            return {"output_text": "", "output_files": []}
        return self.outputs[idx]


class FailingAgentExecutor:
    """Agent that raises exceptions."""

    def execute(self, context: dict) -> dict:
        raise RuntimeError("Agent crashed!")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        ws = os.path.join(tmpdir, "workspace")
        out = os.path.join(tmpdir, "output")
        os.makedirs(ws)
        os.makedirs(out)
        yield ws, out


@pytest.fixture
def memory():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = DenMemoryConfig(db_path=os.path.join(tmpdir, "mem.db"), use_fastembed=False)
        mgr = MemoryManager(config)
        yield mgr
        mgr.close()


# ---------------------------------------------------------------------------
# Single-phase loop tests
# ---------------------------------------------------------------------------


class TestSinglePhaseLoop:
    def test_passes_on_first_iteration(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "A detailed report. " * 50 + "\nhttps://example.com", "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="test-task",
            task_description="Write a report.",
            loop_config=LoopConfig(
                max_iterations=3,
                evaluation=EvaluationConfig(
                    method="algorithmic",
                    algorithmic_checks=[
                        {"name": "wc", "type": "min_word_count", "min_words": 50, "required": True},
                    ],
                ),
                cooldown="0s",
            ),
        )

        assert result.passed
        assert result.status == LoopStatus.SUCCESS
        assert result.iterations == 1

    def test_retries_and_passes(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            # Iteration 1: too short
            {"output_text": "Short.", "output_files": []},
            # Iteration 2: long enough
            {"output_text": "A much more detailed report with many words. " * 20, "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="retry-task",
            task_description="Write a report.",
            loop_config=LoopConfig(
                max_iterations=3,
                evaluation=EvaluationConfig(
                    method="algorithmic",
                    algorithmic_checks=[
                        {"name": "wc", "type": "min_word_count", "min_words": 50, "required": True},
                    ],
                ),
                cooldown="0s",
            ),
        )

        assert result.passed
        assert result.iterations == 2
        assert len(result.iteration_records) == 2

    def test_exhausts_iterations(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "Short.", "output_files": []},
            {"output_text": "Still short.", "output_files": []},
            {"output_text": "Nope.", "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="fail-task",
            task_description="Write a long report.",
            loop_config=LoopConfig(
                max_iterations=3,
                evaluation=EvaluationConfig(
                    method="algorithmic",
                    algorithmic_checks=[
                        {"name": "wc", "type": "min_word_count", "min_words": 1000, "required": True},
                    ],
                ),
                cooldown="0s",
            ),
        )

        assert not result.passed
        assert result.status == LoopStatus.EXHAUSTED
        assert result.iterations == 3

    def test_handles_agent_crash(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = FailingAgentExecutor()
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="crash-task",
            task_description="Do something.",
            loop_config=LoopConfig(max_iterations=2, cooldown="0s"),
        )

        assert not result.passed
        assert result.iterations == 2
        assert "error" in result.iteration_records[0].feedback.lower()

    def test_writes_progress_json(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "Enough words here for the check. " * 20, "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        engine.run_loop(
            task_name="progress-task",
            task_description="Test progress tracking.",
            loop_config=LoopConfig(
                max_iterations=2,
                evaluation=EvaluationConfig(
                    method="algorithmic",
                    algorithmic_checks=[
                        {"name": "wc", "type": "min_word_count", "min_words": 10, "required": True},
                    ],
                ),
                cooldown="0s",
            ),
        )

        # Check progress.json was written
        progress_path = os.path.join(ws, "tasks", "progress-task", "progress.json")
        assert os.path.exists(progress_path)

        import json
        with open(progress_path) as f:
            progress = json.load(f)
        assert progress["status"] == "passed"
        assert progress["current_iteration"] == 1


# ---------------------------------------------------------------------------
# Memory integration
# ---------------------------------------------------------------------------


class TestLoopWithMemory:
    def test_records_success(self, tmp_workspace, memory):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "Great detailed report. " * 20, "output_files": []},
        ])
        engine = LoopEngine(agent, memory=memory, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="mem-task",
            task_description="Generate a report.",
            loop_config=LoopConfig(
                max_iterations=2,
                evaluation=EvaluationConfig(
                    method="algorithmic",
                    algorithmic_checks=[
                        {"name": "wc", "type": "min_word_count", "min_words": 10, "required": True},
                    ],
                ),
                cooldown="0s",
            ),
        )

        assert result.passed
        # Memory should have a "learned" entry
        memories = memory.store.get_all()
        learned = [m for m in memories if m["category"] == "learned"]
        assert len(learned) >= 1
        assert "succeeded" in learned[0]["content"].lower()

    def test_records_failure(self, tmp_workspace, memory):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "Short.", "output_files": []},
        ])
        engine = LoopEngine(agent, memory=memory, workspace=ws, output_dir=out)

        engine.run_loop(
            task_name="fail-mem-task",
            task_description="Write something long.",
            loop_config=LoopConfig(
                max_iterations=1,
                evaluation=EvaluationConfig(
                    method="algorithmic",
                    algorithmic_checks=[
                        {"name": "wc", "type": "min_word_count", "min_words": 1000, "required": True},
                    ],
                ),
                cooldown="0s",
            ),
        )

        memories = memory.store.get_all()
        errors = [m for m in memories if m["category"] == "error"]
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Multi-phase task
# ---------------------------------------------------------------------------


class TestMultiPhaseTask:
    def test_two_phase_task(self, tmp_workspace, memory):
        ws, out = tmp_workspace
        call_count = {"n": 0}

        class TwoPhaseAgent:
            def execute(self, context):
                call_count["n"] += 1
                if "discovery" in context.get("task_name", ""):
                    return {
                        "output_text": "Research findings: competitors include E2B and Modal. "
                                       "See https://e2b.dev and https://modal.com for details. " * 5,
                        "output_files": [],
                    }
                else:
                    return {
                        "output_text": "Implementation complete with all the features. " * 20,
                        "output_files": [],
                    }

        engine = LoopEngine(TwoPhaseAgent(), memory=memory, workspace=ws, output_dir=out)

        task = TaskConfig(
            description="Build a feature.",
            phases=[
                PhaseConfig(
                    name="discovery",
                    type="research",
                    evaluation=EvaluationConfig(
                        method="algorithmic",
                        algorithmic_checks=[
                            {"name": "wc", "type": "min_word_count", "min_words": 20, "required": True},
                            {"name": "src", "type": "sources_present", "min_count": 1, "required": True},
                        ],
                    ),
                    max_iterations=2,
                    cooldown="0s",
                ),
                PhaseConfig(
                    name="implementation",
                    type="execution",
                    input_from="discovery",
                    evaluation=EvaluationConfig(
                        method="algorithmic",
                        algorithmic_checks=[
                            {"name": "wc", "type": "min_word_count", "min_words": 20, "required": True},
                        ],
                    ),
                    max_iterations=2,
                    cooldown="0s",
                ),
            ],
        )

        result = engine.run_task("build-feature", task)

        assert result.status == LoopStatus.SUCCESS
        assert len(result.phases) == 2
        assert result.phases[0].phase_name == "discovery"
        assert result.phases[0].loop_result.passed
        assert result.phases[1].phase_name == "implementation"
        assert result.phases[1].loop_result.passed

    def test_phase_failure_stops_task(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "Short.", "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        task = TaskConfig(
            description="Build something.",
            phases=[
                PhaseConfig(
                    name="research",
                    type="research",
                    evaluation=EvaluationConfig(
                        method="algorithmic",
                        algorithmic_checks=[
                            {"name": "wc", "type": "min_word_count", "min_words": 10000, "required": True},
                        ],
                    ),
                    max_iterations=1,
                    cooldown="0s",
                ),
                PhaseConfig(
                    name="build",
                    type="execution",
                    max_iterations=1,
                    cooldown="0s",
                ),
            ],
        )

        result = engine.run_task("fail-early", task)
        assert result.status == LoopStatus.FAILED
        # Second phase should not have run
        assert len(result.phases) == 1


# ---------------------------------------------------------------------------
# Script evaluator integration
# ---------------------------------------------------------------------------


class TestScriptEvaluation:
    def test_script_passes(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "output", "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="script-task",
            task_description="Run a script.",
            loop_config=LoopConfig(
                max_iterations=1,
                evaluation=EvaluationConfig(
                    method="script",
                    script="echo 'all tests pass'",
                ),
                cooldown="0s",
            ),
        )

        assert result.passed

    def test_script_fails(self, tmp_workspace):
        ws, out = tmp_workspace
        agent = MockAgentExecutor([
            {"output_text": "output", "output_files": []},
        ])
        engine = LoopEngine(agent, workspace=ws, output_dir=out)

        result = engine.run_loop(
            task_name="script-fail-task",
            task_description="Run a failing script.",
            loop_config=LoopConfig(
                max_iterations=1,
                evaluation=EvaluationConfig(
                    method="script",
                    script="echo 'FAIL: tests broken' && exit 1",
                ),
                cooldown="0s",
            ),
        )

        assert not result.passed
