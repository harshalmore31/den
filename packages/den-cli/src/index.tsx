#!/usr/bin/env node

/**
 * Den CLI — The living runtime for AI agents.
 *
 * Built with React + Ink (same stack as Claude Code).
 * Talks to Den agents via the Den Protocol (HTTP/SSE).
 */

import React from "react";
import { render, Box, Text } from "ink";
import { Command } from "commander";
import { DenClient } from "./protocol/client.js";
import { discoverAgents, getClientForAgent, readRegistry, getDenHome } from "./protocol/discovery.js";
import { Banner, HelpCommands } from "./components/Banner.js";
import { AgentList } from "./components/AgentList.js";
import { existsSync, readFileSync } from "fs";
import { execSync } from "child_process";
import { join } from "path";

/**
 * Find the right Python binary — checks venv first, then system.
 * The Den Python runtime (den-core) must be importable.
 */
function findPython(): string {
  // Check for .venv in current directory
  const venvPython = join(process.cwd(), ".venv", "bin", "python");
  if (existsSync(venvPython)) return venvPython;

  // Check for .venv in Den project root (if running from a subdirectory)
  const parentVenv = join(process.cwd(), "..", ".venv", "bin", "python");
  if (existsSync(parentVenv)) return parentVenv;

  // Check VIRTUAL_ENV env var
  if (process.env.VIRTUAL_ENV) {
    const envPython = join(process.env.VIRTUAL_ENV, "bin", "python");
    if (existsSync(envPython)) return envPython;
  }

  // Fallback to system python
  return "python3";
}

const program = new Command();

program
  .name("den")
  .description("Den — The living runtime for AI agents")
  .version("0.1.0");

// ---------------------------------------------------------------------------
// den (no args) — show banner + running agents
// ---------------------------------------------------------------------------

program
  .action(async () => {
    const agents = await discoverAgents();

    function App() {
      return (
        <Box flexDirection="column">
          <Banner />
          <AgentList agents={agents} />
          <HelpCommands commands={[
            { cmd: "den up <agentfile>", desc: "Start an agent in Docker" },
            { cmd: "den connect <agent>", desc: "Interactive chat session" },
            { cmd: "den ask <agent> \"msg\"", desc: "Quick question" },
            { cmd: "den trigger <agent> <task>", desc: "Fire a task with Loop Architecture" },
            { cmd: "den list", desc: "Show all agents on this device" },
            { cmd: "den auth <provider>", desc: "Set API keys (openai, anthropic, brave)" },
            { cmd: "den inspect <file>", desc: "Security analysis of Agentfile" },
            { cmd: "den down <agent>", desc: "Stop an agent" },
          ]} />
        </Box>
      );
    }

    const { unmount, waitUntilExit } = render(<App />);
    await waitUntilExit();
  });

// ---------------------------------------------------------------------------
// den up <agentfile> — start an agent
// ---------------------------------------------------------------------------

