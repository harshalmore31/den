"""Tests for the Den checks library."""

import json
import os
import tempfile
import time

import pytest

from den.checks import (
    CheckContext,
    CheckResult,
    get_check_registry,
    MinWordCount,
    SourcesPresent,
    NoPlaceholderText,
    SectionsPresent,
    AllQuestionsAddressed,
    ArtifactsExist,
    FileCountInDir,
    FileModifiedRecently,
    NoSyntaxErrors,
    NoTodoComments,
    SchemaValid,
    JsonFieldValues,
    CsvRowCount,
    ScriptExitsZero,
)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestCheckRegistry:
    def test_all_checks_registered(self):
        registry = get_check_registry()
        checks = registry.list_checks()
        assert registry.count == 15
        assert "min_word_count" in checks
        assert "sources_present" in checks
        assert "script_exits_zero" in checks
        assert "schema_valid" in checks
        assert "all_questions_addressed" in checks

    def test_get_check(self):
        registry = get_check_registry()
        check = registry.get("min_word_count")
        assert check is not None
        assert check.name == "min_word_count"


# ---------------------------------------------------------------------------
# Content checks
# ---------------------------------------------------------------------------


class TestMinWordCount:
    def test_passes(self):
        ctx = CheckContext(
            output_text="This is a test output with enough words " * 20,
            params={"min_words": 50},
        )
        result = MinWordCount().run(ctx)
        assert result.passed

    def test_fails(self):
        ctx = CheckContext(output_text="Too short", params={"min_words": 100})
        result = MinWordCount().run(ctx)
        assert not result.passed
        assert "2" in result.message  # word count shown
        assert "100" in result.message

    def test_score_proportional(self):
        ctx = CheckContext(output_text="one two three four five", params={"min_words": 10})
        result = MinWordCount().run(ctx)
        assert result.score == 0.5  # 5/10


class TestSourcesPresent:
    def test_finds_urls(self):
        ctx = CheckContext(
            output_text="See https://example.com and https://docs.python.org for details.",
            params={"min_count": 2},
        )
        result = SourcesPresent().run(ctx)
        assert result.passed
        assert result.details["source_count"] == 2

    def test_fails_no_sources(self):
        ctx = CheckContext(output_text="No links here.", params={"min_count": 1})
        result = SourcesPresent().run(ctx)
        assert not result.passed

    def test_deduplicates(self):
        ctx = CheckContext(
            output_text="Visit https://example.com and again https://example.com end",
            params={"min_count": 1},
        )
        result = SourcesPresent().run(ctx)
        assert result.details["source_count"] == 1


class TestNoPlaceholderText:
    def test_clean_text(self):
        ctx = CheckContext(output_text="This is a complete, well-written report.")
        result = NoPlaceholderText().run(ctx)
        assert result.passed

    def test_finds_todo(self):
        ctx = CheckContext(output_text="Section 1 is done. TODO add section 2.")
        result = NoPlaceholderText().run(ctx)
        assert not result.passed
        assert len(result.details["found"]) > 0

    def test_finds_tbd(self):
        ctx = CheckContext(output_text="The timeline is TBD.")
        result = NoPlaceholderText().run(ctx)
        assert not result.passed

    def test_finds_insert_placeholder(self):
        ctx = CheckContext(output_text="Revenue was [insert amount here].")
        result = NoPlaceholderText().run(ctx)
        assert not result.passed


class TestSectionsPresent:
    def test_finds_markdown_headers(self):
        ctx = CheckContext(
            output_text="## Introduction\nSome text\n## Analysis\nMore text\n## Conclusion\nFinal text",
            params={"required_sections": ["introduction", "analysis", "conclusion"]},
        )
        result = SectionsPresent().run(ctx)
        assert result.passed

    def test_missing_section(self):
        ctx = CheckContext(
            output_text="## Introduction\nSome text\n## Conclusion\nFinal text",
            params={"required_sections": ["introduction", "analysis", "conclusion"]},
        )
        result = SectionsPresent().run(ctx)
        assert not result.passed
        assert "analysis" in result.details["missing"]

    def test_score_partial(self):
        ctx = CheckContext(
            output_text="## Introduction\ntext",
            params={"required_sections": ["introduction", "analysis"]},
        )
        result = SectionsPresent().run(ctx)
        assert result.score == 0.5


