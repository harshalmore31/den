/**
 * Den Protocol types.
 */

export interface AgentStatus {
  name: string;
  state: "absent" | "booting" | "idle" | "running" | "stopping" | "stopped";
  model: string;
  uptime_seconds: number;
  tasks_completed: number;
  tasks_failed: number;
  memory_count: number;
  cron_tasks: number;
  current_task: string;
}

/**
 * AgentInfo covers two shapes:
 *   - Local (Docker): port + container_id are set, remote=false (or absent)
 *   - Remote (Northflank/CF/etc.): url is set, remote=true; bearer token
 *     for the agent lives in the encrypted keystore under `_agent:<name>`,
 *     never in this file.
 */
export interface AgentInfo {
  name: string;
  status: string;
  started_at: string;
  // Local-Docker fields
  port?: number;
  container_id?: string;
  // Remote fields
  url?: string;
  remote?: boolean;
}

export interface AgentRegistry {
  [name: string]: AgentInfo;
}

export interface TaskInfo {
  description: string;
  complexity: string | null;
  phases: { name: string; type: string }[];
  has_loop: boolean;
}

export interface ScheduleInfo {
  task: string;
  schedule: string;
  next_fire: string;
  last_run: number;
  run_count: number;
}

export interface MemoryEntry {
  content: string;
  category: string;
  relevance: number;
  strength: number;
}

export interface OutputFile {
  name: string;
  size_bytes: number;
  modified: number;
}

export interface HistoryRecord {
  task_name: string;
  status: string;
  iterations: number;
  summary: string;
  started_at: number;
}
