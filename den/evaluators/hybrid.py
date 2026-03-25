"""Hybrid evaluator -- algorithmic checks first, then qualitative."""

from __future__ import annotations

from typing import Any

from den.evaluators._base import Evaluator, EvaluationResult
from den.evaluators.algorithmic import AlgorithmicEvaluator
from den.evaluators.llm_judge import SelfJudgeEvaluator, LLMJudgeEvaluator


class HybridEvaluator(Evaluator):
    """Algorithmic checks first, then qualitative if configured."""

    method = "hybrid"

    def evaluate(
        self,
        output_text: str,
        output_files: list[str],
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        context = context or {}

        # Step 1: Run algorithmic checks
        algo_eval = AlgorithmicEvaluator()
        algo_result = algo_eval.evaluate(output_text, output_files, config, context)

        # If algorithmic checks failed, return immediately — no point running qualitative
        if not algo_result.passed:
            algo_result.method = self.method
            return algo_result

        # Step 2: Check if qualitative evaluation is configured
        qual_config = config.get("qualitative_checks", {})
        criteria = qual_config.get("criteria", [])
        run_if_passes = qual_config.get("run_if_algorithmic_passes", True)

        if not criteria or not run_if_passes:
            # No qualitative checks — algorithmic pass is sufficient
            algo_result.method = self.method
            return algo_result

        # Step 3: Run qualitative evaluation
        qual_method = qual_config.get("method", "self-judge")
        if qual_method == "llm-judge":
            qual_eval = LLMJudgeEvaluator()
        else:
            qual_eval = SelfJudgeEvaluator()

        qual_result = qual_eval.evaluate(
            output_text, output_files,
            {"criteria": criteria},
            context,
        )

        # Step 4: Combine results
        all_checks = algo_result.check_results + qual_result.check_results
        combined_score = (algo_result.score + qual_result.score) / 2.0
        combined_passed = algo_result.passed and qual_result.passed

        feedback_parts = []
        if not qual_result.passed:
            feedback_parts.append(f"Qualitative: {qual_result.feedback}")
        if combined_passed:
            feedback_parts.append("All checks passed.")

        return EvaluationResult(
            passed=combined_passed,
            score=round(combined_score, 3),
            method=self.method,
            feedback="\n".join(feedback_parts),
            check_results=all_checks,
            details={
                "algorithmic_passed": algo_result.passed,
                "algorithmic_score": algo_result.score,
                "qualitative_passed": qual_result.passed,
                "qualitative_score": qual_result.score,
            },
        )
