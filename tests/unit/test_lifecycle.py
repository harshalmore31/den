"""Tests for the Agent Lifecycle Manager."""

import os
import tempfile
import time

import pytest

from den.core.lifecycle import AgentLifecycle, AgentState


SAMPLE_AGENTFILE = """
name: test-agent
model: claude-sonnet-4-6
system_prompt: You are a test agent.

tools:
  - file_read
  - file_write

bash:
  enabled: false

tasks:
  hello-task:
    description: Say hello.
  report-task:
    description: Write a report.

cron:
  - schedule: "0 9 * * MON"
    task: report-task

permissions:
  network: []
  filesystem:
    - /den/workspace
    - /den/output
    - /den/memory
"""


@pytest.fixture
def agentfile(tmp_path):
    path = tmp_path / "Agentfile"
    path.write_text(SAMPLE_AGENTFILE)
    return path


@pytest.fixture
def den_home(tmp_path):
    return str(tmp_path / ".den")


class TestBoot:
    def test_boot_success(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()

        assert lc.state == AgentState.IDLE
        assert lc.name == "test-agent"
        assert lc.config is not None
        assert lc.config.model == "claude-sonnet-4-6"
        assert lc.memory is not None
        assert lc.scheduler is not None
        assert lc.scheduler.task_count == 2
        assert lc.scheduler.cron_count == 1

        lc.shutdown()

    def test_boot_creates_directories(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()

        assert os.path.isdir(os.path.join(den_home, "memory", "test-agent"))
        assert os.path.isdir(os.path.join(den_home, "workspaces", "test-agent"))
        assert os.path.isdir(os.path.join(den_home, "output", "test-agent"))
        assert os.path.isdir(os.path.join(den_home, "logs"))

        lc.shutdown()


class TestStatus:
    def test_status_after_boot(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()

        status = lc.get_status()
        assert status.name == "test-agent"
        assert status.state == AgentState.IDLE
        assert status.model == "claude-sonnet-4-6"
        assert status.cron_tasks == 1
        assert status.uptime_seconds >= 0

        lc.shutdown()


class TestTrigger:
    def test_trigger_task(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()

        triggered = lc.trigger("hello-task")
        assert triggered

        # Wait for execution
        time.sleep(0.2)

        status = lc.get_status()
        # Task should have completed (with placeholder executor)
        assert status.tasks_completed >= 1 or status.tasks_failed >= 1

        lc.shutdown()

    def test_trigger_unknown_task(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()

        triggered = lc.trigger("nonexistent-task")
        assert not triggered

        lc.shutdown()


class TestShutdown:
    def test_shutdown_writes_state(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()
        lc.shutdown()

        assert lc.state == AgentState.STOPPED

        # Check state file was written
        state_file = os.path.join(den_home, "runs", "test-agent.json")
        assert os.path.exists(state_file)

        import json
        with open(state_file) as f:
            data = json.load(f)
        assert data["name"] == "test-agent"
        assert data["state"] == "stopped"

    def test_double_shutdown(self, agentfile, den_home):
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()
        lc.shutdown()
        lc.shutdown()  # Should not raise


class TestWithCustomExecutor:
    def test_custom_executor(self, agentfile, den_home):
        class MyExecutor:
            def execute(self, context):
                return {
                    "output_text": "Custom output with enough words for the check " * 10,
                    "output_files": [],
                }

        lc = AgentLifecycle(agentfile, den_home=den_home, agent_executor=MyExecutor())
        lc.boot()
        lc.trigger("hello-task")
        time.sleep(0.2)

        status = lc.get_status()
        assert status.tasks_completed >= 1

        lc.shutdown()
