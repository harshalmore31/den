"""Den Task Scheduler -- cron and manual triggers."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    """A task registered with the scheduler."""

    name: str
    cron_expression: str | None = None
    callback: Callable | None = None
    state: TaskState = TaskState.PENDING
    last_run: float = 0.0
    last_status: str = ""
    run_count: int = 0
    next_fire: str = ""


class TaskScheduler:
    """Manages cron-scheduled and manually triggered tasks."""

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._running: bool = False
        self._scheduler = None
        self._task_callback: Callable | None = None

    def set_callback(self, callback: Callable) -> None:
        """Set the function to call when a task fires (receives task_name: str)."""
        self._task_callback = callback

    def register_task(self, name: str, cron_expression: str | None = None) -> None:
        """Register a task with optional cron schedule."""
        with self._lock:
            self._tasks[name] = ScheduledTask(
                name=name,
                cron_expression=cron_expression,
            )
        logger.info(f"Registered task: {name}" + (f" (cron: {cron_expression})" if cron_expression else ""))

    def register_from_agentfile(self, tasks: dict[str, Any], cron_entries: list[dict]) -> None:
        """Register all tasks and cron schedules from a parsed Agentfile."""
        for task_name in tasks:
            self.register_task(task_name)

        cron_map = {entry.get("task", ""): entry.get("schedule", "") for entry in cron_entries}
        for task_name, schedule in cron_map.items():
            if task_name in self._tasks:
                with self._lock:
                    self._tasks[task_name].cron_expression = schedule

    def start(self) -> None:
        """Start the scheduler. Cron tasks will fire at their scheduled times."""
        if self._running:
            return

        self._running = True
        cron_tasks = {
            name: t for name, t in self._tasks.items() if t.cron_expression
        }

        if not cron_tasks:
            logger.info("Scheduler started (no cron tasks)")
            return

        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            self._scheduler = BackgroundScheduler()

            for name, task in cron_tasks.items():
                trigger = CronTrigger.from_crontab(task.cron_expression)
                self._scheduler.add_job(
                    self._fire_task,
                    trigger=trigger,
                    args=[name],
                    id=f"den-{name}",
                    name=name,
                    replace_existing=True,
                )
                from datetime import datetime
                next_fire = trigger.get_next_fire_time(None, datetime.now(tz=trigger.timezone))
                if next_fire:
                    task.next_fire = str(next_fire)
                logger.info(f"Scheduled: {name} -> {task.cron_expression} (next: {task.next_fire})")

            self._scheduler.start()
            logger.info(f"Scheduler started with {len(cron_tasks)} cron tasks")

        except ImportError:
            logger.warning(
                "APScheduler not installed -- cron scheduling disabled. "
                "Install: pip install 'apscheduler>=3.10,<4.0'"
            )

    def stop(self) -> None:
        self._running = False
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
            self._scheduler = None
        logger.info("Scheduler stopped")

    def trigger(self, task_name: str) -> bool:
        """Manually trigger a task immediately. Returns True if fired."""
        with self._lock:
            task = self._tasks.get(task_name)
            if not task:
                logger.warning(f"Cannot trigger unknown task: {task_name}")
                return False
            if task.state == TaskState.RUNNING:
                logger.warning(f"Task already running: {task_name}")
                return False

        thread = threading.Thread(
            target=self._fire_task,
            args=[task_name],
            daemon=True,
        )
        thread.start()
        return True

    def get_task_states(self) -> dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "state": t.state.value,
                    "cron": t.cron_expression,
                    "last_run": t.last_run,
                    "last_status": t.last_status,
                    "run_count": t.run_count,
                    "next_fire": t.next_fire,
                }
                for name, t in self._tasks.items()
            }

    def is_running(self, task_name: str) -> bool:
        with self._lock:
            task = self._tasks.get(task_name)
            return task is not None and task.state == TaskState.RUNNING

    @property
    def task_count(self) -> int:
        return len(self._tasks)

    @property
    def cron_count(self) -> int:
        return sum(1 for t in self._tasks.values() if t.cron_expression)

    def _fire_task(self, task_name: str) -> None:
        with self._lock:
            task = self._tasks.get(task_name)
            if not task:
                return
            if task.state == TaskState.RUNNING:
                logger.warning(f"Skipping {task_name} -- already running")
                return
            task.state = TaskState.RUNNING
            task.last_run = time.time()

        logger.info(f"Firing task: {task_name}")

        try:
            if self._task_callback:
                self._task_callback(task_name)
                status = "success"
            else:
                logger.warning(f"No callback set -- task {task_name} has nothing to execute")
                status = "no_callback"
        except Exception as e:
            logger.error(f"Task {task_name} failed: {e}")
            status = f"error: {e}"

        with self._lock:
            task = self._tasks.get(task_name)
            if task:
                task.state = TaskState.COMPLETED if "error" not in status else TaskState.FAILED
                task.last_status = status
                task.run_count += 1

    def write_state(self, path: str) -> None:
        """Write scheduler state to a JSON file for CLI queries."""
        state = self.get_task_states()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(state, f, indent=2)
