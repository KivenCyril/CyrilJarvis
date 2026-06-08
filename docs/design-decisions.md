# Architecture Decision Records

This document records the key architectural decisions made during the design and development of JARVIS. Each decision follows the ADR (Architecture Decision Record) format.

---

## ADR-001: Streaming Spec as Core Abstraction

**Status:** Accepted

**Context:**
Traditional AI assistants treat tasks as fire-and-forget: the user sends a request, and the system returns a result. This model breaks down for complex, multi-step tasks where the user needs visibility into progress, the ability to add constraints mid-execution, and the option to redirect the task if the initial approach is wrong.

Existing frameworks (OpenClaw, Hermes) use static task descriptions. Once a task is dispatched, the user has no way to interact with it until it completes or fails.

**Decision:**
Introduce the **Streaming Spec** as the central abstraction. A Streaming Spec is a living, editable document that decomposes user intent into a DAG of steps. It can be inspected, modified, and redirected while execution is in progress. Every mutation (human or agent) is recorded in an immutable changelog.

**Consequences:**
- (+) Users get a real-time "control panel" for complex tasks
- (+) Human-in-the-loop editing enables course correction without restarting
- (+) Full audit trail enables debugging, learning, and skill distillation
- (+) DAG structure enables parallel execution
- (-) Higher complexity than simple request/response
- (-) Concurrent editing requires careful state management (version field acts as optimistic lock)

**Implementation:** `src/jarvis/models/streaming_spec.py`

---

## ADR-002: DAG-Based Parallel Execution

**Status:** Accepted

**Context:**
Sequential step execution wastes time when steps are independent. For example, "Design API schema" and "Set up project structure" can run in parallel since neither depends on the other.

**Decision:**
Model step dependencies as a Directed Acyclic Graph (DAG). The executor identifies steps whose dependencies are all satisfied and runs them concurrently using `asyncio.gather`. After each "wave" of parallel execution completes, the executor recomputes readiness and launches the next wave.

**Algorithm:**
1. Compute `READY` steps (all `depends_on` satisfied)
2. Execute ready steps in parallel via `asyncio.gather`
3. Mark completed/failed
4. Recompute readiness
5. Repeat until all steps are terminal

**Consequences:**
- (+) Significant speedup for tasks with independent sub-steps
- (+) Topological sort and critical path analysis are naturally supported
- (+) The DAG is validated for cycles (`validate_dag()`) before execution
- (+) Re-fetch between waves enables human-in-the-loop edits
- (-) Debugging parallel failures is harder than sequential
- (-) Resource contention if too many steps run concurrently (mitigated by agent `max_concurrent`)

**Implementation:** `src/jarvis/engine/executor.py`, `src/jarvis/models/streaming_spec.py`

---

## ADR-003: Multi-Provider LLM Abstraction

**Status:** Accepted

**Context:**
AI capabilities evolve rapidly. Locking into a single LLM provider (e.g., OpenAI) limits flexibility and creates vendor risk. Different tasks may benefit from different models (e.g., a fast model for routing, a powerful model for code generation).

**Decision:**
Define an abstract `LLMProvider` interface with `chat()` and `stream()` methods. Implement concrete providers for OpenAI, Anthropic, Ollama (local), and a `MockProvider` for testing. A `LLMRegistry` manages provider registration and selection.

**Consequences:**
- (+) Switch providers by changing an environment variable
- (+) Run locally with Ollama (no API costs)
- (+) Test without any API keys using MockProvider
- (+) Future providers (DeepSeek, etc.) are trivial to add
- (-) Lowest-common-denominator API may not expose provider-specific features
- (-) Provider-specific prompt optimization may be needed

**Implementation:** `src/jarvis/llm/provider.py`, `src/jarvis/llm/registry.py`

---

## ADR-004: Registry Pattern for Extensibility

**Status:** Accepted

**Context:**
JARVIS has many extensible components: agents, tools, skills, LLM providers, storage backends, channels. Each category needs discovery, registration, and lookup mechanisms.

**Decision:**
Use the **Registry pattern** consistently across all extensible components:

| Registry | Registers | Module |
|----------|-----------|--------|
| `AgentRegistry` | `BaseAgent` implementations | `agents/registry.py` |
| `ToolRegistry` | `BaseTool` implementations | `tools/registry.py` |
| `SkillRegistry` | `Skill` instances | `skills/registry.py` |
| `LLMRegistry` | `LLMProvider` implementations | `llm/registry.py` |