program
  .command("up <agentfile>")
  .description("Start an agent — it lives in its Den (Docker container)")
  .option("--image <image>", "Docker image to use", "den/base:latest")
  .action(async (agentfile: string, opts: { image: string }) => {
    if (!existsSync(agentfile)) {
      console.error(`Error: Agentfile not found: ${agentfile}`);
      console.error(`Run 'den init' to create one.`);
      process.exit(1);
    }

    function StartingApp() {
      const [status, setStatus] = React.useState<string>("booting");
      const [info, setInfo] = React.useState<any>(null);
      const [error, setError] = React.useState<string | null>(null);

      React.useEffect(() => {
        async function boot() {
          try {
            setStatus("parsing");

            // Step 1: Parse Agentfile in TypeScript (no Python needed!)
            const YAML = await import("yaml");
            const agentfileContent = readFileSync(agentfile, "utf-8");
            const parsed = YAML.parse(agentfileContent);
            const agentInfo = {
              name: parsed.name || "unnamed-agent",
              model: parsed.model || "unknown",
              tasks: Object.keys(parsed.tasks || {}).length,
              cron: (parsed.cron || []).length,
              tools: (parsed.tools || []).length,
            };

            // Step 1.5: Check Docker is running
            setStatus("checking docker");
            const { checkDocker, ensureImage, getImageName } = await import("./commands/docker-utils.js");
            const dockerCheck = checkDocker();
            if (!dockerCheck.ok) {
              throw new Error(dockerCheck.error || "Docker not available");
            }

            // Step 1.6: Ensure image exists (auto-pull if needed)
            const imageName = getImageName(opts.image);
            const imageCheck = ensureImage(imageName);
            if (!imageCheck.ok) {
              throw new Error(imageCheck.error || "Docker image not available");
            }

            setStatus("starting container");

            // Step 2: Allocate port and setup directories
            const { allocatePort, registerAgent, getDenHome } = await import("./protocol/discovery.js");
            const port = allocatePort();
            const denHome = getDenHome();
            const memoryDir = join(denHome, "memory", agentInfo.name);
            const workspaceDir = join(denHome, "workspaces", agentInfo.name);
            const outputDir = join(denHome, "output", agentInfo.name);

            // Create host directories
            const { mkdirSync } = await import("fs");
            for (const d of [memoryDir, workspaceDir, outputDir]) {
              mkdirSync(d, { recursive: true });
            }

            // Step 3: Collect env vars — keystore + shell env (shell wins)
            const { getEnvForModel } = await import("./protocol/keystore.js");
            const apiKeys = getEnvForModel(agentInfo.model);
            const envFlags: string[] = [];
            for (const [key, value] of Object.entries(apiKeys)) {
              if (value) envFlags.push("-e", `${key}=${value}`);
            }

            // Step 4: Copy Agentfile path
            const absAgentfile = join(process.cwd(), agentfile);

            // Step 5: Run Docker container
            const containerName = `den-${agentInfo.name}`;

            // Remove old container if exists
            try { execSync(`docker rm -f ${containerName}`, { stdio: "ignore" }); } catch {}

            const dockerCmd = [
              "docker", "run", "-d",
              "--name", containerName,
              "-p", `${port}:7700`,
              "-v", `${absAgentfile}:/den-config/agentfile.yaml:ro`,
              "-v", `${memoryDir}:/den/memory`,
              "-v", `${workspaceDir}:/den/workspace`,
              "-v", `${outputDir}:/den/output`,
              "-e", "DEN_AGENTFILE=/den-config/agentfile.yaml",
              "-e", "DEN_HOME=/den",
              "-e", `DEN_PORT=7700`,
              ...envFlags,
              "--label", "dev.den.agent=true",
              "--label", `dev.den.agent.name=${agentInfo.name}`,
              imageName,
            ].join(" ");

            const containerId = execSync(dockerCmd, { encoding: "utf-8" }).trim();

            // Step 6: Register
            registerAgent(agentInfo.name, port, containerId.slice(0, 12));

            setInfo({ ...agentInfo, port, containerId: containerId.slice(0, 12) });
            setStatus("running");

          } catch (e: any) {
            setError(e.message || "Failed to start agent");
            setStatus("error");
          }
        }
        boot();
      }, []);

      return (
        <Box flexDirection="column">
          <Banner />
          {(status === "booting" || status === "parsing" || status === "starting container") && (
            <Box>
              <Text color="cyan">⠋ </Text>
              <Text>{status === "starting container" ? "Starting Docker container..." : `Parsing ${agentfile}...`}</Text>
            </Box>
          )}

          {status === "error" && (
            <Box flexDirection="column">
              <Text color="red">✗ Failed to start agent</Text>
              <Text color="red">{error}</Text>
            </Box>
          )}

          {status === "running" && info && (
            <Box flexDirection="column">
              <Text color="green">✓ Agent '{info.name}' is UP (Docker: {info.containerId})</Text>
              <Text>  Model:      {info.model}</Text>
              <Text>  Port:       {info.port}</Text>
              <Text>  Tasks:      {info.tasks} ({info.cron} cron)</Text>
              <Text>  Tools:      {info.tools}</Text>
              <Text>  Container:  den-{info.name}</Text>
              <Box marginTop={1} flexDirection="column">
                <Text dimColor>Agent is running in Docker. Use:</Text>
                <Text>  <Text color="cyan">den connect {info.name}</Text>    Interactive session</Text>
                <Text>  <Text color="cyan">den trigger {info.name} {"<task>"}</Text>  Fire a task</Text>
                <Text>  <Text color="cyan">den ask {info.name} "question"</Text>  Quick ask</Text>
                <Text>  <Text color="cyan">den logs {info.name} -f</Text>       Stream logs</Text>
                <Text>  <Text color="cyan">den down {info.name}</Text>          Stop agent</Text>
              </Box>
            </Box>
          )}
        </Box>
      );
    }

    const { waitUntilExit } = render(<StartingApp />);
    await waitUntilExit();
  });

// ---------------------------------------------------------------------------
// den ps / den list — list running agents
// ---------------------------------------------------------------------------

async function listAgents() {
  const agents = await discoverAgents();

  function App() {
    return (
      <Box flexDirection="column">
        <Banner />
        <AgentList agents={agents} />
      </Box>
    );
  }

  const { waitUntilExit } = render(<App />);
  await waitUntilExit();
}

program
  .command("ps")
  .description("List running agents")
  .action(listAgents);

program
  .command("list")
  .description("List all Den agents on this device")
  .action(listAgents);

// ---------------------------------------------------------------------------
// den connect <agent> — interactive session
// ---------------------------------------------------------------------------

