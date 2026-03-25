"""Shared utility functions for Den."""

from __future__ import annotations

import math
import re

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(s|m|h|d)$", re.IGNORECASE)
_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(b|kb|mb|gb|tb)$", re.IGNORECASE)

_DURATION_MULTIPLIERS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_SIZE_MULTIPLIERS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}


def parse_duration(value: str) -> int:
    """Parse a human-readable duration string to seconds (e.g. '30s', '5m', '2h')."""
    match = _DURATION_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid duration: '{value}'. Use format like '30s', '5m', '2h'.")
    amount, unit = float(match.group(1)), match.group(2).lower()
    return int(amount * _DURATION_MULTIPLIERS[unit])


def parse_size(value: str) -> int:
    """Parse a human-readable size string to bytes (e.g. '500mb', '4gb')."""
    match = _SIZE_RE.match(value.strip())
    if not match:
        raise ValueError(f"Invalid size: '{value}'. Use format like '500mb', '4gb'.")
    amount, unit = float(match.group(1)), match.group(2).lower()
    return int(amount * _SIZE_MULTIPLIERS[unit])


def sigmoid(x: float) -> float:
    """Standard sigmoid function."""
    return 1.0 / (1.0 + math.exp(-x))
