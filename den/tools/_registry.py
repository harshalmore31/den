"""Tool registry -- discovers, registers, and loads Den tools."""

from __future__ import annotations

from typing import Any

from den.tools._base import DenTool, ToolSpec


class ToolRegistry:
    """Central registry of all Den tools."""

    def __init__(self) -> None:
        self._tools: dict[str, DenTool] = {}

    def register(self, tool: DenTool) -> None:
        if not tool.name:
            raise ValueError(f"Tool {tool.__class__.__name__} has no name set.")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> DenTool | None:
        return self._tools.get(name)

    def get_spec(self, name: str) -> ToolSpec | None:
        tool = self._tools.get(name)
        if tool:
            return tool.get_spec()
        return None

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def list_specs(self) -> list[ToolSpec]:
        return [t.get_spec() for t in self._tools.values()]

    def load_tools(self, tool_names: list[str]) -> dict[str, DenTool]:
        """Load a subset of tools by name (as declared in Agentfile)."""
        loaded = {}
        for name in tool_names:
            tool = self._tools.get(name)
            if tool is None:
                available = ", ".join(self.list_tools())
                raise ValueError(
                    f"Unknown tool '{name}'. Available tools: {available}"
                )
            loaded[name] = tool
        return loaded

    def get_callables(self, tool_names: list[str]) -> dict[str, Any]:
        """Get callable functions for programmatic tool calling."""
        tools = self.load_tools(tool_names)
        return {name: tool.__call__ for name, tool in tools.items()}

    @property
    def count(self) -> int:
        return len(self._tools)


_global_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    return _global_registry


def register_tool(tool: DenTool) -> DenTool:
    _global_registry.register(tool)
    return tool
