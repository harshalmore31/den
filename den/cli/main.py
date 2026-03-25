"""Den CLI -- the user-facing interface."""

from __future__ import annotations

import json
import os
import sys
import time

import click


def _get_den_home() -> str:
    return os.environ.get("DEN_HOME", os.path.expanduser("~/.den"))


_PROVIDER_ENV_MAP = {
    "openai": {"OPENAI_API_KEY": "$OPENAI_API_KEY"},
    "anthropic": {"ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY"},
    "google": {"GOOGLE_API_KEY": "$GOOGLE_API_KEY"},
    "groq": {"GROQ_API_KEY": "$GROQ_API_KEY"},
    "mistral": {"MISTRAL_API_KEY": "$MISTRAL_API_KEY"},
    "ollama": {},
}

_MODEL_PATTERNS = {
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "claude": "anthropic",
    "gemini": "google",
    "llama": "groq",
    "mixtral": "groq",
    "mistral": "mistral",
}


def _detect_env_vars(model: str) -> dict[str, str]:
    """Detect which API keys to include based on model string."""
    if ":" in model:
        provider = model.split(":")[0].lower()
        return _PROVIDER_ENV_MAP.get(provider, {"OPENAI_API_KEY": "$OPENAI_API_KEY"})

    model_lower = model.lower()
    for pattern, provider in _MODEL_PATTERNS.items():
        if model_lower.startswith(pattern):
            return _PROVIDER_ENV_MAP.get(provider, {})

    return {
        "OPENAI_API_KEY": "$OPENAI_API_KEY",
        "ANTHROPIC_API_KEY": "$ANTHROPIC_API_KEY",
    }


@click.group()
@click.version_option(version="0.1.0", prog_name="den")
def cli():
    """Den -- The living runtime for AI agents."""
    pass


@cli.command()
@click.option("--name", prompt="Agent name", help="Agent name (kebab-case)")
@click.option("--model", default="claude-sonnet-4-6", prompt="Model", help="LLM model")
def init(name: str, model: str):
    """Scaffold a new Agentfile."""
    filename = "Agentfile"
    if os.path.exists(filename):
        click.confirm(f"{filename} already exists. Overwrite?", abort=True)

    env_vars = _detect_env_vars(model)
    env_section = "\n".join(f"  {k}: \"{v}\"" for k, v in env_vars.items())

    kebab_name = name.lower().replace(" ", "-")

    content = f"""name: {kebab_name}
model: {model}

system_prompt: |
  You are {name}. Describe your role and personality here.

env:
{env_section}

tools:
  - web_search
  - file_read
  - file_write

bash:
  enabled: false

memory:
  max_size: 2gb

tasks:
  default-task:
    description: |
      Describe what this agent should do.

    loop:
      max_iterations: 3
      evaluation:
        method: algorithmic
        algorithmic_checks:
          - name: word_count
            type: min_word_count
            min_words: 100
            required: true

permissions:
  network: []
  filesystem:
    - /den/workspace
    - /den/output
    - /den/memory

resources:
  cpu: "2.0"
  memory: "4gb"
  disk: "10gb"
"""
    with open(filename, "w") as f:
        f.write(content)
    click.echo(f"Created: {filename}")
    click.echo(f"Edit it, then run: den up {filename}")


