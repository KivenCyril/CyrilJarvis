# JARVIS Architecture Guide

> Version 0.2.0 | Streaming Spec Driven Personal AI Assistant

## Table of Contents

1. [System Overview](#system-overview)
2. [Core Concepts](#core-concepts)
3. [Module Deep Dives](#module-deep-dives)
4. [Data Flow Examples](#data-flow-examples)
5. [Deployment](#deployment)

---

## System Overview

### High-Level Architecture

```
    +-------------------------------------------------------------+
    |                     User Interfaces                          |
    |  +---------+  +---------+  +----------+  +----------------+ |
    |  |   CLI   |  | Web UI  |  | Telegram |  | Discord/DingTalk| |
    |  +---------+  +---------+  +----------+  +----------------+ |
    +------------+------+------+-----------+-----+----------------+
                 |      |      |           |     |
    +------------v------v------v-----------v-----v----------------+
    |                      Gateway Layer                           |
    |  Channel abstraction, message normalization, rate limiting    |
    +----------------------------+--------------------------------+
                                 |
    +----------------------------v--------------------------------+
    |                       JarvisApp                              |
    |  Top-level wiring: Orchestrator + SpecEngine + ToolRegistry  |
    +--------+----------+----------+-----------+------------------+
             |          |          |           |
    +--------v---+  +---v------+  +---v----+  +---v-----------+
    | Orchestrator|  |SpecEngine|  | Tools  |  | Knowledge     |
    | (routing +  |  |(DAG exec|  | (43    |  | Graph +       |
    |  delegation)|  | + replan)|  | built  |  | Memory +      |
    +------+------+  +----+----+  | in)    |  | Skills        |
           |              |       +---+----+  +---+-----------+
    +------v------+  +----v----+      |           |
    | 10 Specialist|  |Executor |      |      +---v-----------+
    | Agents       |  |(parallel|      |      | Skill Evolver |
    | (base.py ->  |  | waves)  |      |      | (distill +    |
    |  specialists)|  +---------+      |      |  improve)     |
    +--------------+                   |      +---------------+
                                       |
    +----------------------------------v--------------------------+
    |                    LLM Provider Layer                        |
    |  OpenAI | Anthropic | DeepSeek | Ollama | Mock (fallback)   |
    +------------------------------------------------------------+

    +------------------------------------------------------------+
    |                  Cross-Cutting Concerns                      |
    |  Security | Events | Observability | Storage | Middleware    |
    +------------------------------------------------------------+
```

### Module Dependency Graph

```
  JarvisApp (src/jarvis/app.py)
    |
    +--- LLMRegistry (llm/registry.py)
    |      +--- OpenAIProvider (llm/openai_provider.py)
    |      +--- AnthropicProvider (llm/anthropic_provider.py)
    |      +--- OllamaProvider (llm/ollama_provider.py)
    |      +--- MockProvider (llm/mock_provider.py)
    |
    +--- AgentRegistry (agents/registry.py)
    |      +--- Orchestrator (agents/orchestrator.py)
    |      +--- 10 Specialist Agents (agents/specialists/*.py)
    |      +--- BaseAgent (agents/base.py)
    |            +--- ConversationLoop (agents/conversation.py)
    |            +--- ContextBuilder (agents/context.py)
    |
    +--- SpecEngine (engine/spec_engine.py)
    |      +--- StreamingSpec model (models/streaming_spec.py)
    |      +--- Replanner (engine/replanner.py)
    |      +--- SpecExecutor (engine/executor.py)
    |      +--- SpecRegistry (engine/spec_registry.py)
    |
    +--- ToolRegistry (tools/registry.py)
    |      +--- 43 BaseTool implementations (tools/builtin/*.py)
    |
    +--- KnowledgeGraph (knowledge/graph.py)
    +--- HookEngine (hooks/engine.py)
```

### Data Flow Overview

```
  User Message
       |
       v
  Gateway (normalize)
       |
       v
  Orchestrator (route by confidence score)
       |
       v
  Best Agent (execute via ConversationLoop)
       |
       +---> LLM Provider (chat completion)
       |         |
       |         v
       |     Tool calls? --yes--> ToolRegistry.execute()
       |         |                      |
       |         +<---------------------+
       |         |
       |     More tool calls? --yes--> loop
       |         |
       |         no
       |         v
       +<--- Final response
       |
       v
  Gateway (send back to channel)
       |
       v
  User sees response
```

---

## Core Concepts

### Streaming Spec

The **Streaming Spec** is the central abstraction in JARVIS. It represents a user's intent decomposed into a DAG (Directed Acyclic Graph) of executable steps. Unlike traditional task queues, a Streaming Spec is a *living document* that can be inspected, edited, and redirected while execution is in progress.

**Key properties:**
- `intent` -- the original user request in natural language
- `steps` -- a list of `Step` objects forming a dependency DAG via `depends_on`
- `constraints` -- user- or agent-added rules that all steps must respect
- `status` -- lifecycle state: `planning -> executing -> completed/failed/paused/redirected`
- `changelog` -- every mutation is recorded with source (human vs. agent) and timestamp
- `version` -- incremented on every edit for optimistic concurrency

**Defined in:** `src/jarvis/models/streaming_spec.py`

### Agent System

JARVIS uses a **specialist pattern**: 10 domain-specific agents inherit from `BaseAgent`, each declaring an `AgentCard` with skills, domain, and capabilities. The `Orchestrator` routes incoming messages to the best agent using a confidence-scoring algorithm.

**Agents:** code, calendar, knowledge, comms, ops, data, security, devops, writing, research.

**Defined in:** `src/jarvis/agents/`

### Tool System

43 built-in tools provide agents with concrete capabilities (file I/O, shell execution, HTTP requests, Git operations, etc.). Tools follow a `BaseTool -> ToolRegistry` pattern where every tool self-registers on import.

**Defined in:** `src/jarvis/tools/`

### Skill System

Skills are **reusable procedural memories** distilled from successfully completed Streaming Specs. They capture the *how* of accomplishing a category of tasks and self-improve through an evolution loop driven by execution statistics.

**Defined in:** `src/jarvis/skills/`

### Knowledge Graph

An entity-relation store that extracts structured knowledge from unstructured text. Supports manual and LLM-powered entity extraction, graph queries, and visualization export.

**Defined in:** `src/jarvis/knowledge/graph.py`

### Memory System

Persistent recall across sessions with five memory types (conversation, fact, preference, skill_learned, spec_history). Uses keyword-based retrieval scored by TF + importance + recency.

**Defined in:** `src/jarvis/memory/manager.py`

---

## Module Deep Dives

### Engine (Streaming Spec)

#### StreamingSpec Model

The `StreamingSpec` Pydantic model (`src/jarvis/models/streaming_spec.py`) is the data structure at the heart of JARVIS. Key sub-models:

| Model | Purpose |
|-------|---------|
| `StreamingSpec` | Top-level container: intent, steps, constraints, changelog |
| `Step` | A single executable unit with dependencies, status, output |
| `Constraint` | A rule that must be respected (added by human or agent) |
| `SpecChange` | An immutable changelog entry recording every mutation |
| `SpecEvent` | An SSE event emitted by the engine for real-time updates |

**Step statuses:** `pending -> planning -> blocked -> ready -> executing -> completed/failed/skipped/cancelled`

**Spec statuses:** `planning -> executing -> completed/failed/paused/redirected`

#### DAG Execution Strategy (Wave-Based Parallel)

The `SpecExecutor` (`src/jarvis/engine/executor.py`) implements a wave-based parallel execution strategy:

```
Wave 1:  [Step A]  [Step B]  (no dependencies -- run in parallel)
              |         |
              v         v
Wave 2:  [Step C]            (depends on A and B -- waits for both)
              |
              v
Wave 3:  [Step D]  [Step E]  (both depend only on C -- parallel again)
```

**Algorithm:**
1. Compute readiness: find all steps with `status == READY` (all dependencies completed)
2. Execute the ready steps in parallel via `asyncio.gather`
3. On completion, mark steps as `COMPLETED` or `FAILED`
4. Recompute readiness -- new steps may have become `READY`
5. **Re-fetch the spec** between waves so user edits are respected (human-in-the-loop)
6. Repeat until all steps reach a terminal state or the spec is paused/redirected

**Retry logic:** Each step supports `max_retries` (default 2). The executor retries failed steps up to `max_retries + 1` total attempts.

#### Replanner

The `Replanner` (`src/jarvis/engine/replanner.py`) reacts to mid-execution changes:

- **Constraint added** -- identifies affected steps and may re-decompose them
- **Step edited** -- propagates changes to dependent steps
- **Intent redirected** -- replans the entire spec while preserving completed steps

When an LLM registry is available, the replanner uses AI to reason about impacts; otherwise it applies heuristic rules.

#### Spec Lifecycle

```
  User intent
       |
       v
  SpecEngine.create(intent)
       |
       +---> LLM decomposition (or fallback)
       |
       v
  StreamingSpec(status=PLANNING)
       |
       +---> Steps added, status -> EXECUTING
       |
       v
  SpecExecutor.execute_spec(spec_id)
       |
       +---> Wave 1: parallel ready steps
       |     |
       |     +---> User edits? (constraint, step, redirect)
       |     |         |
       |     |         v
       |     |     Replanner reacts
       |     |
       |     +---> Wave 2, 3, ... N
       |
       v
  status -> COMPLETED / FAILED / PAUSED / REDIRECTED
       |
       v
  SkillEvolver.distill_from_spec(spec)  [optional]
```

#### Human-in-the-Loop

Users can modify a running spec in three ways:

1. **Add/remove constraints** -- new rules injected via `POST /specs/{id}/constraints` or WebSocket `add_constraint` message. The replanner identifies affected pending steps and may restructure them.

2. **Edit steps** -- rename or re-describe a step via `PATCH /specs/{id}/steps/{step_id}`. The replanner propagates changes to downstream dependents.

3. **Redirect intent** -- change the goal entirely via `POST /specs/{id}/redirect`. The replanner generates a new plan, preserving completed steps where possible.

The executor re-fetches the spec between each wave, so edits made during execution are always respected in the next wave.

---

### Agent Architecture

#### BaseAgent -> Specialist Pattern

```
BaseAgent (ABC)
    |-- AgentCard (identity, skills, domain)
    |-- AgentStatus (idle, busy, error, shutdown)
    |-- run(message, context) -> TaskResult
    |-- execute(message, context) -> TaskResult  [abstract]
    |-- delegate(agent_name, message, context)
    |-- can_handle(message) -> float  [confidence 0.0-1.0]
    |-- _llm_execute(message, context)  [uses ConversationLoop]
    |
    +--- CodeAgent          (domain: development)
    +--- CalendarAgent      (domain: scheduling)
    +--- KnowledgeAgent     (domain: knowledge)
    +--- CommsAgent         (domain: communication)
    +--- OpsAgent           (domain: operations)
    +--- DataAgent          (domain: data)
    +--- SecurityAgent      (domain: security)
    +--- DevOpsAgent        (domain: devops)
    +--- WritingAgent       (domain: content)
    +--- ResearchAgent      (domain: research)
```

Each specialist overrides `execute()` with domain-specific logic. All agents share the `_llm_execute()` method which delegates to the `ConversationLoop` for multi-turn tool-calling interactions with the LLM.

**Defined in:** `src/jarvis/agents/base.py`, `src/jarvis/agents/specialists/`

#### Orchestrator Routing Algorithm

The `Orchestrator` (`src/jarvis/agents/orchestrator.py`) routes messages in three steps:

1. **Score** -- call `agent.can_handle(message)` on every registered agent. The default implementation counts keyword matches against the agent's declared skills.
2. **Rank** -- sort agents by descending confidence score.
3. **Dispatch** -- send the message to the highest-scoring agent.

The orchestrator also supports:
- **Explicit delegation** -- one agent asks another to handle a sub-task
- **Parallel delegation** -- execute multiple sub-tasks concurrently via `parallel_delegate()`
- **Delegation logging** -- every delegation is recorded for observability

#### ConversationLoop

The `ConversationLoop` (`src/jarvis/agents/conversation.py`) implements a production-grade multi-turn conversation loop modeled after Hermes Agent:

```
User message
     |
     v
+----+------------------------------+
|  for turn in range(max_turns):     |
|    |                               |
|    v                               |
|  Check token budget                |
|    |                               |
|    +-- Over budget? --> compress   |
|    |                               |
|    v                               |
|  LLM.chat(messages, tools)         |
|    |                               |
|    +-- No tool calls? --> break    |
|    |                               |
|    v                               |
|  Execute each tool call            |
|    |                               |
|    v                               |
|  Append tool results to messages   |
+----+------------------------------+
     |
     v
  Final response text
```

**Features:**
- Multi-turn tool calling with proper message threading
- Token budget management (estimated at 4 chars per token)
- Automatic context compression (keeps system prompt + last 4 messages, summarizes the rest)
- Streaming support via `run_streaming()`
- Graceful error handling for tool failures

**Defined in:** `src/jarvis/agents/conversation.py`

#### ContextBuilder

The `ContextBuilder` (`src/jarvis/agents/context.py`) assembles prompts with priority-based sections:

1. System prompt (agent identity)
2. Active constraints from the Streaming Spec
3. Relevant memory entries
4. Available tool descriptions

#### Middleware Chain

The middleware system (`src/jarvis/agents/middleware.py`) wraps agent execution with cross-cutting concerns:

```
MiddlewareChain
    |
    +--- LoggingMiddleware        (start/end times, message previews)
    +--- TracingMiddleware         (distributed trace spans)
    +--- MetricsMiddleware         (call counts, latency, success rates)
    +--- RateLimitMiddleware       (sliding-window rate limiting)
    +--- CachingMiddleware         (TTL-based result caching)
    +--- SecurityMiddleware        (agent allowlist, output redaction)
    +--- InputValidationMiddleware (length limits, control char stripping)
```

Before hooks run in insertion order; after hooks run in reverse order, creating a "wrap-around" pattern similar to HTTP middleware.

#### A2A Protocol Integration

The `src/jarvis/agents/a2a.py` module implements Agent-to-Agent protocol semantics, enabling:
- Agent discovery via `AgentCard`
- Task delegation between agents
- Message passing with structured types

---

### LLM Layer

#### Provider Abstraction

```
LLMProvider (ABC)  -- src/jarvis/llm/provider.py
    |
    +--- chat(messages, tools, temperature, max_tokens) -> LLMResponse
    +--- stream(messages, tools, temperature, max_tokens) -> AsyncIterator[StreamChunk]
    |
    +--- OpenAIProvider    (llm/openai_provider.py)   -- OpenAI API
    +--- AnthropicProvider (llm/anthropic_provider.py) -- Anthropic API
    +--- OllamaProvider    (llm/ollama_provider.py)    -- Ollama local models
    +--- MockProvider      (llm/mock_provider.py)      -- Deterministic fallback
```

**Key data types:**
- `Message` -- role (system/user/assistant/tool), content, tool_calls
- `ToolCall` -- id, name, arguments
- `ToolDefinition` -- name, description, JSON Schema parameters
- `LLMResponse` -- content, tool_calls, finish_reason, usage
- `StreamChunk` -- delta, tool_calls, finish_reason

#### LLMRegistry

The `LLMRegistry` (`src/jarvis/llm/registry.py`) manages provider registration and selection:
- Register multiple providers by name
- `get(name?)` returns the default or named provider
- Auto-detects available providers based on environment variables

#### Streaming Support

All providers implement `stream()` which yields `StreamChunk` objects. The `ConversationLoop.run_streaming()` method uses this for real-time token streaming to the user.

#### Token Budget Management

The `ConversationLoop` estimates tokens at 4 characters per token. When the estimated context exceeds `max_tokens_budget` (default: 100,000), it triggers `_compress_context()` which:
1. Preserves the system prompt
2. Keeps the last 4 messages
3. Summarizes older messages into a single condensed message

---

### Tool System

#### BaseTool -> ToolRegistry Pattern

```
BaseTool (ABC)  -- src/jarvis/tools/base.py
    |
    +--- name: str
    +--- description: str
    +--- parameters: dict[str, Any]  (JSON Schema)
    +--- execute(arguments) -> ToolResult
    +--- to_llm_definition() -> ToolDefinition

ToolRegistry  -- src/jarvis/tools/registry.py
    |
    +--- register(tool)
    +--- get(name) -> BaseTool | None
    +--- list_tools() -> list[BaseTool]
    +--- get_definitions() -> list[ToolDefinition]
    +--- execute(name, arguments) -> ToolResult
```

#### 43 Built-in Tools Across 15 Categories

| Category | Tools | Module |
|----------|-------|--------|
| Shell | `shell_execute` | `builtin/shell.py` |
| File I/O | `read_file`, `write_file` | `builtin/file_ops.py` |
| Directory | `list_directory`, `find_files` | `builtin/directory_ops.py` |
| Git | `git_status`, `git_diff`, `git_log` | `builtin/git_ops.py` |
| HTTP | `http_request`, `http_download` | `builtin/http_client.py` |
| JSON/YAML | `json_query`, `yaml_to_json` | `builtin/json_ops.py` |
| Text | `regex`, `text_summary`, `diff` | `builtin/text_processing.py` |
| System | `system_info`, `process_list` | `builtin/system_info.py` |
| Python | `python_execute` | `builtin/python_exec.py` |
| Web Search | `web_search` | `builtin/web_search.py` |
| Docker | `docker_list`, `docker_logs`, `docker_exec`, `docker_images` | `builtin/docker_ops.py` |
| Database | `sqlite_query`, `sqlite_schemas`, `csv_to_sqlite` | `builtin/database_ops.py` |
| Image | `image_info`, `image_resize`, `screenshot` | `builtin/image_ops.py` |
| Archive | `zip_create`, `zip_extract` | `builtin/archive_ops.py` |
| Network | `ping`, `dns_lookup`, `port_check` | `builtin/network_ops.py` |
| Math | `calculator`, `unit_convert` | `builtin/math_ops.py` |
| Encoding | `base64`, `hash`, `url_encode` | `builtin/encoding_ops.py` |
| DateTime | `datetime`, `date_calc` | `builtin/datetime_ops.py` |
| Template | `template` | `builtin/template_ops.py` |
| Clipboard | `clipboard` | `builtin/clipboard.py` |

All tools are registered in the global `tool_registry` singleton when `jarvis.tools.builtin` is imported (`src/jarvis/tools/builtin/__init__.py`).

#### MCP Client for External Tool Servers

The `src/jarvis/mcp/` module provides a Model Context Protocol client for connecting to external tool servers. The `MCPRegistry` (`src/jarvis/mcp/registry.py`) manages server connections and exposes their tools alongside built-in tools.

#### Safety: Blocklists and Sandbox Validation

Tool execution is gated by the `SandboxValidator` (`src/jarvis/security/sandbox.py`), which checks:
- Command blocklists (e.g., `rm -rf /`, `mkfs`, fork bombs)
- File path access rules (blocked paths like `/etc/shadow`, `~/.ssh`)
- Network access permissions
- Execution time limits (default: 300 seconds)
- File size limits (default: 100 MB)

---

### Skill Evolution

#### Spec -> Skill Distillation

When a Streaming Spec completes successfully, the `SkillEvolver` (`src/jarvis/skills/evolve.py`) can distill it into a reusable `Skill`:

```
Completed StreamingSpec
        |
        v
SkillEvolver.distill_from_spec(spec)
        |
        +-- LLM available? --> _distill_with_llm()
        |       |                  |
        |       |                  +-- Prompt LLM to generalize steps
        |       |                  +-- Parse structured response
        |       |
        +-- No LLM? --> _distill_heuristic()
                |
                +-- Copy steps directly
                +-- Copy active constraints
                +-- Generate safe slug name
        |
        v
  Skill(status=DRAFT, parent_spec_id=spec.id)
        |
        v
  SkillRegistry.register(skill)
```

#### Execution Recording and Stats

Every time a skill is used, a `SkillExecution` record is appended:
- `input_context`, `output`, `success`, `duration_ms`, `feedback`, `score`

Rolling statistics are maintained: `use_count`, `success_rate`, `avg_score`, `last_used_at`.

#### should_evolve() Triggers

Evolution is triggered when a skill has >= 3 executions **and** at least one of:
- `success_rate < 0.8`
- `avg_score < 0.7`
- Downward trend in the last 3 quality scores

#### Version Bumping

Improved skills get a semantic version bump (minor version increment):
- `1.0.0` -> `1.1.0`
- `2.3.1` -> `2.4.0`

The new skill is a separate entity linked via `parent_skill_id`.

#### Curator Review Gate

The `Curator` (`src/jarvis/curator/engine.py`) reviews skill quality before activation:
- Accuracy, completeness, safety, and constraint compliance checks
- Hallucination risk detection
- Quality trend tracking
- Skills must pass review to be promoted from `DRAFT` to `ACTIVE`

---

### Gateway

#### Channel Abstraction

```
Channel (ABC)  -- src/jarvis/gateway/channel.py
    |
    +--- ChannelConfig (name, type, enabled, api_token, webhook_url)
    +--- ChannelMessage (normalized message format)
    +--- start() / stop()
    +--- send(channel_id, content)
    +--- handle_incoming(message) -> str
```

#### Channel Implementations

| Channel | Type | Module |
|---------|------|--------|
| CLI | `cli` | `gateway/channels/cli_channel.py` |
| Webhook | `webhook` | `gateway/channels/webhook_channel.py` |
| Telegram | `telegram` | `gateway/channels/telegram_channel.py` |
| Discord | `discord` | `gateway/channels/discord_channel.py` |
| DingTalk | `dingtalk` | `gateway/channels/dingtalk_channel.py` |

#### Message Normalization

All channels convert platform-specific messages into a unified `ChannelMessage`:

```python
ChannelMessage(
    id="abc123",
    channel_type=ChannelType.TELEGRAM,
    sender_id="user123",
    sender_name="Alice",
    content="Review my PR",
    message_type=MessageType.TEXT,
    timestamp=datetime.now(timezone.utc),
    metadata={},
    attachments=[],
)
```

Supported message types: `text`, `image`, `file`, `audio`, `command`, `system`.

#### Rate Limiting

The `Gateway` (`src/jarvis/gateway/gateway.py`) implements per-sender rate limiting:
- Sliding window: 60 seconds
- Maximum: 30 messages per window
- Exceeding the limit returns an error message without processing

---

### Security

#### Permission System

```
PermissionLevel: NONE < READ < WRITE < EXECUTE < ADMIN

AuthContext:
    user_id, session_id, permissions[], is_admin, channel

Permission:
    resource (filesystem, shell, network, llm)
    level (read, write, execute, admin)
    scope (e.g., "/tmp/*", "localhost:*")
    granted_by, granted_at, expires_at
```

Permission checks follow a hierarchy: a `WRITE` permission on a resource implicitly grants `READ`. Admin users bypass all checks.

**Defined in:** `src/jarvis/security/permissions.py`

#### Sandbox Modes

| Mode | Behavior |
|------|----------|
| `none` | No restrictions (development only) |
| `basic` | Blocklist dangerous commands (default) |
| `strict` | Allowlist only safe commands |
| `docker` | Run in Docker container |

**Defined in:** `src/jarvis/security/sandbox.py`

#### Secret Scanning and Redaction

The `SecurityManager` (`src/jarvis/security/manager.py`) scans all outputs for:
- API keys (generic, OpenAI `sk-*`, GitHub `ghp_*`)
- Passwords, tokens, secrets
- Bearer tokens
- Private keys (RSA, EC)

Detected secrets are replaced with `[REDACTED]` before being returned to the user.

#### Audit Logging

Every permission check is recorded in an audit log with:
- Action type
- User ID
- Resource
- Permission level
- Allowed/denied
- Timestamp

**Defined in:** `src/jarvis/logging/audit.py`

---

### Storage

#### Store Abstraction

```
Store[T] (ABC, Generic)  -- src/jarvis/storage/base.py
    |
    +--- get(key) -> T | None
    +--- put(key, value) -> None
    +--- delete(key) -> bool
    +--- list_keys(prefix) -> list[str]
    +--- exists(key) -> bool
    +--- get_many(keys), put_many(items), count(prefix)
    |
    +--- JSONStore     (storage/json_store.py)   -- one JSON file per key
    +--- SQLiteStore   (storage/sqlite_store.py) -- SQLite database
    +--- MemoryStore   (storage/memory_store.py) -- in-memory dict
```

#### KeyValueStore Facade

The `KeyValueStore` (`src/jarvis/storage/kv.py`) provides a simplified API:

```python
kv = KeyValueStore(backend="json", base_path="~/.jarvis/data")
await kv.set("user:prefs", {"theme": "dark"})
prefs = await kv.get("user:prefs")
```

Backend selection: `json` (default), `sqlite`, `memory`.

#### Atomic Writes

The `JSONStore` writes to a temporary file first, then atomically renames it to the target path, preventing data corruption on crashes.

---

### Observability

#### Distributed Tracing

The `Tracer` (`src/jarvis/observability/tracer.py`) follows OpenTelemetry span semantics:

```
Trace (trace_id)
    |
    +--- Span: "orchestrator.route" (12ms)
    |       +--- agent_name: "code-agent"
    |
    +--- Span: "agent.execute" (450ms)
    |       +--- Span: "llm.chat" (320ms)
    |       |       +--- model: "gpt-4o-mini"
    |       |       +--- tokens: 1200
    |       |
    |       +--- Span: "tool.execute" (80ms)
    |               +--- tool: "read_file"
    |
    +--- Span: "agent.execute" (200ms)  [parallel]
```

Features:
- Hierarchical spans with parent-child relationships
- Async context manager: `async with tracer.trace_operation(...)`
- Per-trace JSON persistence
- Global `tracer` singleton

#### Metrics

The `metrics` module (`src/jarvis/observability/metrics.py`) provides:
- **Counters** -- monotonically increasing values
- **Histograms** -- distribution tracking with percentiles (p50, p95, p99)
- **Gauges** -- current value tracking
- Snapshot export for the `/metrics` API endpoint

#### System Diagnostics

The `SystemDiagnostics` (`src/jarvis/diagnostics/health.py`) checks:
- Python version and dependencies
- LLM provider availability
- Storage backend health
- Memory usage
- Agent registration status

#### Benchmarks

The `BenchmarkSuite` (`src/jarvis/benchmarks/suite.py`) measures:
- Agent routing latency
- Tool execution throughput
- Spec creation and execution time
- Memory and knowledge graph operations

---

### Event System

#### EventBus

The `EventBus` (`src/jarvis/events/bus.py`) provides decoupled communication:

```python
bus = EventBus()

# Subscribe
sub_id = bus.subscribe(
    handler=my_handler,
    topics=["agent.*"],       # wildcard matching
    min_priority=EventPriority.HIGH,
)

# Publish
await bus.publish(Event(
    topic="agent.executed",
    source="code-agent",
    priority=EventPriority.NORMAL,
    data={"duration_ms": 450},
))
```

#### Topic-Based Routing with Wildcards

- Exact match: `"agent.executed"` matches only `"agent.executed"`
- Wildcard: `"agent.*"` matches `"agent.executed"`, `"agent.failed"`, etc.
- Global: `"*"` matches everything

#### Features

- **Priority ordering** -- `LOW(0)`, `NORMAL(5)`, `HIGH(10)`, `CRITICAL(15)`
- **Event filtering** -- by topic, source, and minimum priority
- **One-shot subscriptions** -- auto-unsubscribe after first delivery
- **Event history** -- configurable in-memory history (default: 1000 events)
- **Replay** -- replay stored events through a handler
- **Dead letter queue** -- failed handler deliveries are captured for debugging
- **Middleware** -- transform or drop events before delivery
- **Event persistence** -- `EventStore` writes to JSON-lines files partitioned by day

---

## Data Flow Examples

### Chat Request

```
User types: "Review the code in src/"
     |
     v
Gateway._handle_message(ChannelMessage)
     |
     +-- Rate limit check (pass)
     +-- Message logging
     |
     v
Orchestrator.handle("Review the code in src/")
     |
     +-- AgentRegistry.route("Review the code in src/")
     |     |
     |     +-- code-agent.can_handle() -> 0.67  (matches: "code", "review")
     |     +-- security-agent.can_handle() -> 0.33
     |     +-- knowledge-agent.can_handle() -> 0.17
     |
     v
CodeAgent.run(message, context)
     |
     v
CodeAgent._llm_execute(message, context)
     |
     v
ConversationLoop.run(message)
     |
     +-- Turn 1: LLM returns tool_call: read_file("src/")
     +-- Execute: ToolRegistry.execute("read_file", {"path": "src/"})
     +-- Turn 2: LLM returns tool_call: read_file("src/main.py")
     +-- Execute: ToolRegistry.execute("read_file", {"path": "src/main.py"})
     +-- Turn 3: LLM returns final review text (no tool calls)
     |
     v
TaskResult(success=True, output="Code review: ...")
     |
     v
Response sent back to user via Gateway
```

### Spec Execution

```
User: "Build a REST API for user management"
     |
     v
SpecEngine.create("Build a REST API for user management")
     |
     +-- LLM decomposition (or fallback to 4 default steps)
     |
     v
StreamingSpec(id="abc123", status=EXECUTING, steps=[
    Step(id="s1", name="Design API schema", depends_on=[]),
    Step(id="s2", name="Set up FastAPI project", depends_on=[]),
    Step(id="s3", name="Implement endpoints", depends_on=["s1", "s2"]),
    Step(id="s4", name="Add authentication", depends_on=["s3"]),
    Step(id="s5", name="Write tests", depends_on=["s3"]),
    Step(id="s6", name="Deploy", depends_on=["s4", "s5"]),
])
     |
     v
SpecExecutor.execute_spec("abc123")
     |
     +-- Wave 1: s1 + s2 (parallel, no dependencies)
     |     |
     |     +-- User adds constraint: "Use PostgreSQL"
     |     |     Replanner identifies s3 as affected
     |     |
     +-- Wave 2: s3 (depends on s1, s2 -- both completed)
     |     |
     +-- Wave 3: s4 + s5 (parallel, both depend only on s3)
     |     |
     +-- Wave 4: s6 (depends on s4, s5)
     |
     v
SpecStatus.COMPLETED
```

### Skill Evolution

```
Spec "Build REST API" completed
     |
     v
SkillEvolver.distill_from_spec(spec)
     |
     +-- Extract reusable pattern from steps
     +-- Identify permanent constraints
     +-- Generate system prompt
     |
     v
Skill(name="build-rest-api", version="1.0.0", status=DRAFT)
     |
     v
Curator.review() --> PASS --> Skill status -> ACTIVE
     |
     v
[User requests similar task]
     |
     +-- SkillRegistry matches "Build a REST API for ..."
     +-- Skill executed, SkillExecution recorded
     +-- After 3 executions with success_rate < 0.8
     |
     v
SkillEvolver.should_evolve(skill) -> True
     |
     v
SkillEvolver.improve_skill(skill)
     |
     +-- Analyze failures and low scores
     +-- Generate improved steps/constraints
     |
     v
Skill(name="build-rest-api", version="1.1.0", status=DRAFT)
     |
     v
Curator.review() --> PASS --> ACTIVE
(old version deprecated)
```

---

## Deployment

### Local Development

```bash
# Prerequisites: Python 3.11+, uv
git clone <repo-url> jarvis && cd jarvis
uv sync                          # install deps into .venv
cp .env.example .env             # configure API keys (optional)
make run                         # start FastAPI server on :8000
make demo                        # run interactive demo
make test                        # run full test suite
```

### Docker Compose

Three profiles are available:

```bash
# Core JARVIS only
docker compose up -d

# + Redis + PostgreSQL
docker compose --profile full up -d

# + Ollama (local LLM inference)
docker compose --profile local-llm up -d

# Everything
docker compose --profile full --profile local-llm up -d
```

### Production Considerations

- Set `JARVIS_SANDBOX_MODE=strict` for production environments
- Enable `JARVIS_SECRET_SCANNING=true` (default)
- Configure proper LLM API keys via environment variables
- Use the `full` Docker Compose profile for Redis caching and PostgreSQL persistence
- Monitor the `/health`, `/metrics`, and `/traces` endpoints
- Set up log aggregation from structured JSON logs (`JARVIS_LOG_FORMAT=json`)
- Configure rate limits appropriate for your user base
- Review and restrict CORS origins in `jarvis.yaml`
