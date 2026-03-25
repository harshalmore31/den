"""Filesystem checks -- verify artifacts were produced."""

from __future__ import annotations

import fnmatch
import os
import time

from den.checks._base import Check, CheckContext, CheckResult


class ArtifactsExist(Check):
    """Verify required output files or directories were created."""

    name = "artifacts_exist"
    description = "Check that required artifact files/directories exist and are non-empty."

    def run(self, context: CheckContext) -> CheckResult:
        paths = self._param(context, "paths", [])
        min_size = self._param(context, "min_size_bytes", 1)

        found = []
        missing = []
        too_small = []

        for path in paths:
            if os.path.exists(path):
                if os.path.isdir(path):
                    found.append(path)
                else:
                    size = os.path.getsize(path)
                    if size >= min_size:
                        found.append(path)
                    else:
                        too_small.append(f"{path} ({size}B < {min_size}B)")
            else:
                missing.append(path)

        issues = missing + too_small
        passed = len(issues) == 0

        message_parts = [f"Artifacts: {len(found)}/{len(paths)} present"]
        if missing:
            message_parts.append(f"missing: {', '.join(missing)}")
        if too_small:
            message_parts.append(f"too small: {', '.join(too_small)}")

        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=len(found) / max(len(paths), 1),
            message=" | ".join(message_parts) + (" ✓" if passed else " ✗"),
            details={"found": found, "missing": missing, "too_small": too_small},
        )


class FileCountInDir(Check):
    """Verify a directory contains at least N files."""

    name = "file_count_in_dir"
    description = "Check that a directory contains a minimum number of files."

    def run(self, context: CheckContext) -> CheckResult:
        path = self._param(context, "path", context.output_dir)
        min_count = self._param(context, "min_count", 1)
        pattern = self._param(context, "file_pattern", None)

        if not os.path.isdir(path):
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                score=0.0,
                message=f"Directory not found: {path} ✗",
            )

        files = []
        for name in os.listdir(path):
            full = os.path.join(path, name)
            if os.path.isfile(full):
                if pattern and not fnmatch.fnmatch(name, pattern):
                    continue
                files.append(name)

        count = len(files)
        passed = count >= min_count
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=min(count / max(min_count, 1), 1.0),
            message=f"Files in {path}: {count} (required: {min_count})"
                    + (" ✓" if passed else " ✗"),
            details={"count": count, "files": files[:20], "min_count": min_count},
        )


class FileModifiedRecently(Check):
    """Verify a file was modified within the current task run."""

    name = "file_modified_recently"
    description = "Check that a file was modified recently (not stale from a prior run)."

    def run(self, context: CheckContext) -> CheckResult:
        path = self._param(context, "path", "")
        max_age = self._param(context, "max_age_seconds", 300)

        if not os.path.exists(path):
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                score=0.0,
                message=f"File not found: {path} ✗",
            )

        mtime = os.path.getmtime(path)
        age = time.time() - mtime
        passed = age <= max_age

        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message=f"File age: {int(age)}s (max: {max_age}s)"
                    + (" ✓" if passed else " ✗ — file is stale"),
            details={"age_seconds": int(age), "max_age_seconds": max_age, "path": path},
        )
