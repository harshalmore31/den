"""LLM-based evaluators -- self-judge and independent llm-judge."""

from __future__ import annotations

import json
from typing import Any

from den.evaluators._base import Evaluator, EvaluationResult


# Prompt template for evaluation
_JUDGE_SYSTEM_PROMPT = """You are an evaluator. Your job is to assess whether the given output meets the specified criteria.

For each criterion, score it 0.0 to 1.0 and determine if it passes (score >= 0.7).

You MUST respond with valid JSON in this exact format:
{
  "overall_passed": true/false,
  "overall_score": 0.0-1.0,
  "criteria_results": [
    {
      "criterion": "the criterion text",
      "passed": true/false,
      "score": 0.0-1.0,
      "reasoning": "brief explanation"
    }
  ],
  "feedback": "actionable feedback for improvement (if failed)"
}

Be strict but fair. Only mark as passed if the output genuinely meets the criterion."""

_JUDGE_USER_TEMPLATE = """## Task Description
{task_description}

## Output to Evaluate
{output_text}

## Criteria to Check
{criteria_list}

Evaluate the output against each criterion. Respond with JSON only."""


class SelfJudgeEvaluator(Evaluator):
    """The generating agent evaluates its own output (cheap but biased)."""

    method = "self-judge"

    def evaluate(
        self,
        output_text: str,
        output_files: list[str],
        config: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> EvaluationResult:
        context = context or {}
        criteria = config.get("criteria", [])

        if not criteria:
            return EvaluationResult(
                passed=True, score=1.0, method=self.method,
                feedback="No qualitative criteria configured.",
            )

        return self._run_judge(
            output_text=output_text,
            criteria=criteria,
            task_description=context.get("task_description", ""),
            model=context.get("model", None),
        )

    def _run_judge(
        self,
        output_text: str,
        criteria: list[str],
        task_description: str,
        model: Any = None,
    ) -> EvaluationResult:
        criteria_list = "\n".join(f"- {c}" for c in criteria)
        user_message = _JUDGE_USER_TEMPLATE.format(
            task_description=task_description or "No description provided.",
            output_text=output_text[:8000],  # Limit to avoid context overflow
            criteria_list=criteria_list,
        )

        # Try PydanticAI first
        try:
            return self._evaluate_with_pydantic_ai(user_message, model)
        except Exception:
            pass

        # Try direct Anthropic/OpenAI call
        try:
            return self._evaluate_with_api(user_message)
        except Exception:
            pass

        # Fallback: can't evaluate without LLM
        return EvaluationResult(
            passed=True,  # Default pass if we can't evaluate
            score=0.5,
            method=self.method,
            feedback="LLM judge unavailable — skipping qualitative evaluation. "
                     "Install 'anthropic' or 'openai' package and set API key.",
        )

    def _evaluate_with_pydantic_ai(self, user_message: str, model: Any) -> EvaluationResult:
        from pydantic import BaseModel
        from pydantic_ai import Agent

        class CriterionResult(BaseModel):
            criterion: str
            passed: bool
            score: float
            reasoning: str

        class JudgeOutput(BaseModel):
            overall_passed: bool
            overall_score: float
            criteria_results: list[CriterionResult]
            feedback: str

        model_name = model or "openai:gpt-4o-mini"
        agent = Agent(
            model_name,
            output_type=JudgeOutput,
            instructions=_JUDGE_SYSTEM_PROMPT,
        )

        result = agent.run_sync(user_message)
        output = result.output

        return EvaluationResult(
            passed=output.overall_passed,
            score=output.overall_score,
            method=self.method,
            feedback=output.feedback,
            check_results=[
                {
                    "name": cr.criterion[:50],
                    "passed": cr.passed,
                    "score": cr.score,
                    "message": cr.reasoning,
                }
                for cr in output.criteria_results
            ],
        )

    def _evaluate_with_api(self, user_message: str) -> EvaluationResult:
        import os

        # Try Anthropic
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            return self._evaluate_anthropic(user_message, api_key)

        # Try OpenAI
        api_key = os.environ.get("OPENAI_API_KEY")
        if api_key:
            return self._evaluate_openai(user_message, api_key)

        raise RuntimeError("No LLM API key available")

    def _evaluate_anthropic(self, user_message: str, api_key: str) -> EvaluationResult:
        from anthropic import Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=_JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return self._parse_response(response.content[0].text)

    def _evaluate_openai(self, user_message: str, api_key: str) -> EvaluationResult:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            max_tokens=1024,
        )
        return self._parse_response(response.choices[0].message.content)

    def _parse_response(self, text: str) -> EvaluationResult:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return EvaluationResult(
                passed=True, score=0.5, method=self.method,
                feedback=f"Could not parse judge response as JSON. Raw: {text[:200]}",
            )

        return EvaluationResult(
            passed=data.get("overall_passed", True),
            score=data.get("overall_score", 0.5),
            method=self.method,
            feedback=data.get("feedback", ""),
            check_results=[
                {
                    "name": cr.get("criterion", "")[:50],
                    "passed": cr.get("passed", True),
                    "score": cr.get("score", 0.5),
                    "message": cr.get("reasoning", ""),
                }
                for cr in data.get("criteria_results", [])
            ],
        )


class LLMJudgeEvaluator(SelfJudgeEvaluator):
    """Independent LLM evaluates output (more objective than self-judge)."""

    method = "llm-judge"
