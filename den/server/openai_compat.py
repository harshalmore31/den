"""OpenAI-compatible API layer for Den agents."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter()

_lifecycle = None
_agent_executor = None


def set_refs(lifecycle, executor):
    global _lifecycle, _agent_executor
    _lifecycle = lifecycle
    _agent_executor = executor


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None

class ChatCompletionRequest(BaseModel):
    model: str = "den-agent"
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 1.0
    max_tokens: int = 4096
    tools: list[dict] | None = None
    tool_choice: str = "auto"

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@router.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    """OpenAI-compatible chat completion endpoint."""
    user_messages = [m for m in req.messages if m.role == "user"]
    if not user_messages:
        return _error_response("No user message provided")

    last_message = user_messages[-1].content or ""

    system_override = None
    for m in req.messages:
        if m.role == "system":
            system_override = m.content

    if not _agent_executor:
        return _error_response("Agent executor not configured")

    completion_id = f"den-cmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())
    model_name = _lifecycle.config.model if _lifecycle and _lifecycle.config else "den-agent"

    if req.stream:
        return StreamingResponse(
            _stream_response(last_message, completion_id, created, model_name),
            media_type="text/event-stream",
        )

    try:
        result = _agent_executor.execute({
            "task_name": "_chat",
            "task_description": last_message,
            "iteration": 1,
            "max_iterations": 1,
            "prior_feedback": "",
            "memory_context": _get_memory_context(last_message),
            "system_override": system_override,
            "phase_questions": [],
        })
        response_text = result.get("output_text", "")
    except Exception as e:
        response_text = f"Error: {e}"

    prompt_tokens = sum(len((m.content or "").split()) * 2 for m in req.messages)
    completion_tokens = len(response_text.split()) * 2

    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_text,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


async def _stream_response(message: str, completion_id: str, created: int, model: str):
    import asyncio

    yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}]})}\n\n"

    try:
        result = _agent_executor.execute({
            "task_name": "_chat",
            "task_description": message,
            "iteration": 1,
            "max_iterations": 1,
            "prior_feedback": "",
            "memory_context": _get_memory_context(message),
            "phase_questions": [],
        })
        text = result.get("output_text", "")

        words = text.split()
        for i, word in enumerate(words):
            chunk = word + (" " if i < len(words) - 1 else "")
            yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'content': chunk}, 'finish_reason': None}]})}\n\n"
            await asyncio.sleep(0.02)

    except Exception as e:
        yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {'content': f'Error: {e}'}, 'finish_reason': None}]})}\n\n"

    yield f"data: {json.dumps({'id': completion_id, 'object': 'chat.completion.chunk', 'created': created, 'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})}\n\n"
    yield "data: [DONE]\n\n"


@router.get("/v1/models")
def list_models():
    model_id = _lifecycle.config.model if _lifecycle and _lifecycle.config else "den-agent"
    agent_name = _lifecycle.config.name if _lifecycle and _lifecycle.config else "unknown"

    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "den-agent",
                "name": agent_name,
            }
        ],
    }


@router.get("/v1/models/{model_id}")
def get_model(model_id: str):
    agent_name = _lifecycle.config.name if _lifecycle and _lifecycle.config else "unknown"
    return {
        "id": model_id,
        "object": "model",
        "created": int(time.time()),
        "owned_by": "den-agent",
        "name": agent_name,
    }


def _get_memory_context(message: str) -> str:
    if not _lifecycle or not _lifecycle.memory:
        return ""
    memories = _lifecycle.memory.recall(message, top_k=5)
    if not memories:
        return ""
    lines = ["[Agent memory]"]
    for m in memories:
        lines.append(f"  [{m.get('category', '?')}] {m.get('content', '')[:150]}")
    return "\n".join(lines)


def _error_response(message: str) -> dict:
    return {
        "error": {
            "message": message,
            "type": "invalid_request_error",
            "code": None,
        }
    }
