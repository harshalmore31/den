"""Den Runtime Backends -- swappable isolation layer."""

from den.runtime.base import (
    Mount,
    NetworkPolicy,
    ResourceLimits,
    RuntimeBackend,
    SandboxConfig,
    SandboxHandle,
)
from den.runtime.docker_backend import DockerBackend


def get_backend(backend_name: str = "docker") -> RuntimeBackend:
    backends = {
        "docker": DockerBackend,
    }
    cls = backends.get(backend_name)
    if cls is None:
        raise ValueError(f"Unknown backend: '{backend_name}'. Available: {list(backends.keys())}")
    return cls()


__all__ = [
    "DockerBackend",
    "Mount",
    "NetworkPolicy",
    "ResourceLimits",
    "RuntimeBackend",
    "SandboxConfig",
    "SandboxHandle",
    "get_backend",
]
