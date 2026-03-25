"""Den Loop Engine -- the core of the Loop Architecture.

Orchestrates: evaluation, feedback, retry, memory, and progress tracking.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Protocol

from den.agentfile.schema import EvaluationConfig, LoopConfig, PhaseConfig, TaskConfig
from den.evaluators import EvaluationResult, get_evaluator
from den.memory.manager import MemoryManager


class LoopStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


@dataclass
class IterationRecord:
    """Record of a single loop iteration."""

    iteration: int
    started_at: float
    finished_at: float = 0.0
    output_text: str = ""
    output_files: list[str] = field(default_factory=list)
    evaluation: EvaluationResult | None = None
    feedback: str = ""


@dataclass
class LoopResult:
    """Final result of a loop execution."""

    status: LoopStatus
    iterations: int
    total_duration_ms: int
    final_output: str = ""
    final_files: list[str] = field(default_factory=list)
    iteration_records: list[IterationRecord] = field(default_factory=list)
    evaluation: EvaluationResult | None = None

    @property
    def passed(self) -> bool:
        return self.status == LoopStatus.SUCCESS


@dataclass
class PhaseResult:
    """Result of a single phase in a multi-phase task."""

    phase_name: str
    phase_type: str
    loop_result: LoopResult
    output_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of a full task execution (all phases)."""

    task_name: str
    status: LoopStatus
    phases: list[PhaseResult] = field(default_factory=list)
    total_duration_ms: int = 0
    total_iterations: int = 0


class AgentExecutor(Protocol):
    """Protocol for the agent execution function."""

    def execute(self, context: dict[str, Any]) -> dict[str, Any]: ...


