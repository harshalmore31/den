"""Agentfile YAML parser -- reads, resolves env vars, and validates."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from den.agentfile.schema import AgentfileSchema


class AgentfileError(Exception):
    """Base error for Agentfile parsing and validation."""


class AgentfileParseError(AgentfileError):
    """YAML syntax error in the Agentfile."""


class AgentfileValidationError(AgentfileError):
    """Schema validation failed."""

    def __init__(self, message: str, errors: list[dict] | None = None):
        super().__init__(message)
        self.errors = errors or []


def _resolve_env_vars(data: dict) -> dict:
    """Resolve $VAR_NAME references in the env section from host environment."""
    env_section = data.get("env")
    if not env_section or not isinstance(env_section, dict):
        return data

    resolved = {}
    for key, value in env_section.items():
        if isinstance(value, str) and value.startswith("$"):
            env_name = value[1:]
            env_value = os.environ.get(env_name)
            if env_value is None:
                resolved[key] = ""
            else:
                resolved[key] = env_value
        else:
            resolved[key] = value

    data["env"] = resolved
    return data


def _normalize_check_configs(data: dict) -> dict:
    """Normalize algorithmic_checks: extract top-level fields, put rest into params."""
    TOP_LEVEL_KEYS = {"name", "type", "required", "weight"}

    def normalize_checks(checks: list[dict]) -> list[dict]:
        normalized = []
        for check in checks:
            if not isinstance(check, dict):
                continue
            top = {k: v for k, v in check.items() if k in TOP_LEVEL_KEYS}
            params = {k: v for k, v in check.items() if k not in TOP_LEVEL_KEYS}
            top["params"] = params
            normalized.append(top)
        return normalized

    tasks = data.get("tasks", {})
    if isinstance(tasks, dict):
        for task_name, task in tasks.items():
            if not isinstance(task, dict):
                continue

            loop = task.get("loop")
            if isinstance(loop, dict):
                eval_cfg = loop.get("evaluation", {})
                if isinstance(eval_cfg, dict) and "algorithmic_checks" in eval_cfg:
                    eval_cfg["algorithmic_checks"] = normalize_checks(
                        eval_cfg["algorithmic_checks"]
                    )

            phases = task.get("phases", [])
            if isinstance(phases, list):
                for phase in phases:
                    if not isinstance(phase, dict):
                        continue
                    eval_cfg = phase.get("evaluation", {})
                    if isinstance(eval_cfg, dict) and "algorithmic_checks" in eval_cfg:
                        eval_cfg["algorithmic_checks"] = normalize_checks(
                            eval_cfg["algorithmic_checks"]
                        )

    return data


def parse_agentfile(path: str | Path) -> AgentfileSchema:
    """Parse and validate an Agentfile from a file path."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Agentfile not found: {path}")

    raw = path.read_text(encoding="utf-8")
    return parse_agentfile_string(raw)


def parse_agentfile_string(content: str) -> AgentfileSchema:
    """Parse and validate an Agentfile from a YAML string."""
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise AgentfileParseError(f"Invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise AgentfileParseError("Agentfile must be a YAML mapping (dict), not a scalar or list.")

    data = _resolve_env_vars(data)
    data = _normalize_check_configs(data)

    try:
        return AgentfileSchema(**data)
    except ValidationError as e:
        errors = e.errors()
        messages = []
        for err in errors:
            loc = " → ".join(str(x) for x in err["loc"])
            messages.append(f"  {loc}: {err['msg']}")
        detail = "\n".join(messages)
        raise AgentfileValidationError(
            f"Agentfile validation failed:\n{detail}",
            errors=errors,
        ) from e
