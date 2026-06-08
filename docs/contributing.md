# Contributing to JARVIS

Thank you for your interest in contributing to JARVIS. This guide covers everything you need to get started.

## Table of Contents

1. [Development Setup](#development-setup)
2. [Code Style and Conventions](#code-style-and-conventions)
3. [Testing Requirements](#testing-requirements)
4. [PR Process](#pr-process)
5. [Module Structure](#module-structure)
6. [How to Add New Components](#how-to-add-new-components)

---

## Development Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- Git

### Installation

```bash
# Clone the repository
git clone <repo-url> jarvis && cd jarvis

# Install all dependencies (including dev tools)
make dev

# Or manually:
uv venv
uv pip install -e ".[all]" --python .venv/bin/python
uv pip install pytest pytest-asyncio httpx ruff mypy --python .venv/bin/python

# Copy the example environment file
cp .env.example .env
# Edit .env to add API keys if you want LLM-powered features
```

### Verify Installation

```bash
# Run the test suite
make test

# Run the demo
make demo

# Start the server
make run
```

### IDE Setup

**VS Code recommended extensions:**
- Python (ms-python)
- Ruff (charliermarsh.ruff)
- Mypy Type Checker (matangover.mypy)

**Settings:**
```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.analysis.typeCheckingMode": "basic"
}
```

---

## Code Style and Conventions

### Python Style

- **Formatter:** Ruff (`make format`)
- **Linter:** Ruff (`make lint`)
- **Type checker:** mypy (`make typecheck`)
- **Line length:** 100 characters (Ruff default)
- **Python version:** Use `from __future__ import annotations` in all files
- **Quotes:** Double quotes for strings

### Naming Conventions

| Type | Convention | Example |
|------|-----------|---------|
| Modules | `snake_case` | `spec_engine.py` |
| Classes | `PascalCase` | `SpecExecutor` |
| Functions/methods | `snake_case` | `execute_spec()` |
| Constants | `UPPER_SNAKE_CASE` | `_RATE_LIMIT_WINDOW` |
| Private | Leading underscore | `_specs`, `_emit()` |
| Type vars | Single uppercase | `T = TypeVar("T")` |

### Architecture Conventions

- **Pydantic v2** for all data models (use `BaseModel`, not dataclasses, for serialized types)
- **Dataclasses** for internal-only data structures (`TaskResult`, `AgentContext`, etc.)
- **Abstract base classes** for all extensible components (`BaseAgent`, `BaseTool`, `Channel`, `Store`, `LLMProvider`)
- **Registry pattern** for discoverable components (agents, tools, skills, LLM providers)
- **Async-first** -- all public APIs are async (`async def`), even if the implementation is synchronous
- **Graceful degradation** -- every LLM-powered feature must have a deterministic fallback

### Logging

```python
import logging
logger = logging.getLogger(__name__)

# Use appropriate levels:
logger.debug("Low-level detail: %s", detail)
logger.info("Normal operation: %s initialized", component)
logger.warning("Recoverable issue: %s", issue)
logger.error("Error: %s", error)
logger.exception("Unexpected error")  # includes traceback
```

### Import Order

1. `from __future__ import annotations`
2. Standard library (`import asyncio, logging, ...`)
3. Third-party (`from pydantic import BaseModel`)
4. Local (`from jarvis.agents.base import BaseAgent`)

---

## Testing Requirements

### Test Framework

- **pytest** with **pytest-asyncio** for async tests
- Tests live in `tests/` with filenames matching `test_*.py`
- Use `@pytest.mark.asyncio` for async test functions

### Coverage Requirements

- All new features must include tests
- All bug fixes must include a regression test
- Aim for >80% coverage on new modules

### Running Tests

```bash
# Full suite
make test

# Fast (skip slow tests)
make test-fast

# With coverage report
make test-coverage

# Specific test file
.venv/bin/python -m pytest tests/test_streaming_spec.py -v

# Specific test function
.venv/bin/python -m pytest tests/test_agents.py::test_orchestrator_routing -v

# Integration tests only
make test-integration

# Stress tests
make test-stress
```

### Writing Tests

```python
import pytest
from jarvis.agents.base import BaseAgent, AgentCard, AgentContext, TaskResult

@pytest.mark.asyncio
async def test_agent_routing():
    """Orchestrator routes to the highest-scoring agent."""
    # Arrange
    registry = AgentRegistry()
    # ... setup ...

    # Act
    result = await orchestrator.handle("review my code")

    # Assert
    assert result.success
    assert result.agent_name == "code-agent"
```

### Test Categories

| File | Scope |
|------|-------|
| `test_streaming_spec.py` | StreamingSpec model unit tests |
| `test_executor.py` | SpecExecutor DAG execution |
| `test_agents.py` | Agent routing and delegation |
| `test_tools.py` | Tool registry and execution |
| `test_skills.py` | Skill distillation and evolution |
| `test_events.py` | EventBus pub/sub |
| `test_security.py` | Sandbox and permissions |
| `test_storage.py` | Storage backends |
| `test_llm.py` | LLM provider abstraction |
| `test_gateway.py` | Gateway and channels |
| `test_integration.py` | End-to-end flows |
| `test_cross_module.py` | Cross-module integration |
| `test_stress.py` | Performance and load tests |

---

## PR Process

1. **Fork** the repository and create a feature branch:
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Implement** your changes following the code style and conventions above.

3. **Test** -- write tests and ensure all tests pass:
   ```bash
   make test
   make lint
   make typecheck
   ```

4. **Commit** with a clear message:
   ```
   feat: add WebSocket support for spec editing
   fix: handle empty constraint list in replanner
   docs: update API reference for /specs endpoints
   refactor: extract ContextBuilder from BaseAgent
   test: add integration tests for skill evolution
   ```

5. **Push** and create a Pull Request against `main`.

6. **Review** -- address reviewer feedback. All PRs require at least one approval.

### PR Checklist

- [ ] Tests pass (`make test`)
- [ ] No lint errors (`make lint`)
- [ ] Type checks pass (`make typecheck`)
- [ ] New features have tests
- [ ] API changes are documented
- [ ] No secrets committed (check `.env` is in `.gitignore`)
- [ ] Graceful degradation: if you added LLM-powered logic, there is a fallback

---

## Module Structure

Each module in `src/jarvis/` follows a consistent structure:

```
module_name/
    __init__.py          # Public API exports
    base.py / core.py    # Abstract base classes or core logic
    manager.py           # High-level manager / facade
    models.py            # Pydantic models (if needed)
```

Key modules and their responsibilities:

| Module | Responsibility | Key File |
|--------|---------------|----------|
| `agents/` | Agent system | `base.py`, `orchestrator.py`, `specialists/` |
| `engine/` | Streaming Spec execution | `spec_engine.py`, `executor.py` |
| `tools/` | Tool system | `base.py`, `registry.py`, `builtin/` |
| `skills/` | Skill evolution | `base.py`, `evolve.py`, `registry.py` |
| `llm/` | LLM providers | `provider.py`, `registry.py` |
| `gateway/` | Multi-channel gateway | `channel.py`, `gateway.py`, `channels/` |
| `security/` | Security controls | `sandbox.py`, `permissions.py`, `manager.py` |
| `storage/` | Persistence | `base.py`, `kv.py`, `json_store.py` |
| `events/` | Event bus | `bus.py`, `topics.py` |
| `observability/` | Tracing and metrics | `tracer.py`, `metrics.py` |

---

## How to Add New Components

### Adding a New Agent

1. Create `src/jarvis/agents/specialists/my_agent.py`:

```python
from jarvis.agents.base import BaseAgent, AgentCard, AgentContext, TaskResult

class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(AgentCard(
            name="my-agent",
            description="Handles my-domain tasks",
            skills=["keyword1", "keyword2", "keyword3"],
            domain="my-domain",
        ))

    async def execute(self, message: str, context: AgentContext) -> TaskResult:
        # Use LLM with tool calling:
        return await self._llm_execute(
            message, context,
            system_prompt="You are a specialist in my-domain.",
        )
```

2. Register in `src/jarvis/app.py`:

```python
from jarvis.agents.specialists.my_agent import MyAgent

# In JarvisApp.initialize():
agents = [
    # ... existing agents ...
    MyAgent(),
]
```

3. Add tests in `tests/test_agents_extended.py`.

### Adding a New Tool

1. Create `src/jarvis/tools/builtin/my_tool.py`:

```python
from jarvis.tools.base import BaseTool, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something useful"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "The input"},
        },
        "required": ["input"],
    }

    async def execute(self, arguments: dict) -> ToolResult:
        input_val = arguments["input"]
        # ... tool logic ...
        return ToolResult(success=True, output=f"Result: {input_val}")
```

2. Register in `src/jarvis/tools/builtin/__init__.py`:

```python
from jarvis.tools.builtin.my_tool import MyTool

_BUILTIN_TOOLS = [
    # ... existing tools ...
    MyTool(),
]
```

3. Add tests in `tests/test_tools_extended.py`.

### Adding a New Skill

Create a YAML file in `skills/`:

```yaml
kind: Skill
metadata:
  name: my-skill
  version: "1.0.0"
  description: "A reusable procedure for X"
  author: "contributor-name"
  tags: ["category"]
  domain: "my-domain"
spec:
  system_prompt: "You are an expert at X."
  steps:
    - order: 0
      action: "First, do A"
      tool: "shell_execute"
      tool_args: {}
    - order: 1
      action: "Then, do B"
  constraints:
    - "Always validate input"
    - "Handle errors gracefully"
```

### Adding a New Channel

1. Create `src/jarvis/gateway/channels/my_channel.py`:

```python
from jarvis.gateway.channel import Channel, ChannelConfig, ChannelMessage, ChannelType

class MyChannel(Channel):
    def __init__(self, config: ChannelConfig):
        super().__init__(config)

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    async def send(self, channel_id: str, content: str, **kwargs) -> bool:
        # Send message to the platform
        return True
```

2. Register with the `Gateway`:

```python
from jarvis.gateway.channels.my_channel import MyChannel

gateway.register_channel(MyChannel(ChannelConfig(
    name="my-channel",
    channel_type=ChannelType.WEBHOOK,
)))
```

3. Add tests in `tests/test_gateway_advanced.py`.

### Adding a New Storage Backend

1. Implement the `Store[T]` interface in `src/jarvis/storage/my_store.py`
2. Add the backend enum value in `StorageBackend`
3. Wire it into `KeyValueStore.__init__()` in `src/jarvis/storage/kv.py`

### Adding a New LLM Provider

1. Implement `LLMProvider` in `src/jarvis/llm/my_provider.py`
2. Implement both `chat()` and `stream()` methods
3. Register in `LLMRegistry`
