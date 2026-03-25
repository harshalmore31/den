"""PydanticAI-based Agent Executor -- the LLM brain of a Den agent."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PydanticAIExecutor:
    """Executes agent tasks using PydanticAI, with direct API fallback."""

    def __init__(
        self,
        model: str,
        system_prompt: str,
        tools: dict[str, Any] | None = None,
        memory_manager: Any = None,
    ):
        self.model = model
        self.system_prompt = system_prompt
        self.tools = tools or {}
        self.memory = memory_manager
        self._agent = None

    def _get_agent(self):
        if self._agent is not None:
            return self._agent

        try:
            from pydantic_ai import Agent
            from pydantic_ai.settings import ModelSettings

            pydantic_tools = []
            for name, tool in self.tools.items():
                pydantic_tools.append(self._wrap_tool(tool))

            self._agent = Agent(
                self.model,
                instructions=self.system_prompt,
                tools=pydantic_tools,
                model_settings=ModelSettings(parallel_tool_calls=True),
            )
            logger.info(f"PydanticAI agent initialized: {self.model} ({len(pydantic_tools)} tools)")
            return self._agent

        except ImportError:
            logger.warning("PydanticAI not available -- using simple executor")
            return None
        except Exception as e:
            logger.error(f"Failed to init PydanticAI agent: {e}")
            return None

    def _wrap_tool(self, den_tool: Any):
        """Convert a Den tool to a PydanticAI-compatible async function."""
        tool_name = den_tool.name
        tool_desc = den_tool.description
        tool_ref = den_tool
        executor_ref = self

        async def tool_fn(**kwargs) -> str:
            call_record = {"tool": tool_name, "args": kwargs, "status": "running"}
            executor_ref._tool_calls.append(call_record)
            logger.info(f"[TOOL] {tool_name}({', '.join(f'{k}={repr(v)[:50]}' for k, v in kwargs.items())})")

            try:
                result = tool_ref(**kwargs)
                call_record["status"] = "success"
                if isinstance(result, dict):
                    if result.get("success") is False:
                        call_record["status"] = "error"
                        call_record["error"] = result.get("error", "unknown")
                        return f"Error: {result.get('error', 'unknown error')}"
                    clean = {k: v for k, v in result.items() if k != "success" and v}
                    call_record["result_preview"] = str(clean)[:200]
                    return str(clean) if clean else "Done."
                call_record["result_preview"] = str(result)[:200]
                return str(result)
            except Exception as e:
                call_record["status"] = "error"
                call_record["error"] = str(e)
                return f"Tool error: {e}"

        tool_fn.__name__ = tool_name
        tool_fn.__doc__ = tool_desc

        return tool_fn

    def execute(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute an agent turn (called by the Loop Engine or /den/v1/ask)."""
        task = context.get("task_description", "")
        feedback = context.get("prior_feedback", "")
        memory_ctx = context.get("memory_context", "")
        iteration = context.get("iteration", 1)
        message_history = context.get("message_history", [])

        from datetime import datetime
        now = datetime.now()
        prompt_parts = [
            f"[Current date and time: {now.strftime('%A, %B %d, %Y at %I:%M %p')} | "
            f"Timezone: {now.astimezone().tzname()}]"
        ]

        if memory_ctx:
            prompt_parts.append(memory_ctx)

        if feedback and iteration > 1:
            prompt_parts.append(f"\n[Previous attempt feedback -- fix these issues]\n{feedback}")

        prompt_parts.append(task)
        full_prompt = "\n\n".join(prompt_parts)

        self._tool_calls: list[dict] = []

        agent = self._get_agent()
        if agent:
            result = self._execute_pydantic(agent, full_prompt, message_history)
            result["tool_calls"] = self._tool_calls
            return result

        result = self._execute_direct(full_prompt, message_history)
        result["tool_calls"] = self._tool_calls
        return result

    def _execute_pydantic(self, agent: Any, prompt: str, history: list | None = None) -> dict[str, Any]:
        import asyncio

        async def _run():
            pydantic_history = None
            if history:
                try:
                    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
                    pydantic_history = []
                    for msg in history:
                        if msg.get("role") == "user":
                            pydantic_history.append(ModelRequest(parts=[UserPromptPart(content=msg["content"])]))
                        elif msg.get("role") == "assistant":
                            pydantic_history.append(ModelResponse(parts=[TextPart(content=msg["content"])]))
                except ImportError:
                    pydantic_history = None

            if pydantic_history:
                result = await agent.run(prompt, message_history=pydantic_history)
            else:
                result = await agent.run(prompt)
            return str(result.output) if hasattr(result, 'output') else str(result.data)

        try:
            try:
                loop = asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    output_text = pool.submit(lambda: asyncio.run(_run())).result(timeout=120)
            except RuntimeError:
                output_text = asyncio.run(_run())

            return {
                "output_text": output_text,
                "output_files": [],
            }
        except Exception as e:
            import traceback
            logger.error(f"PydanticAI execution failed: {e}\n{traceback.format_exc()}")
            return self._execute_direct(prompt, history)

    def _build_system_with_tools(self) -> str:
        parts = [self.system_prompt]
        if self.tools:
            parts.append("\n\nYou have access to these tools:")
            for name, tool in self.tools.items():
                parts.append(f"- {name}: {tool.description}")
            parts.append("\nUse these tools when appropriate to help the user.")

        parts.append("""
IMPORTANT rules:
- ALWAYS use your tools. Never say "I can't do that" -- try the tool first.
- You are running inside a sandboxed Docker container. You CAN run bash commands, access the network, read/write files. DO IT.
- If the user asks you to check something, run a command, or perform an action -- USE THE TOOL. Don't just suggest commands for the user to run.
- Save documents and user-requested files to /den/output/ (shared with user's machine)
- Use /den/workspace/ for temporary working files
- Use /den/memory/ ONLY for your own notes
- bash tool: You can run ANY command. Pipes (|) work. Network tools work. Python works. Try it.
- Use the 'path' parameter (not 'file_path') when calling file_write
- Use 'command' parameter (string, not list) when calling bash""")

        return "\n".join(parts)

    def _execute_direct(self, prompt: str, history: list | None = None) -> dict[str, Any]:
        import os

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        if anthropic_key and ("claude" in self.model.lower() or "anthropic" in self.model.lower()):
            return self._call_anthropic(prompt, anthropic_key, history)

        openai_key = os.environ.get("OPENAI_API_KEY")
        if openai_key:
            return self._call_openai(prompt, openai_key, history)

        return {
            "output_text": "[No API key configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY.]",
            "output_files": [],
        }

    def _call_anthropic(self, prompt: str, api_key: str, history: list | None = None) -> dict[str, Any]:
        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            model = self.model.split(":")[-1] if ":" in self.model else self.model

            messages = []
            if history:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": prompt})

            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=self._build_system_with_tools(),
                messages=messages,
            )
            return {
                "output_text": response.content[0].text,
                "output_files": [],
            }
        except Exception as e:
            return {"output_text": f"Anthropic API error: {e}", "output_files": []}

    def _call_openai(self, prompt: str, api_key: str, history: list | None = None) -> dict[str, Any]:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            model = self.model.split(":")[-1] if ":" in self.model else self.model

            messages = [{"role": "system", "content": self._build_system_with_tools()}]
            if history:
                for msg in history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": prompt})

            functions = []
            for name, tool in self.tools.items():
                schema = tool.Input.model_json_schema()
                schema.pop("title", None)
                functions.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": tool.description[:200],
                        "parameters": schema,
                    }
                })

            kwargs: dict = {"model": model, "messages": messages, "max_tokens": 4096}
            if functions:
                kwargs["tools"] = functions
                kwargs["tool_choice"] = "auto"

            response = client.chat.completions.create(**kwargs)
            msg = response.choices[0].message

            if msg.tool_calls:
                messages.append(msg.model_dump())

                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    import json as _json
                    fn_args = _json.loads(tc.function.arguments)

                    tool = self.tools.get(fn_name)
                    if tool:
                        call_record = {"tool": fn_name, "args": fn_args, "status": "running"}
                        self._tool_calls.append(call_record)
                        logger.info(f"[TOOL] {fn_name}({fn_args})")
                        try:
                            result = tool(**fn_args)
                            call_record["status"] = "success"
                            tool_output = str(result) if isinstance(result, dict) else str(result)
                        except Exception as e:
                            call_record["status"] = "error"
                            call_record["error"] = str(e)
                            tool_output = f"Error: {e}"
                    else:
                        tool_output = f"Unknown tool: {fn_name}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": tool_output[:4000],
                    })

                response2 = client.chat.completions.create(
                    model=model, messages=messages, max_tokens=4096,
                )
                return {
                    "output_text": response2.choices[0].message.content or "",
                    "output_files": [],
                }

            return {
                "output_text": msg.content or "",
                "output_files": [],
            }
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return {"output_text": f"OpenAI API error: {e}", "output_files": []}
