"""Tests for Den evaluators."""

import pytest

from den.evaluators import (
    get_evaluator,
    EvaluationResult,
    AlgorithmicEvaluator,
    ScriptEvaluator,
    HybridEvaluator,
)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


class TestFactory:
    def test_get_algorithmic(self):
        e = get_evaluator("algorithmic")
        assert isinstance(e, AlgorithmicEvaluator)

    def test_get_hybrid(self):
        e = get_evaluator("hybrid")
        assert isinstance(e, HybridEvaluator)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown evaluator"):
            get_evaluator("magic")


# ---------------------------------------------------------------------------
# Algorithmic evaluator
# ---------------------------------------------------------------------------


class TestAlgorithmicEvaluator:
    def test_all_checks_pass(self):
        evaluator = AlgorithmicEvaluator()
        result = evaluator.evaluate(
            output_text="This is a detailed report with enough words. " * 30
                        + "\nSee https://example.com and https://docs.python.org",
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "word_count", "type": "min_word_count", "min_words": 50, "required": True},
                    {"name": "sources", "type": "sources_present", "min_count": 2, "required": True},
                ],
            },
        )
        assert result.passed
        assert result.score > 0.9
        assert len(result.check_results) == 2

    def test_required_check_fails(self):
        evaluator = AlgorithmicEvaluator()
        result = evaluator.evaluate(
            output_text="Short.",
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "word_count", "type": "min_word_count", "min_words": 500, "required": True},
                ],
            },
        )
        assert not result.passed
        assert "word_count" in result.feedback.lower() or "Word count" in result.feedback

    def test_optional_check_fails_still_passes(self):
        evaluator = AlgorithmicEvaluator()
        result = evaluator.evaluate(
            output_text="This has enough words for the required check. " * 20,
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "word_count", "type": "min_word_count", "min_words": 10, "required": True},
                    {"name": "sources", "type": "sources_present", "min_count": 5, "required": False},
                ],
            },
        )
        assert result.passed  # Required passed, optional failed is OK

    def test_no_checks_passes(self):
        evaluator = AlgorithmicEvaluator()
        result = evaluator.evaluate("anything", [], {})
        assert result.passed

    def test_unknown_check_type(self):
        evaluator = AlgorithmicEvaluator()
        result = evaluator.evaluate(
            output_text="test",
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "bad", "type": "nonexistent_check", "required": True},
                ],
            },
        )
        assert not result.passed

    def test_feedback_is_actionable(self):
        evaluator = AlgorithmicEvaluator()
        result = evaluator.evaluate(
            output_text="Too short",
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "wc", "type": "min_word_count", "min_words": 1000, "required": True},
                    {"name": "src", "type": "sources_present", "min_count": 3, "required": True},
                ],
            },
        )
        assert not result.passed
        assert "failed" in result.feedback.lower()
        # Should mention both failed checks
        assert "wc" in result.feedback or "Word count" in result.feedback


# ---------------------------------------------------------------------------
# Script evaluator
# ---------------------------------------------------------------------------


class TestScriptEvaluator:
    def test_passing_script(self):
        evaluator = ScriptEvaluator()
        result = evaluator.evaluate(
            output_text="",
            output_files=[],
            config={"script": "echo 'all good'"},
            context={"workspace": "/tmp"},
        )
        assert result.passed
        assert "all good" in result.feedback

    def test_failing_script(self):
        evaluator = ScriptEvaluator()
        result = evaluator.evaluate(
            output_text="",
            output_files=[],
            config={"script": "echo 'test failed' && exit 1"},
            context={"workspace": "/tmp"},
        )
        assert not result.passed

    def test_no_script(self):
        evaluator = ScriptEvaluator()
        result = evaluator.evaluate("", [], {})
        assert not result.passed
        assert "No script" in result.feedback


# ---------------------------------------------------------------------------
# Hybrid evaluator
# ---------------------------------------------------------------------------


class TestHybridEvaluator:
    def test_algorithmic_fails_skips_qualitative(self):
        """If algorithmic checks fail, don't waste an LLM call."""
        evaluator = HybridEvaluator()
        result = evaluator.evaluate(
            output_text="Short",
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "wc", "type": "min_word_count", "min_words": 1000, "required": True},
                ],
                "qualitative_checks": {
                    "method": "self-judge",
                    "criteria": ["Output is well-written"],
                    "run_if_algorithmic_passes": True,
                },
            },
        )
        assert not result.passed
        assert result.method == "hybrid"
        # Should only have algorithmic results, not qualitative
        types = {r.get("type") for r in result.check_results}
        assert "min_word_count" in types

    def test_algorithmic_passes_no_qualitative(self):
        """If no qualitative checks, algorithmic pass is sufficient."""
        evaluator = HybridEvaluator()
        result = evaluator.evaluate(
            output_text="Enough words here for the check. " * 20,
            output_files=[],
            config={
                "algorithmic_checks": [
                    {"name": "wc", "type": "min_word_count", "min_words": 10, "required": True},
                ],
            },
        )
        assert result.passed
