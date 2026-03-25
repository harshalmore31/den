
<p align="center">
  <br>
  <code>&nbsp;______   ________  ___   __&nbsp;</code><br>
  <code>|_   _ `.|_   __  ||_  | |_ |</code><br>
  <code>  | | `. \ | |_ \_|  |  \| | </code><br>
  <code>  | |  | | |  _| _   | .   | </code><br>
  <code> _| |_.' /_| |__/ | _| |\  |_</code><br>
  <code>|______.'|________||____| |__|</code><br>
  <br>
  <strong>The living runtime for AI agents.</strong><br>
  <em>Docker for AI.</em>
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#the-agentfile">Agentfile</a> &bull;
  <a href="#commands">Commands</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#tools">Tools</a> &bull;
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-blue" alt="version">
  <img src="https://img.shields.io/badge/license-Apache%202.0-green" alt="license">
  <img src="https://img.shields.io/badge/tests-passing-brightgreen" alt="tests">
  <img src="https://img.shields.io/badge/node-%3E%3D18-339933?logo=node.js" alt="node">
  <img src="https://img.shields.io/badge/docker-required-2496ED?logo=docker" alt="docker">
</p>

---

Den gives your AI agent a **home** -- a persistent, sandboxed container with memory, tools, scheduled tasks, and identity. You define what your agent is in an `Agentfile`, and Den handles everything else: provisioning, lifecycle, memory, tool execution, and API access.

No frameworks to learn. No orchestration code to write. Just declare and run.

## Quick Demo

```
$ den init
? Agent name: research-bot
? Base model: openai/gpt-4o
? System prompt: You are a research analyst specializing in technology markets.
Created Agentfile

$ den up Agentfile
Pulling den-runtime:latest ... done
Building agent container ... done
Starting research-bot on port 8800 ...

  research-bot is live.
  API:  http://localhost:8800/v1
  Logs: den logs research-bot

$ den connect research-bot
Connected to research-bot. Type /quit to exit.

you> What's the current state of the AI chip market?

research-bot> I'll research that for you now.
  [tool:web_search] "AI chip market 2026 landscape"
  [tool:web_search] "NVIDIA AMD Intel AI accelerator market share 2026"
  [tool:memo_write] Saving research: AI chip market overview

Based on my research, here's the current landscape:

The AI accelerator market reached $87B in 2025 and is projected to hit
$120B by end of 2026. NVIDIA maintains ~72% market share in data center
GPUs, but AMD's MI350 series has captured significant ground...

you> /quit

$ den down research-bot
Stopped research-bot. Memory and state preserved.
```

## Why Den?

Agents need more than an API key and a system prompt. Den provides five pillars:

| Pillar | What it does |
|---|---|
| **Home** | A sandboxed Docker container with persistent filesystem, networking, and resource limits. Your agent has a place to live. |
| **Memory** | SQLite-backed persistent memory with semantic recall, automatic fact extraction, and graph-activated knowledge. Agents remember across sessions. |
| **Loop** | Structured execution loops (research, plan, execute, verify) that give agents disciplined workflows instead of unbounded generation. |
| **Cron** | Scheduled tasks that run on intervals. Agents can monitor, report, and act without being prompted. |
| **Identity** | Name, personality, system prompt, and consistent behavior. Your agent is the same agent every time you start it. |

## Quick Start

**Prerequisites:** Node.js 18+ and Docker.

```bash
# 1. Install the CLI
npm install -g @harshalmore31/den

# 2. Set your API key
den auth openai
# Paste your OpenAI API key when prompted

# 3. Create an Agentfile
den init

# 4. Start the agent
den up Agentfile

# 5. Talk to it
den connect my-agent
```

That's it. Your agent is running in a container with persistent memory, tools, and an OpenAI-compatible API.

## The Agentfile

The Agentfile is a declarative specification for your agent. Here's a complete example:

```yaml
# Agentfile — research analyst agent
name: research-analyst
version: "1.0"

runtime:
  base: den-runtime:latest      # Base container image
  memory: 512                   # Memory limit in MB
  cpu: 1.0                      # CPU cores
  network: filtered             # filtered | none | host
  env:
    OPENAI_API_KEY: "${OPENAI_API_KEY}"

model:
  provider: openai
  name: gpt-4o
  temperature: 0.3
  max_tokens: 4096

identity:
  system_prompt: |
    You are a senior research analyst. You produce thorough, well-sourced
    reports on technology, markets, and business strategy. You always cite
    your sources and flag uncertainty clearly.
  personality:
    tone: professional
    verbosity: detailed

memory:
  backend: sqlite               # sqlite | postgres
  semantic_recall: true         # Enable embedding-based memory search
  fact_extraction: true         # Auto-extract facts from conversations
  max_context_memories: 20      # Memories injected per turn

tools:
  - web_search
  - web_fetch
  - file_read
  - file_write
  - shell_exec
  - memo_write
  - memo_search

checks:
  - name: source_citation
    description: "Ensure all claims have sources"
    on: before_respond

loops:
  - type: research
    max_iterations: 5
    tools: [web_search, web_fetch, memo_write]

cron:
  - name: daily-market-scan
    schedule: "0 8 * * *"
    prompt: >
      Search for today's top AI and semiconductor news.
      Write a brief summary to memory.
```

## Commands

