"""python_exec -- execute Python code snippets in a restricted subprocess."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

from pydantic import BaseModel, Field

from den.tools._base import DenTool, ToolError, ToolOutput

MAX_OUTPUT = 32_000


class PythonExecTool(DenTool):
    name = "python_exec"
    description = (
        "Execute a Python code snippet and return its output. "
        "Runs in a separate subprocess with timeout enforcement. "
        "Output is captured from print() statements. "
        "Use for data processing, calculations, and scripting tasks."
    )
    version = "1.1.0"

    class Input(BaseModel):
        code: str = Field(description="Python code to execute")
        timeout: int = Field(default=30, description="Timeout in seconds")

    class Output(ToolOutput):
        stdout: str = ""
        stderr: str = ""
        return_value: str = ""

    def execute(self, input: Input) -> Output:
        # Run in a subprocess for isolation and real timeout enforcement
        wrapper = textwrap.dedent(f"""\
        import sys, json
        try:
            exec({json.dumps(input.code)})
        except Exception:
            import traceback
            traceback.print_exc()
            sys.exit(1)
        """)

        try:
            result = subprocess.run(
                [sys.executable, "-c", wrapper],
                capture_output=True,
                text=True,
                timeout=input.timeout,
                env=self._restricted_env(),
            )
        except subprocess.TimeoutExpired:
            return self.Output(
                success=False,
                stderr=f"Code execution timed out after {input.timeout}s",
                error=f"Timeout after {input.timeout}s",
            )
        except Exception as e:
            return self.Output(
                success=False,
                stderr=str(e),
                error=str(e),
            )

        stdout = result.stdout[:MAX_OUTPUT]
        stderr = result.stderr[:MAX_OUTPUT]

        return self.Output(
            success=result.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            error=stderr.strip().split("\n")[-1] if result.returncode != 0 and stderr else "",
        )

    @staticmethod
    def _restricted_env() -> dict[str, str]:
        """Minimal environment for subprocess execution."""
        import os
        return {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "PYTHONPATH": os.environ.get("PYTHONPATH", ""),
        }
