# Changelog

All notable changes to JARVIS are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-06-02

### Added

#### Agent System
- 10 specialist agents: code, calendar, knowledge, comms, ops, data, security, devops, writing, research (`src/jarvis/agents/specialists/`)
- `Orchestrator` with confidence-based routing and delegation logging (`agents/orchestrator.py`)
- `ConversationLoop` for multi-turn tool calling with token budget management (`agents/conversation.py`)
- `ContextBuilder` for priority-based prompt assembly (`agents/context.py`)
- `MiddlewareChain` with 7 middleware types: logging, tracing, metrics, rate limiting, caching, security, input validation (`agents/middleware.py`)
- Agent-to-Agent (A2A) protocol integration (`agents/a2a.py`)
- Parallel delegation via `Orchestrator.parallel_delegate()`

#### Tool System
- 43 built-in tools across 15 categories (`tools/builtin/`)
- Batch 2 tools: Docker operations, database (SQLite), image processing, archive, network diagnostics, math, encoding/hashing, datetime, template rendering
- MCP (Model Context Protocol) client for external tool servers (`mcp/client.py`, `mcp/registry.py`)

#### Streaming Spec Engine
- DAG-aware parallel executor with wave-based scheduling (`engine/executor.py`)
- LLM-powered task decomposition with deterministic fallback (`engine/spec_engine.py`)
- Replanner for mid-execution constraint reactions (`engine/replanner.py`)
- Spec registry for YAML-based spec templates (`engine/spec_registry.py`)
- Dependency management: `add_dependency()`, `remove_dependency()` with cycle detection
- Critical path analysis via `StreamingSpec.critical_path()`
- Topological sort via `StreamingSpec.topological_sort()`
- Human-in-the-loop: constraint editing, step modification, intent redirect

#### Skill System
- `Skill` model with versioning, execution tracking, and YAML persistence (`skills/base.py`)
- `SkillRegistry` with domain-based search (`skills/registry.py`)
- `SkillEvolver` with Spec-to-Skill distillation and AI-driven improvement (`skills/evolve.py`)
- `should_evolve()` triggers based on success rate, quality scores, and trends
- agentskills.io compatible YAML format for skill import/export

#### Knowledge Graph
- Entity-relation store with LLM-powered extraction (`knowledge/graph.py`)
- Manual entity/relation creation
- Keyword and semantic graph queries
- JSON persistence and visualization export

#### Memory System
- `MemoryManager` with 5 memory types (`memory/manager.py`)
- Keyword-based retrieval with TF + importance + recency scoring
- LLM-powered importance assessment with heuristic fallback
- Conversation summarization

#### Curator
- Quality review engine (`curator/engine.py`)
- Accuracy, completeness, safety, and constraint compliance checks
- Hallucination risk detection
- Quality trend tracking
- Skill safety review gate

#### Gateway
- `Gateway` with multi-channel message routing (`gateway/gateway.py`)
- `Channel` abstraction with 5 implementations (`gateway/channels/`)
- Platform-normalized `ChannelMessage` model
- Per-sender rate limiting (sliding window)
- Broadcast to all channels

#### LLM Layer
- Provider abstraction: `LLMProvider` with `chat()` and `stream()` (`llm/provider.py`)
- OpenAI provider (`llm/openai_provider.py`)
- Anthropic provider (`llm/anthropic_provider.py`)
- Ollama provider for local models (`llm/ollama_provider.py`)
- Mock provider for testing without API keys (`llm/mock_provider.py`)
- `LLMRegistry` for provider management (`llm/registry.py`)

#### Security
- `SecurityManager` with secret scanning and redaction (`security/manager.py`)
- `SandboxValidator` with 4 modes: none, basic, strict, docker (`security/sandbox.py`)
- Permission system with RBAC-like levels: none, read, write, execute, admin (`security/permissions.py`)
- `AuthContext` with permission hierarchy and expiry support
- Audit logging for all permission checks

#### Storage
- Abstract `Store[T]` interface (`storage/base.py`)
- JSON file backend (`storage/json_store.py`)
- SQLite backend (`storage/sqlite_store.py`)
- In-memory backend (`storage/memory_store.py`)
- `KeyValueStore` facade with backend selection (`storage/kv.py`)