class LoopEngine:
    """Core loop execution engine: attempt, evaluate, feedback, retry."""

    def __init__(
        self,
        agent_executor: AgentExecutor,
        memory: MemoryManager | None = None,
        workspace: str = "/den/workspace",
        output_dir: str = "/den/output",
    ):
        self.agent = agent_executor
        self.memory = memory
        self.workspace = workspace
        self.output_dir = output_dir

    def run_loop(
        self,
        task_name: str,
        task_description: str,
        loop_config: LoopConfig,
        eval_config: EvaluationConfig | None = None,
        phase_questions: list[dict] | None = None,
    ) -> LoopResult:
        """Execute a single-phase loop: attempt, evaluate, feedback, retry."""
        eval_cfg = eval_config or loop_config.evaluation
        max_iter = loop_config.max_iterations
        cooldown = loop_config.cooldown_seconds

        records: list[IterationRecord] = []
        feedback = ""
        start_time = time.monotonic()

        for iteration in range(1, max_iter + 1):
            record = IterationRecord(iteration=iteration, started_at=time.time())

            memory_context = self._gather_memory_context(task_name, task_description)

            context = {
                "task_name": task_name,
                "task_description": task_description,
                "iteration": iteration,
                "max_iterations": max_iter,
                "prior_feedback": feedback,
                "memory_context": memory_context,
                "phase_questions": phase_questions or [],
                "workspace": self.workspace,
                "output_dir": self.output_dir,
            }

            try:
                result = self.agent.execute(context)
                record.output_text = result.get("output_text", "")
                record.output_files = result.get("output_files", [])
            except Exception as e:
                record.output_text = ""
                record.feedback = f"Agent execution error: {e}"
                record.finished_at = time.time()
                records.append(record)
                feedback = record.feedback
                if cooldown > 0 and iteration < max_iter:
                    time.sleep(cooldown)
                continue

            evaluator = get_evaluator(eval_cfg.method)
            eval_result = evaluator.evaluate(
                output_text=record.output_text,
                output_files=record.output_files,
                config=eval_cfg.model_dump() if hasattr(eval_cfg, 'model_dump') else dict(eval_cfg),
                context={
                    "task_description": task_description,
                    "phase_questions": phase_questions or [],
                    "workspace": self.workspace,
                    "output_dir": self.output_dir,
                },
            )
            record.evaluation = eval_result
            record.finished_at = time.time()

            self._write_progress(task_name, iteration, eval_result, records)

            if eval_result.passed:
                records.append(record)
                self._record_success(task_name, iteration, record)

                duration = int((time.monotonic() - start_time) * 1000)
                return LoopResult(
                    status=LoopStatus.SUCCESS,
                    iterations=iteration,
                    total_duration_ms=duration,
                    final_output=record.output_text,
                    final_files=record.output_files,
                    iteration_records=records,
                    evaluation=eval_result,
                )

            feedback = eval_result.feedback
            record.feedback = feedback
            records.append(record)

            self._record_failure(task_name, iteration, feedback)

            if cooldown > 0 and iteration < max_iter:
                time.sleep(cooldown)

        duration = int((time.monotonic() - start_time) * 1000)
        return LoopResult(
            status=LoopStatus.EXHAUSTED,
            iterations=max_iter,
            total_duration_ms=duration,
            final_output=records[-1].output_text if records else "",
            final_files=records[-1].output_files if records else [],
            iteration_records=records,
            evaluation=records[-1].evaluation if records else None,
        )

    def run_task(self, task_name: str, task_config: TaskConfig) -> TaskResult:
        """Execute a full task -- single-phase or multi-phase."""
        if task_config.phases:
            return self._run_multi_phase(task_name, task_config)

        loop_config = task_config.loop or LoopConfig()
        loop_result = self.run_loop(
            task_name=task_name,
            task_description=task_config.description,
            loop_config=loop_config,
        )
        return TaskResult(
            task_name=task_name,
            status=loop_result.status,
            phases=[PhaseResult(
                phase_name="main",
                phase_type="custom",
                loop_result=loop_result,
            )],
            total_duration_ms=loop_result.total_duration_ms,
            total_iterations=loop_result.iterations,
        )

    def _run_multi_phase(self, task_name: str, task_config: TaskConfig) -> TaskResult:
        phase_results: list[PhaseResult] = []
        total_duration = 0
        total_iterations = 0

        for phase in task_config.phases:
            loop_config = LoopConfig(
                max_iterations=phase.max_iterations,
                evaluation=phase.evaluation,
                cooldown=phase.cooldown,
            )

            phase_desc = phase.description or task_config.description
            if phase.input_from:
                prior_context = self._recall_phase_data(phase.input_from)
                if prior_context:
                    phase_desc += f"\n\nContext from prior phases:\n{prior_context}"

            questions = [q.model_dump() for q in phase.questions] if phase.questions else None

            loop_result = self.run_loop(
                task_name=f"{task_name}/{phase.name}",
                task_description=phase_desc,
                loop_config=loop_config,
                eval_config=phase.evaluation,
                phase_questions=questions,
            )

            if loop_result.passed and self.memory:
                self.memory.remember(
                    content=f"Phase '{phase.name}' completed: {loop_result.final_output[:500]}",
                    category="task_result",
                    namespace=f"{task_name}/{phase.name}",
                    source_task=task_name,
                )

            phase_results.append(PhaseResult(
                phase_name=phase.name,
                phase_type=phase.type,
                loop_result=loop_result,
            ))

            total_duration += loop_result.total_duration_ms
            total_iterations += loop_result.iterations

            if not loop_result.passed:
                on_fail = phase.transitions.on_fail
                if on_fail.behavior == "stop":
                    break
                elif on_fail.behavior == "goto":
                    break  # TODO: implement goto
                elif on_fail.behavior == "notify":
                    break

        all_passed = all(pr.loop_result.passed for pr in phase_results)
        status = LoopStatus.SUCCESS if all_passed else LoopStatus.FAILED

        if self.memory:
            self.memory.record_task(
                task_name=task_name,
                status=status.value,
                iterations=total_iterations,
                summary=f"{len(phase_results)} phases, "
                        f"{'all passed' if all_passed else 'some failed'}",
            )

        return TaskResult(
            task_name=task_name,
            status=status,
            phases=phase_results,
            total_duration_ms=total_duration,
            total_iterations=total_iterations,
        )

    def _gather_memory_context(self, task_name: str, description: str) -> str:
        if not self.memory:
            return ""

        memories = self.memory.recall_for_task(task_name, description)
        if not memories:
            return ""

        lines = ["Relevant memories from prior runs:"]
        for m in memories[:10]:
            content = m.get("content", "")[:200]
            category = m.get("category", "fact")
            lines.append(f"  [{category}] {content}")

        return "\n".join(lines)

    def _recall_phase_data(self, input_from: list[str] | str) -> str:
        if not self.memory:
            return ""

        if isinstance(input_from, str):
            input_from = [input_from]

        lines = []
        for phase_name in input_from:
            memories = self.memory.recall(phase_name, namespace=None, top_k=5)
            for m in memories:
                lines.append(f"[from {phase_name}] {m.get('content', '')[:300]}")

        return "\n".join(lines) if lines else ""

    def _record_success(self, task_name: str, iteration: int, record: IterationRecord) -> None:
        if self.memory:
            self.memory.remember(
                content=f"Task '{task_name}' succeeded on iteration {iteration}. "
                        f"Output: {record.output_text[:200]}",
                category="learned",
                source_task=task_name,
            )

    def _record_failure(self, task_name: str, iteration: int, feedback: str) -> None:
        if self.memory:
            self.memory.remember(
                content=f"Task '{task_name}' iteration {iteration} failed: {feedback[:200]}",
                category="error",
                source_task=task_name,
            )

    def _write_progress(
        self,
        task_name: str,
        iteration: int,
        eval_result: EvaluationResult,
        records: list[IterationRecord],
    ) -> None:
        """Write progress.json for crash-resilient resumption."""
        progress_dir = os.path.join(self.workspace, "tasks", task_name.replace("/", "_"))
        os.makedirs(progress_dir, exist_ok=True)

        progress = {
            "task": task_name,
            "current_iteration": iteration,
            "status": "passed" if eval_result.passed else "in_progress",
            "last_evaluation": {
                "passed": eval_result.passed,
                "score": eval_result.score,
                "method": eval_result.method,
                "feedback": eval_result.feedback[:500],
            },
            "check_results": {
                r.get("name", f"check_{i}"): {
                    "passed": r.get("passed"),
                    "message": r.get("message", ""),
                }
                for i, r in enumerate(eval_result.check_results)
            },
            "timestamp": time.time(),
        }

        progress_path = os.path.join(progress_dir, "progress.json")
        with open(progress_path, "w") as f:
            json.dump(progress, f, indent=2)

        iter_dir = os.path.join(progress_dir, "iterations")
        os.makedirs(iter_dir, exist_ok=True)
        iter_path = os.path.join(iter_dir, f"{iteration}.json")
        with open(iter_path, "w") as f:
            json.dump({
                "iteration": iteration,
                "passed": eval_result.passed,
                "score": eval_result.score,
                "feedback": eval_result.feedback[:500],
                "timestamp": time.time(),
            }, f, indent=2)