Each registry provides: `register()`, `get(name)`, `list_*()`. Tool and agent registries use auto-registration on import (importing `tools.builtin` registers all tools).

**Consequences:**
- (+) Consistent API across all component types
- (+) Adding a new agent/tool/skill is a two-step process: implement + register
- (+) Enables runtime discovery and dynamic loading
- (+) Singleton registries (`tool_registry`) simplify dependency injection
- (-) Global singletons can complicate testing (mitigated by creating fresh instances in tests)

**Implementation:** `src/jarvis/agents/registry.py`, `src/jarvis/tools/registry.py`, `src/jarvis/skills/registry.py`

---

## ADR-005: Graceful Degradation (Mock Fallback)

**Status:** Accepted

**Context:**
JARVIS uses LLMs for task decomposition, knowledge extraction, memory scoring, curator review, skill matching, and agent execution. Requiring API keys for basic functionality would be a barrier to development and testing.

**Decision:**
Every LLM-powered feature has a deterministic fallback that activates when no LLM is available:

| Feature | LLM Mode | Fallback Mode |
|---------|----------|---------------|
| Spec decomposition | AI-generated step breakdown | 4 fixed steps (analyze, plan, execute, verify) |
| Knowledge extraction | LLM entity/relation extraction | Regex-based entity detection |
| Memory importance | LLM scoring (0.0-1.0) | Heuristic: keyword density + length |
| Curator review | LLM quality assessment | Rule-based scoring |
| Skill distillation | LLM generalization | Direct step copying |
| Skill evolution | LLM-driven improvement | Add error-handling constraints from failures |
| Agent execution | Full conversation loop | Direct response synthesis |

**Consequences:**
- (+) System is fully functional without API keys
- (+) Tests run without external dependencies
- (+) Demos work out of the box
- (+) Development workflow is unblocked by API quotas
- (-) Fallback quality is lower than LLM-powered mode
- (-) Must maintain two code paths for each feature

**Implementation:** Pattern is pervasive; see `SpecEngine._add_fallback_steps()`, `SkillEvolver._distill_heuristic()`, etc.

---

## ADR-006: Event-Driven Architecture

**Status:** Accepted

**Context:**
As JARVIS grows, modules need to communicate without tight coupling. For example, when a spec completes, the skill evolver might want to distill it, the session manager might want to log it, and the metrics system might want to record it. Hard-wiring these dependencies creates a maintenance burden.

**Decision:**
Implement a central `EventBus` with topic-based pub/sub:

- **Topics** use dot-separated namespaces: `agent.executed`, `spec.created`, `tool.called`
- **Wildcards** enable pattern subscriptions: `agent.*` matches all agent events
- **Priority** levels control delivery order: LOW, NORMAL, HIGH, CRITICAL
- **Dead letter queue** captures handler failures for debugging
- **Middleware** can transform or drop events before delivery
- **EventStore** persists events to JSON-lines files for replay and auditing

**Consequences:**
- (+) Modules are decoupled -- the spec engine does not need to know about skill evolution
- (+) New subscribers can be added without modifying the publisher
- (+) Event replay enables debugging and post-hoc analysis
- (+) Middleware enables cross-cutting concerns (logging, filtering)
- (-) Harder to trace control flow (event-driven indirection)
- (-) Event ordering guarantees are limited (within a single bus, events are delivered in subscription order)

**Implementation:** `src/jarvis/events/bus.py`

---

## ADR-007: Security-First Tool Execution

**Status:** Accepted

**Context:**
Agents execute tools that interact with the filesystem, shell, network, and databases. An LLM-generated tool call could be destructive (e.g., `rm -rf /`) or leak secrets (e.g., printing API keys in output).

**Decision:**
Implement a multi-layered security model:

1. **Sandbox modes** (none, basic, strict, docker) gate which commands can run
2. **Blocklist** of dangerous commands (`rm -rf /`, `mkfs`, fork bombs, etc.)
3. **Allowlist** in strict mode -- only whitelisted commands are permitted
4. **Path restrictions** -- blocked paths (`/etc/shadow`, `~/.ssh`) and allowed paths (`/tmp`, `.`)
5. **Secret scanning** -- regex patterns detect API keys, tokens, passwords, private keys
6. **Secret redaction** -- detected secrets are replaced with `[REDACTED]`
7. **Audit logging** -- every permission check is recorded with user, resource, level, and outcome
8. **Execution limits** -- max execution time (300s), max file size (100MB)

