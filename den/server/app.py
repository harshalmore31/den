"""Den Agent Server -- FastAPI app running inside the container."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_lifecycle = None
_agent_executor = None


def set_lifecycle(lifecycle):
    global _lifecycle
    _lifecycle = lifecycle
    from den.server.openai_compat import set_refs
    set_refs(lifecycle, _agent_executor)


def set_agent_executor(executor):
    global _agent_executor
    _agent_executor = executor
    from den.server.openai_compat import set_refs
    set_refs(_lifecycle, executor)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Den Agent Server starting on :7700")
    yield
    logger.info("Den Agent Server shutting down")
    if _lifecycle:
        _lifecycle.shutdown()


app = FastAPI(
    title="Den Agent Server",
    description="Den Protocol API",
    version="1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def bearer_token_auth(request, call_next):
    """Optional bearer token auth via DEN_API_KEY env var.

    If unset/empty, the server is open (backward compatible).
    If set, every request except /den/v1/health requires
    Authorization: Bearer <DEN_API_KEY>.
    """
    expected = os.environ.get("DEN_API_KEY")
    if not expected:
        return await call_next(request)
    if request.url.path == "/den/v1/health":
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "Missing bearer token"})
    if not secrets.compare_digest(auth[7:].strip(), expected):
        return JSONResponse(status_code=401, content={"error": "Invalid bearer token"})
    return await call_next(request)


from den.server.openai_compat import router as openai_router, set_refs as set_openai_refs
app.include_router(openai_router)


class AskRequest(BaseModel):
    message: str
    session_id: str = "default"

class TriggerRequest(BaseModel):
    task: str

class MemorySearchRequest(BaseModel):
    query: str
    top_k: int = 10

_sessions: dict[str, list] = {}


@app.get("/den/v1/health")
def health():
    return {"ok": True}


@app.get("/den/v1/version")
def version():
    return {"protocol": "1.0", "den": "0.1.0"}


@app.get("/den/v1/status")
def status():
    if not _lifecycle:
        return {"error": "Agent not initialized"}
    s = _lifecycle.get_status()
    return {
        "name": s.name,
        "state": s.state.value,
        "model": s.model,
        "uptime_seconds": round(s.uptime_seconds, 1),
        "tasks_completed": s.tasks_completed,
        "tasks_failed": s.tasks_failed,
        "memory_count": s.memory_count,
        "cron_tasks": s.cron_tasks,
        "current_task": s.current_task,
    }


@app.get("/den/v1/tasks")
def tasks():
    if not _lifecycle or not _lifecycle.config:
        return {"tasks": {}, "schedules": []}

    task_list = {}
    for name, task in _lifecycle.config.tasks.items():
        phases = [{"name": p.name, "type": p.type} for p in task.phases] if task.phases else []
        task_list[name] = {
            "description": task.description.strip()[:200],
            "complexity": task.complexity,
            "phases": phases,
            "has_loop": task.loop is not None,
        }

    schedules = []
    if _lifecycle.scheduler:
        states = _lifecycle.scheduler.get_task_states()
        for name, state in states.items():
            if state.get("cron"):
                schedules.append({
                    "task": name,
                    "schedule": state["cron"],
                    "next_fire": state.get("next_fire", ""),
                    "last_run": state.get("last_run", 0),
                    "run_count": state.get("run_count", 0),
                })

    return {"tasks": task_list, "schedules": schedules}


@app.post("/den/v1/trigger")
async def trigger(req: TriggerRequest):
    """Trigger a task and stream progress via SSE."""
    if not _lifecycle:
        return {"error": "Agent not initialized"}

    async def event_stream():
        yield f"data: {json.dumps({'type': 'started', 'task': req.task})}\n\n"

        triggered = _lifecycle.trigger(req.task)
        if not triggered:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Task {req.task} not found or already running'})}\n\n"
            return

        while _lifecycle.scheduler and _lifecycle.scheduler.is_running(req.task):
            status = _lifecycle.get_status()
            yield f"data: {json.dumps({'type': 'progress', 'current_task': status.current_task, 'state': status.state.value})}\n\n"
            await asyncio.sleep(0.5)

        status = _lifecycle.get_status()
        yield f"data: {json.dumps({'type': 'completed', 'tasks_completed': status.tasks_completed, 'tasks_failed': status.tasks_failed})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/den/v1/ask")
async def ask(req: AskRequest):
    """Ask the agent an ad-hoc question with session persistence."""
    if not _agent_executor:
        return {"error": "Agent executor not configured"}

    if req.session_id not in _sessions:
        _sessions[req.session_id] = []
    history = _sessions[req.session_id]

    memory_ctx = ""
    if _lifecycle and _lifecycle.memory:
        memories = _lifecycle.memory.recall(req.message, top_k=8)
        if memories:
            memory_ctx = _lifecycle.memory.format_for_prompt(memories, max_tokens=500)

    try:
        result = _agent_executor.execute({
            "task_name": "_ask",
            "task_description": req.message,
            "iteration": 1,
            "max_iterations": 1,
            "prior_feedback": "",
            "memory_context": memory_ctx,
            "phase_questions": [],
            "message_history": history,
        })

        response_text = result.get("output_text", "")

        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": response_text})

        if len(history) > 40:
            _sessions[req.session_id] = history[-40:]

        if _lifecycle and _lifecycle.memory:
            _lifecycle.memory.process_conversation(
                user_input=req.message,
                ai_output=response_text,
                source_task="_conversation",
            )
            _lifecycle.memory.feedback_from_response(response_text)

        return {
            "response": response_text,
            "files": result.get("output_files", []),
            "tool_calls": result.get("tool_calls", []),
            "session_id": req.session_id,
            "history_length": len(history),
        }
    except Exception as e:
        return {"error": str(e)}


@app.post("/den/v1/session/clear")
def clear_session(session_id: str = "default"):
    if session_id in _sessions:
        del _sessions[session_id]
    return {"ok": True, "message": f"Session '{session_id}' cleared"}


@app.get("/den/v1/memory")
def memory(search: str | None = None, top_k: int = 10):
    if not _lifecycle or not _lifecycle.memory:
        return {"memories": [], "stats": {}}

    stats = _lifecycle.memory.get_stats()

    memories = []
    if search:
        results = _lifecycle.memory.recall(search, top_k=top_k)
        memories = [
            {
                "content": m.get("content", "")[:200],
                "category": m.get("category", ""),
                "relevance": m.get("relevance", 0),
                "strength": m.get("strength", 0),
            }
            for m in results
        ]

    return {"memories": memories, "stats": stats}


@app.get("/den/v1/history")
def history(task: str | None = None):
    if not _lifecycle or not _lifecycle.memory:
        return {"records": []}

    records = _lifecycle.memory.store.get_task_history(task_name=task, limit=20)
    return {
        "records": [
            {
                "task_name": r["task_name"],
                "status": r["status"],
                "iterations": r["iterations"],
                "summary": r.get("summary", ""),
                "started_at": r.get("started_at", 0),
            }
            for r in records
        ]
    }


@app.get("/den/v1/output")
def list_output():
    output_dir = "/den/output"
    if not os.path.isdir(output_dir):
        return {"files": []}

    files = []
    for root, dirs, filenames in os.walk(output_dir):
        for name in filenames:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, output_dir)
            files.append({
                "name": rel,
                "size_bytes": os.path.getsize(full),
                "modified": os.path.getmtime(full),
            })
    return {"files": files}


@app.get("/den/v1/output/{path:path}")
def get_output(path: str):
    full = os.path.join("/den/output", path)
    if not os.path.exists(full):
        return {"error": f"File not found: {path}"}
    return FileResponse(full)


@app.get("/den/v1/logs")
async def logs(follow: bool = False, lines: int = 50):
    log_dir = "/den/logs"

    if not follow:
        log_lines = []
        if os.path.isdir(log_dir):
            for name in sorted(os.listdir(log_dir), reverse=True):
                path = os.path.join(log_dir, name)
                with open(path) as f:
                    log_lines.extend(f.readlines()[-lines:])
                if len(log_lines) >= lines:
                    break
        return {"lines": log_lines[-lines:]}

    async def log_stream():
        seen = 0
        while True:
            if os.path.isdir(log_dir):
                for name in sorted(os.listdir(log_dir)):
                    path = os.path.join(log_dir, name)
                    with open(path) as f:
                        all_lines = f.readlines()
                    for line in all_lines[seen:]:
                        yield f"data: {json.dumps({'line': line.strip()})}\n\n"
                        seen += 1
            await asyncio.sleep(1)

    return StreamingResponse(log_stream(), media_type="text/event-stream")


@app.post("/den/v1/shutdown")
def shutdown():
    if _lifecycle:
        _lifecycle.shutdown()
    return {"ok": True, "message": "Agent shutting down"}
