# JARVIS

**Streaming Spec Driven Personal AI Assistant**

`10 agents` | `20+ tools` | `DAG execution` | `skill evolution` | `knowledge graph`

JARVIS is a modular, multi-agent AI assistant built on the **Streaming Spec** paradigm -- a real-time editable task control panel that decomposes user intent into a dependency-aware DAG of steps, executes them in parallel where possible, and allows human-in-the-loop constraint editing mid-execution. Completed specs are distilled into self-improving skills, forming a procedural memory that gets better over time.

## Architecture

```
                         +------------------+
                         |    CLI / Web UI  |
                         +--------+---------+
                                  |
                         +--------v---------+
                         |   JarvisApp      |
                         |  (orchestrator)  |
                         +--------+---------+
                                  |
              +-------------------+-------------------+
              |                   |                   |
     +--------v--------+ +-------v--------+ +--------v--------+
     |  SpecEngine     | |  AgentRegistry | |  ToolRegistry   |
     |  (Streaming     | |  (10 specialist| |  (20+ builtin   |
     |   Spec DAG)     | |   agents)      | |   tools)        |
     +--------+--------+ +-------+--------+ +--------+--------+
              |                   |                   |
     +--------v--------+         |          +---------v--------+
     |  SpecExecutor   +---------+          | shell, file,     |
     |  (DAG-parallel) |                    | git, http, json, |
     +--------+--------+                    | python, search,  |
              |                             | text, sysinfo    |
              v                             +------------------+
     +--------+--------+
     |  Replanner      |
     |  (constraint    |
     |   reactions)    |
     +-----------------+

     +------------------+  +------------------+  +------------------+
     |  KnowledgeGraph  |  |  MemoryManager   |  |  SkillRegistry   |
     |  (entity/rel     |  |  (keyword search, |  |  (distillation,  |
     |   extraction)    |  |   persistence)   |  |   evolution)     |
     +------------------+  +------------------+  +------------------+

     +------------------+  +------------------+  +------------------+
     |  Curator         |  |  SessionManager  |  |  Observability   |
     |  (quality review,|  |  (history, multi |  |  (tracing,       |
     |   hallucination) |  |   channel)       |  |   metrics)       |
     +------------------+  +------------------+  +------------------+
```

## Features

### Streaming Spec Engine
- Natural language intent decomposed into executable DAG steps
- Dependency-aware parallel execution via `asyncio.gather`
- Human-in-the-loop: add/remove constraints, edit steps, redirect intent mid-execution
- Full changelog with source tracking (human vs. agent)
- Topological sort, critical path analysis, cycle detection

### Multi-Agent System (10 Agents)
| Agent | Domain | Capabilities |
|-------|--------|-------------|
| code-agent | Development | Code review, generation, git, build, test |
| calendar-agent | Scheduling | Meeting scheduling, availability |
| knowledge-agent | Knowledge | Information search, synthesis |
| comms-agent | Communication | Email, messaging |
| ops-agent | Operations | Server health, monitoring |
| data-agent | Data | CSV analysis, statistics |
| security-agent | Security | Vulnerability audit, compliance |
| devops-agent | DevOps | Docker, CI/CD, deployment |
| writing-agent | Content | Documentation, blog posts |
| research-agent | Research | Market trends, analysis |

### Tool System (20+ Tools)
Builtin tools: `shell_execute`, `read_file`, `write_file`, `python_execute`, `git_status`, `git_diff`, `git_log`, `http_get`, `http_post`, `json_parse`, `json_format`, `text_search`, `text_replace`, `text_count`, `system_info`, `disk_usage`, `process_list`, `web_search`, `git_commit`, `list_directory`.

### Skill Evolution
- **Distillation**: completed Streaming Specs are distilled into reusable Skills
- **Evolution loop**: Skills self-improve based on execution history (success rate, quality scores)
- **Versioning**: semantic version bumps with full audit trail
- **Persistence**: agentskills.io compatible YAML format

### Knowledge Graph
- Manual and LLM-powered entity/relation extraction
- Keyword and semantic graph queries
- JSON persistence, node merging, visualization export

### Memory System
- Five memory types: conversation, fact, preference, skill_learned, spec_history
- Keyword-based retrieval with TF + importance + recency scoring
- LLM-powered importance assessment (with heuristic fallback)
- Conversation summarization

### Curator (Quality Review)
- Accuracy, completeness, safety, and constraint compliance checks
- Hallucination risk detection
- Skill safety review before activation
- Quality trend tracking

### Session Management
- Multi-channel support (CLI, web, API)
- Full conversation history with agent attribution
- Session persistence and expiry
- Cross-session metrics aggregation

### Observability
- OpenTelemetry-style distributed tracing (traces, spans)
- Counters, histograms, gauges with percentile support (p50/p95/p99)
- Per-trace JSON persistence

