import React, { useState, useEffect } from "react";
import { Box, Text } from "ink";
import type { DenClient } from "../protocol/client.js";

interface TaskProgressProps {
  client: DenClient;
  taskName: string;
}

interface ProgressEvent {
  type: string;
  task?: string;
  current_task?: string;
  state?: string;
  message?: string;
  tasks_completed?: number;
  tasks_failed?: number;
}

function PhaseSpinner({ active }: { active: boolean }) {
  const frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
  const [frame, setFrame] = useState(0);

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setFrame((f) => (f + 1) % frames.length), 80);
    return () => clearInterval(timer);
  }, [active]);

  if (!active) return <Text color="green">✓</Text>;
  return <Text color="cyan">{frames[frame]}</Text>;
}

export function TaskProgress({ client, taskName }: TaskProgressProps) {
  const [events, setEvents] = useState<ProgressEvent[]>([]);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function stream() {
      try {
        for await (const event of client.trigger(taskName)) {
          if (cancelled) break;
          setEvents((prev) => [...prev, event]);
          if (event.type === "completed" || event.type === "error") {
            setDone(true);
            if (event.type === "error") setError(event.message || "Task failed");
            break;
          }
        }
      } catch (e: any) {
        setError(e.message || "Connection lost");
        setDone(true);
      }
    }

    stream();
    return () => { cancelled = true; };
  }, [client, taskName]);

  return (
    <Box flexDirection="column">
      <Box marginBottom={1}>
        <Text bold>Triggering: </Text>
        <Text color="cyan">{taskName}</Text>
      </Box>

      {events.map((event, i) => (
        <Box key={i} paddingLeft={2}>
          {event.type === "started" && (
            <Text><PhaseSpinner active={!done} /> Starting task...</Text>
          )}
          {event.type === "progress" && (
            <Text dimColor>
              <PhaseSpinner active={!done} /> {event.state || "running"}
              {event.current_task ? `: ${event.current_task}` : ""}
            </Text>
          )}
          {event.type === "completed" && (
            <Text color="green">
              ✓ Task complete ({event.tasks_completed} passed, {event.tasks_failed} failed)
            </Text>
          )}
          {event.type === "error" && (
            <Text color="red">✗ {event.message}</Text>
          )}
        </Box>
      ))}

      {error && !events.some((e) => e.type === "error") && (
        <Box paddingLeft={2}>
          <Text color="red">✗ {error}</Text>
        </Box>
      )}
    </Box>
  );
}
