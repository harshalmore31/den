"""file_list -- list directory contents with optional filtering."""

from __future__ import annotations

import fnmatch
import os

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput


class FileListEntry(BaseModel):
    name: str
    path: str
    is_dir: bool
    size_bytes: int = 0


class FileListTool(DenTool):
    name = "file_list"
    description = (
        "List files and directories. Returns names, sizes, and types. "
        "Supports recursive listing and glob filtering. "
        "Path must be under /den/."
    )
    version = "1.0.0"
    requires_filesystem = True

    class Input(BaseModel):
        path: str = Field(default="/den/workspace", description="Directory to list")
        recursive: bool = Field(default=False, description="List subdirectories recursively")
        pattern: str | None = Field(default=None, description="Glob pattern filter (e.g. '*.py')")
        max_entries: int = Field(default=100, description="Maximum entries to return")

    class Output(ToolOutput):
        entries: list[FileListEntry] = []
        total_count: int = 0
        truncated: bool = False

    def execute(self, input: Input) -> Output:
        path = input.path

        if not os.path.exists(path):
            raise ToolError(
                f"Directory not found: {path}",
                suggestions=["Check the path", "Use /den/workspace or /den/output"],
            )

        if not os.path.isdir(path):
            raise ToolError(f"'{path}' is a file, not a directory. Use file_read to read it.")

        entries = []
        try:
            if input.recursive:
                for root, dirs, files in os.walk(path):
                    for name in dirs + files:
                        full = os.path.join(root, name)
                        if input.pattern:
                            if not fnmatch.fnmatch(name, input.pattern):
                                continue
                        is_dir = os.path.isdir(full)
                        size = 0 if is_dir else os.path.getsize(full)
                        entries.append(FileListEntry(
                            name=name, path=full, is_dir=is_dir, size_bytes=size,
                        ))
                        if len(entries) >= input.max_entries:
                            return self.Output(
                                entries=entries,
                                total_count=len(entries),
                                truncated=True,
                            )
            else:
                for name in sorted(os.listdir(path)):
                    if input.pattern:
                        if not fnmatch.fnmatch(name, input.pattern):
                            continue
                    full = os.path.join(path, name)
                    is_dir = os.path.isdir(full)
                    size = 0 if is_dir else os.path.getsize(full)
                    entries.append(FileListEntry(
                        name=name, path=full, is_dir=is_dir, size_bytes=size,
                    ))
                    if len(entries) >= input.max_entries:
                        break
        except PermissionError:
            raise ToolError(f"Permission denied reading '{path}'.")

        return self.Output(
            entries=entries,
            total_count=len(entries),
            truncated=len(entries) >= input.max_entries,
        )
