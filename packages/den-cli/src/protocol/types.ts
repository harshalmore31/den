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

export interface AgentInfo {
  name: string;
  port: number;
  container_id: string;
  status: string;
  started_at: string;
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
