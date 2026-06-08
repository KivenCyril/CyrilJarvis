# JARVIS Examples

Runnable Python scripts demonstrating all JARVIS capabilities.
Every example works in **mock mode** -- no API keys required.

## Quick Start

```bash
# From the project root, using the virtual environment:
.venv/bin/python examples/basic_chat.py

# Or activate the venv first:
source .venv/bin/activate
python examples/basic_chat.py
```

## Examples

| # | File | Description | Lines |
|---|------|-------------|-------|
| 1 | `basic_chat.py` | Agent routing, orchestrator, multi-turn conversation | ~150 |
| 2 | `streaming_spec.py` | Streaming Spec lifecycle: create, edit, redirect, DAG | ~200 |
| 3 | `dag_workflows.py` | DAG dependencies: diamond, parallel, critical path | ~200 |
| 4 | `skill_evolution.py` | Skill system: create, execute, evolve, distill from spec | ~200 |
| 5 | `knowledge_graph.py` | Knowledge graph: entities, relations, extraction, query | ~200 |
| 6 | `memory_system.py` | Memory: add, search, context, prune, persistence | ~150 |
| 7 | `tool_usage.py` | Tool registry: all 43 built-in tools demonstrated | ~200 |
| 8 | `workflow_engine.py` | Workflows: branching, loops, parallel, transforms | ~250 |
| 9 | `security_demo.py` | Security: permissions, sandbox, secret scanning | ~150 |
| 10 | `observability_demo.py` | Observability: tracing, metrics, diagnostics | ~150 |
| 11 | `event_driven.py` | Event bus: pub/sub, wildcards, filtering, replay | ~150 |
| 12 | `notifications_demo.py` | Notifications: channels, priority, rate limiting | ~100 |
| 13 | `template_demo.py` | Templates: spec templates, prompt templates | ~150 |
| 14 | `migration_demo.py` | Migration: Hermes and OpenClaw validation and import | ~100 |
| 15 | `full_pipeline.py` | End-to-end pipeline integrating all subsystems | ~300 |

## Example Categories

### Core Concepts
- **basic_chat.py** -- Start here. Shows how agents are registered and how the orchestrator routes messages.
- **streaming_spec.py** -- The core JARVIS innovation. Shows the real-time editable task control panel.
- **dag_workflows.py** -- Deep dive into DAG-based dependency management and parallel execution.

### Knowledge & Memory
- **knowledge_graph.py** -- Entity-relation graph with text extraction and semantic query.
- **memory_system.py** -- Persistent memory with keyword search and importance scoring.

### Skills & Evolution
- **skill_evolution.py** -- Procedural memory that improves through use. Shows the Spec-to-Skill bridge.

### Infrastructure
- **tool_usage.py** -- All 43 built-in tools: shell, files, git, HTTP, math, encoding, and more.
- **workflow_engine.py** -- Complex workflows with conditional branching, loops, and approval gates.
- **event_driven.py** -- Decoupled communication via the event bus.
- **notifications_demo.py** -- Multi-channel notification delivery.
- **template_demo.py** -- Reusable spec and prompt templates.

### Operations
- **security_demo.py** -- Permission checks, sandbox enforcement, secret detection.
- **observability_demo.py** -- Distributed tracing, metrics, and system diagnostics.
- **migration_demo.py** -- Migrate from Hermes Agent or OpenClaw to JARVIS.

### Integration
- **full_pipeline.py** -- The capstone: all subsystems working together in a single pipeline.

## Requirements

- Python 3.12+
- `rich` (for console output)
- `pydantic` (data models)
- `pyyaml` (skill serialisation)

All dependencies are included in the project's `pyproject.toml`.

## Design Principles

1. **Runnable** -- Every example can be executed directly with `python examples/xxx.py`.
2. **Self-contained** -- No external API keys or services needed (mock/fallback mode).
3. **Documented** -- Each step is commented and produces console output.
4. **Correct** -- Examples use the actual JARVIS APIs, not simplified wrappers.
5. **Progressive** -- Start with `basic_chat.py`, end with `full_pipeline.py`.
