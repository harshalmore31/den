"""Data and schema checks -- verify structured output."""

from __future__ import annotations

import csv
import io
import json
import os

from den.checks._base import Check, CheckContext, CheckResult


class SchemaValid(Check):
    """Verify JSON output matches a schema."""

    name = "schema_valid"
    description = "Check that JSON output conforms to a JSON Schema or has required fields."

    def run(self, context: CheckContext) -> CheckResult:
        # Get the JSON to validate
        schema = self._param(context, "schema", None)
        schema_file = self._param(context, "schema_file", None)
        required_fields = self._param(context, "required_fields", None)

        # Try to parse output as JSON
        try:
            data = json.loads(context.output_text)
        except (json.JSONDecodeError, TypeError):
            # Try reading from an output file
            output_files = context.output_files
            data = None
            for f in output_files:
                if f.endswith(".json") and os.path.exists(f):
                    try:
                        with open(f) as fh:
                            data = json.load(fh)
                        break
                    except (json.JSONDecodeError, OSError):
                        continue

            if data is None:
                return CheckResult(
                    name=context.params.get("name", self.name),
                    check_type=self.name,
                    passed=False,
                    message="Could not parse output as JSON ✗",
                )

        # Simple required fields check
        if required_fields and isinstance(data, dict):
            missing = [f for f in required_fields if f not in data]
            if missing:
                return CheckResult(
                    name=context.params.get("name", self.name),
                    check_type=self.name,
                    passed=False,
                    message=f"Missing required fields: {missing} ✗",
                    details={"missing_fields": missing},
                )

        # JSON Schema validation (if jsonschema is available)
        if schema or schema_file:
            if schema_file and os.path.exists(schema_file):
                with open(schema_file) as f:
                    schema = json.load(f)

            if schema:
                try:
                    import jsonschema
                    jsonschema.validate(data, schema)
                except ImportError:
                    # Fallback: just check required fields from schema
                    req = schema.get("required", [])
                    if isinstance(data, dict):
                        missing = [f for f in req if f not in data]
                        if missing:
                            return CheckResult(
                                name=context.params.get("name", self.name),
                                check_type=self.name,
                                passed=False,
                                message=f"Missing fields from schema: {missing} ✗",
                            )
                except jsonschema.ValidationError as e:
                    return CheckResult(
                        name=context.params.get("name", self.name),
                        check_type=self.name,
                        passed=False,
                        message=f"Schema validation failed: {e.message} ✗",
                        details={"error": e.message, "path": list(e.path)},
                    )

        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=True,
            message="Schema validation passed ✓",
        )


class JsonFieldValues(Check):
    """Verify specific JSON fields have expected values."""

    name = "json_field_values"
    description = "Check that specific fields in JSON output have expected values or ranges."

    def run(self, context: CheckContext) -> CheckResult:
        checks = self._param(context, "field_checks", [])
        # Each check: {"field": "status", "expected": "complete"}
        # or: {"field": "score", "min": 0.5, "max": 1.0}

        try:
            data = json.loads(context.output_text)
        except (json.JSONDecodeError, TypeError):
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                message="Could not parse output as JSON ✗",
            )

        failures = []
        for check in checks:
            field = check.get("field", "")
            value = self._get_nested(data, field)

            if value is None:
                failures.append(f"field '{field}' not found")
                continue

            if "expected" in check and value != check["expected"]:
                failures.append(f"{field}: got '{value}', expected '{check['expected']}'")
            if "min" in check and (not isinstance(value, (int, float)) or value < check["min"]):
                failures.append(f"{field}: {value} < {check['min']}")
            if "max" in check and (not isinstance(value, (int, float)) or value > check["max"]):
                failures.append(f"{field}: {value} > {check['max']}")

        passed = len(failures) == 0
        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=1.0 if passed else 0.0,
            message="Field values valid ✓" if passed
                    else f"Field check failures: {'; '.join(failures)} ✗",
            details={"failures": failures},
        )

    @staticmethod
    def _get_nested(data: dict, path: str):
        """Get a nested field using dot notation."""
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current


class CsvRowCount(Check):
    """Verify a CSV file has at least N rows."""

    name = "csv_row_count"
    description = "Check that a CSV file contains a minimum number of data rows."

    def run(self, context: CheckContext) -> CheckResult:
        path = self._param(context, "path", "")
        min_rows = self._param(context, "min_rows", 1)
        has_header = self._param(context, "has_header", True)

        if not os.path.exists(path):
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                message=f"CSV file not found: {path} ✗",
            )

        try:
            with open(path, "r", newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            return CheckResult(
                name=context.params.get("name", self.name),
                check_type=self.name,
                passed=False,
                message=f"Failed to read CSV: {e} ✗",
            )

        data_rows = len(rows) - (1 if has_header else 0)
        passed = data_rows >= min_rows

        return CheckResult(
            name=context.params.get("name", self.name),
            check_type=self.name,
            passed=passed,
            score=min(data_rows / max(min_rows, 1), 1.0),
            message=f"CSV rows: {data_rows} (required: {min_rows})"
                    + (" ✓" if passed else " ✗"),
            details={"row_count": data_rows, "min_rows": min_rows, "path": path},
        )
