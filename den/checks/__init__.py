"""Den Checks Library -- algorithmic quality gates for the Loop Architecture."""

from den.checks._base import Check, CheckContext, CheckResult
from den.checks._registry import CheckRegistry, get_check_registry, register_check

from den.checks.content import MinWordCount, SourcesPresent, NoPlaceholderText, SectionsPresent
from den.checks.questions import AllQuestionsAddressed
from den.checks.filesystem import ArtifactsExist, FileCountInDir, FileModifiedRecently
from den.checks.code_quality import ScriptExitsZero, NoSyntaxErrors, NoTodoComments, LinterPasses
from den.checks.data import SchemaValid, JsonFieldValues, CsvRowCount


def _register_standard_checks() -> None:
    registry = get_check_registry()
    checks = [
        MinWordCount(),
        SourcesPresent(),
        NoPlaceholderText(),
        SectionsPresent(),
        AllQuestionsAddressed(),
        ArtifactsExist(),
        FileCountInDir(),
        FileModifiedRecently(),
        ScriptExitsZero(),
        NoSyntaxErrors(),
        NoTodoComments(),
        LinterPasses(),
        SchemaValid(),
        JsonFieldValues(),
        CsvRowCount(),
    ]
    for check in checks:
        try:
            registry.register(check)
        except ValueError:
            pass


_register_standard_checks()

__all__ = [
    "Check",
    "CheckContext",
    "CheckRegistry",
    "CheckResult",
    "get_check_registry",
    "register_check",
    "MinWordCount",
    "SourcesPresent",
    "NoPlaceholderText",
    "SectionsPresent",
    "AllQuestionsAddressed",
    "ArtifactsExist",
    "FileCountInDir",
    "FileModifiedRecently",
    "ScriptExitsZero",
    "NoSyntaxErrors",
    "NoTodoComments",
    "LinterPasses",
    "SchemaValid",
    "JsonFieldValues",
    "CsvRowCount",
]
