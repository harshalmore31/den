FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    git \
    net-tools \
    procps \
    iproute2 \
    lsof \
    netcat-openbsd \
    wget \
    vim-tiny \
    less \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip first
RUN pip install --no-cache-dir --upgrade pip

# Python deps for agent runtime
RUN pip install --no-cache-dir \
    pydantic-ai \
    anthropic \
    openai \
    httpx \
    pypdf \
    pandas \
    pyyaml \
    pydantic \
    numpy \
    fastapi \
    uvicorn \
    apscheduler \
    structlog

# Create Den directory structure
RUN mkdir -p /den/memory /den/workspace /den/output /den/logs /den/tools /den-config

# Copy den-core package
COPY den/ /opt/den-core/den/
COPY pyproject.toml /opt/den-core/
RUN pip install --no-cache-dir /opt/den-core/

WORKDIR /den/workspace

EXPOSE 7700

CMD ["python", "-m", "den.core.agent_process"]
