"""Code quality checks -- verify code output."""

from __future__ import annotations

import ast
import os
import re

from den.checks._base import Check, CheckContext, CheckResult


class ScriptExitsZero(Check):
    """Run an arbitrary script and verify it exits 0.

    This is the most flexible check — plug in pytest, ruff, mypy,
    custom validators, schema checkers, or any CLI tool.
    """

    name = "script_exits_zero"
    description = "Run a script and check it exits with code 0."

    def run(self, context: CheckContext) -> CheckResult:
        script = self._param(context, "script", "")
        timeout_str = self._param(context, "timeout", "120s")
        timeout_str = self._param(context, "script_timeout", timeout_str)

        if not script:
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                message="No script provided ✗",
            )

        # Parse timeout
        from den.utils import parse_duration
        try:
            timeout = parse_duration(timeout_str) if isinstance(timeout_str, str) else int(timeout_str)
        except (ValueError, TypeError):
            timeout = 120

        # Use BashExecutor for sandboxed execution
        from den.agentfile.schema import BashConfig
        from den.core.bash_executor import BashExecutor

        executor = BashExecutor(BashConfig(enabled=True, timeout=f"{timeout}s"))
        result = executor.execute(script, workdir=context.workspace, timeout=timeout)

        passed = result.exit_code == 0 and not result.blocked
        output = result.stdout[:2000] if result.stdout else result.stderr[:2000]

        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=f"Script exit code: {result.exit_code}"
                    + (" ✓" if passed else f" ✗\n{output}"),
            details={
                "exit_code": result.exit_code,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:1000],
                "blocked": result.blocked,
                "duration_ms": result.duration_ms,
            },
        )


class NoSyntaxErrors(Check):
    """Verify code files have no syntax errors."""

    name = "no_syntax_errors"
    description = "Check that code files parse without syntax errors."

    def run(self, context: CheckContext) -> CheckResult:
        language = self._param(context, "language", "python")
        paths = self._param(context, "paths", [context.workspace])
        extensions = self._param(context, "file_extensions", None)

        if extensions is None:
            ext_map = {
                "python": [".py"],
                "json": [".json"],
                "yaml": [".yaml", ".yml"],
            }
            extensions = ext_map.get(language, [".py"])

        errors = []
        files_checked = 0

        for base_path in paths:
            if not os.path.exists(base_path):
                continue
            if os.path.isfile(base_path):
                file_list = [base_path]
            else:
                file_list = []
                for root, _, files in os.walk(base_path):
                    for f in files:
                        if any(f.endswith(ext) for ext in extensions):
                            file_list.append(os.path.join(root, f))

            for filepath in file_list:
                files_checked += 1
                error = self._check_syntax(filepath, language)
                if error:
                    errors.append(error)

        passed = len(errors) == 0
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=1.0 if passed else max(0, 1.0 - len(errors) / max(files_checked, 1)),
            message=f"Syntax check: {files_checked} files, {len(errors)} errors"
                    + (" ✓" if passed else f" ✗\n" + "\n".join(errors[:5])),
            details={"files_checked": files_checked, "errors": errors[:10]},
        )

    @staticmethod
    def _check_syntax(filepath: str, language: str) -> str | None:
        if language == "python":
            try:
                with open(filepath, "r") as f:
                    ast.parse(f.read(), filename=filepath)
                return None
            except SyntaxError as e:
                return f"{filepath}:{e.lineno}: {e.msg}"
        elif language == "json":
            import json
            try:
                with open(filepath, "r") as f:
                    json.load(f)
                return None
            except json.JSONDecodeError as e:
                return f"{filepath}: {e}"
        return None


class NoTodoComments(Check):
    """Verify no TODO/FIXME/HACK comments remain in code."""

    name = "no_todo_comments"
    description = "Check that code has no TODO, FIXME, or HACK comments."

    DEFAULT_PATTERNS = ["TODO", "FIXME", "HACK", "XXX", "TEMP"]

    def run(self, context: CheckContext) -> CheckResult:
        patterns = self._param(context, "patterns", self.DEFAULT_PATTERNS)
        paths = self._param(context, "paths", [context.workspace])
        exclude = self._param(context, "exclude_paths", [])

        regex = re.compile(
            r"(?:#|//|/\*|\*)\s*(" + "|".join(re.escape(p) for p in patterns) + r")\b",
            re.IGNORECASE,
        )

        found = []
        files_checked = 0

        for base_path in paths:
            if not os.path.exists(base_path):
                continue
            for root, _, files in os.walk(base_path):
                # Check excludes
                if any(root.startswith(ex) for ex in exclude):
                    continue
                for f in files:
                    if not any(f.endswith(ext) for ext in (".py", ".js", ".ts", ".go", ".rs", ".java")):
                        continue
                    filepath = os.path.join(root, f)
                    files_checked += 1
                    try:
                        with open(filepath, "r", errors="replace") as fh:
                            for i, line in enumerate(fh, 1):
                                if regex.search(line):
                                    found.append(f"{filepath}:{i}: {line.strip()[:80]}")
                    except (OSError, IOError):
                        continue

        passed = len(found) == 0
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=f"TODO/FIXME scan: {files_checked} files, {len(found)} found"
                    + (" ✓" if passed else " ✗\n" + "\n".join(found[:5])),
            details={"files_checked": files_checked, "found": found[:20]},
        )


class LinterPasses(Check):
    """Run a linter and verify clean output."""

    name = "linter_passes"
    description = "Run a linter (ruff, flake8, eslint) and check for clean output."

    LINTER_COMMANDS = {
        "ruff": "python -m ruff check {paths}",
        "flake8": "python -m flake8 {paths}",
        "pylint": "python -m pylint {paths} --disable=all --enable=E",
        "eslint": "npx eslint {paths}",
        "mypy": "python -m mypy {paths} --ignore-missing-imports",
    }

    def run(self, context: CheckContext) -> CheckResult:
        linter = self._param(context, "linter", "ruff")
        paths = self._param(context, "paths", [context.workspace])
        max_warnings = self._param(context, "max_warnings", 0)
        config_file = self._param(context, "config_file", None)

        cmd_template = self.LINTER_COMMANDS.get(linter)
        if not cmd_template:
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                message=f"Unknown linter: {linter}. Available: {list(self.LINTER_COMMANDS.keys())}",
            )

        paths_str = " ".join(paths)
        cmd = cmd_template.format(paths=paths_str)
        if config_file:
            cmd += f" --config {config_file}"

        # Delegate to script_exits_zero
        script_check = ScriptExitsZero()
        script_context = CheckContext(
            params={"name": context.params.get("name", self.name), "script": cmd},
            workspace=context.workspace,
        )
        result = script_check.run(script_context)
        result.check_type = self.name
        return result