program
  .command("connect <agent>")
  .description("Interactive chat session with an agent")
  .action(async (agentName: string) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found. Run 'den list' to see agents.`);
      process.exit(1);
    }

    const alive = await client.health();
    if (!alive) {
      console.error(`Agent '${agentName}' is not responding. Is it running?`);
      process.exit(1);
    }

    // ANSI helpers
    const c = {
      reset: "\x1b[0m",
      bold: "\x1b[1m",
      dim: "\x1b[2m",
      italic: "\x1b[3m",
      cyan: "\x1b[36m",
      green: "\x1b[32m",
      yellow: "\x1b[33m",
      red: "\x1b[31m",
      gray: "\x1b[90m",
      white: "\x1b[37m",
      bgCyan: "\x1b[46m",
      bgGray: "\x1b[100m",
    };

    // Create unique session ID for this connection
    const sessionId = `connect-${Date.now()}`;

    // Get agent status for header
    let agentStatus: any = {};
    try { agentStatus = await client.status(); } catch {}

    const model = agentStatus.model || "unknown";
    const memCount = agentStatus.memory_count || 0;
    const tasksDone = agentStatus.tasks_completed || 0;
    const tasksFail = agentStatus.tasks_failed || 0;

    // Print header
    console.log("");
    console.log(`  ${c.cyan}${c.bold}╭──────────────────────────────────────────────────────────────╮${c.reset}`);
    console.log(`  ${c.cyan}${c.bold}│${c.reset}  ${c.bold}${agentName}${c.reset}${c.dim} · ${model}${c.reset}`);
    console.log(`  ${c.cyan}${c.bold}│${c.reset}  ${c.dim}Memory: ${c.white}${memCount}${c.dim} entries  ·  Tasks: ${c.green}${tasksDone}✓${c.dim} ${c.red}${tasksFail}✗${c.dim}  ·  State: ${c.green}${agentStatus.state || "?"}${c.reset}`);
    console.log(`  ${c.cyan}${c.bold}╰──────────────────────────────────────────────────────────────╯${c.reset}`);
    console.log("");
    console.log(`  ${c.dim}Chat with your agent. It has tools, memory, and persistence.${c.reset}`);
    console.log(`  ${c.dim}Commands: ${c.cyan}/tasks${c.dim}  ${c.cyan}/trigger${c.dim} <task>  ${c.cyan}/memory${c.dim} [search]  ${c.cyan}/output${c.dim}  ${c.cyan}/status${c.dim}  ${c.cyan}/exit${c.reset}`);
    console.log(`  ${c.dim}${"─".repeat(64)}${c.reset}`);
    console.log("");

    // Chat REPL using readline
    const readline = await import("readline");
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      prompt: "  \x1b[32m❯\x1b[0m ",
    });

    rl.prompt();

    rl.on("line", async (line: string) => {
      const input = line.trim();
      if (!input) { rl.prompt(); return; }

      // Handle slash commands
      if (input.startsWith("/")) {
        await handleSlashCommand(input, client, rl);
        return;
      }

      // Send to agent
      const spinnerFrames = ["⣾", "⣽", "⣻", "⢿", "⡿", "⣟", "⣯", "⣷"];
      let spinnerIdx = 0;
      const spinner = setInterval(() => {
        process.stdout.write(`\r  ${c.cyan}${spinnerFrames[spinnerIdx++ % spinnerFrames.length]}${c.reset} ${c.dim}Thinking...${c.reset}`);
      }, 80);

      try {
        const result = await client.ask(input, sessionId);
        clearInterval(spinner);
        process.stdout.write("\r\x1b[K");  // clear spinner line

        // Show tool calls if any
        if (result.tool_calls?.length > 0) {
          console.log(`  ${c.dim}─── tool execution ───${c.reset}`);
          for (const tc of result.tool_calls) {
            // Distinguish: real error vs empty result
            const hasRealError = tc.status === "error" && tc.error &&
              !tc.error.includes("validation error");
            const icon = tc.status === "success" ? `${c.green}✓${c.reset}`
              : hasRealError ? `${c.red}✗${c.reset}`
              : `${c.yellow}○${c.reset}`;  // empty/no-result = yellow circle
            const args = Object.entries(tc.args || {})
              .map(([k, v]: [string, any]) => `${k}=${JSON.stringify(v).slice(0, 50)}`)
              .join(", ");
            console.log(`  ${icon} ${c.cyan}${tc.tool}${c.reset}${c.dim}(${args})${c.reset}`);
            if (hasRealError) {
              console.log(`    ${c.red}${tc.error.slice(0, 100)}${c.reset}`);
            } else if (tc.result_preview) {
              // Show brief result preview
              const preview = tc.result_preview.slice(0, 80).replace(/\n/g, " ");
              console.log(`    ${c.dim}→ ${preview}${c.reset}`);
            }
          }
          console.log(`  ${c.dim}──────────────────────${c.reset}`);
          console.log("");
        }

        // Show response
        if (result.response) {
          formatResponse(result.response, c);
        } else if (result.error) {
          console.log(`  ${c.red}✗ ${result.error}${c.reset}`);
        }

        // Show files
        if (result.files?.length) {
          console.log("");
          console.log(`  ${c.dim}📎 Files: ${result.files.join(", ")}${c.reset}`);
        }
      } catch (e: any) {
        clearInterval(spinner);
        process.stdout.write("\r\x1b[K");
        console.log(`  ${c.red}✗ Error: ${e.message}${c.reset}`);
      }

      console.log("");
      rl.prompt();
    });

    rl.on("close", () => {
      console.log("\n  Disconnected.\n");
      process.exit(0);
    });

    function formatResponse(text: string, c: any) {
      const lines = text.split("\n");
      for (const line of lines) {
        // Format markdown-like elements
        let formatted = line;

        // Headers: ## Title → bold cyan
        if (/^#{1,3}\s/.test(formatted)) {
          formatted = formatted.replace(/^#{1,3}\s+/, "");
          console.log(`  ${c.cyan}${c.bold}${formatted}${c.reset}`);
          continue;
        }

        // Bold: **text** → bold
        formatted = formatted.replace(/\*\*(.+?)\*\*/g, `${c.bold}$1${c.reset}`);

        // Inline code: `code` → yellow
        formatted = formatted.replace(/`([^`]+)`/g, `${c.yellow}$1${c.reset}`);

        // Bullet points: - item → cyan bullet
        if (/^\s*[-*]\s/.test(formatted)) {
          formatted = formatted.replace(/^(\s*)[-*]\s/, `$1${c.cyan}▸${c.reset} `);
        }

        // Numbered list: 1. item → cyan number
        if (/^\s*\d+\.\s/.test(formatted)) {
          formatted = formatted.replace(/^(\s*)(\d+)\.\s/, `$1${c.cyan}$2.${c.reset} `);
        }

        // URLs → underlined
        formatted = formatted.replace(/(https?:\/\/[^\s]+)/g, `${c.dim}$1${c.reset}`);

        console.log(`  ${formatted}`);
      }
    }

    async function handleSlashCommand(cmd: string, client: any, rl: any) {
      const parts = cmd.slice(1).split(" ");
      const command = parts[0];
      const args = parts.slice(1).join(" ");

      switch (command) {
        case "exit":
        case "quit":
        case "bye":
          rl.close();
          return;

        case "status": {
          try {
            const s = await client.status();
            const uptime = s.uptime_seconds < 60 ? `${Math.round(s.uptime_seconds)}s`
              : s.uptime_seconds < 3600 ? `${Math.round(s.uptime_seconds / 60)}m`
              : `${Math.floor(s.uptime_seconds / 3600)}h ${Math.round((s.uptime_seconds % 3600) / 60)}m`;
            console.log("");
            console.log(`  ${c.cyan}${c.bold}Agent Status${c.reset}`);
            console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
            console.log(`  ${c.dim}Name:${c.reset}     ${c.bold}${s.name}${c.reset}`);
            console.log(`  ${c.dim}State:${c.reset}    ${s.state === "idle" ? c.green : s.state === "running" ? c.yellow : c.gray}${s.state}${c.reset}`);
            console.log(`  ${c.dim}Model:${c.reset}    ${s.model}`);
            console.log(`  ${c.dim}Memory:${c.reset}   ${s.memory_count} entries`);
            console.log(`  ${c.dim}Tasks:${c.reset}    ${c.green}${s.tasks_completed} completed${c.reset}  ${c.red}${s.tasks_failed} failed${c.reset}`);
            console.log(`  ${c.dim}Uptime:${c.reset}   ${uptime}`);
            if (s.current_task) console.log(`  ${c.dim}Running:${c.reset}  ${c.yellow}${s.current_task}${c.reset}`);
          } catch (e: any) { console.log(`  ${c.red}Error: ${e.message}${c.reset}`); }
          break;
        }

        case "trigger": {
          if (!args) { console.log(`  ${c.dim}Usage: /trigger <task-name>${c.reset}`); break; }
          console.log(`\n  ${c.cyan}${c.bold}Triggering:${c.reset} ${args}`);
          console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
          try {
            for await (const event of client.trigger(args)) {
              if (event.type === "started") {
                console.log(`  ${c.cyan}●${c.reset} Task started`);
              } else if (event.type === "progress") {
                const state = event.state || "running";
                const icon = state === "running" ? `${c.yellow}⣿${c.reset}` : `${c.cyan}●${c.reset}`;
                console.log(`  ${icon} ${state}${event.current_task ? `: ${event.current_task}` : ""}`);
              } else if (event.type === "completed") {
                console.log(`  ${c.green}✓${c.reset} ${c.bold}Task complete${c.reset} (${c.green}${event.tasks_completed}✓${c.reset} ${c.red}${event.tasks_failed}✗${c.reset})`);
              } else if (event.type === "error") {
                console.log(`  ${c.red}✗${c.reset} ${event.message}`);
              }
            }
          } catch (e: any) { console.log(`  ${c.red}Error: ${e.message}${c.reset}`); }
          break;
        }

        case "memory": {
          try {
            const mem = await client.memory(args || undefined);
            console.log("");
            console.log(`  ${c.cyan}${c.bold}Agent Memory${c.reset}`);
            console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
            console.log(`  ${c.dim}Total:${c.reset} ${c.bold}${mem.stats.total}${c.reset} memories  ${c.dim}Avg strength:${c.reset} ${mem.stats.avg_strength}`);
            if (mem.stats.by_category && Object.keys(mem.stats.by_category).length > 0) {
              const cats = Object.entries(mem.stats.by_category)
                .map(([cat, count]) => `${cat}: ${count}`)
                .join("  ");
              console.log(`  ${c.dim}Categories:${c.reset} ${cats}`);
            }
            if (mem.memories?.length > 0) {
              if (args) console.log(`\n  ${c.dim}Search: "${args}"${c.reset}`);
              console.log("");
              for (const m of mem.memories) {
                const catColor = m.category === "error" ? c.red
                  : m.category === "learned" ? c.green
                  : m.category === "task_result" ? c.yellow
                  : c.cyan;
                const bar = "█".repeat(Math.max(1, Math.round(m.relevance * 5)));
                console.log(`  ${catColor}▸${c.reset} ${c.dim}[${m.category}]${c.reset} ${m.content}`);
                console.log(`    ${c.dim}relevance: ${c.cyan}${bar}${c.dim} ${m.relevance}${c.reset}`);
              }
            } else if (args) {
              console.log(`\n  ${c.dim}No memories matching "${args}"${c.reset}`);
            }
          } catch (e: any) { console.log(`  ${c.red}Error: ${e.message}${c.reset}`); }
          break;
        }

        case "output": {
          try {
            const out = await client.output();
            console.log("");
            console.log(`  ${c.cyan}${c.bold}Output Artifacts${c.reset}`);
            console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
            if (out.files.length === 0) { console.log(`  ${c.dim}No output files yet.${c.reset}`); break; }
            for (const f of out.files) {
              const size = f.size_bytes < 1024 ? `${f.size_bytes}B`
                : f.size_bytes < 1024 * 1024 ? `${(f.size_bytes / 1024).toFixed(1)}KB`
                : `${(f.size_bytes / 1024 / 1024).toFixed(1)}MB`;
              const date = new Date(f.modified * 1000).toLocaleTimeString();
              console.log(`  ${c.cyan}📄${c.reset} ${f.name.padEnd(30)} ${c.dim}${size.padStart(8)}  ${date}${c.reset}`);
            }
          } catch (e: any) { console.log(`  ${c.red}Error: ${e.message}${c.reset}`); }
          break;
        }

        case "tasks": {
          try {
            const t = await client.tasks();
            console.log("");
            console.log(`  ${c.cyan}${c.bold}Tasks${c.reset}`);
            console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
            for (const [name, info] of Object.entries(t.tasks) as any) {
              const phases = info.phases?.length ? `${c.dim}(${info.phases.length} phases)${c.reset}` : "";
              const complexity = info.complexity ? `${c.yellow}[${info.complexity}]${c.reset} ` : "";
              console.log(`  ${c.cyan}▸${c.reset} ${c.bold}${name}${c.reset} ${complexity}${phases}`);
              if (info.description) {
                console.log(`    ${c.dim}${info.description.trim().slice(0, 60)}${c.reset}`);
              }
            }
            if (t.schedules?.length) {
              console.log(`\n  ${c.cyan}${c.bold}Schedules${c.reset}`);
              console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
              for (const s of t.schedules) {
                console.log(`  ${c.dim}⏰${c.reset} ${c.yellow}${s.schedule}${c.reset}  →  ${c.bold}${s.task}${c.reset}${s.next_fire ? `  ${c.dim}(next: ${s.next_fire})${c.reset}` : ""}`);
              }
            }
          } catch (e: any) { console.log(`  ${c.red}Error: ${e.message}${c.reset}`); }
          break;
        }

        case "help":
        default:
          console.log("");
          console.log(`  ${c.cyan}${c.bold}Commands${c.reset}`);
          console.log(`  ${c.dim}${"─".repeat(40)}${c.reset}`);
          console.log(`  ${c.cyan}/tasks${c.reset}              List available tasks`);
          console.log(`  ${c.cyan}/trigger${c.reset} <task>     Fire a task (Loop Architecture)`);
          console.log(`  ${c.cyan}/memory${c.reset} [search]    Browse agent memory`);
          console.log(`  ${c.cyan}/output${c.reset}             List produced artifacts`);
          console.log(`  ${c.cyan}/status${c.reset}             Agent status & stats`);
          console.log(`  ${c.cyan}/help${c.reset}               Show this help`);
          console.log(`  ${c.cyan}/exit${c.reset}               Disconnect`);
      }
      console.log("");
      rl.prompt();
    }
  });

