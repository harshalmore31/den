"""Den Tool base class and types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel


class ToolError(Exception):
    """Actionable error from a tool."""

    def __init__(self, message: str, suggestions: list[str] | None = None):
        super().__init__(message)
        self.suggestions = suggestions or []

    def __str__(self) -> str:
        msg = super().__str__()
        if self.suggestions:
            msg += "\nSuggestions:\n" + "\n".join(f"  - {s}" for s in self.suggestions)
        return msg


class ToolOutput(BaseModel):
    """Base output model for all tools."""

    success: bool = True
    error: str = ""


@dataclass
class ToolSpec:
    """Metadata about a tool."""

    name: str
    description: str
    version: str
    requires_network: bool = False
    requires_bash: bool = False
    requires_filesystem: bool = False
    allowed_callers: list[str] = field(default_factory=lambda: ["agent", "code_execution"])
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


class DenTool(ABC):
    """Base class for all Den tools.

    Subclass this, define Input/Output as inner Pydantic models,
    and implement execute(). The tool is callable both as a traditional
    LLM tool_use call and as a Python function for programmatic calling.
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"
    requires_network: bool = False
    requires_bash: bool = False
    requires_filesystem: bool = False
    allowed_callers: list[str] = ["agent", "code_execution"]

    class Input(BaseModel):
        pass

    class Output(ToolOutput):
        pass

    @abstractmethod
    def execute(self, input: Input) -> Output:
        ...

    def __call__(self, **kwargs: Any) -> dict:
        """Callable interface for programmatic tool calling."""
        validated_input = self.Input(**kwargs)
        try:
            output = self.execute(validated_input)
            return output.model_dump()
        except ToolError:
            raise
        except Exception as e:
            return {"success": False, "error": f"Tool error: {type(e).__name__}: {e}"}

    def get_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            version=self.version,
            requires_network=self.requires_network,
            requires_bash=self.requires_bash,
            requires_filesystem=self.requires_filesystem,
            allowed_callers=self.allowed_callers,
            input_schema=self.Input.model_json_schema(),
            output_schema=self.Output.model_json_schema(),
        )

    def get_pydantic_ai_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.Input.model_json_schema(),
        }
