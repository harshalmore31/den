"""Algorithmic evaluator -- runs checks from the registry."""

from __future__ import annotations

from typing import Any

from den.checks import CheckContext, get_check_registry
from den.evaluators._base import Evaluator, EvaluationResult


class AlgorithmicEvaluator(Evaluator):
    """Run algorithmic checks and aggregate results."""

    method = "algorithmic"

    def evaluate(
        self,
        output_text: str,
        output_files: list[str],
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        context = context or {}
        registry = get_check_registry()
        checks_config = config.get("algorithmic_checks", [])

        if not checks_config:
            return EvaluationResult(
                passed=True, score=1.0, method=self.method,
                feedback="No algorithmic checks configured.",
            )

        check_results = []
        total_weight = 0.0
        weighted_score = 0.0

        for check_cfg in checks_config:
            check_type = check_cfg.get("type", "")
            check = registry.get(check_type)

            if check is None:
                check_results.append({
                    "name": check_cfg.get("name", check_type),
                    "passed": False,
                    "message": f"Unknown check type: '{check_type}'",
                    "required": check_cfg.get("required", True),
                })
                continue

            # Build check context
            check_context = CheckContext(
                output_text=output_text,
                output_files=output_files,
                task_description=context.get("task_description", ""),
                phase_questions=context.get("phase_questions", []),
                params=check_cfg,
                workspace=context.get("workspace", "/den/workspace"),
                output_dir=context.get("output_dir", "/den/output"),
            )

            result = check.run(check_context)
            weight = check_cfg.get("weight", 1.0)
            total_weight += weight
            weighted_score += result.score * weight

            check_results.append({
                "name": result.name,
                "type": check_type,
                "passed": result.passed,
                "score": result.score,
                "message": result.message,
                "required": check_cfg.get("required", True),
                "details": result.details,
            })

        # Determine overall pass/fail: all required checks must pass
        required_passed = all(
            r["passed"] for r in check_results if r.get("required", True)
        )
        overall_score = weighted_score / max(total_weight, 1.0)

        feedback = self._generate_feedback(check_results)

        return EvaluationResult(
            passed=required_passed,
            score=round(overall_score, 3),
            method=self.method,
            feedback=feedback,
            check_results=check_results,
        )
