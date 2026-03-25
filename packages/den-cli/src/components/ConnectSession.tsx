import React, { useState, useCallback } from "react";
import { Box, Text, useInput, useApp } from "ink";
import type { DenClient } from "../protocol/client.js";

interface Message {
  role: "user" | "agent" | "system";
  content: string;
}

interface ConnectSessionProps {
  client: DenClient;
  agentName: string;
}

function Spinner() {
  const frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
  const [frame, setFrame] = useState(0);

  React.useEffect(() => {
    const timer = setInterval(() => setFrame((f) => (f + 1) % frames.length), 80);
    return () => clearInterval(timer);
  }, []);

  return <Text color="cyan">{frames[frame]}</Text>;
}

export function ConnectSession({ client, agentName }: ConnectSessionProps) {
  const { exit } = useApp();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [status, setStatus] = useState<any>(null);

  // Load initial status
  React.useEffect(() => {
    client.status().then(setStatus).catch(() => {});
  }, []);

  useInput((value, key) => {
    if (key.escape || (key.ctrl && value === "c")) {
      exit();
      return;
    }

    if (key.return) {
      if (input.trim()) {
        handleSubmit(input.trim());
        setInput("");
      }
      return;
    }

    if (key.backspace || key.delete) {
      setInput((prev) => prev.slice(0, -1));
      return;
    }

    if (value && !key.ctrl && !key.meta) {
      setInput((prev) => prev + value);
    }
  });

  const handleSubmit = useCallback(async (text: string) => {
    // Handle slash commands
    if (text.startsWith("/")) {
      await handleCommand(text);
      return;
    }

    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setThinking(true);

    try {
      const result = await client.ask(text);
      setMessages((prev) => [...prev, { role: "agent", content: result.response }]);
    } catch (e: any) {
      setMessages((prev) => [...prev, { role: "system", content: `Error: ${e.message}` }]);
    } finally {
      setThinking(false);
    }
  }, [client]);

  const handleCommand = useCallback(async (cmd: string) => {
    const parts = cmd.slice(1).split(" ");
    const command = parts[0];
    const args = parts.slice(1).join(" ");

    switch (command) {
      case "trigger": {
        if (!args) {
          setMessages((prev) => [...prev, { role: "system", content: "Usage: /trigger <task-name>" }]);
          return;
        }
        setMessages((prev) => [...prev, { role: "system", content: `Triggering: ${args}` }]);
        setThinking(true);
        try {
          for await (const event of client.trigger(args)) {
            if (event.type === "completed") {
              setMessages((prev) => [...prev, { role: "system", content: `✓ Task complete` }]);
            } else if (event.type === "error") {
              setMessages((prev) => [...prev, { role: "system", content: `✗ ${event.message}` }]);
            }
          }
        } catch (e: any) {
          setMessages((prev) => [...prev, { role: "system", content: `Error: ${e.message}` }]);
        }
        setThinking(false);
        break;
      }
      case "memory": {
        try {
          const mem = await client.memory(args || undefined);
          const lines = [`Memory: ${mem.stats.total} total`];
          if (mem.memories.length > 0) {
            for (const m of mem.memories) {
              lines.push(`  [${m.category}] ${m.content} (${m.relevance})`);
            }
          }
          setMessages((prev) => [...prev, { role: "system", content: lines.join("\n") }]);
        } catch (e: any) {
          setMessages((prev) => [...prev, { role: "system", content: `Error: ${e.message}` }]);
        }
        break;
      }
      case "output": {
        try {
          const out = await client.output();
          const lines = out.files.map((f) => `  ${f.name} (${(f.size_bytes / 1024).toFixed(1)} KB)`);
          setMessages((prev) => [...prev, {
            role: "system",
            content: lines.length ? `Output files:\n${lines.join("\n")}` : "No output files.",
          }]);
        } catch (e: any) {
          setMessages((prev) => [...prev, { role: "system", content: `Error: ${e.message}` }]);
        }
        break;
      }
      case "tasks": {
        try {
          const t = await client.tasks();
          const lines = Object.entries(t.tasks).map(([name, info]) => {
            const phases = info.phases.length ? ` (${info.phases.length} phases)` : "";
            return `  ${name}${phases}`;
          });
          setMessages((prev) => [...prev, { role: "system", content: `Tasks:\n${lines.join("\n")}` }]);
        } catch (e: any) {
          setMessages((prev) => [...prev, { role: "system", content: `Error: ${e.message}` }]);
        }
        break;
      }
      case "exit":
      case "quit":
        exit();
        break;
      default:
        setMessages((prev) => [...prev, {
          role: "system",
          content: `Commands: /trigger <task>, /memory [search], /output, /tasks, /exit`,
        }]);
    }
  }, [client, exit]);

  return (
    <Box flexDirection="column">
      {/* Header */}
      <Box borderStyle="round" borderColor="cyan" paddingX={2} marginBottom={1}>
        <Text bold color="cyan">Connected to: {agentName}</Text>
        {status && (
          <Text dimColor>
            {" "}| {status.model} | {status.memory_count} memories | {status.state}
          </Text>
        )}
      </Box>

      {/* Messages */}
      {messages.map((msg, i) => (
        <Box key={i} paddingLeft={msg.role === "agent" ? 2 : 0} marginBottom={0}>
          {msg.role === "user" && (
            <Text>
              <Text color="green" bold>{">"} </Text>
              {msg.content}
            </Text>
          )}
          {msg.role === "agent" && (
            <Text>
              <Text dimColor>  </Text>
              {msg.content}
            </Text>
          )}
          {msg.role === "system" && (
            <Text color="yellow">{msg.content}</Text>
          )}
        </Box>
      ))}

      {/* Thinking indicator */}
      {thinking && (
        <Box paddingLeft={2}>
          <Spinner />
          <Text dimColor> Thinking...</Text>
        </Box>
      )}

      {/* Input */}
      <Box marginTop={1}>
        <Text color="green" bold>{">"} </Text>
        <Text>{input}</Text>
        <Text dimColor>█</Text>
      </Box>
    </Box>
  );
}
