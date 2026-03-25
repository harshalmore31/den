"""Question-answering checks -- verify research loop completeness."""

from __future__ import annotations

import re

from den.checks._base import Check, CheckContext, CheckResult


class AllQuestionsAddressed(Check):
    """Verify that output contains substantive answers to all required questions.

    Uses paragraph-level analysis to match questions to output content.
    Falls back to keyword matching if embeddings are unavailable.
    """

    name = "all_questions_addressed"
    description = "Check that all research questions have substantive answers."

    def run(self, context: CheckContext) -> CheckResult:
        questions = context.phase_questions or self._param(context, "questions", [])
        min_words = self._param(context, "min_words_per_answer", 50)
        text = context.output_text

        if not questions:
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=True,
                message="No questions to check.",
            )

        # Split output into paragraphs
        paragraphs = self._split_paragraphs(text)

        results = {}
        for q in questions:
            q_text = q.get("text", q) if isinstance(q, dict) else str(q)
            q_id = q.get("id", q_text[:30]) if isinstance(q, dict) else q_text[:30]
            q_required = q.get("required", True) if isinstance(q, dict) else True

            # Find the best matching paragraph(s) for this question
            best_match = self._find_answer(q_text, paragraphs)

            if best_match and len(best_match.split()) >= min_words:
                results[q_id] = {
                    "answered": True,
                    "word_count": len(best_match.split()),
                    "required": q_required,
                }
            else:
                word_count = len(best_match.split()) if best_match else 0
                results[q_id] = {
                    "answered": False,
                    "word_count": word_count,
                    "required": q_required,
                    "reason": f"answer too short ({word_count} words, need {min_words})"
                              if best_match else "no matching content found",
                }

        # Check pass/fail
        required_answered = all(
            r["answered"] for r in results.values() if r["required"]
        )
        total_answered = sum(1 for r in results.values() if r["answered"])

        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=required_answered,
            score=total_answered / max(len(results), 1),
            message=f"Questions answered: {total_answered}/{len(results)}"
                    + (" ✓" if required_answered else " ✗ (required questions unanswered)"),
            details={"questions": results},
        )

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs (by double newline or headers)."""
        # Split on double newlines or markdown headers
        parts = re.split(r"\n\s*\n|(?=^#{1,4}\s)", text, flags=re.MULTILINE)
        return [p.strip() for p in parts if p.strip() and len(p.strip()) > 20]

    def _find_answer(self, question: str, paragraphs: list[str]) -> str | None:
        """Find the paragraph(s) that best answer the question.

        Uses keyword overlap scoring. For each paragraph, count how many
        significant words from the question appear in it.
        """
        q_words = self._extract_keywords(question)
        if not q_words:
            return None

        best_score = 0
        best_paragraphs = []

        for para in paragraphs:
            para_lower = para.lower()
            score = sum(1 for w in q_words if w in para_lower)
            normalized = score / len(q_words)

            if normalized > best_score:
                best_score = normalized
                best_paragraphs = [para]
            elif normalized == best_score and normalized > 0:
                best_paragraphs.append(para)

        if best_score < 0.2:  # Less than 20% keyword overlap
            return None

        return "\n\n".join(best_paragraphs[:3])

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """Extract significant words from text (remove stop words)."""
        stop = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "to", "of", "in", "for", "on", "with", "at", "by", "it", "this",
            "that", "and", "or", "but", "not", "no", "what", "how", "why",
            "when", "where", "which", "who", "do", "does", "did", "has",
            "have", "had", "will", "would", "can", "could", "should", "there",
        }
        words = re.findall(r"[a-z0-9]+", text.lower())
        return [w for w in words if len(w) > 2 and w not in stop]
