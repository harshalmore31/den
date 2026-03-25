"""json_parse -- parse, query, and validate JSON data."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput


class JsonParseTool(DenTool):
    name = "json_parse"
    description = (
        "Parse JSON from a string or file, optionally query specific fields "
        "using dot notation (e.g. 'data.users[0].name'). "
        "Useful for processing API responses, config files, or data files."
    )
    version = "1.0.0"

    class Input(BaseModel):
        content: str | None = Field(default=None, description="JSON string to parse")
        file_path: str | None = Field(default=None, description="Path to JSON file")
        query: str | None = Field(
            default=None,
            description="Dot notation path to extract (e.g. 'data.users[0].name')",
        )

    class Output(ToolOutput):
        data: str = ""  # JSON string of result
        data_type: str = ""
        keys: list[str] = []

    def execute(self, input: Input) -> Output:
        if not input.content and not input.file_path:
            raise ToolError(
                "Provide either 'content' (JSON string) or 'file_path' (path to JSON file).",
            )

        # Load JSON
        if input.file_path:
            try:
                with open(input.file_path, "r") as f:
                    data = json.load(f)
            except FileNotFoundError:
                raise ToolError(f"File not found: {input.file_path}")
            except json.JSONDecodeError as e:
                raise ToolError(f"Invalid JSON in {input.file_path}: {e}")
        else:
            try:
                data = json.loads(input.content)
            except json.JSONDecodeError as e:
                raise ToolError(
                    f"Invalid JSON: {e}",
                    suggestions=["Check for trailing commas", "Ensure proper quoting"],
                )

        # Apply query
        if input.query:
            data = self._query(data, input.query)

        # Format output
        keys = list(data.keys()) if isinstance(data, dict) else []
        data_type = type(data).__name__

        return self.Output(
            data=json.dumps(data, indent=2, default=str)[:32000],
            data_type=data_type,
            keys=keys,
        )

    @staticmethod
    def _query(data: Any, path: str) -> Any:
        """Navigate JSON using dot notation with array support."""
        parts = path.replace("[", ".[").split(".")
        current = data
        for part in parts:
            if not part:
                continue
            if part.startswith("[") and part.endswith("]"):
                idx = int(part[1:-1])
                if not isinstance(current, list):
                    raise ToolError(f"Cannot index non-list with [{idx}]")
                if idx >= len(current):
                    raise ToolError(f"Index {idx} out of range (length {len(current)})")
                current = current[idx]
            elif isinstance(current, dict):
                if part not in current:
                    available = list(current.keys())[:10]
                    raise ToolError(
                        f"Key '{part}' not found. Available keys: {available}",
                    )
                current = current[part]
            else:
                raise ToolError(f"Cannot access '{part}' on {type(current).__name__}")
        return current
