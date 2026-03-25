"""Sandboxed bash execution for Den agents."""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field

from den.agentfile.schema import BashConfig

MAX_OUTPUT = 32_000

ALWAYS_BLOCKED = [
    r":\(\)\{.*\}",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r">\s*/dev/sd[a-z]",
    r"\b(shutdown|reboot|halt|poweroff)\b",
]

ALWAYS_SAFE = [
    "ls", "pwd", "echo", "cat", "head", "tail", "wc", "date", "whoami",
    "which", "type", "file", "stat", "du", "df", "uname", "env", "printenv",
    "uptime", "ps", "hostname", "id", "arch",
]

CHAIN_OPERATORS = re.compile(r"[;&`]|\$\(|&&|\|\|")


@dataclass
class BashResult:
    """Result of a bash command execution."""

    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    blocked: bool = False
    block_reason: str = ""
    timed_out: bool = False


@dataclass
class BashAuditEntry:
    """Audit log entry for a bash execution."""

    timestamp: float
    command: str
    exit_code: int
    duration_ms: int
    blocked: bool
    block_reason: str = ""


class BashExecutor:
    """Sandboxed bash executor for Den agents.

    Security layers: always-blocked patterns, user deny/allow lists,
    timeout enforcement, output size limiting, and audit logging.
    """

    def __init__(self, config: BashConfig):
        self.config = config
        self.audit_log: list[BashAuditEntry] = []

    def execute(
        self,
        command: str,
        workdir: str = "/den/workspace",
        timeout: int | None = None,
    ) -> BashResult:
        """Execute a command in the sandboxed environment."""
        if not self.config.enabled:
            return BashResult(
                command=command, exit_code=1,
                stdout="", stderr="Bash execution is disabled in Agentfile.",
                duration_ms=0, blocked=True, block_reason="bash disabled",
            )

        for pattern in ALWAYS_BLOCKED:
            if re.search(pattern, command):
                return self._blocked(command, f"matches dangerous pattern")

        for blocked in self.config.blocked_commands:
            if " " in blocked:
                if blocked in command:
                    return self._blocked(command, f"blocked: '{blocked}'")
            else:
                if re.search(rf"\b{re.escape(blocked)}\b", command):
                    return self._blocked(command, f"blocked: '{blocked}'")

        stripped = re.sub(r"'[^']*'|\"[^\"]*\"", "", command)
        if CHAIN_OPERATORS.search(stripped):
            return self._blocked(command, "dangerous chaining (;, &, `, $()) detected")

        if self.config.allowed_commands:
            cmd_base = command.strip().split()[0] if command.strip() else ""
            is_allowed = any(
                command.strip().startswith(a) or cmd_base == a
                for a in self.config.allowed_commands
            )
            is_safe = any(command.strip().startswith(s) for s in ALWAYS_SAFE)
            if not is_allowed and not is_safe:
                return self._blocked(command, f"not in allowed_commands")

        timeout_sec = timeout or self.config.timeout_seconds
        start = time.monotonic()

        try:
            cwd = workdir if os.path.isdir(workdir) else os.getcwd()
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=cwd,
                env=self._safe_env(),
            )
            duration = int((time.monotonic() - start) * 1000)

            bash_result = BashResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout[:MAX_OUTPUT],
                stderr=result.stderr[:MAX_OUTPUT],
                duration_ms=duration,
            )

        except subprocess.TimeoutExpired:
            duration = int((time.monotonic() - start) * 1000)
            bash_result = BashResult(
                command=command,
                exit_code=124,
                stdout="",
                stderr=f"Command timed out after {timeout_sec}s",
                duration_ms=duration,
                timed_out=True,
            )

        except Exception as e:
            duration = int((time.monotonic() - start) * 1000)
            bash_result = BashResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=str(e),
                duration_ms=duration,
            )

        self.audit_log.append(BashAuditEntry(
            timestamp=time.time(),
            command=command,
            exit_code=bash_result.exit_code,
            duration_ms=bash_result.duration_ms,
            blocked=False,
        ))

        return bash_result

    def _blocked(self, command: str, reason: str) -> BashResult:
        self.audit_log.append(BashAuditEntry(
            timestamp=time.time(),
            command=command,
            exit_code=-1,
            duration_ms=0,
            blocked=True,
            block_reason=reason,
        ))
        return BashResult(
            command=command,
            exit_code=1,
            stdout="",
            stderr=f"BLOCKED: {reason}",
            duration_ms=0,
            blocked=True,
            block_reason=reason,
        )

    @staticmethod
    def _safe_env() -> dict[str, str]:
        """Build a minimal environment that does not leak host secrets."""
        return {
            "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/root"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "TERM": os.environ.get("TERM", "xterm"),
            "CI": "true",
            "NONINTERACTIVE": "1",
            "DEBIAN_FRONTEND": "noninteractive",
        }

    def get_audit_log(self) -> list[dict]:
        return [
            {
                "timestamp": e.timestamp,
                "command": e.command,
                "exit_code": e.exit_code,
                "duration_ms": e.duration_ms,
                "blocked": e.blocked,
                "block_reason": e.block_reason,
            }
            for e in self.audit_log
        ]