// ---------------------------------------------------------------------------
// den trigger <agent> <task> — fire a task
// ---------------------------------------------------------------------------

program
  .command("trigger <agent> <task>")
  .description("Manually trigger a task")
  .action(async (agentName: string, taskName: string) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found.`);
      process.exit(1);
    }

    console.log(`[den] Triggering: ${agentName} → ${taskName}`);

    try {
      for await (const event of client.trigger(taskName)) {
        if (event.type === "started") {
          console.log(`[den] Task started`);
        } else if (event.type === "progress") {
          console.log(`[den] ${event.state || "running"}${event.current_task ? `: ${event.current_task}` : ""}`);
        } else if (event.type === "completed") {
          console.log(`[den] ✓ Task complete (${event.tasks_completed} passed, ${event.tasks_failed} failed)`);
        } else if (event.type === "error") {
          console.error(`[den] ✗ ${event.message}`);
        }
      }
    } catch (e: any) {
      console.error(`[den] Error: ${e.message}`);
    }
  });

// ---------------------------------------------------------------------------
// den ask <agent> <message> — quick ask
// ---------------------------------------------------------------------------

program
  .command("ask <agent> <message>")
  .description("Ask an agent a question")
  .action(async (agentName: string, message: string) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found.`);
      process.exit(1);
    }

    console.log(`[${agentName}] Thinking...`);
    try {
      const result = await client.ask(message);
      console.log(`\n${result.response}`);
      if (result.files?.length) {
        console.log(`\nFiles: ${result.files.join(", ")}`);
      }
    } catch (e: any) {
      console.error(`Error: ${e.message}`);
    }
  });

