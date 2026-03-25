"""Agent Lifecycle Manager -- den up / den down."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from den.agentfile import AgentfileSchema, parse_agentfile
from den.core.bash_executor import BashExecutor
from den.core.loop_engine import AgentExecutor, LoopEngine, TaskResult
from den.core.scheduler import TaskScheduler
from den.memory.config import DenMemoryConfig
from den.memory.manager import MemoryManager
from den.tools import get_registry, PermissionInterceptor

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    ABSENT = "absent"
    BOOTING = "booting"
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class AgentStatus:
    """Current status of a Den agent."""

    name: str
    state: AgentState
    model: str = ""
    uptime_seconds: float = 0.0
    tasks_completed: int = 0
    tasks_failed: int = 0
    memory_count: int = 0
    cron_tasks: int = 0
    current_task: str = ""


class AgentLifecycle:
    """Manages a Den agent's full lifecycle: boot, run, shutdown."""

    def __init__(
        self,
        agentfile_path: str | Path,
        den_home: str = "~/.den",
        agent_executor: AgentExecutor | None = None,
    ):
        self.agentfile_path = Path(agentfile_path)
        self.den_home = Path(den_home).expanduser()
        self._agent_executor = agent_executor

        self.config: AgentfileSchema | None = None
        self.memory: MemoryManager | None = None
        self.scheduler: TaskScheduler | None = None
        self.loop_engine: LoopEngine | None = None
        self.bash_executor: BashExecutor | None = None

        self._state = AgentState.ABSENT
        self._boot_time: float = 0.0
        self._tasks_completed: int = 0
        self._tasks_failed: int = 0
        self._current_task: str = ""
        self._lock = threading.Lock()

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def name(self) -> str:
        return self.config.name if self.config else "unknown"

    def boot(self) -> None:
        """Boot the agent: parse Agentfile, init all systems."""
        self._state = AgentState.BOOTING
        logger.info(f"Booting agent from {self.agentfile_path}")

        self.config = parse_agentfile(self.agentfile_path)
        logger.info(f"Agent: {self.config.name} (model: {self.config.model})")

        self._setup_directories()

        memory_path = self.den_home / "memory" / self.config.name / "memory.db"
        self.memory = MemoryManager(DenMemoryConfig(
            db_path=str(memory_path),
            use_fastembed=False,
        ))
        logger.info(f"Memory initialized: {memory_path}")

        self.bash_executor = BashExecutor(self.config.bash)

        tool_registry = get_registry()
        interceptor = PermissionInterceptor(self.config.permissions)
        loaded_tools = tool_registry.load_tools(self.config.tools)
        for tool in loaded_tools.values():
            interceptor.wrap(tool)

        bash_tool = loaded_tools.get("bash")
        if bash_tool:
            bash_tool.set_executor(self.bash_executor)

        logger.info(f"Tools loaded: {list(loaded_tools.keys())}")

        workspace = str(self.den_home / "workspaces" / self.config.name)
        output_dir = str(self.den_home / "output" / self.config.name)
        os.makedirs(workspace, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        executor = self._agent_executor or _PlaceholderExecutor()
        self.loop_engine = LoopEngine(
            agent_executor=executor,
            memory=self.memory,
            workspace=workspace,
            output_dir=output_dir,
        )

        self.scheduler = TaskScheduler()
        self.scheduler.set_callback(self._on_task_fired)

        tasks_dict = {name: {} for name in self.config.tasks}
        cron_entries = [{"schedule": c.schedule, "task": c.task} for c in self.config.cron]
        self.scheduler.register_from_agentfile(tasks_dict, cron_entries)

        self._boot_time = time.time()
        self._state = AgentState.IDLE
        logger.info(f"Agent '{self.config.name}' is IDLE. "
                     f"{self.scheduler.task_count} tasks, {self.scheduler.cron_count} cron.")

    def start_scheduler(self) -> None:
        if self.scheduler:
            self.scheduler.start()
            logger.info("Scheduler started -- agent is autonomous")

    def trigger(self, task_name: str) -> bool:
        if not self.scheduler:
            logger.error("Agent not booted -- call boot() first")
            return False
        return self.scheduler.trigger(task_name)

    def shutdown(self) -> None:
        self._state = AgentState.STOPPING
        logger.info(f"Shutting down agent '{self.name}'")

        if self.scheduler:
            self.scheduler.stop()

        self._state = AgentState.STOPPED
        self._write_state()

        if self.memory:
            self.memory.close()

        logger.info(f"Agent '{self.name}' is STOPPED. Den preserved.")

    def get_status(self) -> AgentStatus:
        uptime = time.time() - self._boot_time if self._boot_time else 0
        return AgentStatus(
            name=self.name,
            state=self._state,
            model=self.config.model if self.config else "",
            uptime_seconds=uptime,
            tasks_completed=self._tasks_completed,
            tasks_failed=self._tasks_failed,
            memory_count=self.memory.store.count() if self.memory else 0,
            cron_tasks=self.scheduler.cron_count if self.scheduler else 0,
            current_task=self._current_task,
        )

    def _on_task_fired(self, task_name: str) -> None:
        if not self.config or not self.loop_engine:
            return

        task_config = self.config.tasks.get(task_name)
        if not task_config:
            logger.error(f"Task '{task_name}' not found in Agentfile")
            return

        with self._lock:
            self._state = AgentState.RUNNING
            self._current_task = task_name

        logger.info(f"Executing task: {task_name}")

        try:
            result = self.loop_engine.run_task(task_name, task_config)
            with self._lock:
                if result.status.value == "success":
                    self._tasks_completed += 1
                else:
                    self._tasks_failed += 1
            logger.info(f"Task '{task_name}': {result.status.value} ({result.total_iterations} iters)")
        except Exception as e:
            with self._lock:
                self._tasks_failed += 1
            logger.error(f"Task '{task_name}' crashed: {e}")

        with self._lock:
            self._current_task = ""
            self._state = AgentState.IDLE

    def _setup_directories(self) -> None:
        dirs = [
            self.den_home / "memory" / self.config.name,
            self.den_home / "workspaces" / self.config.name,
            self.den_home / "output" / self.config.name,
            self.den_home / "logs",
            self.den_home / "runs",
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    def _write_state(self) -> None:
        state_path = self.den_home / "runs" / f"{self.name}.json"
        state = {
            "name": self.name,
            "state": self._state.value,
            "model": self.config.model if self.config else "",
            "boot_time": self._boot_time,
            "tasks_completed": self._tasks_completed,
            "tasks_failed": self._tasks_failed,
            "timestamp": time.time(),
        }
        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

        if self.scheduler:
            sched_path = self.den_home / "runs" / f"{self.name}-scheduler.json"
            self.scheduler.write_state(str(sched_path))


class _PlaceholderExecutor:
    """Placeholder executor used when no real LLM is configured."""

    def execute(self, context: dict) -> dict:
        return {
            "output_text": (
                f"[Placeholder] Task: {context.get('task_name', 'unknown')}, "
                f"Iteration: {context.get('iteration', 0)}. "
                f"Configure a real agent executor (PydanticAI) to produce actual output."
            ),
            "output_files": [],
        }
