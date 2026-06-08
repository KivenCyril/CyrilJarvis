# JARVIS API Reference

> Version 0.2.0 | Base URL: `http://localhost:8000`

## Table of Contents

1. [Overview](#overview)
2. [Authentication](#authentication)
3. [Health](#health)
4. [Chat](#chat)
5. [Agents](#agents)
6. [Streaming Specs](#streaming-specs)
7. [Skills](#skills)
8. [Memory](#memory)
9. [Knowledge Graph](#knowledge-graph)
10. [Curator](#curator)
11. [Sessions](#sessions)
12. [Tools](#tools)
13. [MCP](#mcp)
14. [Observability](#observability)
15. [System](#system)
16. [WebSocket Protocol](#websocket-protocol)
17. [Server-Sent Events (SSE)](#server-sent-events)

---

## Overview

The JARVIS API is a RESTful HTTP API built with FastAPI. All endpoints return JSON. Real-time spec updates are available via WebSocket and Server-Sent Events (SSE).

**Server:** `src/jarvis/server/app.py`

**CORS:** All origins allowed by default. Configure `cors_origins` in `jarvis.yaml` for production.

---

## Authentication

Currently, the API does not enforce authentication. All endpoints are open. For production deployment, add an API key or OAuth2 middleware.

---

## Health

### GET /health

Health check endpoint.

**Response:**

```json
{
  "status": "ok",
  "agents": 10,
  "specs": 2,
  "agent_specs": 5
}
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Always `"ok"` if the server is running |
| `agents` | int | Number of registered agents |
| `specs` | int | Number of active Streaming Specs |
| `agent_specs` | int | Number of YAML agent spec templates |

---

## Chat

### POST /chat

Send a message to JARVIS. The orchestrator routes it to the best agent.

**Request body:**

```json
{
  "message": "Review the code in src/"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | The user's message |

**Response:**

```json
{
  "success": true,
  "agent": "code-agent",
  "output": "Here is my code review...",
  "error": null
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | bool | Whether the request was handled successfully |
| `agent` | string | Name of the agent that handled the request |
| `output` | string | The agent's response |
| `error` | string | null | Error message if `success` is false |

---

## Agents

### GET /agents

List all registered agents.

**Response:**

```json
[
  {
    "name": "code-agent",
    "description": "Handles code-related tasks",
    "skills": ["code", "review", "git", "debug", "test"],
    "domain": "development",
    "status": "idle"
  }
]
```

### GET /agents/{name}

Get details for a specific agent.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `name` | string | Agent name (e.g., `code-agent`) |

**Response:**

```json
{
  "name": "code-agent",
  "description": "Handles code-related tasks",
  "skills": ["code", "review", "git", "debug", "test"],
  "domain": "development",
  "status": "idle",
  "can_delegate": true,
  "version": "1.0"
}
```

**Errors:**

| Status | Description |
|--------|-------------|
| 404 | Agent not found |

---

## Streaming Specs

### POST /specs

Create a new Streaming Spec from a user intent.

**Request body:**

```json
{
  "intent": "Build a REST API for user management",
  "name": "User API Project"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `intent` | string | Yes | Natural language description of the task |
| `name` | string | No | Optional display name (defaults to first 50 chars of intent) |

**Response:** Full `StreamingSpec` JSON object.

```json
{
  "id": "a1b2c3d4e5f6",
  "name": "User API Project",
  "intent": "Build a REST API for user management",
  "status": "executing",
  "created_at": "2026-06-02T10:00:00Z",
  "updated_at": "2026-06-02T10:00:01Z",
  "constraints": [],
  "steps": [
    {
      "id": "s1a2b3c4",
      "name": "Design API schema",
      "status": "ready",
      "description": "Define endpoints and data models",
      "depends_on": [],
      "progress_pct": 0
    }
  ],
  "changelog": [...],
  "version": 5,
  "tags": [],
  "parent_spec_id": null
}
```

### GET /specs

List all Streaming Specs.

**Response:** Array of `StreamingSpec` objects.

### GET /specs/{spec_id}

Get a specific Streaming Spec.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `spec_id` | string | 12-character hex spec ID |

**Errors:**

| Status | Description |
|--------|-------------|
| 404 | Spec not found |

### POST /specs/{spec_id}/execute

Execute a Streaming Spec. Runs the DAG-aware parallel executor.

**Response:** Full `StreamingSpec` object with updated step statuses.

**Errors:**

| Status | Description |
|--------|-------------|
| 404 | Spec not found |

### POST /specs/{spec_id}/constraints

Add a constraint to a running spec (human-in-the-loop).

**Request body:**

```json
{
  "content": "Use PostgreSQL as the database"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | The constraint text |

**Response:** Updated `StreamingSpec` object.

### DELETE /specs/{spec_id}/constraints/{constraint_id}

Remove a constraint from a spec.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `spec_id` | string | Spec ID |
| `constraint_id` | string | 8-character hex constraint ID |

**Response:** Updated `StreamingSpec` object.

### PATCH /specs/{spec_id}/steps/{step_id}

Edit a step's name or description.

**Request body:**

```json
{
  "name": "Updated step name",
  "description": "Updated description"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | No | New step name |
| `description` | string | No | New step description |

**Response:** Updated `StreamingSpec` object.

### POST /specs/{spec_id}/steps/{step_id}/status

Update a step's status or output.

**Request body:**

```json
{
  "status": "completed",
  "output": "Step completed successfully"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `status` | string | No | New status: `pending`, `blocked`, `ready`, `executing`, `completed`, `failed`, `skipped`, `cancelled` |
| `output` | string | No | Step output text |

**Response:** Updated `StreamingSpec` object.

### POST /specs/{spec_id}/redirect

Redirect a spec to a new intent (replans while preserving completed steps).

**Request body:**

```json
{
  "new_intent": "Build a GraphQL API instead"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `new_intent` | string | Yes | The new intent |

**Response:** Updated `StreamingSpec` object with status `redirected`.

### GET /specs/{spec_id}/changelog

Get the full changelog for a spec.

**Response:**

```json
[
  {
    "timestamp": "2026-06-02T10:00:01Z",
    "source": "human",
    "change_type": "constraint_added",
    "path": "constraints.abc123",
    "old_value": null,
    "new_value": "Use PostgreSQL"
  }
]
```

### GET /specs/{spec_id}/stream

Stream spec events via Server-Sent Events (SSE).

See [Server-Sent Events](#server-sent-events) section.

---

## Agent Specs

### GET /agent-specs

List all static YAML agent spec templates.

**Response:** Array of agent spec objects loaded from the `specs/` directory.

---

## Delegations

### GET /delegations

Get the orchestrator's delegation log.

**Response:**

```json
[
  {
    "parent": "orchestrator",
    "child": "code-agent",
    "task_id": "abc123",
    "message": "Review the code in src/",
    "success": true,
    "duration_ms": 450
  }
]
```

---

## Skills

### GET /skills

List all registered skills.

**Response:**

```json
[
  {
    "name": "build-rest-api",
    "version": "1.0.0",
    "description": "Build a REST API project",
    "domain": "",
    "tags": ["auto-distilled"],
    "status": "active",
    "use_count": 5,
    "success_rate": 0.8,
    "avg_score": 0.75
  }
]
```

### GET /skills/{name}

Get full details for a specific skill.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `name` | string | Skill name |

**Response:** Full `Skill` JSON object including steps, constraints, and metadata.

**Errors:**

| Status | Description |
|--------|-------------|
| 404 | Skill not found or skill registry not initialized |

---

## Memory

### POST /memory

Add a memory entry.

**Request body:**

```json
{
  "content": "User prefers dark mode",
  "memory_type": "preference",
  "metadata": {"source": "settings"}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `content` | string | Yes | Memory content |
| `memory_type` | string | No | One of: `conversation`, `fact`, `preference`, `skill_learned`, `spec_history`. Default: `fact` |
| `metadata` | object | No | Additional metadata |

**Response:** Memory entry object.

### POST /memory/search

Search memory by query.

**Request body:**

```json
{
  "query": "dark mode",
  "limit": 5,
  "memory_type": "preference"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `query` | string | Yes | Search query |
| `limit` | int | No | Max results (default: 5) |
| `memory_type` | string | No | Filter by memory type |

**Response:** Array of memory entry objects sorted by relevance.

### GET /memory

List all memory entries.

**Response:** Array of memory entry objects.

---

## Knowledge Graph

### GET /knowledge/stats

Get knowledge graph statistics.

**Response:**

```json
{
  "total_nodes": 42,
  "total_edges": 67,
  "node_types": {"person": 10, "concept": 20, "tool": 12}
}
```

### GET /knowledge/graph

Get the full knowledge graph in visualization format.

**Response:** Graph data structure with nodes and edges suitable for rendering.

### POST /knowledge/extract

Extract entities and relations from text using LLM or heuristic extraction.

**Request body:**

```json
{
  "text": "FastAPI is a Python web framework created by Sebastian Ramirez."
}
```

**Response:**

```json
{
  "extracted_nodes": 3,
  "nodes": [
    {"id": "n1", "label": "FastAPI", "type": "tool"},
    {"id": "n2", "label": "Python", "type": "language"},
    {"id": "n3", "label": "Sebastian Ramirez", "type": "person"}
  ]
}
```

### POST /knowledge/query

Query the knowledge graph.

**Request body:**

```json
{
  "query": "FastAPI",
  "limit": 5
}
```

**Response:** Array of matching nodes with properties.

---

## Curator

### POST /curator/review

Submit output for quality review.

**Request body:**

```json
{
  "request": "Write a Python function to sort a list",
  "output": "def sort_list(lst): return sorted(lst)",
  "constraints": ["Must handle empty lists", "Must be O(n log n)"]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `request` | string | Yes | The original request |
| `output` | string | Yes | The output to review |
| `constraints` | list[string] | No | Constraints to check against |

**Response:** Review result with quality scores.

### GET /curator/stats

Get curator statistics.

**Response:**

```json
{
  "review_count": 42,
  "avg_quality": 0.85,
  "quality_trend": [0.8, 0.82, 0.85],
  "flagged_count": 3
}
```

---

## Sessions

### GET /sessions

List all active sessions.

**Response:**

```json
[
  {
    "id": "sess_abc123",
    "state": "active",
    "user_id": "default",
    "channel": "web",
    "message_count": 15,
    "agents_used": ["code-agent", "knowledge-agent"],
    "created_at": "2026-06-02T09:00:00Z",
    "updated_at": "2026-06-02T10:30:00Z"
  }
]
```

### GET /sessions/metrics

Get aggregated session metrics.

**Response:** Session metrics object with counts, averages, and breakdowns.

---

## Tools

### GET /tools

List all registered tools.

**Response:**

```json
[
  {
    "name": "shell_execute",
    "description": "Execute a shell command",
    "parameters": {
      "type": "object",
      "properties": {
        "command": {"type": "string", "description": "The command to execute"},
        "timeout": {"type": "integer", "description": "Timeout in seconds"}
      },
      "required": ["command"]
    }
  }
]
```

---

## MCP

### GET /mcp/servers

List connected MCP (Model Context Protocol) servers.

**Response:** Array of server info objects (empty if no MCP servers are configured).

---

## Observability

### GET /metrics

Get system metrics snapshot.

**Response:**

```json
{
  "counters": {
    "agent.calls": 42,
    "tool.executions": 120
  },
  "histograms": {
    "agent.latency_ms": {
      "count": 42,
      "p50": 200,
      "p95": 800,
      "p99": 1500
    }
  },
  "gauges": {
    "active_specs": 2,
    "active_agents": 10
  }
}
```

### GET /traces

List recent traces.

**Response:**

```json
[
  {
    "trace_id": "abc123def456",
    "span_count": 5,
    "total_duration_ms": 1200.5,
    "root_operation": "chat",
    "status": "ok"
  }
]
```

### GET /traces/{trace_id}

Get all spans for a specific trace.

**Path parameters:**

| Param | Type | Description |
|-------|------|-------------|
| `trace_id` | string | 16-character hex trace ID |

**Response:**

```json
[
  {
    "trace_id": "abc123def456",
    "span_id": "span001",
    "parent_span_id": null,
    "operation": "orchestrator.handle",
    "service": "jarvis",
    "status": "ok",
    "duration_ms": 1200.5,
    "attributes": {"agent": "code-agent"},
    "events": []
  }
]
```

**Errors:**

| Status | Description |
|--------|-------------|
| 404 | Trace not found |

---

## System

### GET /system

Get comprehensive system information.

**Response:**

```json
{
  "app_name": "JARVIS",
  "version": "0.2.0",
  "agents": 10,
  "tools": 43,
  "active_specs": 2,
  "modules": {
    "agents": true,
    "tools": true,
    "skills": true,
    "memory": true,
    "knowledge_graph": true,
    "curator": true,
    "sessions": true,
    "mcp": false,
    "gateway": false
  }
}
```

---

## WebSocket Protocol

### WS /ws/specs/{spec_id}

Real-time bidirectional connection for Streaming Spec interaction.

**Connection:**

```
ws://localhost:8000/ws/specs/{spec_id}?client_id=my-client
```

| Param | Type | Description |
|-------|------|-------------|
| `spec_id` | string | Spec ID to connect to |
| `client_id` | string (query) | Client identifier (default: `"anonymous"`) |

**On connect:** The server sends an initial `spec_snapshot` message with the full spec state.

#### Client -> Server Messages

**Add constraint:**

```json
{
  "type": "add_constraint",
  "content": "Use PostgreSQL as the database"
}
```

**Remove constraint:**

```json
{
  "type": "remove_constraint",
  "constraint_id": "abc12345"
}
```

**Edit step:**

```json
{
  "type": "edit_step",
  "step_id": "s1a2b3c4",
  "name": "Updated step name",
  "description": "Updated description"
}
```

**Redirect spec:**

```json
{
  "type": "redirect",
  "new_intent": "Build a GraphQL API instead"
}
```

**Pause spec:**

```json
{
  "type": "pause"
}
```

**Resume spec:**

```json
{
  "type": "resume"
}
```

#### Server -> Client Messages

**Initial snapshot:**

```json
{
  "type": "spec_snapshot",
  "spec_id": "abc123",
  "data": { /* full StreamingSpec object */ }
}
```

**Acknowledgment (sent to the sender):**

```json
{
  "type": "ack",
  "data": {
    "action": "add_constraint",
    "spec": { /* updated StreamingSpec */ }
  }
}
```

**Broadcast events (sent to other clients):**

```json
{
  "type": "constraint_added",
  "spec_id": "abc123",
  "data": { /* updated StreamingSpec */ }
}
```

Event types: `constraint_added`, `constraint_removed`, `step_edited`, `step_updated`, `spec_redirected`, `spec_paused`, `spec_resumed`, `spec_created`, `spec_completed`.

**Error:**

```json
{
  "type": "error",
  "data": {
    "message": "content is required"
  }
}
```

---

## Server-Sent Events

### GET /specs/{spec_id}/stream

Stream real-time spec events via SSE.

**Headers:**

```
Accept: text/event-stream
```

**Event format:**

```
event: step_updated
data: {"event_type":"step_updated","spec_id":"abc123","data":{"step_id":"s1","status":"completed"},"timestamp":"2026-06-02T10:00:00Z"}

event: constraint_added
data: {"event_type":"constraint_added","spec_id":"abc123","data":{"constraint_id":"c1","content":"Use PostgreSQL"},"timestamp":"2026-06-02T10:00:01Z"}

event: spec_completed
data: {"event_type":"spec_completed","spec_id":"abc123","data":{},"timestamp":"2026-06-02T10:05:00Z"}
```

The stream ends when a `spec_completed` or `spec_redirected` event is received.

**Event types:**
- `spec_created` -- spec was created
- `step_updated` -- step status or output changed
- `constraint_added` -- constraint was added
- `constraint_removed` -- constraint was removed
- `step_edited` -- step name or description changed
- `dependency_added` -- dependency edge added
- `dependency_removed` -- dependency edge removed
- `spec_redirected` -- intent was changed (stream ends)
- `spec_completed` -- all steps completed (stream ends)

---

## Error Handling

All error responses follow this format:

```json
{
  "detail": "Error description"
}
```

| Status Code | Meaning |
|-------------|---------|
| 200 | Success |
| 404 | Resource not found |
| 422 | Validation error (invalid request body) |
| 500 | Internal server error |

---

## Rate Limiting

The Gateway layer enforces rate limiting:
- **Window:** 60 seconds
- **Maximum:** 30 messages per window per sender
- Applied at the channel level, not directly on HTTP endpoints

WebSocket connections are not rate-limited at the HTTP level but individual messages are processed sequentially.
