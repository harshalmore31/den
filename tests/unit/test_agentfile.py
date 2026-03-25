"""Tests for the Agentfile parser and schema validation."""

import pytest

from den.agentfile import (
    AgentfileParseError,
    AgentfileSchema,
    AgentfileValidationError,
    parse_agentfile_string,
    parse_duration,
    parse_size,
)


# ---------------------------------------------------------------------------
# Utility parsers
# ---------------------------------------------------------------------------


class TestParseDuration:
    def test_seconds(self):
        assert parse_duration("30s") == 30

    def test_minutes(self):
        assert parse_duration("5m") == 300

    def test_hours(self):
        assert parse_duration("2h") == 7200

    def test_days(self):
        assert parse_duration("1d") == 86400

    def test_whitespace(self):
        assert parse_duration("  30s  ") == 30

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("30x")

    def test_empty(self):
        with pytest.raises(ValueError, match="Invalid duration"):
            parse_duration("")


class TestParseSize:
    def test_megabytes(self):
        assert parse_size("500mb") == 500 * 1024**2

    def test_gigabytes(self):
        assert parse_size("4gb") == 4 * 1024**3

    def test_kilobytes(self):
        assert parse_size("100kb") == 100 * 1024

    def test_invalid(self):
        with pytest.raises(ValueError, match="Invalid size"):
            parse_size("big")


# ---------------------------------------------------------------------------
# Minimal valid Agentfile
# ---------------------------------------------------------------------------

MINIMAL_AGENTFILE = """
name: test-agent
model: claude-sonnet-4-6
system_prompt: You are a test agent.
"""


class TestMinimalAgentfile:
    def test_parses_successfully(self):
        schema = parse_agentfile_string(MINIMAL_AGENTFILE)
        assert isinstance(schema, AgentfileSchema)
        assert schema.name == "test-agent"
        assert schema.model == "claude-sonnet-4-6"
        assert schema.system_prompt == "You are a test agent."

    def test_defaults(self):
        schema = parse_agentfile_string(MINIMAL_AGENTFILE)
        assert schema.bash.enabled is False
        assert schema.memory.max_size == "2gb"
        assert schema.permissions.shell is False
        assert schema.resources.cpu == "2.0"
        assert schema.resources.memory == "4gb"
        assert schema.tools == []
        assert schema.tasks == {}
        assert schema.cron == []


# ---------------------------------------------------------------------------
# Name validation
# ---------------------------------------------------------------------------


class TestNameValidation:
    def test_valid_kebab_case(self):
        schema = parse_agentfile_string(MINIMAL_AGENTFILE)
        assert schema.name == "test-agent"

    def test_rejects_uppercase(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: TestAgent
model: claude-sonnet-4-6
system_prompt: test
""")

    def test_rejects_spaces(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test agent
model: claude-sonnet-4-6
system_prompt: test
""")

    def test_rejects_starting_with_hyphen(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: -test
model: claude-sonnet-4-6
system_prompt: test
""")


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------


class TestRequiredFields:
    def test_missing_name(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
model: claude-sonnet-4-6
system_prompt: test
""")

    def test_missing_model(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
system_prompt: test
""")

    def test_missing_system_prompt(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
""")

    def test_empty_model(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
model: ""
system_prompt: test
""")

    def test_empty_system_prompt(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: ""
""")


# ---------------------------------------------------------------------------
# YAML parse errors
# ---------------------------------------------------------------------------


class TestYAMLErrors:
    def test_invalid_yaml(self):
        with pytest.raises(AgentfileParseError, match="Invalid YAML"):
            parse_agentfile_string("name: [unterminated")

    def test_non_dict_yaml(self):
        with pytest.raises(AgentfileParseError, match="must be a YAML mapping"):
            parse_agentfile_string("- just\n- a\n- list")


# ---------------------------------------------------------------------------
# Bash config
# ---------------------------------------------------------------------------


class TestBashConfig:
    def test_bash_config(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
bash:
  enabled: true
  allowed_commands: [python3, pip]
  timeout: 120s
""")
        assert schema.bash.enabled is True
        assert schema.bash.allowed_commands == ["python3", "pip"]
        assert schema.bash.timeout_seconds == 120

    def test_invalid_timeout(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
bash:
  timeout: forever
""")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


