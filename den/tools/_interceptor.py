"""Permission interceptor -- wraps every tool call with security checks."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from den.agentfile.schema import Permissions
from den.tools._base import DenTool, ToolError


class PermissionInterceptor:
    """Wraps tool calls with default-deny permission enforcement."""

    def __init__(self, permissions: Permissions):
        self.permissions = permissions

    def wrap(self, tool: DenTool) -> DenTool:
        """Wrap a tool's execute() with permission checks."""
        original_execute = tool.execute
        interceptor = self

        def checked_execute(input_data: tool.Input) -> tool.Output:
            interceptor.check(tool, input_data)
            return original_execute(input_data)

        tool.execute = checked_execute
        return tool

    def check(self, tool: DenTool, input_data: Any) -> None:
        if tool.requires_network:
            if not self.permissions.network:
                raise ToolError(
                    "Network access denied: no hosts are allowed. "
                    "Add hosts to permissions.network in your Agentfile.",
                )
            url = getattr(input_data, "url", None)
            if url and url.startswith("http"):
                self._check_network(url)

        if tool.requires_filesystem:
            path = getattr(input_data, "path", None)
            if path:
                self._check_filesystem(path)

        if tool.requires_bash and not self.permissions.shell:
            raise ToolError(
                "Shell execution is not permitted. "
                "Set permissions.shell: true in your Agentfile to enable bash tools."
            )

    def _check_network(self, url: str) -> None:
        try:
            host = urlparse(url).hostname
        except Exception:
            host = url

        if not host:
            return

        for pattern in self.permissions.network:
            if fnmatch.fnmatch(host, pattern):
                return

        raise ToolError(
            f"Network access denied: '{host}' is not in the allowed network list. "
            f"Allowed hosts: {self.permissions.network}. "
            f"Add '{host}' to permissions.network in your Agentfile.",
            suggestions=[
                f"Add '{host}' to permissions.network in your Agentfile",
                "Use a different URL from an allowed host",
            ],
        )

    def _check_filesystem(self, path: str) -> None:
        """Check file path, resolving to prevent traversal attacks."""
        resolved = str(Path(path).resolve())

        for allowed in self.permissions.filesystem:
            allowed_resolved = str(Path(allowed).resolve())
            if resolved.startswith(allowed_resolved):
                return

        raise ToolError(
            f"Filesystem access denied: '{path}' (resolved: {resolved}) "
            f"is not under any allowed path. "
            f"Allowed paths: {self.permissions.filesystem}",
            suggestions=[
                f"Use a path under one of: {self.permissions.filesystem}",
                "Add the required path to permissions.filesystem in your Agentfile",
            ],
        )
