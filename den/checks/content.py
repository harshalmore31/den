"""Content checks -- verify text output quality."""

from __future__ import annotations

import re

from den.checks._base import Check, CheckContext, CheckResult


class MinWordCount(Check):
    """Verify output meets a minimum word count."""

    name = "min_word_count"
    description = "Check that output has at least N words."

    def run(self, context: CheckContext) -> CheckResult:
        min_words = self._param(context, "min_words", 100)
        text = context.output_text
        word_count = len(text.split())

        passed = word_count >= min_words
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=min(word_count / max(min_words, 1), 1.0),
            message=f"Word count: {word_count} (required: {min_words})"
                    + (" ✓" if passed else " ✗"),
            details={"word_count": word_count, "min_words": min_words},
        )


class SourcesPresent(Check):
    """Verify output contains source URLs/references."""

    name = "sources_present"
    description = "Check that output contains source URLs or references."

    # Patterns that look like sources
    _URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")
    _REF_PATTERN = re.compile(
        r"(?:source|reference|citation|ref|see|from|via|according to)\s*[:.]?\s*\S+",
        re.IGNORECASE,
    )

    def run(self, context: CheckContext) -> CheckResult:
        min_count = self._param(context, "min_count", 1)
        text = context.output_text

        urls = self._URL_PATTERN.findall(text)
        # Deduplicate
        unique_urls = list(set(urls))
        count = len(unique_urls)

        passed = count >= min_count
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=min(count / max(min_count, 1), 1.0),
            message=f"Sources found: {count} (required: {min_count})"
                    + (" ✓" if passed else " ✗"),
            details={"source_count": count, "urls": unique_urls[:20], "min_count": min_count},
        )


class NoPlaceholderText(Check):
    """Verify output contains no placeholder text."""

    name = "no_placeholder_text"
    description = "Check that output has no TODO, TBD, placeholder, or lorem ipsum text."

    DEFAULT_PATTERNS = [
        r"\bTODO\b",
        r"\bTBD\b",
        r"\bFIXME\b",
        r"\bPLACEHOLDER\b",
        r"\blorem ipsum\b",
        r"\[insert .+?\]",
        r"\[add .+?\]",
        r"\bto be (added|completed|determined|written)\b",
        r"\bcoming soon\b",
    ]

    def run(self, context: CheckContext) -> CheckResult:
        patterns = self._param(context, "patterns", self.DEFAULT_PATTERNS)
        text = context.output_text
        found = []

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                found.extend(matches)

        passed = len(found) == 0
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message="No placeholder text found ✓" if passed
                    else f"Placeholder text found: {', '.join(found[:5])} ✗",
            details={"found": found[:10], "count": len(found)},
        )


class SectionsPresent(Check):
    """Verify output contains required section headers."""

    name = "sections_present"
    description = "Check that output contains all required sections/headers."

    def run(self, context: CheckContext) -> CheckResult:
        required = self._param(context, "required_sections", [])
        text = context.output_text.lower()

        found = []
        missing = []

        for section in required:
            section_lower = section.lower()
            # Check for the section name in headers (## Section) or as bold text
            patterns = [
                rf"#+\s*{re.escape(section_lower)}",     # ## Section Name
                rf"\*\*{re.escape(section_lower)}\*\*",   # **Section Name**
                rf"^{re.escape(section_lower)}\s*$",       # Section Name on its own line
                rf"^{re.escape(section_lower)}:",          # Section Name:
            ]
            found_section = any(
                re.search(p, text, re.IGNORECASE | re.MULTILINE)
                for p in patterns
            )
            if found_section:
                found.append(section)
            else:
                missing.append(section)

        passed = len(missing) == 0
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=len(found) / max(len(required), 1),
            message=f"Sections: {len(found)}/{len(required)}"
                    + (f" (missing: {', '.join(missing)})" if missing else " ✓"),
            details={"found": found, "missing": missing, "required": required},
        )
