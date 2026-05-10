# den-agent (CLI)

The Den CLI — manage local and remote Den agents from one terminal.

> Den is the living runtime for AI agents. The full framework lives at
> [github.com/harshalmore31/den](https://github.com/harshalmore31/den).
>
> The npm package `den-agent` is the **CLI** (this).
> The PyPI package [`den-agent`](https://pypi.org/project/den-agent/) is the
> **Python runtime** that runs inside agent containers. Same name, different
> layer — install whichever you need (or both).

## Install

```bash
npm install -g den-agent
# or
bunx den-agent
# or one-shot
npx den-agent
```

Requires Node 18+. For local agents, also requires Docker.

## What it does

Den agents are containers that:
- Run your Agentfile (declarative agent identity, tools, memory, cron)
- Expose an OpenAI-compatible HTTP API
- Persist memory across restarts

The CLI gives you one interface to talk to them whether they're running on:
- **Your laptop** in Docker (`den up Agentfile`)
- **A deployed service** (Northflank, Cloudflare, your own VM, anywhere)

## Quick start

### Talk to a local Docker agent

```bash
den auth openai                 # store an API key (encrypted)
den init                        # scaffold an Agentfile
den up Agentfile                # spin up in Docker
den connect my-agent            # interactive chat
```

### Talk to a deployed agent

```bash
den remote add prod-agent https://denapi.harshalmore.dev
# prompts for the bearer token (DEN_API_KEY), encrypts it locally

den connect prod-agent          # same chat UX, hits the remote
den ask prod-agent "what should I ship this week?"
```

`den list` shows both local and remote agents in one view.

## Commands

| Command | What it does |
|---|---|
| `den` | Banner + agent list + quick help |
| `den up <agentfile>` | Start a local agent in Docker |
| `den down <agent>` | Stop a local Docker agent (preserves memory) |
| `den remote add <name> <url>` | Register a deployed agent (prompts for bearer) |
| `den remote list` | List remote agents |
| `den remote rm <name>` | Unregister a remote agent (also wipes its token) |
| `den remote token <name>` | Replace the bearer token for a remote agent |
| `den connect <agent>` | Interactive REPL with an agent (local or remote) |
| `den ask <agent> "msg"` | One-shot question |
| `den trigger <agent> <task>` | Fire a named task and stream Loop progress |
| `den list` / `den ps` | All registered agents |
| `den memory <agent>` | Browse / search agent memory |
| `den output <agent>` | List artifact files the agent produced |
| `den logs <agent>` | Stream live logs |
| `den history <agent>` | Past task runs |
| `den auth <provider>` | Manage API keys for model providers |
| `den inspect <agentfile>` | Static security analysis of an Agentfile |
| `den init` | Scaffold a new Agentfile |
| `den doctor` | Verify prerequisites (Docker, Node, Python) |

## Where things are stored

```
~/.den/
├── agents.json       Local + remote agent registry (URLs, ports)
├── keys.enc          AES-256-GCM encrypted: API keys + bearer tokens
└── .salt             Per-machine encryption salt
```

The encrypted file is bound to your machine fingerprint (user + hostname + home).
Copying it to another machine renders it useless. `chmod 600` on both files.

## Bearer token flow for remote agents

```
den remote add prod-agent https://denapi.example.com
  └─ prompts for DEN_API_KEY
  └─ saved to keys.enc encrypted as _agent:prod-agent
  └─ registered in agents.json with remote=true

den connect prod-agent
  └─ loads agents.json -> sees remote=true -> reads URL
  └─ loads keys.enc -> retrieves bearer for prod-agent
  └─ DenClient sends Authorization: Bearer <token> on every request
  └─ agent's middleware validates and authenticates
```

The token never appears in plain text on disk and never reaches the model.

## License

Apache-2.0 — see the [LICENSE](https://github.com/harshalmore31/den/blob/main/LICENSE)
in the parent repo.
