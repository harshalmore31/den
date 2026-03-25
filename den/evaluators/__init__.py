"""Den Evaluators -- aggregate checks into pass/fail decisions."""

from den.evaluators._base import Evaluator, EvaluationResult
from den.evaluators.algorithmic import AlgorithmicEvaluator
from den.evaluators.script import ScriptEvaluator
from den.evaluators.llm_judge import SelfJudgeEvaluator, LLMJudgeEvaluator
from den.evaluators.hybrid import HybridEvaluator


def get_evaluator(method: str) -> Evaluator:
    """Factory: get an evaluator by method name."""
    evaluators = {
        "algorithmic": AlgorithmicEvaluator,
        "script": ScriptEvaluator,
        "self-judge": SelfJudgeEvaluator,
        "llm-judge": LLMJudgeEvaluator,
        "hybrid": HybridEvaluator,
    }
    cls = evaluators.get(method)
    if cls is None:
        raise ValueError(f"Unknown evaluator method: '{method}'. Available: {list(evaluators.keys())}")
    return cls()


__all__ = [
    "Evaluator",
    "EvaluationResult",
    "AlgorithmicEvaluator",
    "ScriptEvaluator",
    "SelfJudgeEvaluator",
    "LLMJudgeEvaluator",
    "HybridEvaluator",
    "get_evaluator",
]
