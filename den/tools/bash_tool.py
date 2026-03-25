"""bash -- sandboxed shell command execution."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolOutput


class BashTool(DenTool):
    name = "bash"
    description = (
        "Execute a shell command in the sandboxed Docker environment. "
        "You MUST use this tool when the user asks to run commands, check ports, "
        "list processes, or perform system operations. Do NOT just suggest commands — run them. "
        "Available commands: python3, pip, curl, wget, git, jq, grep, find, ls, cat, "
        "head, tail, wc, ps, top, lsof, netstat, ss, nc, df, du, whoami, uname, date, echo. "
        "Pipes (|) work. Use 'command' parameter as a string. "
        "If a command fails, try an alternative (e.g. if lsof fails, try netstat or ss)."
    )
    version = "1.0.0"
    requires_bash = True

    class Input(BaseModel):
        command: str = Field(default="", description="Shell command to execute")
        commands: list[str] = Field(default_factory=list, description="Alias: list of commands (uses first)")
        workdir: str = Field(default="/den/workspace", description="Working directory")
        timeout: int = Field(default=60, description="Timeout in seconds")

        def model_post_init(self, __context: Any) -> None:
            # Accept 'commands' (list) as alias — LLMs sometimes send this
            if not self.command and self.commands:
                self.command = self.commands[0]

    class Output(ToolOutput):
        stdout: str = ""
        stderr: str = ""
        exit_code: int = 0
        duration_ms: int = 0
        blocked: bool = False
        block_reason: str = ""

    def __init__(self, bash_executor=None):
        self._executor = bash_executor

    def set_executor(self, executor) -> None:
        """Set the BashExecutor instance (injected at runtime)."""
        self._executor = executor

    def execute(self, input: Input) -> Output:
        if self._executor is None:
            from den.agentfile.schema import BashConfig
            from den.core.bash_executor import BashExecutor
            self._executor = BashExecutor(BashConfig(enabled=True))

        result = self._executor.execute(
            command=input.command,
            workdir=input.workdir,
            timeout=input.timeout,
        )

        # Make empty output explicit so the LLM understands it
        stdout = result.stdout
        if not stdout and not result.stderr and result.exit_code == 0:
            stdout = "(command succeeded with no output — this means nothing matched or the result is empty)"

        return self.Output(
            success=result.exit_code == 0 and not result.blocked,
            stdout=stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            blocked=result.blocked,
            block_reason=result.block_reason,
        )