| Command | Description |
|---|---|
| `den init` | Create a new Agentfile interactively |
| `den up <agentfile>` | Build and start an agent from an Agentfile |
| `den down <name>` | Stop a running agent (preserves state) |
| `den connect <name>` | Open an interactive chat session |
| `den status` | List all running agents and their resource usage |
| `den logs <name>` | Stream agent logs |
| `den inspect <name>` | Show agent config, memory stats, and tool usage |
| `den auth <provider>` | Configure API keys for a model provider |
| `den memory <name>` | Browse and search an agent's memory |
| `den exec <name> <cmd>` | Run a command inside the agent's container |
| `den destroy <name>` | Stop agent and delete all state (irreversible) |
| `den api <name>` | Show API endpoint and connection details |

## Architecture

```
┌─────────────────────────────────────────────────┐
│                  User World                      │
│  CLI (den connect)  ·  API clients  ·  Cron      │
└──────────────────────┬──────────────────────────┘
                       │ HTTP / WebSocket
┌──────────────────────▼──────────────────────────┐
│                  Den Core                        │
│                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  Router   │ │  Memory  │ │  Loop Engine     │ │
│  │  & Auth   │ │  Manager │ │  (R/P/E/V)       │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │  Tool     │ │  Check   │ │  Cron Scheduler  │ │
│  │  Registry │ │  Runner  │ │                  │ │
│  └──────────┘ └──────────┘ └──────────────────┘ │
└──────────────────────┬──────────────────────────┘
                       │ Docker API
┌──────────────────────▼──────────────────────────┐
│              Runtime Backend                     │
│  Docker container per agent                      │
│  Isolated filesystem · Network filtering         │
│  Resource limits · Volume mounts                 │
└─────────────────────────────────────────────────┘
```

Den Core runs on the host and manages agent lifecycles. Each agent gets its own Docker container with enforced resource limits. The core communicates with containers via a local HTTP bridge.

## Loop Architecture

Loops give agents structured workflows instead of open-ended generation. Den supports four loop types:

| Loop | Purpose | Example |
|---|---|---|
| **Research** | Gather information iteratively, stopping when sufficient data is collected | "Find the top 5 competitors in this market" |
| **Plan** | Break a goal into steps, validate the plan, then commit | "Create a migration plan for this database" |
| **Execute** | Run a sequence of tool calls with rollback on failure | "Set up monitoring for these 3 services" |
| **Verify** | Check work against criteria, retry if checks fail | "Ensure the report has citations for every claim" |

Loops are composable. A research loop can feed into a plan loop, which triggers an execute loop, verified by a verify loop.

## Tools

Den ships with 11 built-in tools. Agents can only use tools explicitly listed in their Agentfile.

| Tool | Description |
|---|---|
| `web_search` | Search the web via configurable search provider |
| `web_fetch` | Fetch and extract content from a URL |
| `file_read` | Read files from the agent's sandboxed filesystem |
| `file_write` | Write files to the agent's sandboxed filesystem |
| `file_list` | List directory contents |
| `shell_exec` | Execute shell commands inside the container |
| `memo_write` | Write a note to persistent memory |
| `memo_search` | Semantic search over memory |
| `memo_list` | List recent memory entries |
| `http_request` | Make HTTP requests (subject to network policy) |
| `schedule_task` | Create or modify cron tasks at runtime |

Custom tools can be added by subclassing `DenTool`. See [CONTRIBUTING.md](CONTRIBUTING.md).

## Memory System

Every Den agent has persistent memory backed by SQLite. Memory is not just storage -- it is actively used during conversations:

- **Semantic recall** -- relevant memories are retrieved via embedding similarity and injected into context each turn.
- **Fact extraction** -- the system automatically extracts structured facts from conversations and stores them.
- **Graph activation** -- related memories activate associated memories, simulating associative recall.
- **Scoped access** -- agents can only access their own memory. No cross-agent leakage.

Memory persists across `den down` / `den up` cycles. Use `den memory <name>` to browse it, or `den destroy <name>` to wipe it.

## API

Every running agent exposes an **OpenAI-compatible API** on its assigned port:

```bash
curl http://localhost:8800/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "research-analyst",
    "messages": [{"role": "user", "content": "Summarize today'\''s AI news"}]
  }'
```

Den also implements the **Den Protocol** for extended functionality:

```
GET  /den/v1/status          # Agent health and stats
GET  /den/v1/memory          # Memory contents
POST /den/v1/memory          # Write to memory
GET  /den/v1/tools           # List available tools
POST /den/v1/tools/:name     # Invoke a tool directly
```

Use `den api <name>` to see the endpoint for any running agent.

## Security

Den follows a **default-deny** security model:

- **Sandboxed execution** -- each agent runs in its own Docker container with no access to the host filesystem.
- **Network filtering** -- outbound network access is filtered by default. Agents can only reach explicitly allowed domains.
- **Permission interceptor** -- tool calls are checked against the Agentfile's tool list. Unauthorized tool use is blocked.
- **Resource limits** -- CPU and memory are capped per-agent. No single agent can starve the host.
- **Secret isolation** -- API keys are injected via environment variables at runtime. They never touch disk inside the container.

## Roadmap

**v1 (current)** -- Single-host, Docker-based runtime. Core features: Agentfile, memory, loops, tools, cron, CLI.

**v2 (planned)**
- Firecracker microVM backend for stronger isolation
- `den-compose` for multi-agent systems with shared context
- Den Registry for publishing and sharing Agentfiles
- Cloud-hosted runtime (managed Den)
- Plugin system for third-party tool packages
- Multi-model support within a single agent (router model + specialist models)

## Contributing

We welcome contributions. See [CONTRIBUTING.md](CONTRIBUTING.md) for setup instructions, code style, and PR guidelines.

## License

Apache 2.0. See [LICENSE](LICENSE).

---

<p align="center">
  Built by <a href="https://github.com/harshalmore31">Harshal More</a>
</p>