class TestPermissions:
    def test_default_filesystem(self):
        schema = parse_agentfile_string(MINIMAL_AGENTFILE)
        assert "/den/workspace" in schema.permissions.filesystem
        assert "/den/output" in schema.permissions.filesystem
        assert "/den/memory" in schema.permissions.filesystem

    def test_rejects_non_den_path(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
permissions:
  filesystem:
    - /etc/passwd
""")

    def test_network_whitelist(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
permissions:
  network:
    - api.anthropic.com
    - "*.wikipedia.org"
""")
        assert len(schema.permissions.network) == 2


# ---------------------------------------------------------------------------
# Tasks and cron
# ---------------------------------------------------------------------------


class TestTasks:
    def test_basic_task(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
tasks:
  my-task:
    description: Do something useful.
""")
        assert "my-task" in schema.tasks
        assert schema.tasks["my-task"].description == "Do something useful."

    def test_task_with_loop(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
tasks:
  my-task:
    description: Do work.
    loop:
      max_iterations: 3
      cooldown: 10s
      on_fail: stop
""")
        task = schema.tasks["my-task"]
        assert task.loop is not None
        assert task.loop.max_iterations == 3
        assert task.loop.cooldown_seconds == 10

    def test_task_with_phases(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
tasks:
  my-task:
    description: Do work.
    phases:
      - name: research
        type: research
        questions:
          - id: q1
            text: "What is X?"
        max_iterations: 2
      - name: execute
        type: execution
        input_from: research
        max_iterations: 3
""")
        task = schema.tasks["my-task"]
        assert len(task.phases) == 2
        assert task.phases[0].name == "research"
        assert task.phases[0].type == "research"
        assert task.phases[1].input_from == ["research"]

    def test_rejects_loop_and_phases(self):
        with pytest.raises(AgentfileValidationError):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
tasks:
  my-task:
    description: Both.
    loop:
      max_iterations: 3
    phases:
      - name: p1
        type: custom
""")

    def test_cron_references_existing_task(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
cron:
  - schedule: "0 9 * * MON"
    task: my-task
tasks:
  my-task:
    description: Weekly work.
""")
        assert len(schema.cron) == 1

    def test_cron_rejects_missing_task(self):
        with pytest.raises(AgentfileValidationError, match="not defined in tasks"):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
cron:
  - schedule: "0 9 * * MON"
    task: nonexistent
tasks:
  my-task:
    description: Exists.
""")


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------


class TestPhaseTransitions:
    def test_valid_goto(self):
        schema = parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
tasks:
  build:
    description: Build it.
    phases:
      - name: plan
        type: plan
      - name: execute
        type: execution
        transitions:
          on_fail:
            behavior: goto
            goto: plan
""")
        phase = schema.tasks["build"].phases[1]
        assert phase.transitions.on_fail.goto == "plan"

    def test_rejects_invalid_goto(self):
        with pytest.raises(AgentfileValidationError, match="not a valid phase"):
            parse_agentfile_string("""
name: test-agent
model: claude-sonnet-4-6
system_prompt: test
tasks:
  build:
    description: Build it.
    phases:
      - name: plan
        type: plan
      - name: execute
        type: execution
        transitions:
          on_fail:
            behavior: goto
            goto: nonexistent
""")


# ---------------------------------------------------------------------------
# Full example Agentfile
# ---------------------------------------------------------------------------


class TestFullExample:
    def test_research_analyst_parses(self):
        """Validate the full research-analyst example Agentfile."""
        from pathlib import Path
        from den.agentfile import parse_agentfile

        example_path = Path(__file__).parent.parent.parent / "examples" / "research-analyst.yaml"
        if not example_path.exists():
            pytest.skip("Example file not found")

        schema = parse_agentfile(example_path)
        assert schema.name == "research-analyst"
        assert schema.model in ("anthropic:claude-sonnet-4-6", "openai:gpt-4o")
        assert len(schema.tools) == 5
        assert schema.bash.enabled is True
        assert len(schema.cron) == 2
        assert "weekly-market-report" in schema.tasks
        assert "check-news-alerts" in schema.tasks
        weekly = schema.tasks["weekly-market-report"]
        assert len(weekly.phases) == 3
        assert weekly.phases[0].name == "discovery"
        assert weekly.phases[0].type == "research"
        assert len(weekly.phases[0].questions) == 3