// ---------------------------------------------------------------------------
// den memory <agent> — inspect memory
// ---------------------------------------------------------------------------

program
  .command("memory <agent>")
  .description("Inspect agent memory")
  .option("--search <query>", "Search memories")
  .action(async (agentName: string, opts: { search?: string }) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found.`);
      process.exit(1);
    }

    try {
      const mem = await client.memory(opts.search);
      console.log(`\nMemory: ${agentName}`);
      console.log(`Total: ${mem.stats.total} memories | Avg strength: ${mem.stats.avg_strength}`);

      if (mem.stats.by_category) {
        console.log(`\nBy category:`);
        for (const [cat, count] of Object.entries(mem.stats.by_category)) {
          console.log(`  ${cat}: ${count}`);
        }
      }

      if (mem.memories.length > 0) {
        console.log(opts.search ? `\nSearch: '${opts.search}'` : `\nRecent:`);
        for (const m of mem.memories) {
          console.log(`  [${m.category}] ${m.content}  (${m.relevance})`);
        }
      }
    } catch (e: any) {
      console.error(`Error: ${e.message}`);
    }
  });

// ---------------------------------------------------------------------------
// den output <agent> — list artifacts
// ---------------------------------------------------------------------------

program
  .command("output <agent>")
  .description("List agent output artifacts")
  .action(async (agentName: string) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found.`);
      process.exit(1);
    }

    try {
      const out = await client.output();
      if (out.files.length === 0) {
        console.log("No output files.");
        return;
      }
      console.log(`\nOutput: ${agentName}`);
      for (const f of out.files) {
        const size = (f.size_bytes / 1024).toFixed(1);
        const date = new Date(f.modified * 1000).toLocaleString();
        console.log(`  ${f.name.padEnd(30)} ${size.padStart(8)} KB   ${date}`);
      }
    } catch (e: any) {
      console.error(`Error: ${e.message}`);
    }
  });

