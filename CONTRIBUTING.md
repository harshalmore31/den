# Contributing to Den

Thanks for your interest in contributing to Den. This guide will help you get set up and productive quickly.

## Prerequisites

- Python 3.11+
- Node.js 18+ (or Bun 1.0+)
- Docker
- Git

## Development Setup

### 1. Clone and set up Python (den-agent)

```bash
git clone https://github.com/harshalmore31/Den.git
cd Den

python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

pip install -e ".[dev]"
```

### 2. Set up the CLI (packages/den-cli)

```bash
cd packages/den-cli
npm install        # or: bun install
npm run build      # or: bun build ./src/index.ts --outdir ./dist --target node
cd ../..
```

### 3. Verify everything works

```bash
pytest                          # run Python test suite
cd packages/den-cli && npm test # run CLI tests
```

## Running Tests

```bash
# All Python tests
pytest

# With coverage
pytest --cov=den --cov-report=html

# Specific test file
pytest tests/test_memory.py

# Specific test
pytest tests/test_loop.py::test_research_loop -v
```

## Building the Docker Image

```bash
docker build -t den:dev .

# Run locally
docker run --rm -it den:dev
```

## Building the CLI

```bash
cd packages/den-cli

# Development (watch mode)
npm run dev

# Production build
npm run build
# or with Bun:
bun build ./src/index.ts --outdir ./dist --target node
```

## Code Style

We use **ruff** for linting and formatting, and **mypy** for type checking.

```bash
# Lint
ruff check .

# Format
ruff format .

# Type check
mypy den/
```

All code must pass `ruff check`, `ruff format --check`, and `mypy` before merge. CI enforces this.

## Adding a New Tool

Tools live in `den/tools/`. To add one:

1. Create a new file in `den/tools/`, e.g. `den/tools/my_tool.py`.
2. Subclass `DenTool`:

```python
from den.tools.base import DenTool, ToolResult

class MyTool(DenTool):
    name = "my_tool"
    description = "Does something useful."
    parameters = {
        "input": {"type": "string", "description": "The input value", "required": True},
    }

    async def run(self, input: str) -> ToolResult:
        # Your logic here
        return ToolResult(output=f"Processed: {input}")
```

3. Register it in `den/tools/__init__.py`.
4. Write tests in `tests/test_tools/test_my_tool.py`.

## Adding a New Check

Checks live in `den/checks/`. To add one:

1. Create a new file in `den/checks/`, e.g. `den/checks/my_check.py`.
2. Subclass `Check`:

```python
from den.checks.base import Check, CheckResult

class MyCheck(Check):
    name = "my_check"
    description = "Validates something."

    async def run(self, context: dict) -> CheckResult:
        # Your validation logic
        passed = True
        return CheckResult(passed=passed, message="All good.")
```

3. Register it in `den/checks/__init__.py`.
4. Write tests.

## Pull Request Guidelines

1. **Branch from `main`**. Use a descriptive branch name: `feat/tool-name`, `fix/memory-leak`, `docs/readme-update`.
2. **Keep PRs focused**. One feature or fix per PR.
3. **Write tests** for new functionality. We aim for >80% coverage on new code.
4. **Run the full check suite** before pushing:
   ```bash
   ruff check . && ruff format --check . && mypy den/ && pytest
   ```
5. **Write a clear PR description** explaining what changed and why.
6. **Link related issues** using `Closes #123` in the PR body.

## Questions?

Open an issue or start a discussion on GitHub. We're happy to help.