@cli.command()
@click.argument("agentfile", default="Agentfile")
@click.option("--den-home", default=None, help="Override Den home directory")
def up(agentfile: str, den_home: str | None):
    """Boot an agent -- it lives in its Den."""
    from den.core.lifecycle import AgentLifecycle

    den_home = den_home or _get_den_home()

    try:
        lc = AgentLifecycle(agentfile, den_home=den_home)
        lc.boot()
    except FileNotFoundError:
        click.echo(f"Error: Agentfile not found: {agentfile}", err=True)
        click.echo("Run 'den init' to create one.", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error booting agent: {e}", err=True)
        sys.exit(1)

    status = lc.get_status()
    click.echo(f"[den] Agent '{status.name}' is UP")
    click.echo(f"[den] Model: {status.model}")
    click.echo(f"[den] Tasks: {lc.scheduler.task_count} ({lc.scheduler.cron_count} cron)")
    click.echo(f"[den] Memory: {status.memory_count} memories")

    lc.start_scheduler()
    click.echo(f"[den] Scheduler started -- agent is autonomous")
    click.echo(f"[den] Use 'den trigger {status.name} <task>' to fire tasks manually")
    click.echo(f"[den] Use Ctrl+C to stop")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        click.echo(f"\n[den] Shutting down...")
        lc.shutdown()
        click.echo(f"[den] Agent '{status.name}' is DOWN. Den preserved.")


@cli.command()
@click.argument("agentfile", default="Agentfile")
def inspect(agentfile: str):
    """Analyze security posture of an Agentfile."""
    from den.agentfile import parse_agentfile, AgentfileError
    from den.tools import get_registry

    try:
        config = parse_agentfile(agentfile)
    except FileNotFoundError:
        click.echo(f"Error: {agentfile} not found", err=True)
        sys.exit(1)
    except AgentfileError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    registry = get_registry()

    click.echo(f"\nDen Agentfile Security Analysis")
    click.echo(f"{'=' * 40}")
    click.echo(f"Agent:    {config.name}")
    click.echo(f"Model:    {config.model}")
    click.echo()

    click.echo("Tools:")
    for tool_name in config.tools:
        spec = registry.get_spec(tool_name)
        if spec:
            flags = []
            if spec.requires_network:
                flags.append("network")
            if spec.requires_bash:
                flags.append("bash")
            if spec.requires_filesystem:
                flags.append("filesystem")
            flag_str = f" ({', '.join(flags)})" if flags else ""
            click.echo(f"  [ALLOWED]  {tool_name} v{spec.version}{flag_str}")
        else:
            click.echo(f"  [UNKNOWN]  {tool_name}")
    click.echo()

    click.echo("Network Permissions:")
    if config.permissions.network:
        for host in config.permissions.network:
            click.echo(f"  [ALLOWED]  {host}")
    else:
        click.echo(f"  [BLOCKED]  all outbound (no hosts allowed)")
    click.echo(f"  [BLOCKED]  all other outbound")
    click.echo()

    click.echo("Filesystem Permissions:")
    for path in config.permissions.filesystem:
        click.echo(f"  [ALLOWED]  {path}")
    click.echo(f"  [BLOCKED]  host filesystem")
    click.echo()

    click.echo("Bash Execution:")
    if config.bash.enabled:
        click.echo(f"  [ENABLED]  timeout: {config.bash.timeout}")
        if config.bash.allowed_commands:
            click.echo(f"  Allowed:   {', '.join(config.bash.allowed_commands)}")
        if config.bash.blocked_commands:
            click.echo(f"  Blocked:   {', '.join(config.bash.blocked_commands)}")
    else:
        click.echo(f"  [DISABLED]")
    click.echo()

    click.echo("Resources:")
    click.echo(f"  CPU:     {config.resources.cpu} cores")
    click.echo(f"  Memory:  {config.resources.memory}")
    click.echo(f"  Disk:    {config.resources.disk}")
    click.echo()

    click.echo(f"Tasks: {len(config.tasks)}")
    for name, task in config.tasks.items():
        phases = f" ({len(task.phases)} phases)" if task.phases else ""
        click.echo(f"  {name}{phases}")
    click.echo()

    if config.cron:
        click.echo("Cron Schedules:")
        for entry in config.cron:
            click.echo(f"  {entry.schedule}  ->  {entry.task}")
        click.echo()

    risks = []
    if config.bash.enabled:
        risks.append("Bash execution is enabled")
    if config.permissions.shell:
        risks.append("Shell permission is granted")
    if any(registry.get_spec(t) and registry.get_spec(t).requires_network for t in config.tools):
        risks.append("Network-accessing tools are enabled")

    if risks:
        click.echo("Risk Assessment:")
        for r in risks:
            click.echo(f"  WARNING: {r}")
    else:
        click.echo("Risk Assessment: LOW")


@cli.command()
@click.argument("agentfile", default="Agentfile")
@click.argument("task_name")
@click.option("--den-home", default=None)
def trigger(agentfile: str, task_name: str, den_home: str | None):
    """Manually trigger a task."""
    from den.core.lifecycle import AgentLifecycle

    den_home = den_home or _get_den_home()

    lc = AgentLifecycle(agentfile, den_home=den_home)
    lc.boot()

    click.echo(f"[den] Triggering: {task_name}")
    lc.trigger(task_name)

    time.sleep(0.5)
    while lc.scheduler and lc.scheduler.is_running(task_name):
        time.sleep(0.5)

    status = lc.get_status()
    click.echo(f"[den] Completed: {status.tasks_completed} passed, {status.tasks_failed} failed")
    lc.shutdown()


@cli.command()
@click.argument("agentfile", default="Agentfile")
@click.option("--search", default=None, help="Search memories")
@click.option("--den-home", default=None)
def memory(agentfile: str, search: str | None, den_home: str | None):
    """Inspect agent memory."""
    from den.agentfile import parse_agentfile
    from den.memory.config import DenMemoryConfig
    from den.memory.manager import MemoryManager

    den_home = den_home or _get_den_home()
    config = parse_agentfile(agentfile)

    db_path = os.path.join(den_home, "memory", config.name, "memory.db")
    if not os.path.exists(db_path):
        click.echo(f"No memory found for agent '{config.name}'")
        return

    mem = MemoryManager(DenMemoryConfig(db_path=db_path, use_fastembed=False))
    stats = mem.get_stats()

    click.echo(f"\nMemory: {config.name}")
    click.echo(f"Location: {db_path}")
    click.echo(f"Total memories: {stats['total']}")
    click.echo(f"Avg strength: {stats['avg_strength']}")
    click.echo(f"Tasks recorded: {stats['tasks_recorded']}")

    if stats.get("by_category"):
        click.echo(f"\nBy category:")
        for cat, count in stats["by_category"].items():
            click.echo(f"  {cat}: {count}")

    if search:
        click.echo(f"\nSearch: '{search}'")
        results = mem.recall(search, top_k=10)
        for r in results:
            click.echo(f"  [{r.get('category', '?')}] {r['content'][:80]}  (relevance: {r.get('relevance', '?')})")

    mem.close()


@cli.command()
@click.argument("agentfile", default="Agentfile")
@click.option("--den-home", default=None)
def tasks(agentfile: str, den_home: str | None):
    """Show task definitions from an Agentfile."""
    from den.agentfile import parse_agentfile

    config = parse_agentfile(agentfile)

    click.echo(f"\nAgent: {config.name}")
    click.echo(f"Tasks: {len(config.tasks)}")
    click.echo()

    for name, task in config.tasks.items():
        phases = f" ({len(task.phases)} phases)" if task.phases else ""
        loop_info = ""
        if task.loop:
            loop_info = f" [loop: max {task.loop.max_iterations} iterations]"
        click.echo(f"  {name}{phases}{loop_info}")
        click.echo(f"    {task.description.strip()[:80]}")

    if config.cron:
        click.echo(f"\nSchedules:")
        for entry in config.cron:
            click.echo(f"  {entry.schedule}  ->  {entry.task}")


@cli.command()
@click.argument("agentfile", default="Agentfile")
@click.option("--task", default=None, help="Filter by task name")
@click.option("--den-home", default=None)
def history(agentfile: str, task: str | None, den_home: str | None):
    """Show past task execution history."""
    from den.agentfile import parse_agentfile
    from den.memory.config import DenMemoryConfig
    from den.memory.store import MemoryStore

    den_home = den_home or _get_den_home()
    config = parse_agentfile(agentfile)

    db_path = os.path.join(den_home, "memory", config.name, "memory.db")
    if not os.path.exists(db_path):
        click.echo(f"No history found for agent '{config.name}'")
        return

    store = MemoryStore(DenMemoryConfig(db_path=db_path, use_fastembed=False))
    records = store.get_task_history(task_name=task, limit=20)
    store.close()

    if not records:
        click.echo("No task history recorded.")
        return

    click.echo(f"\nTask History: {config.name}")
    click.echo(f"{'=' * 60}")

    for r in records:
        from datetime import datetime
        ts = datetime.fromtimestamp(r["started_at"]).strftime("%Y-%m-%d %H:%M") if r["started_at"] else "?"
        status_icon = "+" if r["status"] == "success" else "-"
        click.echo(f"  [{status_icon}] {ts}  {r['task_name']}  "
                    f"({r['iterations']} iters, {r['status']})")
        if r.get("summary"):
            click.echo(f"      {r['summary'][:60]}")


if __name__ == "__main__":
    cli()
