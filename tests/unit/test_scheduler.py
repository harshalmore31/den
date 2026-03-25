"""Tests for the Den Task Scheduler."""

import time
import threading

import pytest

from den.core.scheduler import TaskScheduler, TaskState


class TestSchedulerRegistration:
    def test_register_task(self):
        s = TaskScheduler()
        s.register_task("my-task")
        assert s.task_count == 1
        states = s.get_task_states()
        assert "my-task" in states

    def test_register_with_cron(self):
        s = TaskScheduler()
        s.register_task("weekly-report", cron_expression="0 9 * * MON")
        assert s.cron_count == 1
        states = s.get_task_states()
        assert states["weekly-report"]["cron"] == "0 9 * * MON"

    def test_register_from_agentfile(self):
        s = TaskScheduler()
        s.register_from_agentfile(
            tasks={"task-a": {}, "task-b": {}},
            cron_entries=[
                {"schedule": "0 9 * * MON", "task": "task-a"},
            ],
        )
        assert s.task_count == 2
        assert s.cron_count == 1
        states = s.get_task_states()
        assert states["task-a"]["cron"] == "0 9 * * MON"
        assert states["task-b"]["cron"] is None


class TestSchedulerTrigger:
    def test_manual_trigger(self):
        s = TaskScheduler()
        results = []

        def callback(task_name):
            results.append(task_name)

        s.set_callback(callback)
        s.register_task("test-task")
        triggered = s.trigger("test-task")
        assert triggered

        # Wait for thread to complete
        time.sleep(0.1)
        assert "test-task" in results

    def test_trigger_unknown_task(self):
        s = TaskScheduler()
        assert not s.trigger("nonexistent")

    def test_trigger_already_running(self):
        s = TaskScheduler()
        barrier = threading.Event()

        def slow_callback(task_name):
            barrier.wait(timeout=2)

        s.set_callback(slow_callback)
        s.register_task("slow-task")

        # First trigger starts
        s.trigger("slow-task")
        time.sleep(0.05)

        # Second trigger should be rejected
        assert not s.trigger("slow-task")

        # Cleanup
        barrier.set()
        time.sleep(0.1)

    def test_callback_updates_state(self):
        s = TaskScheduler()

        def callback(task_name):
            pass  # Success

        s.set_callback(callback)
        s.register_task("state-task")
        s.trigger("state-task")
        time.sleep(0.1)

        states = s.get_task_states()
        assert states["state-task"]["state"] == "completed"
        assert states["state-task"]["run_count"] == 1
        assert states["state-task"]["last_status"] == "success"

    def test_failed_callback_updates_state(self):
        s = TaskScheduler()

        def bad_callback(task_name):
            raise RuntimeError("boom")

        s.set_callback(bad_callback)
        s.register_task("fail-task")
        s.trigger("fail-task")
        time.sleep(0.1)

        states = s.get_task_states()
        assert states["fail-task"]["state"] == "failed"
        assert "error" in states["fail-task"]["last_status"]


class TestSchedulerLifecycle:
    def test_start_stop_no_cron(self):
        s = TaskScheduler()
        s.register_task("no-cron-task")
        s.start()
        s.stop()  # Should not raise

    def test_start_with_cron(self):
        s = TaskScheduler()
        s.register_task("cron-task", cron_expression="0 9 * * MON")
        s.start()
        assert s._scheduler is not None
        s.stop()

    def test_write_state(self, tmp_path):
        s = TaskScheduler()
        s.register_task("task-a", cron_expression="*/5 * * * *")
        s.register_task("task-b")

        state_file = str(tmp_path / "state.json")
        s.write_state(state_file)

        import json
        with open(state_file) as f:
            data = json.load(f)
        assert "task-a" in data
        assert "task-b" in data