**Consequences:**
- (+) Defense in depth -- multiple independent checks
- (+) Configurable via `SandboxConfig` -- can be relaxed for development
- (+) Secret redaction prevents accidental leakage in logs and UI
- (+) Audit trail for compliance and forensics
- (-) False positives in secret scanning may redact legitimate content
- (-) Strict mode may block valid tool calls (requires allowlist maintenance)

**Implementation:** `src/jarvis/security/sandbox.py`, `src/jarvis/security/manager.py`, `src/jarvis/security/permissions.py`

---

## ADR-008: Self-Evolving Skills

**Status:** Accepted

**Context:**
Every time a user asks JARVIS to perform a similar task, the system starts from scratch. There is no mechanism to learn from past successes or failures. The Hermes project pioneered "procedural memory" but did not implement it fully.

**Decision:**
Implement a skill evolution loop:

```
Streaming Spec completed
    -> SkillEvolver.distill_from_spec(spec) -> Skill v1.0.0 (DRAFT)
    -> Curator.review() -> Skill v1.0.0 (ACTIVE)
    -> Execute skill 3+ times
    -> should_evolve()? -> success_rate < 0.8 or avg_score < 0.7 or downward trend
    -> SkillEvolver.improve_skill(skill) -> Skill v1.1.0 (DRAFT)
    -> Curator.review() -> Skill v1.1.0 (ACTIVE), v1.0.0 (DEPRECATED)
```

Evolution triggers:
- Minimum 3 executions recorded
- Success rate below 80%
- Average quality score below 0.7
- Downward trend in the last 3 scores

**Consequences:**
- (+) JARVIS gets better at tasks it has done before
- (+) Skills are versioned with full audit trail
- (+) YAML persistence enables sharing via skill marketplace
- (+) Curator gate prevents bad skills from being promoted
- (-) Evolution requires sufficient execution data (cold start problem)
- (-) LLM-driven improvement may introduce regressions (mitigated by curator review)
- (-) Storage grows over time with execution history

**Implementation:** `src/jarvis/skills/evolve.py`, `src/jarvis/skills/base.py`

---

## ADR-009: Plugin System for Extensibility

**Status:** Accepted

**Context:**
Some capabilities do not belong in the core JARVIS distribution. Third-party integrations (Jira, GitHub, Slack, Google Calendar) should be pluggable without modifying core code.

**Decision:**
Implement a plugin system with:
- `BasePlugin` abstract class defining the plugin lifecycle (`initialize`, `shutdown`)
- `PluginManager` for discovery, loading, and lifecycle management
- Integration modules (`src/jarvis/integrations/`) for common services
- Plugins can register agents, tools, and channels at initialization time

**Consequences:**
- (+) Core stays lean -- integrations are opt-in
- (+) Third parties can build JARVIS plugins
- (+) Plugin lifecycle is managed centrally
- (-) Plugin API must be stable (breaking changes affect third parties)
- (-) Plugin isolation is not enforced (a bad plugin can crash the system)

**Implementation:** `src/jarvis/plugins/base.py`, `src/jarvis/plugins/manager.py`, `src/jarvis/integrations/`

---

## ADR-010: Gateway for Multi-Channel Support

**Status:** Accepted

**Context:**
JARVIS needs to be accessible from multiple platforms: CLI, web UI, Telegram, Discord, DingTalk, and webhooks. Each platform has different message formats, authentication, and delivery mechanisms. Without a unifying abstraction, each channel would need its own integration with the orchestrator.

**Decision:**
Implement a `Gateway` layer that:
1. Defines an abstract `Channel` interface with `start()`, `stop()`, `send()`, and `handle_incoming()`
2. Normalizes all messages into a platform-agnostic `ChannelMessage` model
3. Routes normalized messages to the orchestrator
4. Converts responses back to platform-specific format
5. Applies per-sender rate limiting at the gateway level

The `ChannelMessage` model captures:
- Channel type and ID
- Sender identity
- Content and message type (text, image, file, audio, command)
- Attachments, threading, and platform metadata

**Consequences:**
- (+) Adding a new channel is a single class implementation
- (+) Core JARVIS code does not depend on any specific platform
- (+) Rate limiting is applied uniformly across all channels
- (+) Message logging and analytics work across all channels
- (-) Platform-specific features (reactions, threads, rich embeds) require escape hatches via `metadata`
- (-) Some platforms require long-running connections (WebSocket, polling) which complicate deployment

**Implementation:** `src/jarvis/gateway/channel.py`, `src/jarvis/gateway/gateway.py`, `src/jarvis/gateway/channels/`