# ---------------------------------------------------------------------------
# Questions check
# ---------------------------------------------------------------------------


class TestAllQuestionsAddressed:
    def test_all_answered(self):
        ctx = CheckContext(
            output_text=(
                "## Competitors\nThe main competitors are E2B, Modal, and Daytona. "
                "Each provides sandbox environments for AI agent execution.\n\n"
                "## Technical Risks\nThe primary risks include Docker dependency, "
                "network enforcement complexity, and APScheduler version conflicts."
            ),
            phase_questions=[
                {"id": "competitors", "text": "What are the competitors?", "required": True},
                {"id": "risks", "text": "What are the technical risks?", "required": True},
            ],
            params={"min_words_per_answer": 10},
        )
        result = AllQuestionsAddressed().run(ctx)
        assert result.passed

    def test_unanswered_question(self):
        ctx = CheckContext(
            output_text="## Competitors\nE2B and Modal are competitors.",
            phase_questions=[
                {"id": "competitors", "text": "What are the competitors?", "required": True},
                {"id": "timeline", "text": "What is the delivery timeline?", "required": True},
            ],
            params={"min_words_per_answer": 5},
        )
        result = AllQuestionsAddressed().run(ctx)
        assert not result.passed

    def test_no_questions(self):
        ctx = CheckContext(output_text="Some text")
        result = AllQuestionsAddressed().run(ctx)
        assert result.passed  # No questions = pass


# ---------------------------------------------------------------------------
# Filesystem checks
# ---------------------------------------------------------------------------


class TestArtifactsExist:
    def test_files_exist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = os.path.join(tmpdir, "report.md")
            p2 = os.path.join(tmpdir, "data.json")
            open(p1, "w").write("# Report\nContent here")
            open(p2, "w").write('{"key": "value"}')

            ctx = CheckContext(params={"paths": [p1, p2], "min_size_bytes": 1})
            result = ArtifactsExist().run(ctx)
            assert result.passed

    def test_missing_file(self):
        ctx = CheckContext(params={"paths": ["/nonexistent/file.md"]})
        result = ArtifactsExist().run(ctx)
        assert not result.passed
        assert "/nonexistent/file.md" in result.details["missing"]

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"")
            ctx = CheckContext(params={"paths": [f.name], "min_size_bytes": 10})
            result = ArtifactsExist().run(ctx)
            assert not result.passed
        os.unlink(f.name)


class TestFileCountInDir:
    def test_enough_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(5):
                open(os.path.join(tmpdir, f"file{i}.txt"), "w").close()
            ctx = CheckContext(params={"path": tmpdir, "min_count": 3})
            result = FileCountInDir().run(ctx)
            assert result.passed

    def test_with_pattern(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            open(os.path.join(tmpdir, "a.py"), "w").close()
            open(os.path.join(tmpdir, "b.txt"), "w").close()
            ctx = CheckContext(params={"path": tmpdir, "min_count": 1, "file_pattern": "*.py"})
            result = FileCountInDir().run(ctx)
            assert result.passed
            assert result.details["count"] == 1


class TestFileModifiedRecently:
    def test_recent_file(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"fresh content")
            ctx = CheckContext(params={"path": f.name, "max_age_seconds": 60})
            result = FileModifiedRecently().run(ctx)
            assert result.passed
        os.unlink(f.name)


# ---------------------------------------------------------------------------
# Code quality checks
# ---------------------------------------------------------------------------


class TestNoSyntaxErrors:
    def test_valid_python(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "good.py")
            with open(path, "w") as f:
                f.write("def hello():\n    return 'world'\n")
            ctx = CheckContext(params={"language": "python", "paths": [tmpdir]})
            result = NoSyntaxErrors().run(ctx)
            assert result.passed

    def test_invalid_python(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "bad.py")
            with open(path, "w") as f:
                f.write("def hello(\n")  # syntax error
            ctx = CheckContext(params={"language": "python", "paths": [tmpdir]})
            result = NoSyntaxErrors().run(ctx)
            assert not result.passed

    def test_valid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "good.json")
            with open(path, "w") as f:
                json.dump({"key": "value"}, f)
            ctx = CheckContext(
                params={"language": "json", "paths": [tmpdir], "file_extensions": [".json"]}
            )
            result = NoSyntaxErrors().run(ctx)
            assert result.passed


