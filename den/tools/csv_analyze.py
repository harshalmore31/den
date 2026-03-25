"""csv_analyze -- read, analyze, and query CSV data."""

from __future__ import annotations

import csv
import io
import json
import re

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput


class CsvAnalyzeTool(DenTool):
    name = "csv_analyze"
    description = (
        "Read and analyze CSV files. Returns summary statistics, column info, "
        "and optionally filtered/queried rows. Use for data analysis tasks. "
        "For large files, returns a summary rather than all rows."
    )
    version = "1.0.0"
    requires_filesystem = True

    class Input(BaseModel):
        path: str = Field(description="Path to CSV file")
        query: str | None = Field(
            default=None,
            description="Filter expression: 'column_name == value' or 'column_name > 100'",
        )
        columns: list[str] | None = Field(default=None, description="Select specific columns")
        max_rows: int = Field(default=50, description="Maximum rows to return")
        summary_only: bool = Field(default=False, description="Return only summary statistics")

    class Output(ToolOutput):
        columns: list[str] = []
        row_count: int = 0
        sample_rows: list[dict] = []
        summary: str = ""
        truncated: bool = False

    def execute(self, input: Input) -> Output:
        try:
            with open(input.path, "r", newline="", encoding="utf-8-sig") as f:
                content = f.read()
        except FileNotFoundError:
            raise ToolError(f"CSV file not found: {input.path}")

        try:
            reader = csv.DictReader(io.StringIO(content))
            all_rows = list(reader)
            columns = reader.fieldnames or []
        except Exception as e:
            raise ToolError(f"Failed to parse CSV: {e}")

        if not all_rows:
            return self.Output(columns=list(columns), row_count=0, summary="Empty CSV file.")

        # Column selection
        if input.columns:
            for col in input.columns:
                if col not in columns:
                    raise ToolError(
                        f"Column '{col}' not found. Available: {list(columns)}",
                    )
            columns = input.columns
            all_rows = [{k: r[k] for k in columns if k in r} for r in all_rows]

        # Filtering
        rows = all_rows
        if input.query:
            rows = self._filter(all_rows, input.query)

        # Summary
        summary_lines = [
            f"File: {input.path}",
            f"Total rows: {len(all_rows)}",
            f"Columns ({len(columns)}): {', '.join(str(c) for c in columns)}",
        ]

        if input.query:
            summary_lines.append(f"Filtered rows: {len(rows)}")

        # Numeric column stats
        for col in columns:
            vals = []
            for r in all_rows:
                try:
                    vals.append(float(r.get(col, "")))
                except (ValueError, TypeError):
                    continue
            if vals:
                summary_lines.append(
                    f"  {col}: min={min(vals):.2f}, max={max(vals):.2f}, "
                    f"avg={sum(vals)/len(vals):.2f}"
                )

        sample = rows[:input.max_rows] if not input.summary_only else []

        return self.Output(
            columns=list(columns),
            row_count=len(all_rows),
            sample_rows=sample,
            summary="\n".join(summary_lines),
            truncated=len(rows) > input.max_rows,
        )

    @staticmethod
    def _filter(rows: list[dict], query: str) -> list[dict]:
        """Simple filter: 'column == value' or 'column > 100'."""
        match = re.match(r"(\w+)\s*(==|!=|>|<|>=|<=|contains)\s*(.+)", query.strip())
        if not match:
            return rows

        col, op, val = match.group(1), match.group(2), match.group(3).strip().strip("'\"")

        filtered = []
        for row in rows:
            cell = row.get(col, "")
            try:
                if op == "==" and str(cell) == val:
                    filtered.append(row)
                elif op == "!=" and str(cell) != val:
                    filtered.append(row)
                elif op == "contains" and val.lower() in str(cell).lower():
                    filtered.append(row)
                elif op in (">", "<", ">=", "<="):
                    if op == ">" and float(cell) > float(val):
                        filtered.append(row)
                    elif op == "<" and float(cell) < float(val):
                        filtered.append(row)
                    elif op == ">=" and float(cell) >= float(val):
                        filtered.append(row)
                    elif op == "<=" and float(cell) <= float(val):
                        filtered.append(row)
            except (ValueError, TypeError):
                continue
        return filtered
