import React from "react";
import { Box, Text } from "ink";
import { Separator, StatusDot } from "./Banner.js";

interface Agent {
  name: string;
  port: number;
  live: boolean;
  liveStatus?: {
    state: string;
    model: string;
    uptime_seconds: number;
    tasks_completed: number;
    tasks_failed: number;
    memory_count: number;
    current_task: string;
  };
}

function formatUptime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return h < 24 ? `${h}h${m}m` : `${Math.floor(s / 86400)}d`;
}

export function AgentList({ agents }: { agents: Agent[] }) {
  if (agents.length === 0) {
    return (
      <Box flexDirection="column" paddingLeft={2}>
        <Text dimColor>No agents running.</Text>
        <Box marginTop={1} flexDirection="column">
          <Text dimColor>Quick start:</Text>
          <Text>  <Text color="cyan">1.</Text> <Text color="white">den auth openai</Text>       <Text dimColor>Set your API key</Text></Text>
          <Text>  <Text color="cyan">2.</Text> <Text color="white">den init</Text>              <Text dimColor>Create an Agentfile</Text></Text>
          <Text>  <Text color="cyan">3.</Text> <Text color="white">den up Agentfile</Text>      <Text dimColor>Start the agent</Text></Text>
          <Text>  <Text color="cyan">4.</Text> <Text color="white">den connect my-agent</Text>  <Text dimColor>Chat with it</Text></Text>
        </Box>
      </Box>
    );
  }

  const running = agents.filter((a) => a.live).length;

  return (
    <Box flexDirection="column">
      <Separator label="Agents" />

      {agents.map((agent) => {
        const s = agent.liveStatus;
        const status = !agent.live ? "off" : s?.state === "running" ? "warn" : "ok";

        return (
          <Box key={agent.name} paddingLeft={2} marginBottom={0}>
            <Box width={2}><StatusDot status={status} /></Box>
            <Box width={22}><Text bold={agent.live}>{agent.name}</Text></Box>
            <Box width={10}>
              <Text color={status === "ok" ? "green" : status === "warn" ? "yellow" : "gray"}>
                {s?.state || "stopped"}
              </Text>
            </Box>
            <Box width={24}><Text dimColor={!agent.live}>{(s?.model || "—").slice(0, 22)}</Text></Box>
            <Box width={8}><Text dimColor>{agent.live && s ? formatUptime(s.uptime_seconds) : "—"}</Text></Box>
            <Box width={7}><Text dimColor>:{agent.port}</Text></Box>
            {s && (
              <Box>
                <Text dimColor>{s.memory_count}mem </Text>
                <Text color="green">{s.tasks_completed}✓</Text>
                <Text dimColor> </Text>
                <Text color={s.tasks_failed > 0 ? "red" : "gray"}>{s.tasks_failed}✗</Text>
              </Box>
            )}
          </Box>
        );
      })}

      <Box marginTop={1} paddingLeft={2}>
        <Text dimColor>
          {agents.length} agent{agents.length !== 1 ? "s" : ""} · {running} running
        </Text>
      </Box>
    </Box>
  );
}
