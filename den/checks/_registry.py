"""Check registry -- discovers and loads checks by type name."""

from __future__ import annotations

from den.checks._base import Check


class CheckRegistry:
    """Central registry of all Den checks."""

    def __init__(self) -> None:
        self._checks: dict[str, Check] = {}

    def register(self, check: Check) -> None:
        if not check.name:
            raise ValueError(f"Check {check.__class__.__name__} has no name.")
        self._checks[check.name] = check

    def get(self, name: str) -> Check | None:
        return self._checks.get(name)

    def list_checks(self) -> list[str]:
        return sorted(self._checks.keys())

    @property
    def count(self) -> int:
        return len(self._checks)


_global_check_registry = CheckRegistry()


def get_check_registry() -> CheckRegistry:
    return _global_check_registry


def register_check(check: Check) -> Check:
    _global_check_registry.register(check)
    return check
