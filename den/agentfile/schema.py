"""Pydantic v2 models for the Den Agentfile specification."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from den.utils import parse_duration, parse_size

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class BashConfig(BaseModel):
    """Sandboxed bash execution configuration."""

    enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(
        default_factory=lambda: ["rm -rf /", "sudo", "chmod 777", ":(){:|:&};:"]
    )
    timeout: str = "60s"

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: str) -> str:
        parse_duration(v)
        return v

    @property
    def timeout_seconds(self) -> int:
        return parse_duration(self.timeout)


class MemoryConfig(BaseModel):
    """Memory system configuration."""

    max_size: str = "2gb"

    @field_validator("max_size")
    @classmethod
    def validate_max_size(cls, v: str) -> str:
        parse_size(v)
        return v

    @property
    def max_size_bytes(self) -> int:
        return parse_size(self.max_size)


class CheckConfig(BaseModel):
    """A single algorithmic check in an evaluation."""

    name: str
    type: str
    required: bool = True
    weight: float = 1.0
    params: dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        pass


class EvaluationConfig(BaseModel):
    """Evaluation configuration for a loop or phase."""

    method: Literal["algorithmic", "self-judge", "hybrid", "script", "llm-judge"] = "hybrid"
    algorithmic_checks: list[dict[str, Any]] = Field(default_factory=list)
    qualitative_checks: dict[str, Any] = Field(default_factory=dict)
    script: str | None = None
    script_timeout: str = "120s"
    criteria: list[str] = Field(default_factory=list)
    run_if_algorithmic_passes: bool = True

    @field_validator("script_timeout")
    @classmethod
    def validate_script_timeout(cls, v: str) -> str:
        parse_duration(v)
        return v


class ContextBudget(BaseModel):
    """Context budget management for loop iterations."""

    memory_tokens: int = Field(default=500, description="Max tokens for memory injection")
    feedback_tokens: int = Field(default=1000, description="Max tokens for prior feedback")
    clear_tool_results: bool = Field(default=True, description="Drop intermediate tool results between iterations")


class ToolExecutionConfig(BaseModel):
    """Tool execution mode configuration."""

    mode: Literal["auto", "programmatic", "traditional"] = "auto"


class TransitionConfig(BaseModel):
    """Transition behavior after a phase passes or fails."""

    behavior: Literal["next", "goto", "stop", "notify"] = "next"
    goto: str | None = None
    max_retries: int = 1
    feedback: str | None = None
    condition: str | None = None
    write_failure_report: str | None = None
    notify: bool = False


class PhaseTransitions(BaseModel):
    """Transition config for both pass and fail outcomes."""

    on_pass: TransitionConfig = Field(default_factory=lambda: TransitionConfig(behavior="next"))
    on_fail: TransitionConfig = Field(default_factory=lambda: TransitionConfig(behavior="stop"))


class QuestionConfig(BaseModel):
    """A question in a research loop."""

    id: str
    text: str
    required: bool = True


class LoopConfig(BaseModel):
    """Single-phase loop configuration."""

    max_iterations: int = Field(default=5, ge=1, le=50)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    on_fail: Literal["retry_with_feedback", "stop", "notify"] = "notify"
    cooldown: str = "30s"
    context_budget: ContextBudget = Field(default_factory=ContextBudget)

    @field_validator("cooldown")
    @classmethod
    def validate_cooldown(cls, v: str) -> str:
        parse_duration(v)
        return v

    @property
    def cooldown_seconds(self) -> int:
        return parse_duration(self.cooldown)


class ArtifactConfig(BaseModel):
    """Expected artifact from a task or phase."""

    path: str
    type: Literal[
        "markdown", "json", "csv", "html", "pdf",
        "code", "image", "directory", "any",
    ] = "any"
    required: bool = True


class PhaseConfig(BaseModel):
    """A single phase in a multi-phase loop architecture."""

    name: str
    type: Literal["research", "plan", "execution", "verification", "custom"] = "custom"
    description: str | None = None
    questions: list[QuestionConfig] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    input_from: list[str] = Field(default_factory=list)
    evaluation: EvaluationConfig = Field(default_factory=EvaluationConfig)
    max_iterations: int = Field(default=3, ge=1, le=50)
    cooldown: str = "15s"
    approval: Literal["user", "auto", "skip"] = "skip"
    transitions: PhaseTransitions = Field(default_factory=PhaseTransitions)
    artifacts: list[ArtifactConfig] = Field(default_factory=list)

    @field_validator("cooldown")
    @classmethod
    def validate_cooldown(cls, v: str) -> str:
        parse_duration(v)
        return v

    @field_validator("input_from", mode="before")
    @classmethod
    def normalize_input_from(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [v]
        return v or []


class CronEntry(BaseModel):
    """A scheduled trigger for a task."""

    schedule: str
    task: str


class TaskConfig(BaseModel):
    """A named task -- the unit of work in Den."""

    description: str
    complexity: Literal["low", "medium", "high"] | None = None
    loop: LoopConfig | None = None
    phases: list[PhaseConfig] = Field(default_factory=list)
    artifacts: list[ArtifactConfig] = Field(default_factory=list)
    on_fail: Literal["retry_with_feedback", "stop", "notify"] = "notify"

    @model_validator(mode="after")
    def validate_loop_or_phases(self) -> TaskConfig:
        if self.loop and self.phases:
            raise ValueError(
                "Task cannot have both 'loop' and 'phases'. "
                "Use 'loop' for single-phase or 'phases' for multi-phase."
            )
        return self


class Permissions(BaseModel):
    """Default-deny permission declarations."""

    network: list[str] = Field(default_factory=list)
    filesystem: list[str] = Field(
        default_factory=lambda: ["/den/workspace", "/den/output", "/den/memory"]
    )
    shell: bool = False

    @field_validator("filesystem")
    @classmethod
    def validate_filesystem_paths(cls, v: list[str]) -> list[str]:
        for path in v:
            if not path.startswith("/den/"):
                raise ValueError(
                    f"Filesystem path must be inside /den/: got '{path}'"
                )
        return v


class Resources(BaseModel):
    """Container resource constraints."""

    cpu: str = "2.0"
    memory: str = "4gb"
    disk: str = "10gb"

    @field_validator("memory")
    @classmethod
    def validate_memory(cls, v: str) -> str:
        parse_size(v)
        return v

    @field_validator("disk")
    @classmethod
    def validate_disk(cls, v: str) -> str:
        parse_size(v)
        return v

    @property
    def cpu_cores(self) -> float:
        return float(self.cpu)

    @property
    def memory_bytes(self) -> int:
        return parse_size(self.memory)

    @property
    def disk_bytes(self) -> int:
        return parse_size(self.disk)


class AgentfileSchema(BaseModel):
    """The complete Agentfile specification."""

    name: str
    model: str
    system_prompt: str
    env: dict[str, str] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=list)
    tool_execution: ToolExecutionConfig = Field(default_factory=ToolExecutionConfig)
    bash: BashConfig = Field(default_factory=BashConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    cron: list[CronEntry] = Field(default_factory=list)
    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    permissions: Permissions = Field(default_factory=Permissions)
    resources: Resources = Field(default_factory=Resources)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _NAME_RE.match(v):
            raise ValueError(
                f"Agent name must be kebab-case (lowercase, digits, hyphens): got '{v}'"
            )
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Model cannot be empty.")
        return v.strip()

    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("System prompt cannot be empty.")
        return v.strip()

    @model_validator(mode="after")
    def validate_env_matches_model(self) -> AgentfileSchema:
        """Auto-detect required API key from model and warn if missing."""
        model = self.model.lower()

        provider_key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "claude": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gpt": "OPENAI_API_KEY",
            "o1": "OPENAI_API_KEY",
            "o3": "OPENAI_API_KEY",
            "google": "GOOGLE_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "groq": "GROQ_API_KEY",
            "mistral": "MISTRAL_API_KEY",
        }

        needed_key = None
        if ":" in model:
            prefix = model.split(":")[0]
            needed_key = provider_key_map.get(prefix)
        else:
            for pattern, key in provider_key_map.items():
                if model.startswith(pattern):
                    needed_key = key
                    break

        if needed_key and self.env:
            has_correct_key = needed_key in self.env
            if not has_correct_key:
                wrong_keys = [
                    k for k in self.env
                    if k.endswith("_API_KEY") and k != needed_key
                ]
                if wrong_keys:
                    import warnings
                    warnings.warn(
                        f"Model '{self.model}' requires {needed_key} but env has "
                        f"{', '.join(wrong_keys)}. Add {needed_key} to env or "
                        f"change the model to match your API key.",
                        UserWarning,
                        stacklevel=2,
                    )

        return self

    @model_validator(mode="after")
    def validate_cron_tasks_exist(self) -> AgentfileSchema:
        """Every cron entry must reference an existing task."""
        task_names = set(self.tasks.keys())
        for entry in self.cron:
            if entry.task not in task_names:
                raise ValueError(
                    f"Cron entry references task '{entry.task}' "
                    f"which is not defined in tasks. "
                    f"Available tasks: {sorted(task_names)}"
                )
        return self

    @model_validator(mode="after")
    def validate_phase_transitions(self) -> AgentfileSchema:
        """Phase goto targets must reference existing phase names within the same task."""
        for task_name, task in self.tasks.items():
            if not task.phases:
                continue
            phase_names = {p.name for p in task.phases}
            for phase in task.phases:
                for transition in [phase.transitions.on_pass, phase.transitions.on_fail]:
                    if transition.goto and transition.goto not in ("next", "done"):
                        if transition.goto not in phase_names:
                            raise ValueError(
                                f"Task '{task_name}', phase '{phase.name}': "
                                f"transition goto '{transition.goto}' is not a valid phase. "
                                f"Available phases: {sorted(phase_names)}"
                            )
        return self