#### Event System
- `EventBus` with topic-based pub/sub and wildcard matching (`events/bus.py`)
- Priority-based event ordering (LOW, NORMAL, HIGH, CRITICAL)
- Event filtering by topic, source, and priority
- One-shot subscriptions
- Event history and replay
- Dead letter queue for failed handlers
- Middleware pipeline for event transformation
- `EventStore` for JSON-lines persistence (`events/bus.py`)

#### Observability
- `Tracer` with OpenTelemetry-style spans and traces (`observability/tracer.py`)
- `Metrics` with counters, histograms, and gauges (`observability/metrics.py`)
- Percentile support: p50, p95, p99
- Per-trace JSON file persistence
- `SystemDiagnostics` health checks (`diagnostics/health.py`)
- `BenchmarkSuite` for performance measurement (`benchmarks/suite.py`)

#### Server
- FastAPI server with REST API (`server/app.py`)
- WebSocket support for real-time spec editing (`server/websocket.py`)
- Server-Sent Events (SSE) for spec streaming
- Static file serving for web UI (`server/static.py`)
- CORS middleware

#### CLI
- `jarvis chat` -- interactive chat mode
- `jarvis spec` -- spec creation and management
- `jarvis server` -- start the web server
- Built with Typer and Rich (`cli/main.py`)

#### Infrastructure
- Docker multi-stage build (`Dockerfile`)
- Docker Compose with 3 profiles: basic, full (Redis+PostgreSQL), local-llm (Ollama) (`docker-compose.yml`)
- Makefile with 25+ targets
- `jarvis.yaml` configuration file
- `.env.example` template

#### Other Modules
- Plugin system with base class and manager (`plugins/base.py`, `plugins/manager.py`)
- Hook engine for event-driven actions (`hooks/engine.py`)
- Session management (`session/manager.py`)
- User modeling and profiling (`user/modeler.py`, `user/profile.py`)
- Internationalization with English and Chinese strings (`i18n/`)
- Notification system (`notifications/manager.py`, `notifications/models.py`)
- Validation framework (`validation/core.py`)
- Workflow engine with persistence and templates (`workflow/`)
- Resilience: circuit breaker, retry, rate limiter, fallback (`resilience/`)
- Scheduler for recurring tasks (`scheduler/scheduler.py`)
- SDK client for programmatic access (`sdk/client.py`, `sdk/examples.py`)
- Auto-generated API docs (`docs/generator.py`)
- Prompt engineering: builder, factory, few-shot, optimizer (`prompts/`)
- Template engine for specs and prompts (`templates/`)
- Migration adapters for OpenClaw and Hermes (`migration/`)

#### Web UI
- Dashboard (`web/index.html`)
- Agent management (`web/agents.html`)
- Skill browser (`web/skills.html`)
- Tool explorer (`web/tools.html`)
- Knowledge graph viewer (`web/knowledge.html`)
- Memory browser (`web/memory.html`)
- Session viewer (`web/sessions.html`)
- Settings panel (`web/settings.html`)
- Workflow designer (`web/workflows.html`)

#### Tests
- 50+ test modules covering all subsystems
- Integration tests (`test_integration.py`, `test_cross_module.py`)
- Stress tests (`test_stress.py`)
- Edge case tests (`test_edge_cases.py`)
- 15 example scripts in `examples/`

---

## [0.1.0] - 2026-06-01

### Added

- Initial project scaffold
- `pyproject.toml` with Hatch build system
- Basic project structure: `src/jarvis/`, `tests/`, `examples/`
- `.gitignore` and `.env.example`
- Python 3.11+ requirement
- uv dependency management with `uv.lock`

---

## Future Roadmap

### Planned for v0.3.0

- Persistent storage migration from JSON to PostgreSQL
- Redis-backed event bus for horizontal scaling
- OAuth2 / API key authentication for the REST API
- Plugin marketplace integration
- Multi-user support with per-user memory and permissions
- Streaming Spec templates (reusable spec patterns)
- Advanced skill matching using embeddings
- Agent performance benchmarking dashboard
- Webhook channel for CI/CD integration
- Rate limiting per user (not just per sender)

### Planned for v0.4.0

- Distributed execution across multiple JARVIS instances
- LLM fine-tuning on execution history
- Voice channel support
- Mobile app companion
- Spec visualization in the web UI (interactive DAG editor)