// ---------------------------------------------------------------------------
// den logs <agent> — show/stream logs
// ---------------------------------------------------------------------------

program
  .command("logs <agent>")
  .description("Show agent logs")
  .option("-f, --follow", "Follow log output")
  .action(async (agentName: string, opts: { follow?: boolean }) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found.`);
      process.exit(1);
    }

    if (opts.follow) {
      console.log(`[den] Streaming logs for ${agentName}... (Ctrl+C to stop)`);
      try {
        for await (const line of client.logs()) {
          console.log(line);
        }
      } catch {
        console.log("[den] Log stream ended.");
      }
    } else {
      try {
        const response = await fetch(`http://localhost:${readRegistry()[agentName]?.port}/den/v1/logs?lines=50`);
        const data = await response.json() as any;
        for (const line of data.lines || []) {
          console.log(line.trimEnd());
        }
      } catch (e: any) {
        console.error(`Error: ${e.message}`);
      }
    }
  });

// ---------------------------------------------------------------------------
// den history <agent> — task history
// ---------------------------------------------------------------------------

program
  .command("history <agent>")
  .description("Show task execution history")
  .option("--task <name>", "Filter by task name")
  .action(async (agentName: string, opts: { task?: string }) => {
    const client = getClientForAgent(agentName);
    if (!client) {
      console.error(`Agent '${agentName}' not found.`);
      process.exit(1);
    }

    try {
      const hist = await client.history(opts.task);
      if (hist.records.length === 0) {
        console.log("No task history.");
        return;
      }
      console.log(`\nHistory: ${agentName}`);
      for (const r of hist.records) {
        const icon = r.status === "success" ? "✓" : "✗";
        const date = r.started_at ? new Date(r.started_at * 1000).toLocaleString() : "?";
        console.log(`  ${icon} ${date}  ${r.task_name}  (${r.iterations} iters, ${r.status})`);
        if (r.summary) console.log(`    ${r.summary}`);
      }
    } catch (e: any) {
      console.error(`Error: ${e.message}`);
    }
  });

// ---------------------------------------------------------------------------
// den down <agent> — stop an agent
// ---------------------------------------------------------------------------

program
  .command("down <agent>")
  .description("Stop a running agent")
  .action(async (agentName: string) => {
    const registry = readRegistry();
    const info = registry[agentName];

    if (!info) {
      console.error(`Agent '${agentName}' not found. Run 'den list' to see agents.`);
      process.exit(1);
    }

    console.log(`[den] Shutting down ${agentName}...`);

    // Try graceful shutdown via API first
    const client = getClientForAgent(agentName);
    if (client) {
      try { await client.shutdown(); } catch {}
    }

    // Stop and remove Docker container
    try {
      execSync(`docker stop den-${agentName}`, { stdio: "ignore", timeout: 10000 });
      execSync(`docker rm den-${agentName}`, { stdio: "ignore" });
    } catch {}

    // Unregister
    const { unregisterAgent } = await import("./protocol/discovery.js");
    unregisterAgent(agentName);

    console.log(`[den] Agent '${agentName}' is DOWN. Den preserved.`);
  });

