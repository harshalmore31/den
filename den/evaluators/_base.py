"""Evaluator base class and result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationResult:
    """Result of running an evaluator on task output."""

    passed: bool
    score: float = 0.0
    method: str = ""
    feedback: str = ""
    check_results: list[dict] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] score={self.score:.2f} method={self.method}: {self.feedback[:100]}"


class Evaluator(ABC):
    """Base class for all evaluators."""

    method: str = ""

    @abstractmethod
    def evaluate(
        self,
        output_text: str,
        output_files: list[str],
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        ...

    @staticmethod
    def _generate_feedback(check_results: list[dict]) -> str:
        failed = [r for r in check_results if not r.get("passed", True)]
        if not failed:
            return "All checks passed."

        lines = ["The following checks failed:"]
        for r in failed:
            lines.append(f"  - {r.get('name', 'unknown')}: {r.get('message', 'no details')}")

        lines.append("\nFix these issues in your next attempt.")
        return "\n".join(lines)
