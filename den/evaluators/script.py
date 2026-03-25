"""Script evaluator -- run an external script and check exit code."""

from __future__ import annotations

from typing import Any

from den.agentfile.schema import BashConfig
from den.core.bash_executor import BashExecutor
from den.evaluators._base import Evaluator, EvaluationResult
from den.utils import parse_duration


class ScriptEvaluator(Evaluator):
    """Run an external validation script."""

    method = "script"

    def evaluate(
        self,
        output_text: str,
        output_files: list[str],
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        context = context or {}
        script = config.get("script", "")
        timeout_str = config.get("script_timeout", config.get("timeout", "120s"))

        if not script:
            return EvaluationResult(
                passed=False, score=0.0, method=self.method,
                feedback="No script provided in evaluation config.",
            )

        try:
            timeout = parse_duration(timeout_str) if isinstance(timeout_str, str) else int(timeout_str)
        except (ValueError, TypeError):
            timeout = 120

        executor = BashExecutor(BashConfig(enabled=True, timeout=f"{timeout}s"))
        workspace = context.get("workspace", "/den/workspace")
        result = executor.execute(script, workdir=workspace, timeout=timeout)

        passed = result.exit_code == 0 and not result.blocked
        output = result.stdout.strip() if result.stdout else result.stderr.strip()

        feedback = output if output else (
            "Script passed." if passed else f"Script failed with exit code {result.exit_code}."
        )

        return EvaluationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            method=self.method,
            feedback=feedback[:2000],
            details={
                "exit_code": result.exit_code,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000],
                "duration_ms": result.duration_ms,
            },
        )
