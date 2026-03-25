"""Den Agent Process -- PID 1 inside the Docker container."""

from __future__ import annotations

import logging
import os
import sys

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("den.agent")


def main():
    """Boot the agent and start the server."""
    agentfile_path = os.environ.get("DEN_AGENTFILE", "/den-config/agentfile.yaml")
    if not os.path.exists(agentfile_path):
        for fallback in ["/den/agentfile.yaml", "/den/Agentfile", "Agentfile"]:
            if os.path.exists(fallback):
                agentfile_path = fallback
                break
        else:
            logger.error(f"Agentfile not found at {agentfile_path}")
            sys.exit(1)

    logger.info(f"Loading Agentfile: {agentfile_path}")

    from den.core.lifecycle import AgentLifecycle
    den_home = os.environ.get("DEN_HOME", os.path.expanduser("~/.den"))
    lifecycle = AgentLifecycle(
        agentfile_path=agentfile_path,
        den_home=den_home,
    )
    lifecycle.boot()
    lifecycle.start_scheduler()

    from den.core.pydantic_executor import PydanticAIExecutor
    from den.tools import get_registry

    loaded_tools = get_registry().load_tools(lifecycle.config.tools)
    executor = PydanticAIExecutor(
        model=lifecycle.config.model,
        system_prompt=lifecycle.config.system_prompt,
        tools=loaded_tools,
        memory_manager=lifecycle.memory,
    )
    logger.info(f"Agent executor ready: {lifecycle.config.model}")

    from den.server.app import app, set_lifecycle, set_agent_executor
    set_lifecycle(lifecycle)
    set_agent_executor(executor)

    port = int(os.environ.get("DEN_PORT", "7700"))
    logger.info(f"Agent '{lifecycle.name}' booted. Starting server on :{port}")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