class TestNoTodoComments:
    def test_clean_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "clean.py")
            with open(path, "w") as f:
                f.write("def hello():\n    return 'world'\n")
            ctx = CheckContext(params={"paths": [tmpdir]})
            result = NoTodoComments().run(ctx)
            assert result.passed

    def test_finds_todo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "dirty.py")
            with open(path, "w") as f:
                f.write("def hello():\n    # TODO implement this\n    pass\n")
            ctx = CheckContext(params={"paths": [tmpdir]})
            result = NoTodoComments().run(ctx)
            assert not result.passed


class TestScriptExitsZero:
    def test_passing_script(self):
        ctx = CheckContext(
            params={"script": "echo 'hello'"},
            workspace="/tmp",
        )
        result = ScriptExitsZero().run(ctx)
        assert result.passed

    def test_failing_script(self):
        ctx = CheckContext(
            params={"script": "exit 1"},
            workspace="/tmp",
        )
        result = ScriptExitsZero().run(ctx)
        assert not result.passed
        assert result.details["exit_code"] == 1


# ---------------------------------------------------------------------------
# Data checks
# ---------------------------------------------------------------------------


class TestSchemaValid:
    def test_valid_json_with_required_fields(self):
        ctx = CheckContext(
            output_text='{"name": "Den", "version": "1.0", "status": "active"}',
            params={"required_fields": ["name", "version"]},
        )
        result = SchemaValid().run(ctx)
        assert result.passed

    def test_missing_required_field(self):
        ctx = CheckContext(
            output_text='{"name": "Den"}',
            params={"required_fields": ["name", "version"]},
        )
        result = SchemaValid().run(ctx)
        assert not result.passed

    def test_invalid_json(self):
        ctx = CheckContext(output_text="not json at all")
        result = SchemaValid().run(ctx)
        assert not result.passed


class TestJsonFieldValues:
    def test_correct_values(self):
        ctx = CheckContext(
            output_text='{"status": "complete", "score": 0.95}',
            params={"field_checks": [
                {"field": "status", "expected": "complete"},
                {"field": "score", "min": 0.5, "max": 1.0},
            ]},
        )
        result = JsonFieldValues().run(ctx)
        assert result.passed

    def test_wrong_value(self):
        ctx = CheckContext(
            output_text='{"status": "incomplete"}',
            params={"field_checks": [{"field": "status", "expected": "complete"}]},
        )
        result = JsonFieldValues().run(ctx)
        assert not result.passed

    def test_out_of_range(self):
        ctx = CheckContext(
            output_text='{"score": 0.3}',
            params={"field_checks": [{"field": "score", "min": 0.5}]},
        )
        result = JsonFieldValues().run(ctx)
        assert not result.passed


class TestCsvRowCount:
    def test_enough_rows(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,value\na,1\nb,2\nc,3\n")
            f.flush()
            ctx = CheckContext(params={"path": f.name, "min_rows": 2})
            result = CsvRowCount().run(ctx)
            assert result.passed
            assert result.details["row_count"] == 3
        os.unlink(f.name)

    def test_not_enough_rows(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,value\na,1\n")
            f.flush()
            ctx = CheckContext(params={"path": f.name, "min_rows": 5})
            result = CsvRowCount().run(ctx)
            assert not result.passed
        os.unlink(f.name)

    def test_file_not_found(self):
        ctx = CheckContext(params={"path": "/nonexistent.csv", "min_rows": 1})
        result = CsvRowCount().run(ctx)
        assert not result.passed
