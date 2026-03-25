import React from "react";
import { Box, Text } from "ink";

export function Banner() {
  return (
    <Box flexDirection="column" marginBottom={1}>
      <Box>
        <Text color="cyan" bold>  ╺╋╸ </Text>
        <Text bold color="white">Den</Text>
        <Text color="gray"> v0.1.0</Text>
      </Box>
      <Box>
        <Text dimColor>  The living runtime for AI agents</Text>
      </Box>
    </Box>
  );
}

export function Separator({ label, width = 60 }: { label?: string; width?: number }) {
  if (label) {
    const pad = Math.max(0, width - label.length - 4);
    return (
      <Box>
        <Text dimColor>──</Text>
        <Text color="cyan" bold> {label} </Text>
        <Text dimColor>{"─".repeat(pad)}</Text>
      </Box>
    );
  }
  return (
    <Box>
      <Text dimColor>{"─".repeat(width)}</Text>
    </Box>
  );
}

export function KeyValue({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box>
      <Box width={14}>
        <Text dimColor>{label}</Text>
      </Box>
      <Box>
        {children}
      </Box>
    </Box>
  );
}

export function StatusDot({ status }: { status: "ok" | "warn" | "error" | "off" }) {
  const colors = { ok: "green", warn: "yellow", error: "red", off: "gray" } as const;
  return <Text color={colors[status]}>●</Text>;
}

export function HelpCommands({ commands }: { commands: { cmd: string; desc: string }[] }) {
  return (
    <Box flexDirection="column" marginTop={1}>
      <Separator label="Commands" />
      {commands.map((c, i) => (
        <Box key={i} paddingLeft={2}>
          <Box width={32}>
            <Text color="cyan">{c.cmd}</Text>
          </Box>
          <Text dimColor>{c.desc}</Text>
        </Box>
      ))}
    </Box>
  );
}