## Quick Start

### Prerequisites
- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Install

```bash
git clone <repo-url> jarvis && cd jarvis
uv sync                      # install deps into .venv
# or: pip install -e ".[all]"
```

### Configure (optional)

```bash
# For LLM-powered features, set one of:
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."

# Or run in mock mode (no API key needed -- all features still work)
```

### Run the demo

```bash
.venv/bin/python demo.py
```

### CLI

```bash
# Interactive chat
jarvis chat

# One-shot task
jarvis chat "review the code in src/"

# Create and execute a Streaming Spec
jarvis spec create "Build a REST API for user management"
jarvis spec list
jarvis spec show <spec-id>
jarvis spec constrain <spec-id> "Use FastAPI framework"
jarvis spec execute <spec-id>

# Web UI
jarvis server --port 8000
```

## Project Structure

```
jarvis/
  demo.py                       # Interactive demo script
  pyproject.toml                # Project metadata and dependencies
  jarvis.yaml                  # Runtime configuration
  src/jarvis/
    app.py                     # JarvisApp -- top-level wiring
    cli/main.py                # Typer CLI entry point
    server/                    # FastAPI server + WebSocket
    models/
      streaming_spec.py        # StreamingSpec, Step, Constraint (Pydantic)
      agent_spec.py            # Agent spec definitions
    engine/
      spec_engine.py           # Spec creation, editing, streaming
      executor.py              # DAG-aware parallel executor
      replanner.py             # Constraint reaction engine
      spec_registry.py         # YAML-based spec templates
    agents/
      base.py                  # BaseAgent, AgentCard, TaskResult
      orchestrator.py          # Intent routing + delegation
      registry.py              # Agent discovery and lifecycle
      conversation.py          # LLM conversation loop with tools
      context.py               # Context builder for prompts
      a2a.py                   # Agent-to-Agent protocol
      specialists/             # 10 domain-specific agents
    tools/
      base.py                  # BaseTool, ToolResult
      registry.py              # ToolRegistry singleton
      builtin/                 # 20+ builtin tools
    knowledge/graph.py         # KnowledgeGraph with LLM extraction
    memory/manager.py          # MemoryManager with persistence
    skills/
      base.py                  # Skill, SkillStep, SkillExecution
      registry.py              # SkillRegistry with search
      evolve.py                # SkillEvolver -- distillation + improvement
    curator/engine.py          # Quality review + hallucination detection
    session/manager.py         # Session lifecycle and persistence
    observability/
      tracer.py                # Distributed tracing (spans)
      metrics.py               # Counters, histograms, gauges
    llm/                       # LLM provider abstraction
    security/                  # Sandbox, permissions
    plugins/                   # Plugin system
    hooks/                     # Event hooks engine
    mcp/                       # MCP client integration
    gateway/                   # API gateway
  tests/
    test_integration.py        # End-to-end integration tests
    test_streaming_spec.py     # Spec model unit tests
    test_executor.py           # Executor unit tests
    test_agents.py             # Agent routing tests
    test_tools.py              # Tool registry tests
    test_observability.py      # Tracer + metrics tests
    test_session.py            # Session management tests
    ...                        # 17 test modules total
  specs/                       # YAML spec templates
  skills/                      # Persisted skill definitions
  web/                         # Frontend assets
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Models | Pydantic v2 |
| Web | FastAPI + Uvicorn + SSE + WebSocket |
| CLI | Typer + Rich |
| LLM | OpenAI / Anthropic (pluggable) |
| Serialization | YAML (skills, specs) + JSON (memory, sessions, traces) |
| Testing | pytest + pytest-asyncio |
| Packaging | Hatch (PEP 517) |
| Dependency management | uv |

## Testing

```bash
# Run full test suite
.venv/bin/python -m pytest tests/ -q

# Run integration tests only
.venv/bin/python -m pytest tests/test_integration.py -v

# Run with coverage
.venv/bin/python -m pytest tests/ --tb=short -q
```

## Key Design Decisions

1. **Streaming Spec as first-class primitive**: Tasks are not fire-and-forget. They are living documents that can be inspected, edited, and redirected while executing.

2. **DAG-parallel execution**: Steps with no dependencies run concurrently. The executor re-evaluates readiness after each wave, respecting edits made between waves.

3. **Graceful degradation**: Every LLM-powered feature (spec decomposition, knowledge extraction, memory scoring, curator review, skill matching) has a deterministic fallback so the system works without API keys.

4. **Skill evolution loop**: Specs -> Skills -> Execution History -> Improvement -> Better Skills. This is the core learning mechanism inspired by Hermes.

5. **Agent-to-Agent delegation**: Agents can delegate sub-tasks to each other through the orchestrator, enabling complex multi-step workflows.

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for new functionality
4. Ensure `pytest tests/` passes
5. Submit a pull request

## License

MIT
