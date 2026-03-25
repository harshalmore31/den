# Den Architecture

> **Status:** Implementation-ready specification
> **Version:** 2.0 — The Living Agent Runtime
> **Last updated:** 2026-03-25

---

## Table of Contents

1. [Philosophy and Vision](#1-philosophy-and-vision)
2. [Architecture Layers](#2-architecture-layers)
   - 2.1 [Key Architectural Decisions from Research](#21-key-architectural-decisions-from-research)
3. [The Five Pillars](#3-the-five-pillars)
   - 3.1 [Den — The Home](#31-den--the-home)
   - 3.2 [Memory — Always On](#32-memory--always-on)
   - 3.3 [Loop Architecture — Self-Correcting Execution](#33-loop-architecture--self-correcting-execution)
   - 3.4 [Cron and Scheduling — Autonomous Operation](#34-cron-and-scheduling--autonomous-operation)
   - 3.5 [Identity — Consistent, Accumulated, Persistent](#35-identity--consistent-accumulated-persistent)
4. [Agentfile Specification](#4-agentfile-specification)
5. [Execution Lifecycle](#5-execution-lifecycle)
6. [Loop Engine](#6-loop-engine)
7. [Task Scheduler](#7-task-scheduler)
8. [Bash Executor](#8-bash-executor)
9. [Memory System](#9-memory-system)
10. [Tool Library](#10-tool-library)
11. [Security Model](#11-security-model)
12. [CLI Design](#12-cli-design)
13. [Runtime Backend Abstraction](#13-runtime-backend-abstraction)
14. [Project Layout](#14-project-layout)
15. [Future Roadmap](#15-future-roadmap)

---

## 1. Philosophy and Vision

### The Industry's Broken Definition of "Agent"

The AI industry has converged on a definition of "agent" that is fundamentally wrong:

```
system_prompt + tools + LLM call-loop = "agent"
```

This is not an agent. This is a chatbot with function calling. It does not remember anything between sessions. It does not work while you sleep. It does not retry when it fails. It does not improve from experience. When the conversation ends, it ceases to exist. Call it again and it starts over, blind.

The consequences are real. Teams build "agents" that hallucinate because they cannot verify their own output. They build pipelines that fail silently because there is no retry logic. They instrument elaborate memory bolted on as an afterthought. They create brittle cron jobs that wrap LLM calls. They wonder why their agents cannot be trusted with real work.

The problem is architectural, not model-level. Giving a better LLM to a broken architecture produces a smarter chatbot, not a better agent.

### Den's Definition

Den draws a sharp line. A Den Agent has five properties. If it is missing any one of them, it is not an agent — it is a chatbot.

| Property | What it means |
|---|---|
| **Home** | Its own sandboxed environment with a filesystem, bash, and tools that persist |
| **Memory** | Persistent storage by default — the agent's brain survives forever |
| **Loop** | Self-correcting retry cycles with pass/fail evaluation |
| **Cron** | Works autonomously on schedule without being asked |
| **Identity** | Consistent personality plus accumulated history across all interactions |

Den's purpose is to provide infrastructure for all five. The developer provides the model, the system prompt, and the task definitions. Den provides everything else.

### The Analogy That Matters

Docker standardized how software is packaged and run. Before Docker, deploying software meant a unique snowflake of configuration on every machine. After Docker: write a Dockerfile, ship a container, run it anywhere. The environment became a first-class artifact.

Den does the same for AI agents. Before Den, every team hand-builds memory, retry logic, scheduling, and sandboxing from scratch — producing unique snowflakes of agent infrastructure. After Den: write an Agentfile, run `den up`, and the agent lives in its Den. The agent's environment — persistent, sandboxed, scheduled, self-correcting — becomes a first-class artifact.

```
Den is to AI agents what Docker is to services.
```

The key difference from the old analogy: Docker containers run and exit. Den agents live.

### Design Principles

**Persistence by default.** Memory is not opt-in. Every Den agent has a persistent brain. If you want a stateless agent, use a different tool.

**Loop before output.** Agents do not ship their first attempt. The Loop Engine wraps every task. Output leaves only when evaluation passes or retries are exhausted.

**Autonomous by design.** Cron is not a feature addition — it is core. Agents should work while their operators sleep.

**Sandboxed by default.** Every agent runs in isolation. Network access, filesystem access, and bash commands are explicitly declared. The default is deny.

**Auditable always.** Memory is plain files. Logs are structured. Every iteration of every task is recorded. Nothing happens in a black box.

**Swappable runtime.** Den Core does not care whether the underlying isolation is Docker, Firecracker, or a hosted sandbox. The RuntimeBackend is an abstraction. Switch without changing Agentfiles.

---

## 2. Architecture Layers

Den is organized into three layers with hard responsibility boundaries.

```
+-------------------------------------------------------------+
|                        User's World                         |
|                                                             |
|   Agentfile  -->  den up  -->  Agent Lives in its Den       |
|                                                             |
|   den trigger / cron schedule  -->  Tasks execute           |
|   Loop Engine evaluates  -->  retries or outputs artifact   |
|   den down  -->  Agent sleeps (state preserved)             |
|                                                             |
|   den ps / den logs / den memory / den history              |
|   (full observability at all times)                         |
+-------------------------------------------------------------+
|                    Den Core  (the product)                  |
|                                                             |
|  +----------------------+   +---------------------------+   |
|  | Agentfile Parser     |   | Agent Lifecycle Manager   |   |
|  | & Schema Validator   |   | (up / down / ps / shell)  |   |
|  +----------------------+   +---------------------------+   |
|                                                             |
|  +----------------------+   +---------------------------+   |
|  | Loop Engine          |   | Task Scheduler            |   |
|  | (self-correction)    |   | (cron + manual triggers)  |   |
|  +----------------------+   +---------------------------+   |
|                                                             |
|  +----------------------+                                   |
|  | PydanticAI Agent     |                                   |
|  | Runtime              |                                   |
|  +----------------------+                                   |
|                                                             |
|  +----------------------+   +---------------------------+   |
|  | Bash Executor        |   | Tool Library              |   |
|  | (sandboxed)          |   | & Permission Interceptor  |   |
|  +----------------------+   +---------------------------+   |
|                                                             |
|  +----------------------+   +---------------------------+   |
|  | Memory System        |   | Artifact Collector        |   |
|  | (always-on, /den/)   |   | & Output Manager          |   |
|  +----------------------+   +---------------------------+   |
|                                                             |
|  +----------------------+   +---------------------------+   |
|  | Logging &            |   | RuntimeBackend            |   |
|  | Observability        |   | Interface                 |   |
|  +----------------------+   +---------------------------+   |
+-------------------------------------------------------------+
|                Runtime Backend  (swappable)                 |
|                                                             |
|   DockerBackend (v1 — local)                                |
|   FirecrackerBackend (v2 — cloud, sub-100ms boot)          |
|   E2BBackend / FlyBackend (v2 — hosted option)             |
+-------------------------------------------------------------+
```

**User's World** is the only layer users touch. An Agentfile is the entire interface. All complexity is beneath this layer.

**Den Core** is the product. It parses Agentfiles, manages agent lifecycle, runs the Loop Engine, schedules tasks, executes sandboxed bash, manages memory, intercepts tool calls for permission enforcement, collects artifacts, and streams logs. Den Core does not know or care what runtime backend is underneath it.

**Runtime Backend** is an implementation detail. It provides isolation, filesystem mounting, process execution, and resource limiting. In v1, this is Docker. In v2, this is Firecracker or a hosted alternative. Swapping backends requires no Agentfile changes.

### 2.1 Key Architectural Decisions from Research

The following ten decisions were derived from primary research (Anthropic engineering blogs, PydanticAI documentation, and production agent experience). Each decision has a concrete impact on Den's architecture.

**1. Programmatic Tool Calling** — The LLM writes Python code that orchestrates multiple tools in a single round-trip, rather than making one tool call at a time. This eliminates conversational back-and-forth between the LLM and the tool runtime. Based on Anthropic's Advanced Tool Use blog, this approach yields approximately 37% fewer tokens per task. Den supports this via the `tool_execution.mode` Agentfile setting (`programmatic`, `traditional`, or `auto`).

**2. PydanticAI as Agent Framework** — Den uses PydanticAI as the agent runtime layer sitting between the Loop Engine and raw LLM SDK calls. PydanticAI handles the LLM tool-use loop, multi-provider support (Anthropic, OpenAI, etc.), structured output enforcement via `output_type`, and parallel tool calls. This replaces hand-rolled SDK call management and gives Den provider-swappable agent execution for free.

**3. Structured State Files (JSON, not Markdown)** — Phase outputs and progress tracking use Pydantic models serialized to JSON, not Markdown files. Per Anthropic's Long-Running Agents blog: "models are less likely to inappropriately change or overwrite JSON files." Markdown remains available for human-facing artifacts, but all machine-consumed state (progress, phase output, task history) is JSON.

**4. Context Budget Management** — The Loop Engine actively manages what goes into each iteration's context window. Rather than letting context grow unboundedly across iterations, the engine clears intermediate tool results between iterations and enforces configurable token budgets for memory injection (`memory_tokens`) and feedback injection (`feedback_tokens`). This is drawn from Anthropic's Context Engineering blog.

**5. Memory-based Phase Data Passing** — In multi-phase tasks, phases do not compress their output to fit into the next phase's prompt. Instead, each phase writes its full output to memory (namespaced by phase name), and the next phase recalls only what is relevant via semantic search. This eliminates information loss from compression and provides relevance-based retrieval instead of brute-force context stuffing.

**6. Consolidated Tool Design** — Tools are designed to solve workflows, not wrap API calls. Each tool returns concise output by default (not raw API responses). Errors must be actionable (tell the agent what to do differently, not just what went wrong). Tool descriptions serve as onboarding documentation — they teach the agent when and how to use the tool. Identifiers are semantic (`search_web`, not `tool_007`). Based on Anthropic's Writing Tools blog.

**7. Built-in Task Startup Sequence** — Every task execution begins with a deterministic startup sequence built into the Loop Engine infrastructure, not the system prompt. The sequence: read `/den/memory/` for relevant memories, read task history from SQLite, read `progress.json` if resuming, read prior iteration check results, inject compressed context, then begin work. This ensures agents always orient themselves before acting, without relying on prompt instructions.

**8. Expanded Memory Categories** — Two new memory categories are added alongside the existing `fact`, `preference`, `task_result`, and `error` categories: `progress` (current to-do state and checkpoint data for resumable tasks) and `learned` (meta-knowledge about what strategies and approaches worked or failed). These categories enable richer agent self-improvement across runs.

**9. Built-in Evaluation Rubrics** — Den ships standard evaluation rubrics for common task types: research, code, report, and analysis. These rubrics use an LLM-judge that scores output on a 0.0-1.0 scale across dimensions including factual accuracy, citation accuracy, completeness, and source quality. Developers can use built-in rubrics as-is, extend them, or define their own. This lowers the barrier to meaningful quality evaluation.

**10. Sub-agents are v2** — Phases within a single Agentfile are the v1 "lightweight sub-agents." They run in the same container, share memory, and are orchestrated by the Loop Engine. Real multi-container sub-agents — with independent Dens, separate models, and their own lifecycles — come in v2 via `den-compose.yaml`. Phases are the migration path: what works as a v1 phase can be promoted to a v2 independent agent without rewriting task logic.

---

## 3. The Five Pillars

### 3.1 Den — The Home

Each agent gets its own isolated sandboxed environment. This is not a scratch directory that gets deleted when the run finishes. It is a persistent home that the agent returns to every time it wakes up.

The Den includes:

- **Its own filesystem** mounted at `/den/` inside the sandbox, persisted to the host via a named Docker volume
- **Its own bash** (sandboxed — see Section 8)
- **Its own tools** (declared in the Agentfile, loaded on boot)
- **Its own memory** at `/den/memory/` (see Section 9)
- **Its own output space** at `/den/output/`
- **Its own workspace** at `/den/workspace/`

The agent does not "spin up, run, tear down." It boots, does work, sleeps between tasks, and wakes for the next trigger — all while preserving its filesystem, memory, and state.

```
/den/
├── memory/           # Brain — persists forever across all runs
│   ├── knowledge/    # Learned facts, domain knowledge
│   ├── task_history/ # Past task results, what worked
│   ├── notes/        # Agent's freeform notes to itself
│   └── index.json    # Memory index for fast lookup
├── workspace/        # Working scratch space during task execution
│   └── (task-specific working files)
├── output/           # Finalized artifacts delivered to user
│   ├── reports/
│   ├── data/
│   └── alerts/
└── logs/             # Execution logs, iteration records
    └── (structured JSON log files)
```

This is the agent's machine. It owns this space. The operator mounts it, inspects it with `den memory`, and reads artifacts from `den/output/`. But the agent works here, thinks here, and remembers here.

**Docker implementation detail:** The Den filesystem is a named Docker volume `den-{agent-name}-home`. The container mounts it at `/den/`. When `den down` stops the container, the volume persists. When `den up` starts the agent again, the volume is remounted and the agent resumes exactly where it left off.

### 3.2 Memory — Always On

Memory is not an option. Every Den agent has persistent memory. There is no configuration knob to disable it. If persistent memory is not what you want, Den is not the right tool.

**Why memory must be default-on:**

Current agent frameworks treat memory as an add-on. The result is agents that ask the same clarifying questions in every session, repeat mistakes they have already made, and cannot accumulate domain knowledge over time. This is the difference between an employee who has been on the job for two years and one who starts fresh every morning.

Den's position: persistent memory is what makes an agent an agent rather than a query.

**Memory is plain files.** Not a vector database. Not an opaque embedding store. Plain files in `/den/memory/`, fully auditable by anyone with `den shell` or `den memory`. The agent reads and writes these files using its file tools. The structure is the agent's to decide — Den enforces the directory, not the schema.

**Memory survives everything.** Container restarts. `den down` / `den up` cycles. Model version upgrades. The volume persists.

**Memory is per-agent.** Agent A's memory is not accessible to Agent B unless explicitly configured (v2 shared memory, see Section 15).

Full memory system design is in Section 9.

### 3.3 Loop Architecture — Self-Correcting Execution

This is Den's core innovation. Everything else exists to support it.

**The problem with single-shot execution:**

Every existing "agent" framework produces output from a single pass. The LLM generates text, the tools get called, the result is returned. If the output is wrong, incomplete, or low quality — you get what you got. You can prompt-engineer to improve average quality, but there is no systematic quality gate.

Den agents do not have a single pass. They have a loop.

```
                    +-------------------+
                    |  Task Triggered   |
                    |  (cron or manual) |
                    +--------+----------+
                             |
                             v
                    +--------+----------+
             +----->|  Attempt N        |
             |      |  (tools + bash    |
             |      |   + memory read)  |
             |      +--------+----------+
             |               |
             |               v
             |      +--------+----------+
             |      |  Evaluate Result  |
             |      |  against criteria |
             |      +--------+----------+
             |               |
             |       +-------+--------+
             |       |                |
             |    FAILED           PASSED
             |       |                |
             |       v                v
             |  +---------+    +------+--------+
             |  | Generate|    | Collect       |
             |  | feedback|    | Artifacts     |
             |  +---------+    +------+--------+
             |       |                |
             |       v                v
             | +----------+    +------+--------+
             | | Write to |    | Write success |
             | | memory   |    | to memory     |
             | | (attempt)|    | (what worked) |
             | +----------+    +------+--------+
             |       |                |
             | +-----+------+         v
             | | cooldown   |   +-----+------+
             | +-----+------+   | Sleep /    |
             |       |          | Wait next  |
             | N < max_iter?    | trigger    |
             |  Yes  |          +------------+
             +-------+
                (No: on_fail behavior)
```

**Three evaluation methods:**

`self` — The agent judges its own output against the criteria. Fast, no external dependencies. Works well for criteria that are structural (does the report have 3 sections?) or factual (are there source URLs?). Less reliable for subjective quality judgments.

`script` — A shell script or Python script receives the output path and exits 0 for pass or non-zero for fail. Use this when you have a deterministic checker (lint, schema validation, test suite). The script runs inside the sandbox.

`llm-judge` — A separate LLM call evaluates the output against the criteria. Use this for subjective quality judgments (is this report well-written? is the analysis thorough?). Costs more, but provides genuine quality assurance for complex outputs.

**Feedback is structured.** When evaluation fails, the evaluator generates structured feedback explaining what was wrong and what the next attempt should do differently. This feedback is passed as context to the next iteration. The agent does not retry blind — it retries informed.

**Memory tracks iterations.** Every attempt — pass or fail — is logged to `/den/memory/task_history/`. The agent can read its own history and learn from past failures across task executions, not just within a single run.

Full Loop Engine design is in Section 6.

### 3.4 Cron and Scheduling — Autonomous Operation

An agent that only works when you ask it to is not autonomous. It is a sophisticated API call. Den agents work on schedule.

Cron expressions in the Agentfile define when each task triggers. The Task Scheduler (Section 7) runs inside the agent's Den, parses these expressions, and fires tasks at the correct times. The agent wakes up, does the work, loops until quality passes, outputs the artifact, and goes back to sleep.

The operator does not need to be present. The agent does not need to be prompted. This is the point.

**Manual triggers are always available.** `den trigger agent-name task-name` fires a task immediately regardless of schedule. Cron and manual triggers are not mutually exclusive — a weekly report agent can be triggered manually for an ad-hoc run without changing its schedule.

**Trigger types (v1):**

- Cron schedule (time-based, e.g., `0 9 * * MON`)
- Manual (`den trigger`)
- Queue-based (v2 — external event queue)
- Webhook (v2 — HTTP trigger)

### 3.5 Identity — Consistent, Accumulated, Persistent

Identity is not just a system prompt. System prompts are stateless. Den identity has three components:

**System prompt** — The agent's permanent instructions, role, and personality. Written in the Agentfile. Does not change between runs.

**Tool configuration** — The specific set of tools the agent has access to. A research analyst has web search and PDF reading. A code reviewer has bash and file tools. Tools define the agent's capability profile.

**Accumulated history** — Everything the agent has learned, every task it has completed, every failure it has recovered from. This lives in `/den/memory/` and grows forever. Two agents with identical system prompts but different histories are different agents.

Identity persists because the Den persists. `den down` does not erase identity — it pauses it. `den up` resumes it. The agent that wakes up next Monday for its weekly report is the same agent that ran last Monday, with one more week of experience.

---

## 4. Agentfile Specification

The Agentfile is the complete declarative specification of a Den agent. It is a YAML file. It is the only artifact a developer needs to create and configure a Den agent.

### Annotated Full Schema

```yaml
# ============================================================
# Agentfile — Den Agent Specification
# ============================================================

# Required. Unique name for this agent. Used as the identifier
# for den up, den trigger, den logs, etc.
name: research-analyst

# Required. The model to use. Supports any provider in the
# format provider/model or just model for default provider.
model: claude-sonnet-4-6

# ============================================================
# IDENTITY
# ============================================================

# Required. The agent's permanent instructions, role, and
# personality. This does not change between runs.
system_prompt: |
  You are a research analyst specializing in market trends.
  You work methodically, verify all sources, and produce
  thorough reports that a professional would be proud to
  sign their name to.

  When you begin a task, read your memory first to understand
  what you have learned in past runs. When you finish, write
  what you learned to memory so your future self benefits.

  You do not produce placeholder text. You do not write
  "TBD" or "to be added later." Every section you start,
  you finish.

# ============================================================
# ENVIRONMENT
# ============================================================

# Environment variables available inside the Den.
# Use $VAR_NAME syntax to reference host environment variables.
env:
  ANTHROPIC_API_KEY: "$ANTHROPIC_API_KEY"
  OPENAI_API_KEY: "$OPENAI_API_KEY"
  CUSTOM_SETTING: "literal-value"

# ============================================================
# TOOL EXECUTION
# ============================================================

# How the agent invokes tools. Modes:
#   programmatic — LLM writes Python code that calls multiple
#                  tools in one round-trip (~37% fewer tokens)
#   traditional  — standard one-tool-at-a-time LLM tool calling
#   auto         — Den picks based on task complexity and model
tool_execution:
  mode: auto    # programmatic | traditional | auto

# ============================================================
# TOOLS
# ============================================================

# Tools the agent can use. These are loaded from the Den Tool
# Library and made available through the permission interceptor.
# The agent cannot use tools not listed here.
tools:
  - web_search
  - file_read
  - file_write
  - csv_analyze
  - pdf_read
  - http_get

# ============================================================
# BASH (sandboxed)
# ============================================================

# Gives the agent access to sandboxed shell execution.
# Optional. If omitted, bash is disabled.
bash:
  enabled: true

  # Commands the agent is allowed to run. Enforced at
  # the Bash Executor level before any execution.
  allowed_commands:
    - python3
    - pip
    - curl
    - jq
    - pandoc
    - wc
    - grep
    - sort
    - awk

  # Commands that are explicitly blocked, even if they
  # would otherwise be allowed. Takes precedence over
  # allowed_commands. Matched by prefix.
  blocked_commands:
    - "rm -rf"
    - sudo
    - chmod
    - chown
    - "curl * | bash"  # pipe-to-bash pattern

  # Maximum wall-clock time for any single bash invocation.
  timeout: 120s

# ============================================================
# MEMORY
# ============================================================

# Memory is always persistent. This section configures limits.
# Memory cannot be disabled — it is a core Den primitive.
memory:
  max_size: 2gb

  # Optional: seed the agent's memory with initial knowledge
  # on first boot. Useful for domain knowledge files, reference
  # data, or initial instructions to the agent's future self.
  seed:
    - source: ./initial-knowledge/markets.md
      dest: /den/memory/knowledge/markets.md

# ============================================================
# LOOP ARCHITECTURE (global defaults)
# ============================================================

# Default loop configuration. Individual tasks can override
# any of these values.
loop:
  # Maximum retry attempts before declaring failure.
  max_iterations: 5

  evaluation:
    # method: self | script | llm-judge
    method: self

    # Criteria the output must satisfy. Written as a checklist.
    # For method: self, the agent evaluates against this list.
    # For method: script, this is passed to the script as context.
    # For method: llm-judge, this is the judge's evaluation rubric.
    criteria: |
      - Report has at least three distinct sections with headers
      - Every factual claim includes a source URL in parentheses
      - No placeholder text (TBD, to be added, lorem ipsum, etc.)
      - Report is at least 800 words
      - Conclusion section present and summarizes key findings

  # Context budget management — controls how much context is
  # injected per iteration to prevent unbounded context growth.
  context_budget:
    memory_tokens: 500       # Max tokens from memory injection
    feedback_tokens: 1000    # Max tokens from prior feedback
    clear_tool_results: true # Clear intermediate tool results between iterations

  # What to do when max_iterations is exhausted without passing.
  # retry_with_feedback | stop | notify
  on_fail: notify

  # Wait between retry attempts. Gives external resources time
  # to settle and prevents tight loops from burning tokens.
  cooldown: 30s

# ============================================================
# SCHEDULING
# ============================================================

# Define when tasks run automatically. Uses standard cron
# expression syntax: minute hour day-of-month month day-of-week
cron:
  - schedule: "0 9 * * MON"
    task: weekly-market-report

  - schedule: "*/30 * * * *"
    task: check-news-alerts

  - schedule: "0 8 * * *"
    task: daily-briefing

# ============================================================
# TASKS
# ============================================================

# Named units of work. Each task can be triggered manually
# or by a cron schedule. Each task has its own description,
# artifacts, and optionally its own loop configuration that
# overrides the global defaults.
tasks:

  weekly-market-report:
    # Task complexity hint — auto-scales iteration budgets,
    # context window allocation, and cooldown timing.
    # low: quick lookups, simple transforms
    # medium: multi-step research, moderate synthesis
    # high: deep analysis, multi-source, long-form output
    complexity: medium    # low | medium | high

    description: |
      Generate this week's market report. The report must cover:
      1. Key market movements (major indices, notable movers)
      2. Notable company news (earnings, M&A, leadership changes)
      3. Upcoming events (economic calendar, Fed meetings, earnings)

      Use web_search to gather current data. Read your memory
      first to understand what you covered last week. Write a
      summary of what you found to memory when done.

    # Artifacts this task is expected to produce.
    artifacts:
      - path: /den/output/weekly-report.md
        type: markdown
        required: true   # Failure to produce this = task failure

    # Task-level loop config overrides global defaults.
    loop:
      max_iterations: 3
      evaluation:
        method: self
        criteria: |
          - Covers all three required sections with subheadings
          - Data references are from the current week (check dates)
          - At least 5 distinct source URLs cited
          - Word count exceeds 1000 words

  check-news-alerts:
    description: |
      Scan for breaking market news from the past 30 minutes.
      If any story is significant (major index move >2%, major
      earnings surprise, Fed announcement, M&A >$1B), write a
      brief alert to /den/output/alerts/ named with a timestamp.
      If nothing significant, write nothing and log a quiet check.

    artifacts:
      - path: /den/output/alerts/
        type: directory
        # required: false means the task passes even if no
        # artifact is produced (appropriate for conditional output)
        required: false

    loop:
      max_iterations: 2
      evaluation:
        method: self
        criteria: |
          - If news is significant, alert file exists and is complete
          - If no significant news, nothing was written (correct behavior)
          - No false alarms (trivial movements reported as significant)

  daily-briefing:
    description: |
      Produce a one-page daily briefing for review at 8am.
      Consult memory for ongoing stories to follow up on.
      Update memory with new developments on tracked stories.

    artifacts:
      - path: /den/output/briefings/daily-{date}.md
        type: markdown
        required: true

    loop:
      max_iterations: 4
      evaluation:
        method: llm-judge
        criteria: |
          - Briefing is concise (one page, under 600 words)
          - Covers 3-5 top stories
          - Each story has 2-3 sentence summary and so-what
          - Professional tone throughout
          - No grammatical errors
      on_fail: notify

# ============================================================
# PERMISSIONS
# ============================================================

permissions:
  # Allowlisted network destinations. The agent cannot make
  # outbound connections to any host not listed here.
  # Supports wildcard subdomains with *.
  network:
    - api.anthropic.com
    - "*.reuters.com"
    - "*.bloomberg.com"
    - "*.ft.com"
    - "*.wsj.com"
    - finance.yahoo.com
    - api.openai.com

  # Filesystem paths the agent can read and write.
  # The agent cannot access paths outside this list.
  filesystem:
    - /den/workspace
    - /den/output
    - /den/memory

# ============================================================
# RESOURCES
# ============================================================

resources:
  cpu: "2.0"        # CPU cores (float)
  memory: "4gb"     # RAM limit
  disk: "20gb"      # Disk quota for the Den volume
```

### Agentfile Schema Reference

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Unique agent identifier |
| `model` | string | yes | Model identifier |
| `system_prompt` | string | yes | Agent's permanent instructions |
| `tool_execution.mode` | enum | no | `programmatic` / `traditional` / `auto` (default: auto) |
| `env` | map | no | Environment variables |
| `tools` | list | no | Tools from the Tool Library |
| `bash.enabled` | bool | no | Enable sandboxed bash (default: false) |
| `bash.allowed_commands` | list | no | Command prefix whitelist |
| `bash.blocked_commands` | list | no | Command prefix blacklist (takes precedence) |
| `bash.timeout` | duration | no | Max wall time per invocation (default: 60s) |
| `memory.max_size` | size | no | Memory volume size limit (default: 1gb) |
| `memory.seed` | list | no | Files to copy into memory on first boot |
| `loop.max_iterations` | int | no | Global retry limit (default: 3) |
| `loop.evaluation.method` | enum | no | `self` / `script` / `llm-judge` (default: self) |
| `loop.evaluation.criteria` | string | no | Evaluation rubric |
| `loop.context_budget.memory_tokens` | int | no | Max tokens from memory injection (default: 500) |
| `loop.context_budget.feedback_tokens` | int | no | Max tokens from prior feedback (default: 1000) |
| `loop.context_budget.clear_tool_results` | bool | no | Clear tool results between iterations (default: true) |
| `loop.on_fail` | enum | no | `retry_with_feedback` / `stop` / `notify` (default: stop) |
| `loop.cooldown` | duration | no | Wait between retries (default: 10s) |
| `cron` | list | no | Scheduled task triggers |
| `tasks` | map | yes | Named task definitions |
| `permissions.network` | list | no | Allowed outbound hosts |
| `permissions.filesystem` | list | no | Allowed filesystem paths |
| `resources.cpu` | float | no | CPU core limit |
| `resources.memory` | size | no | RAM limit |
| `resources.disk` | size | no | Disk limit |

### Task Schema Reference

Each entry in `tasks:` supports:

| Field | Type | Required | Description |
|---|---|---|---|
| `complexity` | enum | no | `low` / `medium` / `high` — auto-scales iteration budgets (default: medium) |
| `description` | string | yes | Task instructions passed to the agent |
| `artifacts` | list | no | Expected output files or directories |
| `artifacts[].path` | string | yes | Path inside Den (supports `{date}`, `{timestamp}`) |
| `artifacts[].type` | enum | yes | `markdown` / `json` / `csv` / `directory` / `any` |
| `artifacts[].required` | bool | no | Whether absence = failure (default: true) |
| `loop` | object | no | Task-level loop override (merges with global defaults) |

---

## 5. Execution Lifecycle

### Full Lifecycle: From Agentfile to Sleeping Agent

```
den up agent.yaml
    |
    v
[Parse & Validate]
    Parse Agentfile YAML
    Validate schema (required fields, enum values, etc.)
    Validate tool names against Tool Library registry
    Validate cron expressions
    Validate permissions (no contradictions)
    Emit parse errors with line numbers before any execution
    |
    v
[Build Den Image]
    Pull base image (den-base:v1)
    Install declared tools
    Apply resource limits
    Configure network egress rules (iptables)
    Tag image as den-{name}:latest
    |
    v
[Provision Den Volume]
    Check if den-{name}-home volume exists
    If yes: mount existing (agent resumes with its memory)
    If no: create new volume, run memory.seed if configured
    |
    v
[Start Agent Container]
    docker run -d
        --name den-{name}
        --mount den-{name}-home:/den
        --network den-{name}-net
        --cpus {resources.cpu}
        --memory {resources.memory}
        den-{name}:latest
        den-agent-process
    |
    v
[Boot Agent Process]
    Load Agentfile config into process memory
    Initialize Tool Library with declared tools + permissions
    Initialize Bash Executor with allowed/blocked lists
    Initialize Memory System (index /den/memory/)
    Start Task Scheduler with cron definitions
    Log: "Agent {name} is up. Scheduler running."
    |
    v
[Scheduler Loop - runs forever until den down]
    For each cron entry:
        Register with APScheduler
        On fire: enqueue task to TaskQueue

    Listen for manual triggers (den trigger via IPC socket)
    Dequeue tasks and dispatch to Loop Engine
    |
    v
[Built-in Task Startup Sequence — per task, before agent work]
    This sequence runs automatically. It is built into infrastructure,
    not the system prompt. The agent does not need to be told to do this.
        |
        v
    1. Read /den/memory/ for relevant memories (semantic search)
    2. Read task history from SQLite (past attempts, scores, feedback)
    3. Read progress.json if resuming an interrupted task
    4. Read prior iteration check results (what failed last time)
    5. Inject compressed context within context_budget limits
    6. Begin work — agent executes with full orientation
        |
        v
[Loop Engine — per task execution]
    See Section 6 for full detail
    |
    v
[Agent Sleeps Between Tasks]
    Scheduler idles, waiting for next cron tick or trigger
    Container remains running
    Memory persists on volume
    Logs continue to accumulate
    |
    v
den down agent-name
    |
    v
[Graceful Shutdown]
    Signal running task to complete current iteration
    Wait up to 30s for clean exit
    Write shutdown record to /den/logs/
    Stop container (volume persists — agent's brain is safe)
    Log: "Agent {name} is down. Den preserved."
```

### State Transitions

```
            den up
ABSENT  ----------->  BOOTING
                          |
                    (init complete)
                          |
                          v
             task fires   IDLE  <---- task completes
                    +--------+
                    |        |
                    v        |
                 RUNNING ----+
                    |
              (evaluation fails,
               N < max_iterations)
                    |
                    v
                 RETRYING ---> RUNNING
                    |
              (max_iterations reached)
                    |
                    v
                 FAILING
                    |
              (on_fail: notify)
                    |
                    v
                 IDLE (notified)

    den down (from any state)
        ---> STOPPING ---> STOPPED (volume preserved)
```

---

## 6. Loop Engine

The Loop Engine is the architectural centerpiece of Den. Every task execution — whether triggered by cron or manually — passes through the Loop Engine.

### Design

```python
# den/core/loop_engine.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time
import logging

logger = logging.getLogger(__name__)


class LoopStatus(Enum):
    SUCCESS = "success"
    FAILED = "failed"
    EXHAUSTED = "exhausted"


@dataclass
class EvaluationResult:
    passed: bool
    score: float          # 0.0 to 1.0
    feedback: str         # What was wrong and what to try differently
    method_used: str      # self | script | llm-judge
    criteria_results: list[dict]  # Per-criterion pass/fail


@dataclass
class IterationRecord:
    iteration: int
    start_time: float
    end_time: float
    result_summary: str
    evaluation: EvaluationResult
    artifact_paths: list[str]


@dataclass
class LoopResult:
    status: LoopStatus
    iterations: int
    final_evaluation: Optional[EvaluationResult]
    artifact_paths: list[str]
    iteration_records: list[IterationRecord]
    total_duration_s: float


class LoopEngine:
    def __init__(self, agent_context, memory_system, artifact_collector):
        self.agent = agent_context
        self.memory = memory_system
        self.artifacts = artifact_collector

    def execute(self, task: "Task", loop_config: "LoopConfig") -> LoopResult:
        """
        Execute a task in a self-correcting loop.
        Returns only when the task passes evaluation, exhausts retries,
        or encounters a non-recoverable error.
        """
        iteration = 0
        feedback: Optional[str] = None
        records: list[IterationRecord] = []
        start = time.monotonic()

        while iteration < loop_config.max_iterations:
            iteration += 1
            iter_start = time.monotonic()

            logger.info(f"[{task.name}] Iteration {iteration}/{loop_config.max_iterations}")

            # Build execution context: task description + any feedback
            # from prior failed iterations + relevant memory
            context = self._build_context(task, iteration, feedback)

            # Run the agent on this task with the full context
            result = self.agent.execute(context)

            # Evaluate the result against declared criteria
            evaluation = self._evaluate(result, task, loop_config.evaluation)

            record = IterationRecord(
                iteration=iteration,
                start_time=iter_start,
                end_time=time.monotonic(),
                result_summary=result.summary,
                evaluation=evaluation,
                artifact_paths=result.artifact_paths,
            )
            records.append(record)

            # Write attempt to memory regardless of pass/fail
            self.memory.write(
                f"task_history/{task.name}/attempt_{iteration}.json",
                {
                    "task": task.name,
                    "iteration": iteration,
                    "passed": evaluation.passed,
                    "score": evaluation.score,
                    "feedback": evaluation.feedback,
                    "timestamp": iter_start,
                }
            )

            if evaluation.passed:
                # Collect artifacts from the run
                collected = self.artifacts.collect(result, task)

                # Write success record to memory — future runs can learn from this
                self.memory.write(
                    f"task_history/{task.name}/last_success.json",
                    {
                        "task": task.name,
                        "iterations_needed": iteration,
                        "criteria_results": evaluation.criteria_results,
                        "artifact_paths": collected,
                        "timestamp": iter_start,
                    }
                )

                logger.info(
                    f"[{task.name}] PASSED on iteration {iteration}. "
                    f"Artifacts: {collected}"
                )

                return LoopResult(
                    status=LoopStatus.SUCCESS,
                    iterations=iteration,
                    final_evaluation=evaluation,
                    artifact_paths=collected,
                    iteration_records=records,
                    total_duration_s=time.monotonic() - start,
                )

            # Failed — generate feedback for next iteration
            feedback = self._generate_feedback(evaluation, iteration, loop_config)
            logger.warning(
                f"[{task.name}] Iteration {iteration} FAILED. "
                f"Score: {evaluation.score:.2f}. Feedback: {feedback[:100]}..."
            )

            if iteration < loop_config.max_iterations:
                logger.info(f"[{task.name}] Waiting {loop_config.cooldown}s before retry...")
                time.sleep(loop_config.cooldown)

        # Exhausted all iterations
        logger.error(
            f"[{task.name}] EXHAUSTED {loop_config.max_iterations} iterations without passing."
        )
        self._handle_failure(task, loop_config.on_fail, records)

        return LoopResult(
            status=LoopStatus.EXHAUSTED,
            iterations=iteration,
            final_evaluation=records[-1].evaluation if records else None,
            artifact_paths=[],
            iteration_records=records,
            total_duration_s=time.monotonic() - start,
        )

    def _build_context(self, task, iteration, feedback):
        """Build the full context passed to the agent for this iteration."""
        ctx = {
            "task_description": task.description,
            "iteration": iteration,
            "prior_feedback": feedback,
            "memory_index": self.memory.read_index(),
        }
        return ctx

    def _evaluate(self, result, task, eval_config) -> EvaluationResult:
        """Dispatch to the configured evaluation method."""
        method = eval_config.method
        if method == "self":
            return SelfEvaluator().evaluate(result, eval_config.criteria)
        elif method == "script":
            return ScriptEvaluator(eval_config.script_path).evaluate(result, eval_config.criteria)
        elif method == "llm-judge":
            return LLMJudgeEvaluator(self.agent.model).evaluate(result, eval_config.criteria)
        else:
            raise ValueError(f"Unknown evaluation method: {method}")

    def _generate_feedback(self, evaluation, iteration, config) -> str:
        """Generate structured feedback for the next iteration."""
        failed_criteria = [
            c for c in evaluation.criteria_results if not c["passed"]
        ]
        lines = [
            f"Iteration {iteration} did not pass evaluation.",
            f"Overall score: {evaluation.score:.0%}",
            "",
            "The following criteria were not satisfied:",
        ]
        for c in failed_criteria:
            lines.append(f"  - {c['criterion']}: {c['reason']}")
        lines += [
            "",
            "In your next attempt, specifically address these gaps.",
            "Do not repeat the same approach that just failed.",
        ]
        return "\n".join(lines)

    def _handle_failure(self, task, on_fail, records):
        """Handle exhausted retries per on_fail configuration."""
        if on_fail == "notify":
            # Write a notification record; the CLI polls this
            self.memory.write(
                f"task_history/{task.name}/failure_notification.json",
                {
                    "task": task.name,
                    "total_iterations": len(records),
                    "final_score": records[-1].evaluation.score if records else 0,
                    "notify": True,
                }
            )
        elif on_fail == "stop":
            pass  # Log already written, nothing else needed
        # retry_with_feedback has already been applied in the loop
```

### PydanticAI Integration

The Loop Engine delegates agent execution to PydanticAI, which manages the LLM tool-use loop internally.

**Structured Phase Output** — Each phase declares a PydanticAI `output_type` (a Pydantic model). PydanticAI enforces that the LLM's output conforms to this schema before returning. This means phase outputs are always valid, typed data — not free-form text that might need parsing.

**Validation-Retry via `@output_validator`** — PydanticAI's `@output_validator` decorator provides a framework-level validation-retry loop that sits below the Loop Engine's evaluation retry. If the LLM produces output that is structurally valid but semantically wrong (e.g., a summary that is too long), the validator rejects it and PydanticAI retries within the same iteration. The Loop Engine's evaluation operates on the final validated output.

**Memory-based Phase Data Passing** — Phases do not pass data directly. Instead, each phase writes its output to memory with `namespace=phase_name`. The next phase recalls relevant data via semantic search filtered by the prior phase's namespace. This means Phase 2 does not receive Phase 1's entire output — it retrieves only what is relevant to its own task.

```
Phase 1 (research):
  → writes to /den/memory/phases/research/*.json

Phase 2 (analysis):
  → semantic search: namespace="research", query="key findings"
  → retrieves only relevant research memories
  → writes to /den/memory/phases/analysis/*.json
```

**Progress Tracking** — The Loop Engine auto-writes `progress.json` after each iteration of each task. This file contains the current iteration number, pass/fail status, criteria results, and a checkpoint of work completed so far. If the agent is interrupted (`den down` during execution), the next `den up` reads `progress.json` and resumes from the last checkpoint rather than starting over.

**Context Budget Management** — Between iterations, the Loop Engine clears intermediate tool results from context. Only the task description, structured feedback from the prior iteration, and budgeted memory/context survive into the next iteration. This prevents context window exhaustion on multi-iteration tasks. Token budgets are configurable via `loop.context_budget` in the Agentfile.

### Evaluator Implementations

```python
# den/core/evaluators.py

import subprocess
import json
from pathlib import Path


class SelfEvaluator:
    """
    The agent judges its own output.
    The agent receives the criteria checklist and the output,
    and returns a structured pass/fail for each criterion.
    """

    def evaluate(self, result, criteria: str) -> EvaluationResult:
        # This call goes back to the LLM with a structured prompt
        # asking it to evaluate the output against each criterion.
        # The prompt enforces JSON output for reliable parsing.
        evaluation_prompt = f"""
You are evaluating your own work. Below is the output you produced,
followed by the criteria it must satisfy.

For each criterion, output whether it PASSED or FAILED, and if FAILED,
explain exactly what is missing or wrong.

Output format (JSON):
{{
  "criteria_results": [
    {{"criterion": "...", "passed": true/false, "reason": "..."}}
  ],
  "overall_score": 0.0-1.0,
  "overall_passed": true/false
}}

OUTPUT TO EVALUATE:
{result.content}

CRITERIA:
{criteria}
"""
        # ... LLM call with structured output parsing ...
        pass


class ScriptEvaluator:
    """
    A shell script evaluates the output.
    Script receives output path via environment variable.
    Exit 0 = pass. Non-zero = fail. Stdout = feedback.
    """

    def __init__(self, script_path: str):
        self.script_path = script_path

    def evaluate(self, result, criteria: str) -> EvaluationResult:
        env = {
            "DEN_OUTPUT_PATH": str(result.primary_artifact_path),
            "DEN_CRITERIA": criteria,
        }
        proc = subprocess.run(
            [self.script_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        passed = proc.returncode == 0
        feedback = proc.stdout.strip() if not passed else ""
        return EvaluationResult(
            passed=passed,
            score=1.0 if passed else 0.0,
            feedback=feedback,
            method_used="script",
            criteria_results=[{"criterion": "script_exit_code", "passed": passed, "reason": feedback}],
        )


class LLMJudgeEvaluator:
    """
    A separate LLM call evaluates the output against the criteria.
    Useful for subjective quality judgments.
    Uses a different/independent call to avoid self-serving bias.
    """

    def __init__(self, model: str):
        self.model = model

    def evaluate(self, result, criteria: str) -> EvaluationResult:
        judge_prompt = f"""
You are an independent quality judge. You will evaluate a piece of work
against specific criteria and provide a structured assessment.

Be rigorous. Do not pass work that does not fully satisfy the criteria.
Partial completion is a failure.

Work to evaluate:
{result.content}

Evaluation criteria:
{criteria}

Return JSON in this exact format:
{{
  "criteria_results": [
    {{"criterion": "...", "passed": true/false, "reason": "precise explanation"}}
  ],
  "overall_score": 0.0-1.0,
  "overall_passed": true/false,
  "summary": "one sentence overall assessment"
}}
"""
        # ... independent LLM call, no tool access, structured output ...
        pass
```

### Loop State in the CLI

```
$ den history research-analyst

Agent: research-analyst
Showing last 10 task executions

TASK                   TRIGGERED          RESULT    ITERS  DURATION
weekly-market-report   2026-03-24 09:00   PASSED    2/3    4m 12s
check-news-alerts      2026-03-23 23:30   PASSED    1/2    47s
check-news-alerts      2026-03-23 23:00   PASSED    1/2    39s
weekly-market-report   2026-03-17 09:00   PASSED    3/3    7m 55s
daily-briefing         2026-03-17 08:00   FAILED    4/4    9m 01s
check-news-alerts      2026-03-17 07:30   PASSED    1/2    42s
...

$ den history research-analyst --task weekly-market-report --last 1 --verbose

Task: weekly-market-report
Triggered: 2026-03-24 09:00:00
Final status: PASSED (iteration 2 of 3)
Duration: 4m 12s

  Iteration 1 — FAILED (score: 0.60, duration: 1m 55s)
    Criteria failures:
      - "At least 5 distinct source URLs cited" — found only 3 URLs
      - "Word count exceeds 1000 words" — 743 words produced

  Iteration 2 — PASSED (score: 1.00, duration: 2m 17s)
    All criteria satisfied.
    Artifact: /den/output/weekly-report.md (1,847 words)
```

---

## 7. Task Scheduler

The Task Scheduler runs inside each agent's Den process. It is responsible for firing tasks on schedule and handling manual trigger signals.

### Design

```python
# den/core/scheduler.py

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import socket
import threading
import json
import logging

logger = logging.getLogger(__name__)


class TaskScheduler:
    """
    Manages cron-based and manual triggering of tasks.
    Runs as a background thread within the agent process.
    """

    def __init__(self, tasks: dict, cron_defs: list, loop_engine, trigger_socket_path: str):
        self.tasks = tasks
        self.loop_engine = loop_engine
        self.trigger_socket = trigger_socket_path
        self.queue = TaskQueue()
        self.scheduler = BackgroundScheduler()
        self._running_tasks: dict[str, threading.Thread] = {}

    def start(self):
        """Register all cron jobs and start listening for manual triggers."""
        for cron_def in self.cron_defs:
            task_name = cron_def["task"]
            schedule = cron_def["schedule"]

            if task_name not in self.tasks:
                raise ValueError(f"Cron references unknown task: {task_name}")

            self.scheduler.add_job(
                func=self._enqueue,
                trigger=CronTrigger.from_crontab(schedule),
                args=[task_name, "cron"],
                id=f"cron-{task_name}",
                name=f"Cron trigger for {task_name}",
                replace_existing=True,
            )
            logger.info(f"Scheduled task '{task_name}' with cron '{schedule}'")

        self.scheduler.start()

        # Start Unix socket listener for manual triggers (den trigger)
        trigger_thread = threading.Thread(
            target=self._listen_for_triggers,
            daemon=True,
        )
        trigger_thread.start()

        logger.info("Task Scheduler started.")

    def _enqueue(self, task_name: str, trigger_source: str):
        """Add a task to the execution queue."""
        self.queue.put({
            "task_name": task_name,
            "trigger_source": trigger_source,
        })
        logger.info(f"Task '{task_name}' enqueued (trigger: {trigger_source})")

    def _listen_for_triggers(self):
        """
        Listen on a Unix socket for manual trigger commands.
        'den trigger agent-name task-name' sends to this socket.
        """
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(self.trigger_socket)
            server.listen(5)
            while True:
                conn, _ = server.accept()
                with conn:
                    data = conn.recv(1024).decode()
                    try:
                        msg = json.loads(data)
                        task_name = msg["task"]
                        self._enqueue(task_name, "manual")
                        conn.send(json.dumps({"status": "queued"}).encode())
                    except (json.JSONDecodeError, KeyError) as e:
                        conn.send(json.dumps({"error": str(e)}).encode())

    def run_dispatch_loop(self):
        """
        Main loop: dequeue tasks and dispatch to Loop Engine.
        Respects concurrency — by default, one task runs at a time per agent.
        """
        while True:
            task_def = self.queue.get()  # blocks until task available
            task_name = task_def["task_name"]

            if task_name in self._running_tasks:
                logger.warning(
                    f"Task '{task_name}' is already running. "
                    f"Queued execution will wait."
                )
                # Re-enqueue and wait — simple sequential model for v1
                self.queue.put(task_def)
                time.sleep(5)
                continue

            thread = threading.Thread(
                target=self._run_task,
                args=[task_name, task_def["trigger_source"]],
                daemon=True,
            )
            self._running_tasks[task_name] = thread
            thread.start()

    def _run_task(self, task_name: str, trigger_source: str):
        """Execute a task through the Loop Engine."""
        task = self.tasks[task_name]
        try:
            result = self.loop_engine.execute(task, task.loop_config)
            logger.info(
                f"Task '{task_name}' finished: {result.status.value} "
                f"in {result.iterations} iteration(s)"
            )
        except Exception as e:
            logger.exception(f"Unhandled exception in task '{task_name}': {e}")
        finally:
            del self._running_tasks[task_name]
```

### Concurrency Model (v1)

In v1, each agent runs tasks sequentially. If a cron fires while a task is already running, the new task is queued and executes when the current one completes. This is intentional — it avoids resource contention and race conditions on the shared Den filesystem.

v2 will introduce a concurrency configuration allowing named tasks to run in parallel when explicitly declared safe to do so.

### Task Queue Observability

```
$ den tasks research-analyst

Agent: research-analyst
Status: RUNNING

SCHEDULED TASKS:
  weekly-market-report     cron: "0 9 * * MON"      next: Mon 2026-03-30 09:00
  check-news-alerts        cron: "*/30 * * * *"      next: 2026-03-25 14:30
  daily-briefing           cron: "0 8 * * *"         next: Wed 2026-03-26 08:00

CURRENTLY RUNNING:
  check-news-alerts        started: 14:01:23          duration: 0m 47s (iteration 1/2)

QUEUED:
  (none)
```

---

## 8. Bash Executor

The Bash Executor provides sandboxed shell access to the agent. It is the mechanism by which agents can run Python scripts, use CLI tools, install packages, and chain commands.

### Security Architecture

The Bash Executor applies a layered security model:

```
Agent requests bash execution:
  "python3 analyze.py --input data.csv"
        |
        v
[Layer 1: Command Parser]
    Parse the command string into command + arguments
    Extract the base command (first token): "python3"
        |
        v
[Layer 2: Blocked Command Check]
    Check against blocked_commands list (prefix match)
    If any blocked prefix matches: REJECT immediately
    (blocked takes precedence over allowed)
        |
        v
[Layer 3: Allowed Command Check]
    Check against allowed_commands list (prefix match)
    If base command not in allowed list: REJECT
        |
        v
[Layer 4: Path Validation]
    Check that any file arguments resolve to
    allowed filesystem paths (from permissions.filesystem)
    Symlink traversal is resolved before checking
        |
        v
[Layer 5: Execute in Sandbox]
    Run inside container with:
      - Working directory: /den/workspace
      - Environment: declared env vars only (no host env leak)
      - Timeout: bash.timeout (default 60s)
      - No network (unless command is in explicit tool list)
      - rlimits: prevent fork bombs, excessive file descriptors
        |
        v
[Capture Output]
    stdout/stderr streamed back to agent
    Exit code checked (non-zero = command failed)
    Output logged to /den/logs/bash_history.jsonl
```

### Implementation

```python
# den/core/bash_executor.py

import subprocess
import shlex
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class BashExecutor:
    def __init__(self, config: "BashConfig", allowed_paths: list[str]):
        self.config = config
        self.allowed_paths = [Path(p).resolve() for p in allowed_paths]
        self.history_log = Path("/den/logs/bash_history.jsonl")

    def execute(self, command: str, cwd: str = "/den/workspace") -> "BashResult":
        """
        Execute a shell command inside the sandbox.
        Returns stdout, stderr, and exit code.
        Raises BashSecurityError if the command violates policy.
        """
        if not self.config.enabled:
            raise BashSecurityError("Bash execution is not enabled for this agent.")

        tokens = shlex.split(command)
        if not tokens:
            raise BashSecurityError("Empty command.")

        base_command = tokens[0]

        # Blocked takes precedence
        for blocked in self.config.blocked_commands:
            if command.startswith(blocked) or base_command == blocked.split()[0]:
                raise BashSecurityError(
                    f"Command blocked by policy: '{blocked}'"
                )

        # Must be in allowlist
        if base_command not in self.config.allowed_commands:
            raise BashSecurityError(
                f"Command not in allowed_commands: '{base_command}'. "
                f"Allowed: {self.config.allowed_commands}"
            )

        # Validate file argument paths
        for token in tokens[1:]:
            if token.startswith("/") or token.startswith("./") or token.startswith("../"):
                resolved = Path(cwd).joinpath(token).resolve()
                if not any(
                    str(resolved).startswith(str(allowed))
                    for allowed in self.allowed_paths
                ):
                    raise BashSecurityError(
                        f"File path not in allowed filesystem paths: {resolved}"
                    )

        # Execute
        try:
            result = subprocess.run(
                tokens,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=self.config.timeout_seconds,
                env=self._safe_env(),
            )
        except subprocess.TimeoutExpired:
            raise BashTimeoutError(
                f"Command timed out after {self.config.timeout_seconds}s: {command}"
            )

        self._log(command, result)

        return BashResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.returncode,
            command=command,
        )

    def _safe_env(self) -> dict:
        """Return only declared environment variables. Never leak host env."""
        return dict(os.environ)  # In container, host env is already isolated

    def _log(self, command, result):
        import json, time
        record = {
            "timestamp": time.time(),
            "command": command,
            "exit_code": result.returncode,
            "stdout_len": len(result.stdout),
            "stderr_len": len(result.stderr),
        }
        with open(self.history_log, "a") as f:
            f.write(json.dumps(record) + "\n")
```

### Agent Interaction with Bash

The agent uses a `bash` tool that wraps the Bash Executor. From the agent's perspective:

```
Tool call: bash
Input: {
  "command": "python3 analyze.py --input /den/workspace/data.csv --output /den/output/results.json"
}

Output: {
  "stdout": "Processed 1,247 rows. Output written to results.json.\n",
  "stderr": "",
  "exit_code": 0
}
```

If the command is blocked:
```
Output: {
  "error": "BashSecurityError: Command not in allowed_commands: 'curl'. Allowed: ['python3', 'pip', 'jq', ...]",
  "exit_code": -1
}
```

---

## 9. Memory System

Memory is the agent's brain. It is always on, always persistent, and always filesystem-based.

### Directory Structure

```
/den/memory/
├── index.json                  # Master index: what's in memory, when last updated
├── knowledge/                  # Long-term domain knowledge
│   ├── markets.md              # Domain facts the agent has learned
│   ├── sources.md              # Trusted sources and their characteristics
│   └── terminology.md          # Domain vocabulary
├── task_history/               # Per-task historical records
│   ├── weekly-market-report/
│   │   ├── last_success.json   # Most recent successful run metadata
│   │   ├── attempt_1.json      # All attempts logged
│   │   ├── attempt_2.json
│   │   └── ...
│   ├── check-news-alerts/
│   │   └── last_success.json
│   └── daily-briefing/
│       └── ...
├── progress/                   # Current to-do state and checkpoint data
│   ├── progress.json           # Active task checkpoint (auto-written by Loop Engine)
│   └── backlog.json            # Queued work items across tasks
├── learned/                    # Meta-knowledge: what worked, what failed
│   ├── strategies.json         # Successful approaches by task type
│   └── failures.json           # Patterns that led to failures (avoid repeating)
├── phases/                     # Phase-scoped memory (namespace = phase name)
│   ├── research/               # Written by "research" phase
│   │   ├── findings.json
│   │   └── sources.json
│   └── analysis/               # Written by "analysis" phase
│       └── insights.json
├── notes/                      # Agent's freeform notes to itself
│   ├── 2026-03-24.md           # Daily notes
│   └── ongoing-stories.md      # Stories being tracked across runs
└── context/                    # Session-level context (cleared between major cycles)
    └── current-task.json       # What the agent is working on right now
```

### Memory Categories

Each memory entry is tagged with a category that determines how it is indexed and recalled:

| Category | Purpose | Example |
|---|---|---|
| `fact` | Domain knowledge, learned truths | "Fed meets every 6 weeks" |
| `preference` | User or operator preferences | "Reports should be under 2 pages" |
| `task_result` | Outcome of a completed task | "Weekly report passed on iteration 2" |
| `error` | Errors encountered and their resolutions | "Bloomberg API returns 429 after 10 req/min" |
| `progress` | Current to-do state, checkpoint data | "3 of 5 sections drafted, resuming at section 4" |
| `learned` | Meta-knowledge about what strategies work | "Searching news by topic then by date yields better coverage" |

### Phase-Scoped Namespacing

In multi-phase tasks, each phase writes to memory under its own namespace (`/den/memory/phases/{phase_name}/`). The next phase does not receive the prior phase's raw output. Instead, it queries memory with a namespace filter:

```python
# Phase 1 (research) writes its output:
memory.write("phases/research/findings.json", research_output, namespace="research")

# Phase 2 (analysis) recalls relevant research:
relevant = memory.search(
    query="key findings and data points",
    namespace="research",   # Only search Phase 1's memory
    max_tokens=500,
)
# Phase 2 gets only what is relevant to its task — not everything Phase 1 produced.
```

This eliminates information loss from compression (the full output is in memory) while avoiding context bloat (only relevant parts are recalled).

### Memory Operations

The agent interacts with memory using its standard file tools (`file_read`, `file_write`). Memory is not a special API — it is a directory.

```
# Agent reads its memory at start of task:
file_read("/den/memory/index.json")
file_read("/den/memory/task_history/weekly-market-report/last_success.json")
file_read("/den/memory/notes/ongoing-stories.md")

# Agent writes to memory at end of task:
file_write(
  "/den/memory/notes/ongoing-stories.md",
  "# Ongoing Stories\n\n## Fed Rate Decision (updated 2026-03-24)\n..."
)
file_write(
  "/den/memory/knowledge/sources.md",
  "Bloomberg terminal: reliable for real-time data but paywalled...\n"
)
```

### Memory Index

The index is updated automatically by the Memory System on every write. The agent can read the index to understand what is available without reading every file:

```json
{
  "last_updated": "2026-03-24T09:17:43Z",
  "entries": [
    {
      "path": "knowledge/markets.md",
      "size_bytes": 4821,
      "last_modified": "2026-03-24T09:17:43Z",
      "summary": "General market structure knowledge"
    },
    {
      "path": "task_history/weekly-market-report/last_success.json",
      "size_bytes": 891,
      "last_modified": "2026-03-24T09:17:43Z",
      "summary": "Last successful run: 2026-03-24, 2 iterations"
    },
    {
      "path": "notes/ongoing-stories.md",
      "size_bytes": 2104,
      "last_modified": "2026-03-21T14:22:11Z",
      "summary": "3 ongoing stories tracked"
    }
  ],
  "total_size_bytes": 7816
}
```

### Memory System Implementation

```python
# den/core/memory_system.py

import json
import os
import time
from pathlib import Path


class MemorySystem:
    def __init__(self, memory_root: str = "/den/memory"):
        self.root = Path(memory_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self._ensure_structure()

    def _ensure_structure(self):
        """Create required subdirectories if they do not exist."""
        for subdir in ["knowledge", "task_history", "notes", "context"]:
            (self.root / subdir).mkdir(exist_ok=True)

        if not self.index_path.exists():
            self._write_index({"last_updated": None, "entries": [], "total_size_bytes": 0})

    def write(self, relative_path: str, content) -> Path:
        """Write content to a memory path. Updates the index."""
        target = self.root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(content, dict) or isinstance(content, list):
            target.write_text(json.dumps(content, indent=2))
        else:
            target.write_text(str(content))

        self._update_index(relative_path, target)
        return target

    def read(self, relative_path: str) -> str:
        """Read a file from memory. Returns empty string if not found."""
        target = self.root / relative_path
        if not target.exists():
            return ""
        return target.read_text()

    def read_index(self) -> dict:
        """Return the memory index for the agent to inspect."""
        return json.loads(self.index_path.read_text())

    def _update_index(self, relative_path: str, file_path: Path):
        """Update the master index after a write."""
        index = self.read_index()
        size = file_path.stat().st_size

        # Update or insert entry
        existing = next(
            (e for e in index["entries"] if e["path"] == relative_path), None
        )
        entry = {
            "path": relative_path,
            "size_bytes": size,
            "last_modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if existing:
            existing.update(entry)
        else:
            index["entries"].append(entry)

        index["total_size_bytes"] = sum(e["size_bytes"] for e in index["entries"])
        index["last_updated"] = entry["last_modified"]
        self._write_index(index)

    def _write_index(self, index: dict):
        self.index_path.write_text(json.dumps(index, indent=2))
```

### CLI Memory Inspection

```
$ den memory research-analyst

Agent: research-analyst
Memory root: /den/memory/  (7.6 KB used of 2 GB)
Last updated: 2026-03-24 09:17:43

CONTENTS:
  knowledge/markets.md             4.7 KB    updated 2026-03-24
  knowledge/sources.md             1.1 KB    updated 2026-03-21
  notes/ongoing-stories.md         2.1 KB    updated 2026-03-21
  task_history/weekly-market-report/last_success.json
                                   0.9 KB    updated 2026-03-24

$ den memory research-analyst --file notes/ongoing-stories.md

# Ongoing Stories

## Fed Rate Decision (updated 2026-03-24)
Powell signaled a hold in March. Next decision April 30.
Watch for jobs data March 28 as key input.

## OpenAI Valuation Round (updated 2026-03-21)
Series rumored at $300B. No announcement yet.
Check back weekly.
```

---

## 10. Tool Library

The Tool Library is the set of capabilities available to agents beyond bash and file access. Tools are registered in a central registry, loaded at agent boot based on the Agentfile declaration, and all calls pass through a Permission Interceptor before execution.

### Registry

```python
# den/tools/registry.py

TOOL_REGISTRY: dict[str, type] = {}

def register_tool(name: str):
    def decorator(cls):
        TOOL_REGISTRY[name] = cls
        return cls
    return decorator


def load_tools(declared_tools: list[str], permissions) -> dict[str, "Tool"]:
    """
    Load and instantiate tools declared in the Agentfile.
    Wraps each tool with the PermissionInterceptor.
    """
    loaded = {}
    for name in declared_tools:
        if name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: '{name}'. Check the Tool Library.")
        tool_cls = TOOL_REGISTRY[name]
        loaded[name] = PermissionInterceptor(tool_cls(), permissions)
    return loaded
```

### Standard Tools (v1)

| Tool | Description | Key Parameters |
|---|---|---|
| `web_search` | Search the web via configured search API | `query`, `num_results` |
| `http_get` | Make HTTP GET requests to allowlisted hosts | `url`, `headers` |
| `file_read` | Read files within allowed filesystem paths | `path` |
| `file_write` | Write files within allowed filesystem paths | `path`, `content` |
| `file_list` | List directory contents | `path`, `recursive` |
| `pdf_read` | Extract text from PDF files | `path` |
| `csv_analyze` | Parse and summarize CSV data | `path`, `query` |
| `bash` | Execute sandboxed shell commands | `command` |
| `json_parse` | Parse and query JSON data | `content`, `path` |
| `markdown_render` | Render markdown to HTML | `content` |

### Permission Interceptor

Every tool call passes through the Permission Interceptor before execution. This is the enforcement point for the permissions declared in the Agentfile.

```python
# den/tools/permission_interceptor.py

from urllib.parse import urlparse
from pathlib import Path
import fnmatch


class PermissionInterceptor:
    """
    Wraps every tool call with permission enforcement.
    Implements default-deny: if not explicitly allowed, deny.
    """

    def __init__(self, tool, permissions: "Permissions"):
        self.tool = tool
        self.permissions = permissions

    def __call__(self, **kwargs):
        tool_name = self.tool.__class__.__name__

        # Network permission check
        if "url" in kwargs:
            self._check_network(kwargs["url"])

        # Filesystem permission check
        if "path" in kwargs:
            self._check_filesystem(kwargs["path"])

        return self.tool(**kwargs)

    def _check_network(self, url: str):
        host = urlparse(url).hostname
        allowed = self.permissions.network

        for pattern in allowed:
            if fnmatch.fnmatch(host, pattern):
                return  # Allowed

        raise PermissionError(
            f"Network access denied: '{host}' is not in the allowed network list. "
            f"Add it to permissions.network in your Agentfile."
        )

    def _check_filesystem(self, path: str):
        resolved = Path(path).resolve()
        allowed = [Path(p).resolve() for p in self.permissions.filesystem]

        for allowed_path in allowed:
            if str(resolved).startswith(str(allowed_path)):
                return  # Allowed

        raise PermissionError(
            f"Filesystem access denied: '{path}' is not under any allowed path. "
            f"Allowed: {self.permissions.filesystem}"
        )
```

### Tool Design Principles

These principles govern all tools in the Den Tool Library:

1. **Solve workflows, not API calls.** A tool should accomplish a meaningful unit of work, not just wrap a single HTTP endpoint. `search_web` returns summarized results, not raw HTML.
2. **Concise by default.** Tool output is compact. If the agent needs more detail, it can request it. Default responses do not dump raw payloads.
3. **Actionable errors.** When a tool fails, the error message tells the agent what to do differently — not just what went wrong. "Rate limited. Retry after 30 seconds or reduce query frequency." not "HTTP 429."
4. **Descriptions are onboarding docs.** The tool description teaches the agent when to use the tool, what it is good at, what its limitations are, and what inputs produce the best results. It is not a one-line summary.
5. **Semantic identifiers.** Tool names describe what they do: `search_web`, `read_pdf`, `analyze_csv`. Not `tool_1` or `sw_v2`.

### Tool Definition Contract

Every Den tool is both a class (with typed input/output, permission flags, and metadata) and a callable function (for programmatic tool calling). Tools register as PydanticAI-compatible so they can be used by the PydanticAI agent runtime directly.

```python
# den/tools/base.py

from abc import ABC, abstractmethod
from pydantic import BaseModel
from typing import Any


class ToolResult(BaseModel):
    success: bool
    output: Any
    error: str = ""


class DenTool(ABC):
    """
    Base class for all Den tools.

    Every tool is both a class with metadata (for registration,
    permission enforcement, and documentation) and a callable
    (for programmatic tool calling where the LLM writes code
    that invokes tools directly).
    """

    # Metadata — used by registry, permission interceptor, and docs
    version: str = "1.0.0"
    allowed_callers: list[str] = ["agent", "code_execution"]

    # Permission flags — checked by PermissionInterceptor
    requires_network: bool = False
    requires_filesystem: bool = False

    @property
    @abstractmethod
    def name(self) -> str:
        """Semantic tool name as it appears in the Agentfile."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Onboarding documentation for the agent. Should explain:
        - When to use this tool (and when not to)
        - What inputs produce the best results
        - What the output looks like
        - Known limitations
        """
        ...

    @property
    @abstractmethod
    def input_type(self) -> type[BaseModel]:
        """Pydantic model defining the tool's input parameters."""
        ...

    @property
    @abstractmethod
    def output_type(self) -> type[BaseModel]:
        """Pydantic model defining the tool's output structure."""
        ...

    @abstractmethod
    def __call__(self, **kwargs) -> ToolResult:
        """Execute the tool. Returns a ToolResult."""
        ...

    def as_pydantic_ai_tool(self):
        """
        Register this tool as a PydanticAI-compatible tool function.
        Enables the tool to participate in PydanticAI's tool-use loop
        and programmatic tool calling.
        """
        from pydantic_ai import Tool as PAITool
        return PAITool(self.__call__, name=self.name, description=self.description)
```

---

## 11. Security Model

Den applies a five-layer security model. Each layer is independent. Bypassing one does not compromise the others.

### Layer 1: Default-Deny Permissions

Everything starts denied. The Agentfile must explicitly declare:

- Which tools the agent can use
- Which network hosts the agent can contact
- Which filesystem paths the agent can read and write
- Which shell commands the agent can execute

If something is not in the declaration, the Permission Interceptor rejects it. There is no ambient access.

### Layer 2: Container Isolation

Each agent runs in its own Docker container. The agent's process cannot reach the host filesystem, host network, or other agent containers. Container isolation is enforced by the Docker runtime (namespaces + cgroups).

```
Host
├── Container: den-research-analyst
│   ├── Process: den-agent-process
│   ├── Network: den-research-analyst-net (isolated bridge)
│   └── Volume: den-research-analyst-home (mounted at /den/)
├── Container: den-code-reviewer
│   └── ... (isolated from research-analyst)
└── Host filesystem (not mounted — invisible to agents)
```

### Layer 3: Network Egress Filtering

When a container starts, Den configures iptables rules on the container's network interface to enforce the `permissions.network` allowlist. Outbound connections to hosts not in the allowlist are dropped at the network layer — not just the application layer.

This means a compromised tool or a jailbroken agent cannot exfiltrate data to an unapproved host even if it bypasses the Permission Interceptor.

```python
# den/runtime/network.py

import subprocess


def apply_network_policy(container_name: str, allowed_hosts: list[str]):
    """
    Configure iptables egress rules for a container.
    Resolves allowed_hosts to IPs and creates an allowlist.
    Default policy: DROP for all outbound traffic.
    Allowed IPs: ACCEPT.
    """
    # Step 1: Default deny all outbound from container
    subprocess.run([
        "docker", "exec", container_name,
        "iptables", "-P", "OUTPUT", "DROP"
    ], check=True)

    # Step 2: Allow loopback
    subprocess.run([
        "docker", "exec", container_name,
        "iptables", "-A", "OUTPUT", "-o", "lo", "-j", "ACCEPT"
    ], check=True)

    # Step 3: Allow each declared host
    for host in allowed_hosts:
        ips = resolve_host(host)  # Handles wildcard patterns
        for ip in ips:
            subprocess.run([
                "docker", "exec", container_name,
                "iptables", "-A", "OUTPUT", "-d", ip, "-j", "ACCEPT"
            ], check=True)
```

### Layer 4: Bash Sandboxing

The Bash Executor enforces the `allowed_commands` / `blocked_commands` policy before any shell command executes. Commands not in the allowlist are rejected without being executed. The `blocked_commands` list takes precedence and cannot be overridden by a clever command construction.

Additionally, all bash execution uses `subprocess.run` with:
- `timeout` enforcement (prevents runaway processes)
- `capture_output=True` (no TTY, no interactive escape)
- Container-level rlimits (prevent fork bombs, file descriptor exhaustion)

### Layer 5: Resource Limits

Resource limits are applied at the Docker level via cgroup constraints:

```python
# den/runtime/docker_backend.py (excerpt)

container = client.containers.run(
    image=f"den-{agent_name}:latest",
    name=f"den-{agent_name}",
    detach=True,
    nano_cpus=int(resources.cpu * 1e9),      # CPU limit
    mem_limit=resources.memory,               # RAM limit
    storage_opt={"size": resources.disk},     # Disk limit
    network=f"den-{agent_name}-net",
    mounts=[Mount(target="/den", source=f"den-{agent_name}-home", type="volume")],
    environment=env_vars,
)
```

### Security Invariants

These invariants hold regardless of agent behavior:

1. An agent cannot read or write files outside `permissions.filesystem`
2. An agent cannot connect to network hosts outside `permissions.network`
3. An agent cannot execute shell commands outside `bash.allowed_commands`
4. An agent cannot access another agent's Den volume
5. An agent cannot exceed its declared CPU, memory, or disk limits
6. An agent cannot see the host machine's filesystem or environment
7. Shell command output is captured — agents cannot spawn interactive processes

---

## 12. CLI Design

The Den CLI is the user's entire interface. It is designed to mirror the mental model of `den up` = "agent lives here" and to provide full observability into running agents.

### All Commands

```bash
# ============================================================
# LIFECYCLE
# ============================================================

# Start an agent from an Agentfile. The agent lives in its Den.
# Does not exit — the agent runs in the background.
den up agent.yaml

# Start with explicit name (overrides name: in Agentfile)
den up agent.yaml --name my-analyst

# Stop a running agent. Den volume (memory) is preserved.
den down research-analyst

# List all running agents.
den ps

# ============================================================
# OBSERVABILITY
# ============================================================

# Follow live logs from a running agent.
den logs research-analyst -f

# Show last 100 log lines.
den logs research-analyst --tail 100

# Show task execution history (pass/fail, iterations, duration).
den history research-analyst

# Filter history by task.
den history research-analyst --task weekly-market-report

# Show detailed iteration breakdown for the last run.
den history research-analyst --task weekly-market-report --last 1 --verbose

# List scheduled and running tasks.
den tasks research-analyst

# ============================================================
# INTERACTION
# ============================================================

# Drop into the agent's sandboxed shell environment.
# Full bash access with the agent's tool environment loaded.
den shell research-analyst

# Browse and inspect the agent's memory.
den memory research-analyst

# Read a specific memory file.
den memory research-analyst --file notes/ongoing-stories.md

# Write to the agent's memory (useful for operator injection).
den memory research-analyst --write notes/operator-notes.md --content "Focus on tech sector this week."

# Manually trigger a task (fires immediately, ignores schedule).
den trigger research-analyst weekly-market-report

# Trigger a task and follow its logs in real time.
den trigger research-analyst weekly-market-report -f

# ============================================================
# ARTIFACTS
# ============================================================

# Copy an artifact out of the agent's Den to the local machine.
den cp research-analyst /den/output/weekly-report.md ./reports/

# List all artifacts in /den/output/.
den ls research-analyst /den/output/

# ============================================================
# SECURITY
# ============================================================

# Analyze an Agentfile for security implications before running.
# Shows effective permissions, network access, bash capabilities.
den inspect agent.yaml

# ============================================================
# SCAFFOLDING
# ============================================================

# Scaffold a new Agentfile with prompts.
den init

# Scaffold from a template.
den init --template researcher
den init --template code-reviewer
den init --template data-analyst
```

### Terminal Output Mockups

```
$ den up agent.yaml

  Parsing Agentfile...            OK
  Validating schema...            OK
  Validating tools...             OK (6 tools)
  Validating cron expressions...  OK (2 schedules)
  Building Den image...           OK (den-research-analyst:latest)
  Provisioning Den volume...      OK (existing volume mounted — memory preserved)
  Starting agent container...     OK

  Agent research-analyst is up.
  Memory: /den/memory/ (7.6 KB from previous runs)
  Next scheduled task: check-news-alerts at 14:30

  Use 'den logs research-analyst -f' to follow live logs.
  Use 'den trigger research-analyst <task>' to trigger manually.
  Use 'den down research-analyst' to stop.

$ den ps

NAME                 STATUS    UPTIME    MEMORY USED   NEXT TASK
research-analyst     running   2h 14m    7.6 KB        check-news-alerts (14:30)
code-reviewer        running   45m       2.1 KB        pr-review (on trigger)
data-pipeline        idle      3d 7h     124 MB        etl-run (00:00)

$ den logs research-analyst -f

2026-03-25 14:30:01  [SCHEDULER]  Firing task: check-news-alerts (cron)
2026-03-25 14:30:01  [LOOP]       Task check-news-alerts: iteration 1/2
2026-03-25 14:30:01  [AGENT]      Reading memory index...
2026-03-25 14:30:02  [TOOL]       web_search("market news last 30 minutes")
2026-03-25 14:30:03  [TOOL]       web_search("S&P 500 today")
2026-03-25 14:30:04  [AGENT]      No significant movements detected (SPY -0.3%).
2026-03-25 14:30:04  [AGENT]      No alert file written (correct for quiet market).
2026-03-25 14:30:04  [LOOP]       Evaluating iteration 1...
2026-03-25 14:30:05  [LOOP]       PASSED (score: 1.00). No artifact required.
2026-03-25 14:30:05  [MEMORY]     Writing task_history/check-news-alerts/last_success.json
2026-03-25 14:30:05  [SCHEDULER]  Task check-news-alerts complete. Duration: 4s.
2026-03-25 14:30:05  [SCHEDULER]  Next: check-news-alerts at 15:00

$ den trigger research-analyst weekly-market-report -f

  Triggering task: weekly-market-report on research-analyst...

2026-03-25 14:31:00  [SCHEDULER]  Manual trigger: weekly-market-report
2026-03-25 14:31:00  [LOOP]       Task weekly-market-report: iteration 1/3
2026-03-25 14:31:00  [AGENT]      Reading memory...
2026-03-25 14:31:01  [MEMORY]     Read: task_history/weekly-market-report/last_success.json
2026-03-25 14:31:01  [MEMORY]     Read: notes/ongoing-stories.md
2026-03-25 14:31:02  [TOOL]       web_search("market movements this week March 2026")
2026-03-25 14:31:04  [TOOL]       web_search("company earnings news this week")
2026-03-25 14:31:06  [TOOL]       web_search("economic calendar upcoming events")
2026-03-25 14:31:08  [TOOL]       file_write("/den/output/weekly-report.md", ...)
2026-03-25 14:31:08  [LOOP]       Evaluating iteration 1...
2026-03-25 14:31:10  [LOOP]       FAILED (score: 0.60)
                                  - "Word count exceeds 1000 words": 743 words
                                  - "At least 5 distinct source URLs": found 3
2026-03-25 14:31:10  [LOOP]       Waiting 30s before iteration 2...
2026-03-25 14:31:40  [LOOP]       Task weekly-market-report: iteration 2/3
2026-03-25 14:31:40  [AGENT]      Addressing feedback: expanding sections, adding sources...
2026-03-25 14:31:42  [TOOL]       web_search("Fed meeting minutes March 2026")
2026-03-25 14:31:44  [TOOL]       web_search("tech earnings this week Apple Microsoft")
2026-03-25 14:31:48  [TOOL]       file_write("/den/output/weekly-report.md", ...)
2026-03-25 14:31:48  [LOOP]       Evaluating iteration 2...
2026-03-25 14:31:50  [LOOP]       PASSED (score: 1.00). All criteria satisfied.
2026-03-25 14:31:50  [ARTIFACT]   Collected: /den/output/weekly-report.md (1,847 words)
2026-03-25 14:31:50  [MEMORY]     Writing success record to task_history/
2026-03-25 14:31:51  [SCHEDULER]  Task weekly-market-report complete. 2 iterations, 2m 51s.

$ den inspect agent.yaml

  Den Security Analysis: agent.yaml
  ===================================

  IDENTITY
    name:          research-analyst
    model:         claude-sonnet-4-6

  TOOLS (6)
    web_search     network access required
    http_get       network access required
    file_read      filesystem access required
    file_write     filesystem access required
    csv_analyze    filesystem access required
    pdf_read       filesystem access required

  BASH
    enabled:       true
    allowed:       python3, pip, curl, jq, pandoc, wc, grep, sort, awk
    blocked:       rm -rf, sudo, chmod, chown, curl * | bash

  NETWORK (6 hosts)
    api.anthropic.com
    *.reuters.com       (wildcard — all reuters subdomains)
    *.bloomberg.com     (wildcard — all bloomberg subdomains)
    *.ft.com            (wildcard)
    *.wsj.com           (wildcard)
    finance.yahoo.com

  FILESYSTEM (3 paths)
    /den/workspace      read + write
    /den/output         read + write
    /den/memory         read + write

  RESOURCES
    cpu:           2.0 cores
    memory:        4 GB
    disk:          20 GB

  RISK ASSESSMENT
    [WARN] Wildcard network patterns (*.reuters.com) allow all subdomains.
           Consider specifying exact hosts if possible.
    [OK]   Bash blocked list includes common dangerous patterns.
    [OK]   No access to host filesystem.
    [OK]   Memory isolated to /den/memory.
    [OK]   Resource limits declared.

  Overall: LOW RISK — suitable for production use.
```

---

## 13. Runtime Backend Abstraction

The RuntimeBackend is an abstract interface that Den Core uses to manage containers. Den Core never calls Docker directly — it calls the RuntimeBackend. This makes the runtime swappable without touching any other code.

### Abstract Base Class

```python
# den/runtime/base.py

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ContainerSpec:
    name: str
    image: str
    env: dict[str, str]
    mounts: list[dict]
    network: str
    cpu_cores: float
    memory_limit: str
    disk_limit: str


@dataclass
class ContainerInfo:
    name: str
    status: str          # running | stopped | not_found
    uptime_seconds: int
    cpu_usage_pct: float
    memory_usage_mb: int


class RuntimeBackend(ABC):
    """
    Abstract interface for Den's container runtime.
    All runtime operations go through this interface.
    Den Core never imports docker, firecracker, or any
    specific runtime library directly.
    """

    @abstractmethod
    def build_image(self, agent_name: str, agentfile: "Agentfile") -> str:
        """Build a Den image from an Agentfile. Returns image tag."""
        ...

    @abstractmethod
    def provision_volume(self, volume_name: str, size_limit: str) -> bool:
        """
        Create a persistent volume for the agent's Den.
        Returns True if newly created, False if already existed.
        """
        ...

    @abstractmethod
    def start_container(self, spec: ContainerSpec) -> str:
        """Start a container. Returns container ID."""
        ...

    @abstractmethod
    def stop_container(self, name: str, graceful_timeout_s: int = 30) -> None:
        """Stop a running container gracefully."""
        ...

    @abstractmethod
    def get_container_info(self, name: str) -> ContainerInfo:
        """Get current status and resource usage of a container."""
        ...

    @abstractmethod
    def exec_in_container(self, name: str, command: list[str]) -> tuple[str, str, int]:
        """
        Execute a command inside a running container.
        Returns (stdout, stderr, exit_code).
        """
        ...

    @abstractmethod
    def stream_logs(self, name: str, follow: bool = False):
        """Stream container logs. Yields log line strings."""
        ...

    @abstractmethod
    def list_containers(self) -> list[ContainerInfo]:
        """List all Den-managed containers."""
        ...
```

### Docker Backend (v1)

```python
# den/runtime/docker_backend.py

import docker
from den.runtime.base import RuntimeBackend, ContainerSpec, ContainerInfo


class DockerBackend(RuntimeBackend):
    """
    Docker-based runtime backend. The v1 implementation.
    Requires Docker Desktop or Docker Engine on the host.
    """

    LABEL = "den.managed=true"

    def __init__(self):
        self.client = docker.from_env()

    def build_image(self, agent_name: str, agentfile) -> str:
        tag = f"den-{agent_name}:latest"
        dockerfile_content = self._generate_dockerfile(agentfile)
        # Write dockerfile to temp dir, build, tag
        # ...
        return tag

    def provision_volume(self, volume_name: str, size_limit: str) -> bool:
        existing = self.client.volumes.list(filters={"name": volume_name})
        if existing:
            return False  # Already existed
        self.client.volumes.create(
            name=volume_name,
            labels={"den.managed": "true", "den.agent": volume_name},
        )
        return True  # Newly created

    def start_container(self, spec: ContainerSpec) -> str:
        container = self.client.containers.run(
            image=spec.image,
            name=spec.name,
            detach=True,
            environment=spec.env,
            mounts=[
                docker.types.Mount(
                    target=m["target"],
                    source=m["source"],
                    type=m.get("type", "volume"),
                )
                for m in spec.mounts
            ],
            network=spec.network,
            nano_cpus=int(spec.cpu_cores * 1e9),
            mem_limit=spec.memory_limit,
            labels={"den.managed": "true"},
        )
        return container.id

    def stop_container(self, name: str, graceful_timeout_s: int = 30):
        container = self.client.containers.get(name)
        container.stop(timeout=graceful_timeout_s)

    def get_container_info(self, name: str) -> ContainerInfo:
        try:
            container = self.client.containers.get(name)
            stats = container.stats(stream=False)
            return ContainerInfo(
                name=name,
                status=container.status,
                uptime_seconds=self._compute_uptime(container),
                cpu_usage_pct=self._compute_cpu_pct(stats),
                memory_usage_mb=stats["memory_stats"]["usage"] // (1024 * 1024),
            )
        except docker.errors.NotFound:
            return ContainerInfo(name=name, status="not_found", uptime_seconds=0,
                                 cpu_usage_pct=0.0, memory_usage_mb=0)

    def exec_in_container(self, name: str, command: list[str]):
        container = self.client.containers.get(name)
        result = container.exec_run(command, demux=True)
        stdout = result.output[0].decode() if result.output[0] else ""
        stderr = result.output[1].decode() if result.output[1] else ""
        return stdout, stderr, result.exit_code

    def stream_logs(self, name: str, follow: bool = False):
        container = self.client.containers.get(name)
        for line in container.logs(stream=follow, follow=follow):
            yield line.decode().rstrip()

    def list_containers(self) -> list[ContainerInfo]:
        containers = self.client.containers.list(
            filters={"label": "den.managed=true"}
        )
        return [self.get_container_info(c.name) for c in containers]
```

### Backend Selection

```python
# den/runtime/__init__.py

import os
from den.runtime.base import RuntimeBackend


def get_backend() -> RuntimeBackend:
    """
    Select the runtime backend based on configuration.
    DEN_RUNTIME environment variable or den config file.
    """
    backend_name = os.environ.get("DEN_RUNTIME", "docker")

    if backend_name == "docker":
        from den.runtime.docker_backend import DockerBackend
        return DockerBackend()
    elif backend_name == "firecracker":
        from den.runtime.firecracker_backend import FirecrackerBackend
        return FirecrackerBackend()
    elif backend_name == "e2b":
        from den.runtime.e2b_backend import E2BBackend
        return E2BBackend()
    else:
        raise ValueError(f"Unknown runtime backend: '{backend_name}'")
```

---

## 14. Project Layout

```
den/
├── pyproject.toml                  # Package config, dependencies, CLI entry point
├── README.md
├── architecture.md                 # This document
│
├── den/                            # Main package
│   ├── __init__.py
│   ├── cli/                        # CLI commands (Click-based)
│   │   ├── __init__.py
│   │   ├── main.py                 # CLI entry point, command registration
│   │   ├── up.py                   # den up
│   │   ├── down.py                 # den down
│   │   ├── ps.py                   # den ps
│   │   ├── logs.py                 # den logs
│   │   ├── shell.py                # den shell
│   │   ├── memory.py               # den memory
│   │   ├── tasks.py                # den tasks
│   │   ├── trigger.py              # den trigger
│   │   ├── history.py              # den history
│   │   ├── inspect.py              # den inspect
│   │   ├── init.py                 # den init
│   │   └── cp.py                   # den cp
│   │
│   ├── core/                       # Core execution logic
│   │   ├── __init__.py
│   │   ├── agentfile.py            # Agentfile parser & schema validator
│   │   ├── agent_lifecycle.py      # Agent start/stop/status management
│   │   ├── loop_engine.py          # Loop Engine (self-correcting execution)
│   │   ├── scheduler.py            # Task Scheduler (cron + manual triggers)
│   │   ├── bash_executor.py        # Sandboxed bash execution
│   │   ├── memory_system.py        # Memory read/write/index
│   │   ├── artifact_collector.py   # Artifact collection & delivery
│   │   └── evaluators.py           # Self / Script / LLM-Judge evaluators
│   │
│   ├── tools/                      # Tool Library
│   │   ├── __init__.py
│   │   ├── base.py                 # Tool ABC and ToolResult dataclass
│   │   ├── registry.py             # Tool registry and loader
│   │   ├── permission_interceptor.py  # Permission enforcement wrapper
│   │   ├── web_search.py
│   │   ├── http_get.py
│   │   ├── file_read.py
│   │   ├── file_write.py
│   │   ├── file_list.py
│   │   ├── pdf_read.py
│   │   ├── csv_analyze.py
│   │   ├── json_parse.py
│   │   └── bash.py                 # Bash tool (wraps BashExecutor)
│   │
│   ├── runtime/                    # Runtime backend abstraction
│   │   ├── __init__.py             # get_backend() factory
│   │   ├── base.py                 # RuntimeBackend ABC
│   │   ├── docker_backend.py       # Docker implementation (v1)
│   │   ├── network.py              # Network policy (iptables)
│   │   └── image_builder.py        # Dockerfile generation
│   │
│   └── models/                     # Model provider abstraction
│       ├── __init__.py
│       ├── base.py                 # ModelProvider ABC
│       ├── anthropic.py            # Claude integration
│       └── openai.py               # OpenAI integration
│
├── templates/                      # den init templates
│   ├── researcher.yaml
│   ├── code-reviewer.yaml
│   └── data-analyst.yaml
│
└── tests/
    ├── unit/
    │   ├── test_agentfile.py
    │   ├── test_loop_engine.py
    │   ├── test_bash_executor.py
    │   ├── test_memory_system.py
    │   ├── test_permission_interceptor.py
    │   └── test_scheduler.py
    └── integration/
        ├── test_full_lifecycle.py
        └── test_evaluation_methods.py
```

### Key Dependencies

```toml
# pyproject.toml (dependencies section)

[project.dependencies]
click = ">=8.1"               # CLI framework
pyyaml = ">=6.0"              # Agentfile parsing
docker = ">=7.0"              # Docker SDK for Python
apscheduler = ">=3.10"        # Cron scheduling
anthropic = ">=0.25"          # Claude API
openai = ">=1.20"             # OpenAI API (optional)
pydantic = ">=2.0"            # Schema validation
rich = ">=13.0"               # Terminal output formatting
jsonschema = ">=4.20"         # Agentfile schema validation

[project.scripts]
den = "den.cli.main:cli"
```

---

## 15. Future Roadmap

### v1 (Local CLI — Current Scope)

The foundational implementation. Everything in this document up to this point is v1.

- Docker-based runtime
- Local machine execution
- Full Five Pillars implementation (Den, Memory, Loop, Cron, Identity)
- All CLI commands
- Self and script evaluation methods
- Standard tool library

### v2 — Cloud and Multi-Agent

**Firecracker Runtime**
Replace Docker with Firecracker microVMs. Sub-100ms boot times. Better isolation (hypervisor-level, not namespace-level). Enables true multi-tenant cloud hosting where multiple users' agents run on shared infrastructure securely.

**den-compose.yaml for Multi-Container Sub-Agents**
Phases are the migration path from v1 to v2. In v1, phases are "lightweight sub-agents" — they run in the same container, share memory, and are orchestrated by the Loop Engine. In v2, any phase can be promoted to a full independent agent with its own Den, its own model, and its own lifecycle — declared in `den-compose.yaml` and orchestrated across containers. The Agentfile phase definition remains the same; only the deployment target changes.

**Programmatic Tool Calling as Default**
In v2, `tool_execution.mode` defaults to `programmatic` rather than `auto`. Agents write Python code that orchestrates tool calls, with `traditional` mode available as a fallback for simple tasks or models that do not support code generation.

**Den Registry**
A hosted registry for Den images. `den push my-analyst` publishes the image. `den pull organization/analyst` pulls it. Enables team sharing of agent configurations.

```
den push research-analyst           # Publish to Den Registry
den pull acme-corp/research-analyst # Pull a team's agent
```

**LLM-Judge Evaluation**
The third evaluation method (sketched in this document) becomes production-ready with independent judge model calls, evaluation scoring APIs, and score persistence in memory.

**den-compose — Multi-Agent Orchestration**
Compose files define networks of agents that work together:

```yaml
# den-compose.yaml

version: "1"

agents:
  researcher:
    agentfile: researcher.yaml

  analyst:
    agentfile: analyst.yaml
    depends_on: [researcher]
    triggers:
      - on_artifact: researcher:/den/output/raw-data/

  publisher:
    agentfile: publisher.yaml
    depends_on: [analyst]
    triggers:
      - on_artifact: analyst:/den/output/report.md
```

```bash
den-compose up         # Start all agents
den-compose ps         # Status of all agents
den-compose down       # Stop all agents
```

**Webhook Triggers**
Agents can be triggered by HTTP events in addition to cron and manual triggers:

```yaml
# In Agentfile
triggers:
  - type: webhook
    path: /trigger/pr-review
    task: review-pull-request
    secret: "$WEBHOOK_SECRET"
```

**Shared Memory (Agent-to-Agent)**
Opt-in shared memory volumes that multiple agents can read (and optionally write). Enables agent teams to share learned knowledge:

```yaml
# In den-compose.yaml
shared_memory:
  market-knowledge:
    agents: [researcher, analyst]
    mode: read-write
```

**Queue-Based Triggers**
Agents consume tasks from external queues (SQS, Redis, RabbitMQ). Enables event-driven pipelines at scale:

```yaml
triggers:
  - type: queue
    provider: sqs
    queue_url: "$SQS_QUEUE_URL"
    task: process-document
```

**Hosted Den**
A fully managed cloud offering. `den up agent.yaml --hosted` provisions a cloud-hosted Den without requiring Docker or any local infrastructure. The agent's Den persists in the cloud. Access via CLI. Pay per compute hour.

### The Longer Vision

Den's definition of what an agent must be — Home, Memory, Loop, Cron, Identity — should become an industry standard, not a proprietary format. The ambition is for "Den Agent" to mean something specific and verifiable, the same way "Docker container" means something specific. Not just "an LLM that calls tools." An autonomous, persistent, self-correcting, scheduled system that lives somewhere, remembers everything, and works whether you are watching or not.

The industry built chatbots and called them agents. Den builds agents.

---

*Den Architecture v2.0 — The Living Agent Runtime*
*Last updated: 2026-03-25*
