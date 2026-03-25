"""file_read -- read files with optional search and line ranges."""

from __future__ import annotations

import os
import re
from typing import Any

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput

MAX_SIZE = 64_000  # bytes


class FileReadTool(DenTool):
    name = "file_read"
    description = (
        "Read a file from the workspace. Supports optional content search "
        "and line ranges. Use this instead of bash cat/head/tail/grep. "
        "Path must be under /den/ (workspace, output, or memory)."
    )
    version = "1.0.0"
    requires_filesystem = True

    class Input(BaseModel):
        path: str = Field(default="", description="File path to read (must be under /den/)")
        file_path: str = Field(default="", description="Alias for path")

        def model_post_init(self, __context: Any) -> None:
            if not self.path and self.file_path:
                self.path = self.file_path
        search: str | None = Field(
            default=None,
            description="Optional: search for this text and return matching lines with context",
        )
        line_start: int | None = Field(default=None, description="Optional: start reading from this line (1-indexed)")
        line_end: int | None = Field(default=None, description="Optional: stop reading at this line")

    class Output(ToolOutput):
        content: str = ""
        path: str = ""
        lines: int = 0
        size_bytes: int = 0
        truncated: bool = False

    def execute(self, input: Input) -> Output:
        path = input.path

        if not os.path.exists(path):
            # List available files in the directory for a helpful error
            parent = os.path.dirname(path)
            available = []
            if os.path.isdir(parent):
                available = os.listdir(parent)[:20]
            raise ToolError(
                f"File not found: {path}",
                suggestions=[
                    f"Available in {parent}/: {', '.join(available)}" if available else "Check the path",
                    "Use file_list to browse directories",
                ],
            )

        if os.path.isdir(path):
            raise ToolError(
                f"'{path}' is a directory, not a file. Use file_list to browse directories.",
            )

        size = os.path.getsize(path)
        if size > MAX_SIZE:
            # Read partial
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(MAX_SIZE)
            return self.Output(
                content=content,
                path=path,
                lines=content.count("\n"),
                size_bytes=size,
                truncated=True,
            )

        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        # Apply line range
        if input.line_start or input.line_end:
            start = (input.line_start or 1) - 1
            end = input.line_end or len(lines)
            lines = lines[start:end]

        # Apply search filter
        if input.search:
            pattern = re.compile(re.escape(input.search), re.IGNORECASE)
            matching = []
            for i, line in enumerate(lines):
                if pattern.search(line):
                    # Include 2 lines of context
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    for j in range(start, end):
                        matching.append(f"{j + 1}: {lines[j]}")
                    matching.append("---")
            content = "".join(matching) if matching else f"No matches for '{input.search}'"
        else:
            content = "".join(lines)

        return self.Output(
            content=content,
            path=path,
            lines=len(lines),
            size_bytes=size,
        )
