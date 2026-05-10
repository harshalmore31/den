/**
 * Den Protocol Client — talks to agent servers via HTTP/SSE.
 *
 * Supports two modes:
 *   - Local Docker agent: new DenClient({ host: "localhost", port: 7702 })
 *   - Remote agent + bearer: new DenClient({ baseUrl: "https://...", token: "hex" })
 *
 * Backward-compatible signature `new DenClient(host, port)` still works
 * for callers that haven't migrated.
 */

import type {
  AgentStatus,
  TaskInfo,
  ScheduleInfo,
  MemoryEntry,
  OutputFile,
  HistoryRecord,
} from "./types.js";

export interface DenClientConfig {
  baseUrl?: string;
  host?: string;
  port?: number;
  token?: string | null;
}

export class DenClient {
  private baseUrl: string;
  private token: string | null;

  constructor(
    config: DenClientConfig | string = {},
    legacyPort?: number,
  ) {
    if (typeof config === "string") {
      // Legacy: new DenClient("localhost", 7700)
      this.baseUrl = `http://${config}:${legacyPort ?? 7700}`;
      this.token = null;
    } else if (config.baseUrl) {
      this.baseUrl = config.baseUrl.replace(/\/+$/, "");
      this.token = config.token ?? null;
    } else {
      this.baseUrl = `http://${config.host ?? "localhost"}:${config.port ?? 7700}`;
      this.token = config.token ?? null;
    }
  }

  private headers(extra?: Record<string, string>): Record<string, string> {
    const h: Record<string, string> = { ...(extra ?? {}) };
    if (this.token) h["Authorization"] = `Bearer ${this.token}`;
    return h;
  }

  private async get<T>(path: string): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this.headers() });
    if (!res.ok) throw new Error(`Den Protocol error: ${res.status} ${res.statusText}`);
    return res.json() as Promise<T>;
  }

  private async post<T>(path: string, body: object): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`Den Protocol error: ${res.status} ${res.statusText}`);
    return res.json() as Promise<T>;
  }

  // -- Health --
  async health(): Promise<boolean> {
    try {
      // /den/v1/health is intentionally unauthenticated server-side, but
      // sending the bearer is harmless and proves connectivity end-to-end.
      const res = await fetch(`${this.baseUrl}/den/v1/health`, { headers: this.headers() });
      return res.ok;
    } catch {
      return false;
    }
  }

  // -- Status --
  async status(): Promise<AgentStatus> {
    return this.get("/den/v1/status");
  }

  // -- Tasks --
  async tasks(): Promise<{ tasks: Record<string, TaskInfo>; schedules: ScheduleInfo[] }> {
    return this.get("/den/v1/tasks");
  }

  // -- Trigger (SSE stream) --
  async *trigger(taskName: string): AsyncGenerator<any> {
    const res = await fetch(`${this.baseUrl}/den/v1/trigger`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({ task: taskName }),
    });

    if (!res.body) throw new Error("No response body");
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            yield JSON.parse(line.slice(6));
          } catch {}
        }
      }
    }
  }

  // -- Ask (with session persistence) --
  async ask(
    message: string,
    sessionId: string = "default",
  ): Promise<{
    response: string;
    files: string[];
    tool_calls?: any[];
    session_id?: string;
    history_length?: number;
    error?: string;
  }> {
    return this.post("/den/v1/ask", { message, session_id: sessionId });
  }

  // -- Clear session --
  async clearSession(sessionId: string = "default"): Promise<void> {
    await this.post("/den/v1/session/clear", { session_id: sessionId });
  }

  // -- Memory --
  async memory(
    search?: string,
    topK: number = 10,
  ): Promise<{ memories: MemoryEntry[]; stats: any }> {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    params.set("top_k", String(topK));
    return this.get(`/den/v1/memory?${params}`);
  }

  // -- Output --
  async output(): Promise<{ files: OutputFile[] }> {
    return this.get("/den/v1/output");
  }

  async downloadOutput(path: string): Promise<string> {
    const res = await fetch(`${this.baseUrl}/den/v1/output/${path}`, {
      headers: this.headers(),
    });
    return res.text();
  }

  /** Binary-safe download from /den/output/{path}. Returns the raw bytes. */
  async downloadOutputBinary(path: string): Promise<ArrayBuffer> {
    const res = await fetch(`${this.baseUrl}/den/v1/output/${path}`, {
      headers: this.headers(),
    });
    if (!res.ok) {
      throw new Error(`Download failed: ${res.status} ${res.statusText}`);
    }
    return await res.arrayBuffer();
  }

  // -- History --
  async history(task?: string): Promise<{ records: HistoryRecord[] }> {
    const params = task ? `?task=${task}` : "";
    return this.get(`/den/v1/history${params}`);
  }

  // -- Logs (SSE stream) --
  async *logs(): AsyncGenerator<string> {
    const res = await fetch(`${this.baseUrl}/den/v1/logs?follow=true`, {
      headers: this.headers(),
    });
    if (!res.body) return;
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data.line || JSON.stringify(data);
          } catch {}
        }
      }
    }
  }

  // -- Shutdown --
  async shutdown(): Promise<void> {
    await this.post("/den/v1/shutdown", {});
  }
}