// ---------------------------------------------------------------------------
// den inspect <agentfile> — security analysis (local, no running agent needed)
// ---------------------------------------------------------------------------

program
  .command("inspect <agentfile>")
  .description("Analyze security posture of an Agentfile")
  .action(async (agentfile: string) => {
    if (!existsSync(agentfile)) {
      console.error(`  Error: ${agentfile} not found`);
      process.exit(1);
    }

    const YAML = await import("yaml");
    const config = YAML.parse(readFileSync(agentfile, "utf-8"));
    const c = {
      reset: "\x1b[0m", bold: "\x1b[1m", dim: "\x1b[2m",
      cyan: "\x1b[36m", green: "\x1b[32m", yellow: "\x1b[33m", red: "\x1b[31m",
    };

    console.log(`\n  ${c.cyan}${c.bold}Den Agentfile Security Analysis${c.reset}`);
    console.log(`  ${"═".repeat(40)}`);
    console.log(`  ${c.dim}Agent:${c.reset}    ${c.bold}${config.name}${c.reset}`);
    console.log(`  ${c.dim}Model:${c.reset}    ${config.model}`);
    console.log();

    // Tools
    console.log(`  ${c.cyan}Tools:${c.reset}`);
    for (const tool of (config.tools || [])) {
      console.log(`    ${c.green}[ALLOWED]${c.reset}  ${tool}`);
    }
    console.log();

    // Network
    console.log(`  ${c.cyan}Network:${c.reset}`);
    for (const host of (config.permissions?.network || [])) {
      console.log(`    ${c.green}[ALLOWED]${c.reset}  ${host}`);
    }
    console.log(`    ${c.red}[BLOCKED]${c.reset}  all other outbound`);
    console.log();

    // Filesystem
    console.log(`  ${c.cyan}Filesystem:${c.reset}`);
    for (const path of (config.permissions?.filesystem || [])) {
      console.log(`    ${c.green}[ALLOWED]${c.reset}  ${path}`);
    }
    console.log(`    ${c.red}[BLOCKED]${c.reset}  host filesystem`);
    console.log();

    // Bash
    console.log(`  ${c.cyan}Bash:${c.reset}`);
    if (config.bash?.enabled) {
      console.log(`    ${c.yellow}[ENABLED]${c.reset}  timeout: ${config.bash.timeout || "60s"}`);
      if (config.bash.blocked_commands?.length) {
        console.log(`    ${c.dim}Blocked:${c.reset} ${config.bash.blocked_commands.join(", ")}`);
      }
    } else {
      console.log(`    ${c.green}[DISABLED]${c.reset}`);
    }
    console.log();

    // Tasks
    const tasks = Object.keys(config.tasks || {});
    console.log(`  ${c.cyan}Tasks:${c.reset} ${tasks.length}`);
    for (const name of tasks) {
      const task = config.tasks[name];
      const phases = task.phases?.length ? ` (${task.phases.length} phases)` : "";
      console.log(`    ${name}${phases}`);
    }
    console.log();

    // Risks
    const risks: string[] = [];
    if (config.bash?.enabled) risks.push("Bash execution enabled");
    if (config.permissions?.shell) risks.push("Shell permission granted");
    if ((config.tools || []).includes("bash")) risks.push("Bash tool in tools list");

    if (risks.length) {
      console.log(`  ${c.yellow}Risks:${c.reset}`);
      for (const r of risks) console.log(`    ${c.yellow}⚠${c.reset}  ${r}`);
    } else {
      console.log(`  ${c.green}Risk: LOW${c.reset}`);
    }
    console.log();
  });

// ---------------------------------------------------------------------------
// den init — scaffold (delegates to Python CLI)
// ---------------------------------------------------------------------------

program
  .command("init")
  .description("Scaffold a new Agentfile")
  .action(async () => {
    const readline = await import("readline");
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask = (q: string): Promise<string> => new Promise(r => rl.question(q, r));

    const name = await ask("  Agent name: ");
    const model = await ask("  Model [openai:gpt-4o]: ") || "openai:gpt-4o";
    rl.close();

    const kebab = name.toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9-]/g, "");

    // Detect provider for env
    const provider = model.split(":")[0] || "openai";
    const envMap: Record<string, string> = {
      openai: "OPENAI_API_KEY", anthropic: "ANTHROPIC_API_KEY",
      google: "GOOGLE_API_KEY", groq: "GROQ_API_KEY", mistral: "MISTRAL_API_KEY",
    };
    const envKey = envMap[provider] || "OPENAI_API_KEY";

    const content = `name: ${kebab}
model: ${model}

system_prompt: |
  You are ${name}. Describe your role and personality here.

env:
  ${envKey}: "$${envKey}"
  BRAVE_API_KEY: "$BRAVE_API_KEY"

tools:
  - web_search
  - web_context
  - file_read
  - file_write
  - file_list
  - bash
  - python_exec
  - json_parse
  - csv_analyze
  - pdf_read

bash:
  enabled: true
  blocked_commands: [rm -rf, sudo, chmod, shutdown, reboot]
  timeout: 120s

memory:
  max_size: 2gb

tasks:
  default-task:
    description: |
      Describe what this agent should do.

permissions:
  network:
    - api.openai.com
    - api.anthropic.com
    - api.search.brave.com
  filesystem:
    - /den/workspace
    - /den/output
    - /den/memory
  shell: true

resources:
  cpu: "2.0"
  memory: "4gb"
  disk: "10gb"
`;

    const filename = "Agentfile";
    if (existsSync(filename)) {
      const overwrite = await new Promise<string>(r => {
        const rl2 = readline.createInterface({ input: process.stdin, output: process.stdout });
        rl2.question(`  ${filename} exists. Overwrite? [y/N]: `, a => { rl2.close(); r(a); });
      });
      if (overwrite.toLowerCase() !== "y") { console.log("  Aborted."); return; }
    }

    const { writeFileSync } = await import("fs");
    writeFileSync(filename, content);
    console.log(`\n  ✓ Created: ${filename}`);
    console.log(`  Next: den up ${filename}`);
  });

