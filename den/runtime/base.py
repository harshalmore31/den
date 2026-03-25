"""Runtime Backend abstraction -- the swappable isolation layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class Mount:
    """A volume mount configuration."""

    host_path: str
    container_path: str
    mode: str = "rw"


@dataclass
class NetworkPolicy:
    """Network egress policy -- default deny, explicit allow."""

    allowed_hosts: list[str] = field(default_factory=list)


@dataclass
class ResourceLimits:
    """Container resource constraints."""

    cpu_cores: float = 2.0
    memory_bytes: int = 4 * 1024**3
    disk_bytes: int = 10 * 1024**3
    max_runtime_seconds: int = 3600


@dataclass
class SandboxConfig:
    """Complete configuration for creating a sandbox."""

    name: str
    image: str = "den/base:latest"
    env: dict[str, str] = field(default_factory=dict)
    mounts: list[Mount] = field(default_factory=list)
    network_policy: NetworkPolicy = field(default_factory=NetworkPolicy)
    resources: ResourceLimits = field(default_factory=ResourceLimits)
    entrypoint: list[str] = field(default_factory=lambda: ["python", "-m", "den.core.agent_process"])
    labels: dict[str, str] = field(default_factory=dict)


@dataclass
class SandboxHandle:
    """Reference to a running sandbox."""

    sandbox_id: str
    name: str
    backend: str


class RuntimeBackend(ABC):
    """Abstract base for sandbox runtimes. Docker for v1."""

    @abstractmethod
    def create_sandbox(self, config: SandboxConfig) -> SandboxHandle: ...

    @abstractmethod
    def start_sandbox(self, handle: SandboxHandle) -> None: ...

    @abstractmethod
    def stop_sandbox(self, handle: SandboxHandle, timeout: int = 30) -> None: ...

    @abstractmethod
    def destroy_sandbox(self, handle: SandboxHandle) -> None: ...

    @abstractmethod
    def is_running(self, handle: SandboxHandle) -> bool: ...

    @abstractmethod
    def stream_logs(self, handle: SandboxHandle) -> Iterator[str]: ...

    @abstractmethod
    def exec_command(self, handle: SandboxHandle, command: str) -> tuple[int, str]: ...

    @abstractmethod
    def copy_from(self, handle: SandboxHandle, container_path: str, host_path: str) -> None: ...

    @abstractmethod
    def copy_to(self, handle: SandboxHandle, host_path: str, container_path: str) -> None: ...

    @abstractmethod
    def list_sandboxes(self) -> list[SandboxHandle]: ...
