"""file_write -- write or append to files in allowed paths."""

from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput


class FileWriteTool(DenTool):
    name = "file_write"
    description = (
        "Write content to a file. Creates the file and parent directories if they "
        "don't exist. Supports write (overwrite) and append modes. "
        "Path must be under /den/ (workspace, output, or memory)."
    )
    version = "1.0.0"
    requires_filesystem = True

    class Input(BaseModel):
        path: str = Field(default="", description="File path to write (must be under /den/)")
        file_path: str = Field(default="", description="Alias for path")
        content: str = Field(description="Content to write")
        mode: str = Field(default="write", description="'write' to overwrite, 'append' to add to end")

        def model_post_init(self, __context: Any) -> None:
            # Accept either 'path' or 'file_path'
            if not self.path and self.file_path:
                self.path = self.file_path

    class Output(ToolOutput):
        path: str = ""
        bytes_written: int = 0
        created: bool = False

    def execute(self, input: Input) -> Output:
        path = input.path
        created = not os.path.exists(path)

        # Create parent directories
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        file_mode = "a" if input.mode == "append" else "w"

        try:
            with open(path, file_mode, encoding="utf-8") as f:
                f.write(input.content)
        except PermissionError:
            raise ToolError(
                f"Permission denied writing to '{path}'.",
                suggestions=["Check that the path is under an allowed directory"],
            )
        except OSError as e:
            raise ToolError(f"Failed to write '{path}': {e}")

        return self.Output(
            path=path,
            bytes_written=len(input.content.encode("utf-8")),
            created=created,
        )