// ---------------------------------------------------------------------------
// den auth — manage API keys
// ---------------------------------------------------------------------------

program
  .command("auth [provider]")
  .description("Set API keys (anthropic, openai, google, groq, mistral)")
  .option("--remove", "Remove a stored key")
  .option("--list", "List stored keys")
  .action(async (provider: string | undefined, opts: { remove?: boolean; list?: boolean }) => {
    const { saveKey, removeKey, listKeys, PROVIDER_ENV_MAP } = await import("./protocol/keystore.js");

    if (opts.list || !provider) {
      const keys = listKeys();
      if (keys.length === 0) {
        console.log("No API keys stored. Run: den auth <provider>");
        console.log(`Available: ${Object.keys(PROVIDER_ENV_MAP).join(", ")}`);
      } else {
        console.log("\nStored API keys:");
        for (const k of keys) {
          console.log(`  ${k.provider.padEnd(12)} ${k.envVar.padEnd(22)} ${k.masked}`);
        }
      }
      return;
    }

    if (!(provider in PROVIDER_ENV_MAP) && provider !== "ollama") {
      console.error(`Unknown provider: '${provider}'`);
      console.error(`Available: ${Object.keys(PROVIDER_ENV_MAP).join(", ")}`);
      process.exit(1);
    }

    if (opts.remove) {
      removeKey(provider);
      console.log(`✓ Removed ${provider} API key`);
      return;
    }

    const envVar = PROVIDER_ENV_MAP[provider] || `${provider.toUpperCase()}_API_KEY`;

    // Check if key was passed as next argument or via pipe
    const args = process.argv.slice(process.argv.indexOf(provider) + 1);
    const inlineKey = args.find(a => !a.startsWith("-"));

    if (inlineKey) {
      saveKey(provider, inlineKey);
      const masked = inlineKey.slice(0, 7) + "..." + inlineKey.slice(-4);
      console.log(`✓ ${provider} API key saved (${masked})`);
      console.log(`  Stored in ~/.den/keys.json (chmod 600)`);
      return;
    }

    // Interactive prompt
    const readline = await import("readline");
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });

    const key = await new Promise<string>((resolve) => {
      rl.question(`\n  🔑 Enter ${provider} API key (${envVar}): `, (answer: string) => {
        rl.close();
        resolve(answer.trim());
      });
    });

    if (!key) {
      console.error("\n  ✗ No key provided.");
      process.exit(1);
    }

    saveKey(provider, key);
    const masked = key.slice(0, 7) + "..." + key.slice(-4);
    console.log(`\n  ✓ ${provider} API key saved (${masked})`);
    console.log(`  Stored in ~/.den/keys.json (chmod 600)`);
  });

// ---------------------------------------------------------------------------
// den doctor — check prerequisites
// ---------------------------------------------------------------------------

program
  .command("doctor")
  .description("Check if Den is properly set up")
  .action(async () => {
    const { checkDocker, imageExists, DEFAULT_IMAGE } = await import("./commands/docker-utils.js");
    const { listKeys } = await import("./protocol/keystore.js");

    console.log("\n  Den Doctor");
    console.log("  " + "─".repeat(40));

    // Check Node
    console.log(`  ✓ Node.js ${process.version}`);

    // Check Docker
    const docker = checkDocker();
    if (docker.ok) {
      console.log("  ✓ Docker is running");
    } else {
      console.log(`  ✗ ${docker.error}`);
    }

    // Check image
    if (imageExists(DEFAULT_IMAGE)) {
      console.log(`  ✓ Den image: ${DEFAULT_IMAGE}`);
    } else if (imageExists("den/base:latest")) {
      console.log("  ✓ Den image: den/base:latest (local build)");
    } else {
      console.log(`  ○ Den image not found (will be pulled on first 'den up')`);
    }

    // Check API keys
    const keys = listKeys();
    if (keys.length > 0) {
      for (const k of keys) {
        console.log(`  ✓ ${k.provider} key: ${k.masked}`);
      }
    } else {
      console.log("  ○ No API keys set (run: den auth <provider>)");
    }

    console.log("");
  });

program.parse();
