/**
 * Agent discovery — finds running Den agents.
 *
 * Reads ~/.den/agents.json for registered agents,
 * then pings each one to check if it's alive.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from "fs";
import { homedir } from "os";
import { join } from "path";
import type { AgentInfo, AgentRegistry } from "./types.js";
import { DenClient } from "./client.js";

const DEN_HOME = process.env.DEN_HOME || join(homedir(), ".den");
const REGISTRY_PATH = join(DEN_HOME, "agents.json");
const BASE_PORT = 7701;

export function getDenHome(): string {
  return DEN_HOME;
}

export function readRegistry(): AgentRegistry {
  if (!existsSync(REGISTRY_PATH)) return {};
  try {
    return JSON.parse(readFileSync(REGISTRY_PATH, "utf-8"));
  } catch {
    return {};
  }
}

export function writeRegistry(registry: AgentRegistry): void {
  mkdirSync(DEN_HOME, { recursive: true });
  writeFileSync(REGISTRY_PATH, JSON.stringify(registry, null, 2));
}

export function allocatePort(): number {
  const registry = readRegistry();
  const usedPorts = new Set(Object.values(registry).map((a) => a.port));
  let port = BASE_PORT;
  while (usedPorts.has(port)) port++;
  return port;
}

export function registerAgent(name: string, port: number, containerId: string): void {
  const registry = readRegistry();
  registry[name] = {
    name,
    port,
    container_id: containerId,
    status: "running",
    started_at: new Date().toISOString(),
  };
  writeRegistry(registry);
}

export function unregisterAgent(name: string): void {
  const registry = readRegistry();
  delete registry[name];
  writeRegistry(registry);
}

export async function discoverAgents(): Promise<(AgentInfo & { live: boolean; liveStatus?: any })[]> {
  const registry = readRegistry();
  const agents: (AgentInfo & { live: boolean; liveStatus?: any })[] = [];

  for (const [name, info] of Object.entries(registry)) {
    const client = new DenClient("localhost", info.port);
    const live = await client.health();
    let liveStatus = undefined;

    if (live) {
      try {
        liveStatus = await client.status();
      } catch {}
    }

    agents.push({ ...info, live, liveStatus });
  }

  return agents;
}

export function getClientForAgent(name: string): DenClient | null {
  const registry = readRegistry();
  const info = registry[name];
  if (!info) return null;
  return new DenClient("localhost", info.port);
}
