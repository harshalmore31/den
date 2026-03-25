"""Check base class, context, and result types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CheckContext:
    """Everything a check needs to evaluate task output."""

    output_text: str = ""
    output_files: list[str] = field(default_factory=list)
    task_description: str = ""
    phase_questions: list[dict] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    workspace: str = "/den/workspace"
    output_dir: str = "/den/output"


@dataclass
class CheckResult:
    """Result of a single check execution."""

    name: str
    check_type: str
    passed: bool
    score: float = 1.0
    message: str = ""
    details: dict = field(default_factory=dict)

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.message}"


class Check(ABC):
    """Base class for all algorithmic checks."""

    name: str = ""
    description: str = ""

    @abstractmethod
    def run(self, context: CheckContext) -> CheckResult:
        ...

    def _param(self, context: CheckContext, key: str, default: Any = None) -> Any:
        return context.params.get(key, default)
