"""Docker Runtime Backend -- v1 isolation layer."""

from __future__ import annotations

import logging
import os
import tarfile
import tempfile
from io import BytesIO
from typing import Iterator

from den.runtime.base import (
    Mount,
    NetworkPolicy,
    ResourceLimits,
    RuntimeBackend,
    SandboxConfig,
    SandboxHandle,
)

logger = logging.getLogger(__name__)

DEN_LABEL = "dev.den.agent"


class DockerBackend(RuntimeBackend):
    """Docker-based sandbox runtime for Den agents."""

    def __init__(self) -> None:
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
                self._client.ping()
            except ImportError:
                raise RuntimeError(
                    "Docker SDK not installed. Install: pip install docker"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Cannot connect to Docker daemon: {e}. "
                    f"Is Docker running? Try: docker info"
                )
        return self._client

    def create_sandbox(self, config: SandboxConfig) -> SandboxHandle:
        client = self._get_client()

        # Build volume mounts
        volumes = {}
        for mount in config.mounts:
            os.makedirs(mount.host_path, exist_ok=True)
            volumes[mount.host_path] = {
                "bind": mount.container_path,
                "mode": mount.mode,
            }

        # Resource limits
        nano_cpus = int(config.resources.cpu_cores * 1e9)
        mem_limit = config.resources.memory_bytes

        # Labels for discovery
        labels = {
            DEN_LABEL: "true",
            f"{DEN_LABEL}.name": config.name,
        }
        labels.update(config.labels)

        # Create container
        container_name = f"den-{config.name}"

        # Remove existing container with same name if stopped
        try:
            existing = client.containers.get(container_name)
            if existing.status != "running":
                existing.remove(force=True)
            else:
                raise RuntimeError(
                    f"Container '{container_name}' is already running. "
                    f"Stop it first with: den down {config.name}"
                )
        except Exception:
            pass  # Container doesn't exist, good

        container = client.containers.create(
            image=config.image,
            name=container_name,
            environment=config.env,
            volumes=volumes,
            nano_cpus=nano_cpus,
            mem_limit=mem_limit,
            entrypoint=config.entrypoint,
            labels=labels,
            detach=True,
            stdin_open=False,
            tty=False,
        )

        handle = SandboxHandle(
            sandbox_id=container.id,
            name=config.name,
            backend="docker",
        )
        logger.info(f"Created sandbox: {container_name} ({container.short_id})")
        return handle

    def start_sandbox(self, handle: SandboxHandle) -> None:
        client = self._get_client()
        container = client.containers.get(handle.sandbox_id)
        container.start()
        logger.info(f"Started sandbox: {handle.name}")

    def stop_sandbox(self, handle: SandboxHandle, timeout: int = 30) -> None:
        client = self._get_client()
        try:
            container = client.containers.get(handle.sandbox_id)
            container.stop(timeout=timeout)
            logger.info(f"Stopped sandbox: {handle.name}")
        except Exception as e:
            logger.warning(f"Error stopping sandbox {handle.name}: {e}")

    def destroy_sandbox(self, handle: SandboxHandle) -> None:
        client = self._get_client()
        try:
            container = client.containers.get(handle.sandbox_id)
            container.remove(force=True)
            logger.info(f"Destroyed sandbox: {handle.name}")
        except Exception as e:
            logger.warning(f"Error destroying sandbox {handle.name}: {e}")

    def is_running(self, handle: SandboxHandle) -> bool:
        client = self._get_client()
        try:
            container = client.containers.get(handle.sandbox_id)
            return container.status == "running"
        except Exception:
            return False

    def stream_logs(self, handle: SandboxHandle) -> Iterator[str]:
        client = self._get_client()
        container = client.containers.get(handle.sandbox_id)
        for chunk in container.logs(stream=True, follow=True):
            yield chunk.decode("utf-8", errors="replace")

    def exec_command(self, handle: SandboxHandle, command: str) -> tuple[int, str]:
        client = self._get_client()
        container = client.containers.get(handle.sandbox_id)
        exit_code, output = container.exec_run(command, demux=False)
        return exit_code, output.decode("utf-8", errors="replace") if output else ""

    def copy_from(self, handle: SandboxHandle, container_path: str, host_path: str) -> None:
        client = self._get_client()
        container = client.containers.get(handle.sandbox_id)
        bits, _ = container.get_archive(container_path)

        # Extract tar stream to host path
        os.makedirs(os.path.dirname(host_path), exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            for chunk in bits:
                tmp.write(chunk)
            tmp.flush()
            tmp_path = tmp.name

        with tarfile.open(tmp_path, "r") as tar:
            # Prevent path traversal
            safe_members = []
            dest = os.path.dirname(host_path)
            for member in tar.getmembers():
                member_path = os.path.normpath(os.path.join(dest, member.name))
                if not member_path.startswith(os.path.abspath(dest)):
                    logger.warning(f"Skipping unsafe tar member: {member.name}")
                    continue
                safe_members.append(member)
            tar.extractall(path=dest, members=safe_members)
        os.unlink(tmp_path)

    def copy_to(self, handle: SandboxHandle, host_path: str, container_path: str) -> None:
        client = self._get_client()
        container = client.containers.get(handle.sandbox_id)

        # Create tar from host file
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            tar.add(host_path, arcname=os.path.basename(container_path))
        buf.seek(0)

        container.put_archive(os.path.dirname(container_path), buf)

    def list_sandboxes(self) -> list[SandboxHandle]:
        client = self._get_client()
        containers = client.containers.list(
            all=True,
            filters={"label": DEN_LABEL},
        )
        return [
            SandboxHandle(
                sandbox_id=c.id,
                name=c.labels.get(f"{DEN_LABEL}.name", c.name),
                backend="docker",
            )
            for c in containers
        ]

    def build_den_image(self, tag: str = "den/base:latest") -> str:
        """Build the base Den image for running agents."""
        client = self._get_client()

        dockerfile = """
FROM python:3.11-slim

RUN pip install --no-cache-dir \\
    pydantic-ai \\
    anthropic \\
    openai \\
    httpx \\
    duckduckgo-search \\
    pypdf \\
    pandas \\
    pyyaml \\
    pydantic

# Create Den directory structure
RUN mkdir -p /den/memory /den/workspace /den/output /den/logs

WORKDIR /den/workspace
"""
        # Build from string
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tar:
            dockerfile_bytes = dockerfile.encode("utf-8")
            info = tarfile.TarInfo(name="Dockerfile")
            info.size = len(dockerfile_bytes)
            tar.addfile(info, BytesIO(dockerfile_bytes))
        buf.seek(0)

        image, logs = client.images.build(
            fileobj=buf,
            custom_context=True,
            tag=tag,
            rm=True,
        )
        logger.info(f"Built Den image: {tag}")
        return tag

    def create_den_sandbox(
        self,
        agent_name: str,
        env: dict[str, str],
        den_home: str,
        resources: ResourceLimits | None = None,
        image: str = "den/base:latest",
    ) -> SandboxHandle:
        """Create a sandbox pre-configured for a Den agent."""
        memory_path = os.path.join(den_home, "memory", agent_name)
        workspace_path = os.path.join(den_home, "workspaces", agent_name)
        output_path = os.path.join(den_home, "output", agent_name)

        config = SandboxConfig(
            name=agent_name,
            image=image,
            env=env,
            mounts=[
                Mount(memory_path, "/den/memory", "rw"),
                Mount(workspace_path, "/den/workspace", "rw"),
                Mount(output_path, "/den/output", "rw"),
            ],
            resources=resources or ResourceLimits(),
            labels={
                f"{DEN_LABEL}.home": den_home,
            },
        )

        return self.create_sandbox(config)
