from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, WebSocket, Query, WebSocketDisconnect
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from jarvis.app import JarvisApp
from jarvis.models.streaming_spec import ChangeSource, SpecStatus, StepStatus
from jarvis.server.websocket import manager, ConnectionManager

jarvis = JarvisApp()


def _patch_spec_engine_emit(engine) -> None:
    """Monkey-patch SpecEngine._emit to also broadcast via WebSocket."""
    import asyncio
    original_emit = engine._emit

    def _emit_with_ws(spec_id: str, event_type: str, data: dict) -> None:
        original_emit(spec_id, event_type, data)
        # Schedule WebSocket broadcast (non-blocking)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                manager.broadcast(spec_id, {"type": event_type, "spec_id": spec_id, "data": data})
            )
        except RuntimeError:
            pass  # No running loop yet; skip WS broadcast

    engine._emit = _emit_with_ws


@asynccontextmanager
async def lifespan(_app: FastAPI):
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    await jarvis.initialize()
    _patch_spec_engine_emit(jarvis.spec_engine)
    yield
    await jarvis.shutdown()


app = FastAPI(
    title="JARVIS",
    description="Streaming Spec driven personal AI assistant",
    version="0.1.0",
    lifespan=lifespan,
)

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# --- Request models ---

class CreateSpecRequest(BaseModel):
    intent: str
    name: str | None = None


class AddConstraintRequest(BaseModel):
    content: str


class EditStepRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class RedirectRequest(BaseModel):
    new_intent: str


class UpdateStepRequest(BaseModel):
    status: str | None = None
    output: str | None = None


class ChatRequest(BaseModel):
    message: str
    agent: str | None = None


class RunSpecRequest(BaseModel):
    intent: str


# --- Health ---

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "agents": len(jarvis.registry),
        "specs": len(jarvis.spec_engine.list_specs()),
        "agent_specs": len(jarvis.spec_registry.list_specs()),
    }


# --- Chat (direct agent routing) ---

_CHAT_TIMEOUT = 30

@app.post("/chat")
async def chat(req: ChatRequest):
    import asyncio
    from jarvis.agents.base import AgentContext, TaskResult

    try:
        if req.agent and req.agent != "auto":
            agent = jarvis.registry.get(req.agent)
            if not agent:
                raise HTTPException(404, f"Agent '{req.agent}' not found")
            coro = agent.run(req.message)
        else:
            coro = jarvis.orchestrator.handle(req.message)

        result = await asyncio.wait_for(coro, timeout=_CHAT_TIMEOUT)
    except asyncio.TimeoutError:
        result = TaskResult(
            task_id="timeout",
            agent_name=req.agent or "orchestrator",
            success=False,
            error=f"Request timed out after {_CHAT_TIMEOUT}s",
        )

    return {
        "success": result.success,
        "agent": result.agent_name,
        "output": result.output,
        "error": result.error,
    }


# --- Agents ---

@app.get("/agents")
async def list_agents():
    return [
        {
            "name": a.name,
            "description": a.card.description,
            "skills": a.card.skills,
            "domain": a.card.domain,
            "status": a.status.value,
        }
        for a in jarvis.registry.list_agents()
    ]


@app.get("/agents/{name}")
async def get_agent(name: str):
    agent = jarvis.registry.get(name)
    if not agent:
        raise HTTPException(404, f"Agent '{name}' not found")
    return {
        "name": agent.name,
        "description": agent.card.description,
        "skills": agent.card.skills,
        "domain": agent.card.domain,
        "status": agent.status.value,
        "can_delegate": agent.card.can_delegate,
        "version": agent.card.version,
    }


# --- Streaming Specs ---

@app.post("/specs")
async def create_spec(req: CreateSpecRequest):
    spec = await jarvis.spec_engine.create(req.intent, req.name)
    return spec.model_dump(mode="json")


@app.get("/specs")
async def list_specs():
    return [s.model_dump(mode="json") for s in jarvis.spec_engine.list_specs()]


@app.get("/specs/{spec_id}")
async def get_spec(spec_id: str):
    spec = jarvis.spec_engine.get(spec_id)
    if not spec:
        raise HTTPException(404, f"Spec {spec_id} not found")
    return spec.model_dump(mode="json")


@app.get("/specs/{spec_id}/stream")
async def stream_spec(spec_id: str):
    if not jarvis.spec_engine.get(spec_id):
        raise HTTPException(404, f"Spec {spec_id} not found")

    async def event_generator():
        async for event in jarvis.spec_engine.stream(spec_id):
            yield {"event": event.event_type, "data": event.model_dump_json()}

    return EventSourceResponse(event_generator())


@app.post("/specs/{spec_id}/execute")
async def execute_spec(spec_id: str):
    result = await jarvis.executor.execute_spec(spec_id)
    if not result:
        raise HTTPException(404, f"Spec {spec_id} not found")
    return result.model_dump(mode="json")


@app.post("/specs/{spec_id}/constraints")
async def add_constraint(spec_id: str, req: AddConstraintRequest):
    spec = await jarvis.spec_engine.add_constraint(spec_id, req.content, source=ChangeSource.HUMAN)
    if not spec:
        raise HTTPException(404, f"Spec {spec_id} not found")
    return spec.model_dump(mode="json")


@app.delete("/specs/{spec_id}/constraints/{constraint_id}")
async def remove_constraint(spec_id: str, constraint_id: str):
    spec = await jarvis.spec_engine.remove_constraint(spec_id, constraint_id)
    if not spec:
        raise HTTPException(404, f"Spec {spec_id} not found")
    return spec.model_dump(mode="json")


@app.patch("/specs/{spec_id}/steps/{step_id}")
async def edit_step(spec_id: str, step_id: str, req: EditStepRequest):
    spec = await jarvis.spec_engine.edit_step(spec_id, step_id, name=req.name, description=req.description)
    if not spec:
        raise HTTPException(404, "Spec or step not found")
    return spec.model_dump(mode="json")


@app.post("/specs/{spec_id}/steps/{step_id}/status")
async def update_step_status(spec_id: str, step_id: str, req: UpdateStepRequest):
    status = StepStatus(req.status) if req.status else None
    spec = await jarvis.spec_engine.update_step(spec_id, step_id, status=status, output=req.output)
    if not spec:
        raise HTTPException(404, "Spec or step not found")
    return spec.model_dump(mode="json")


@app.post("/specs/{spec_id}/redirect")
async def redirect_spec(spec_id: str, req: RedirectRequest):
    spec = await jarvis.spec_engine.redirect(spec_id, req.new_intent)
    if not spec:
        raise HTTPException(404, f"Spec {spec_id} not found")
    return spec.model_dump(mode="json")


@app.get("/specs/{spec_id}/changelog")
async def get_changelog(spec_id: str):
    spec = jarvis.spec_engine.get(spec_id)
    if not spec:
        raise HTTPException(404, f"Spec {spec_id} not found")
    return [c.model_dump(mode="json") for c in spec.changelog]


# --- Static AgentSpecs ---

@app.get("/agent-specs")
async def list_agent_specs():
    return [s.model_dump(mode="json") for s in jarvis.spec_registry.list_specs()]


# --- Orchestrator ---

@app.get("/delegations")
async def get_delegations():
    return jarvis.orchestrator.get_delegation_log()


# --- WebSocket: Real-time Streaming Spec cockpit ---

@app.websocket("/ws/specs/{spec_id}")
async def ws_spec(websocket: WebSocket, spec_id: str, client_id: str = Query("anonymous")):
    spec = jarvis.spec_engine.get(spec_id)
    if not spec:
        await websocket.close(code=4004, reason=f"Spec {spec_id} not found")
        return

    conn = await manager.connect(websocket, spec_id, client_id)

    # Send current spec state as initial snapshot
    try:
        await conn.send({
            "type": "spec_snapshot",
            "spec_id": spec_id,
            "data": spec.model_dump(mode="json"),
        })
    except Exception:
        manager.disconnect(conn)
        return

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await conn.send({"type": "error", "data": {"message": "Invalid JSON"}})
                continue

            msg_type = msg.get("type", "")
            result_spec = None
            event_type = ""
            event_data: dict = {}

            if msg_type == "add_constraint":
                content = msg.get("content", "")
                if not content:
                    await conn.send({"type": "error", "data": {"message": "content is required"}})
                    continue
                result_spec = await jarvis.spec_engine.add_constraint(
                    spec_id, content, source=ChangeSource.HUMAN,
                )
                event_type = "constraint_added"
                event_data = {"content": content}

            elif msg_type == "remove_constraint":
                constraint_id = msg.get("constraint_id", "")
                if not constraint_id:
                    await conn.send({"type": "error", "data": {"message": "constraint_id is required"}})
                    continue
                result_spec = await jarvis.spec_engine.remove_constraint(
                    spec_id, constraint_id, source=ChangeSource.HUMAN,
                )
                event_type = "constraint_removed"
                event_data = {"constraint_id": constraint_id}

            elif msg_type == "edit_step":
                step_id = msg.get("step_id", "")
                if not step_id:
                    await conn.send({"type": "error", "data": {"message": "step_id is required"}})
                    continue
                result_spec = await jarvis.spec_engine.edit_step(
                    spec_id, step_id,
                    name=msg.get("name"),
                    description=msg.get("description"),
                )
                event_type = "step_edited"
                event_data = {"step_id": step_id}

            elif msg_type == "redirect":
                new_intent = msg.get("new_intent", "")
                if not new_intent:
                    await conn.send({"type": "error", "data": {"message": "new_intent is required"}})
                    continue
                result_spec = await jarvis.spec_engine.redirect(spec_id, new_intent)
                event_type = "spec_redirected"
                event_data = {"new_intent": new_intent}

            elif msg_type == "pause":
                spec = jarvis.spec_engine.get(spec_id)
                if spec:
                    spec.status = SpecStatus.PAUSED
                    result_spec = spec
                event_type = "spec_paused"
                event_data = {}

            elif msg_type == "resume":
                spec = jarvis.spec_engine.get(spec_id)
                if spec:
                    spec.status = SpecStatus.EXECUTING
                    result_spec = spec
                event_type = "spec_resumed"
                event_data = {}

            else:
                await conn.send({"type": "error", "data": {"message": f"Unknown message type: {msg_type}"}})
                continue

            if result_spec is None:
                await conn.send({"type": "error", "data": {"message": "Spec or resource not found"}})
                continue

            # Acknowledge to the sender
            await conn.send({
                "type": "ack",
                "data": {"action": msg_type, "spec": result_spec.model_dump(mode="json")},
            })

            # Broadcast to other connected clients
            await manager.broadcast(
                spec_id,
                {"type": event_type, "spec_id": spec_id, "data": result_spec.model_dump(mode="json")},
                exclude_client=client_id,
            )

    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(conn)


# --- Skills ---

@app.get("/skills")
async def list_skills():
    """List all registered skills."""
    from jarvis.skills import SkillRegistry
    registry = getattr(jarvis, '_skill_registry', None)
    if not registry:
        return []
    return [
        {
            "name": s.metadata.name,
            "version": s.metadata.version,
            "description": s.metadata.description,
            "domain": s.metadata.domain,
            "tags": s.metadata.tags,
            "status": s.status.value,
            "use_count": s.use_count,
            "success_rate": round(s.success_rate, 2),
            "avg_score": round(s.avg_score, 2),
        }
        for s in registry.list_skills()
    ]


@app.get("/skills/{name}")
async def get_skill(name: str):
    registry = getattr(jarvis, '_skill_registry', None)
    if not registry:
        raise HTTPException(404, "Skill registry not initialized")
    skill = registry.get(name)
    if not skill:
        raise HTTPException(404, f"Skill '{name}' not found")
    return skill.model_dump(mode="json")


# --- Memory ---

class AddMemoryRequest(BaseModel):
    content: str
    memory_type: str = "fact"
    metadata: dict = {}


class SearchMemoryRequest(BaseModel):
    query: str
    limit: int = 5
    memory_type: str | None = None


@app.post("/memory")
async def add_memory(req: AddMemoryRequest):
    from jarvis.memory import MemoryManager, MemoryType
    mm = getattr(jarvis, '_memory_manager', None)
    if not mm:
        mm = MemoryManager()
        jarvis._memory_manager = mm
    entry = await mm.add(req.content, MemoryType(req.memory_type), req.metadata)
    return entry.to_dict()


@app.post("/memory/search")
async def search_memory(req: SearchMemoryRequest):
    mm = getattr(jarvis, '_memory_manager', None)
    if not mm:
        return []
    from jarvis.memory import MemoryType
    mt = MemoryType(req.memory_type) if req.memory_type else None
    results = await mm.search(req.query, req.limit, mt)
    return [e.to_dict() for e in results]


@app.get("/memory")
async def list_memories():
    mm = getattr(jarvis, '_memory_manager', None)
    if not mm:
        return []
    return [e.to_dict() for e in mm.list_memories()]


# --- Knowledge Graph ---

class ExtractKnowledgeRequest(BaseModel):
    text: str


@app.get("/knowledge/stats")
async def knowledge_stats():
    return jarvis.knowledge_graph.stats


@app.get("/knowledge/graph")
async def knowledge_graph_viz():
    return jarvis.knowledge_graph.to_visualization()


@app.post("/knowledge/extract")
async def extract_knowledge(req: ExtractKnowledgeRequest):
    nodes = await jarvis.knowledge_graph.extract_from_text(req.text)
    return {"extracted_nodes": len(nodes), "nodes": [{"id": n.id, "label": n.label, "type": n.node_type} for n in nodes]}


@app.post("/knowledge/query")
async def query_knowledge(req: SearchMemoryRequest):
    nodes = await jarvis.knowledge_graph.query(req.query)
    return [{"id": n.id, "label": n.label, "type": n.node_type, "properties": n.properties} for n in nodes]


# --- Curator ---

class ReviewRequest(BaseModel):
    request: str
    output: str
    constraints: list[str] = []


@app.post("/curator/review")
async def curator_review(req: ReviewRequest):
    from jarvis.curator import Curator
    curator = getattr(jarvis, '_curator', None)
    if not curator:
        curator = Curator()
        jarvis._curator = curator
    result = await curator.review_output(req.request, req.output, req.constraints)
    return result.model_dump(mode="json")


@app.get("/curator/stats")
async def curator_stats():
    curator = getattr(jarvis, '_curator', None)
    if not curator:
        return {"review_count": 0, "avg_quality": 0}
    return {
        "review_count": curator.review_count,
        "avg_quality": round(curator.avg_quality_score, 2),
        "quality_trend": curator.quality_trend(),
        "flagged_count": len(curator.get_flagged_reviews()),
    }


# --- Sessions ---

@app.get("/sessions")
async def list_sessions():
    from jarvis.session import SessionManager
    sm = getattr(jarvis, '_session_manager', None)
    if not sm:
        return []
    return [
        {
            "id": s.id,
            "state": s.state.value,
            "user_id": s.user_id,
            "channel": s.channel,
            "message_count": s.message_count,
            "agents_used": s.agents_used,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sm.list_sessions()
    ]


@app.get("/sessions/metrics")
async def session_metrics():
    sm = getattr(jarvis, '_session_manager', None)
    if not sm:
        return {}
    return sm.get_metrics()


# --- Observability ---

@app.get("/metrics")
async def get_metrics():
    from jarvis.observability.metrics import metrics
    return metrics.snapshot()


@app.get("/traces")
async def list_traces():
    from jarvis.observability.tracer import tracer
    return tracer.list_traces()


@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    from jarvis.observability.tracer import tracer
    trace = tracer.get_trace(trace_id)
    if not trace:
        raise HTTPException(404, f"Trace {trace_id} not found")
    return trace


# --- Tools ---

@app.get("/tools")
async def list_tools():
    if not jarvis._tool_registry:
        return []
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in jarvis._tool_registry.list_tools()
    ]


# --- MCP ---

@app.get("/mcp/servers")
async def list_mcp_servers():
    registry = getattr(jarvis, '_mcp_registry', None)
    if not registry:
        return []
    return registry.list_servers()


# --- System Info ---

@app.get("/system")
async def system_info():
    """Comprehensive system information."""
    return {
        "app_name": "JARVIS",
        "version": "0.2.0",
        "agents": len(jarvis.registry),
        "tools": len(jarvis._tool_registry.list_tools()) if jarvis._tool_registry else 0,
        "active_specs": len(jarvis.spec_engine.list_specs()),
        "modules": {
            "agents": True,
            "tools": True,
            "skills": hasattr(jarvis, '_skill_registry'),
            "memory": hasattr(jarvis, '_memory_manager'),
            "knowledge_graph": True,
            "curator": hasattr(jarvis, '_curator'),
            "sessions": hasattr(jarvis, '_session_manager'),
            "mcp": hasattr(jarvis, '_mcp_registry'),
            "gateway": hasattr(jarvis, '_gateway'),
        },
    }


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

class CreateWorkflowRequest(BaseModel):
    name: str
    description: str = ""
    steps: list[dict] = []
    triggers: list[str] = []
    schedule: str | None = None
    tags: list[str] = []


class WorkflowApproveRequest(BaseModel):
    approved: bool = True
    comment: str = ""


# In-memory workflow store
_workflows: dict[str, dict] = {}
_workflow_counter: int = 0


def _next_workflow_id() -> str:
    global _workflow_counter
    _workflow_counter += 1
    return f"wf-{_workflow_counter:04d}"


@app.post("/workflows")
async def create_workflow(req: CreateWorkflowRequest):
    """Create a new workflow definition."""
    wf_id = _next_workflow_id()
    import datetime
    wf = {
        "id": wf_id,
        "name": req.name,
        "description": req.description,
        "steps": req.steps or [
            {"id": "step-1", "name": "Init", "status": "pending", "output": None},
            {"id": "step-2", "name": "Process", "status": "pending", "output": None},
            {"id": "step-3", "name": "Finalize", "status": "pending", "output": None},
        ],
        "triggers": req.triggers,
        "schedule": req.schedule,
        "tags": req.tags,
        "status": "created",
        "created_at": datetime.datetime.utcnow().isoformat(),
        "updated_at": datetime.datetime.utcnow().isoformat(),
        "execution_count": 0,
        "last_result": None,
    }
    _workflows[wf_id] = wf
    return wf


@app.get("/workflows")
async def list_workflows(
    status: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """List all workflow definitions with optional filtering."""
    items = list(_workflows.values())
    if status:
        items = [w for w in items if w["status"] == status]
    if tag:
        items = [w for w in items if tag in w.get("tags", [])]
    total = len(items)
    items = items[offset: offset + limit]
    return {"total": total, "workflows": items}


@app.get("/workflows/{wf_id}")
async def get_workflow(wf_id: str):
    """Get a workflow definition by ID."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, f"Workflow '{wf_id}' not found")
    return wf


@app.post("/workflows/{wf_id}/execute")
async def execute_workflow(wf_id: str):
    """Execute a workflow — advances all steps to completed."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, f"Workflow '{wf_id}' not found")
    import datetime
    wf["status"] = "running"
    for step in wf["steps"]:
        step["status"] = "completed"
        step["output"] = f"Step '{step['name']}' completed successfully"
    wf["status"] = "completed"
    wf["execution_count"] += 1
    wf["updated_at"] = datetime.datetime.utcnow().isoformat()
    wf["last_result"] = {"success": True, "steps_completed": len(wf["steps"])}
    return wf


@app.post("/workflows/{wf_id}/pause")
async def pause_workflow(wf_id: str):
    """Pause a running workflow."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, f"Workflow '{wf_id}' not found")
    if wf["status"] not in ("running", "created"):
        raise HTTPException(400, f"Workflow is in '{wf['status']}' state, cannot pause")
    import datetime
    wf["status"] = "paused"
    wf["updated_at"] = datetime.datetime.utcnow().isoformat()
    return wf


@app.post("/workflows/{wf_id}/resume")
async def resume_workflow(wf_id: str):
    """Resume a paused workflow."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, f"Workflow '{wf_id}' not found")
    if wf["status"] != "paused":
        raise HTTPException(400, f"Workflow is in '{wf['status']}' state, cannot resume")
    import datetime
    wf["status"] = "running"
    wf["updated_at"] = datetime.datetime.utcnow().isoformat()
    return wf


@app.post("/workflows/{wf_id}/approve/{step_id}")
async def approve_workflow_step(wf_id: str, step_id: str, req: WorkflowApproveRequest):
    """Approve or reject a workflow step that requires manual approval."""
    wf = _workflows.get(wf_id)
    if not wf:
        raise HTTPException(404, f"Workflow '{wf_id}' not found")
    step = next((s for s in wf["steps"] if s["id"] == step_id), None)
    if not step:
        raise HTTPException(404, f"Step '{step_id}' not found in workflow '{wf_id}'")
    import datetime
    step["status"] = "approved" if req.approved else "rejected"
    step["approval_comment"] = req.comment
    step["approved_at"] = datetime.datetime.utcnow().isoformat()
    wf["updated_at"] = datetime.datetime.utcnow().isoformat()
    return wf


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

_events: list[dict] = []
_event_counter: int = 0


class PublishEventRequest(BaseModel):
    topic: str
    payload: dict = {}
    source: str = "api"
    priority: str = "normal"


@app.get("/events")
async def list_events(
    topic: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """List published events with optional topic/source filtering."""
    items = list(_events)
    if topic:
        items = [e for e in items if e["topic"] == topic]
    if source:
        items = [e for e in items if e["source"] == source]
    total = len(items)
    items = items[offset: offset + limit]
    return {"total": total, "events": items}


@app.post("/events/publish")
async def publish_event(req: PublishEventRequest):
    """Publish a new event to the event bus."""
    global _event_counter
    _event_counter += 1
    import datetime
    event = {
        "id": f"evt-{_event_counter:06d}",
        "topic": req.topic,
        "payload": req.payload,
        "source": req.source,
        "priority": req.priority,
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "delivered": True,
        "subscriber_count": 0,
    }
    _events.append(event)
    return event


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

_notifications: list[dict] = []
_notification_counter: int = 0


class CreateNotificationRequest(BaseModel):
    title: str
    body: str = ""
    level: str = "info"
    target: str = "all"
    channel: str = "in_app"
    action_url: str | None = None


@app.get("/notifications")
async def list_notifications(
    level: str | None = Query(None),
    read: bool | None = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
):
    """List notifications with optional level/read filtering."""
    items = list(_notifications)
    if level:
        items = [n for n in items if n["level"] == level]
    if read is not None:
        items = [n for n in items if n["read"] == read]
    total = len(items)
    items = items[offset: offset + limit]
    return {"total": total, "notifications": items}


@app.post("/notifications")
async def create_notification(req: CreateNotificationRequest):
    """Create and send a notification."""
    global _notification_counter
    _notification_counter += 1
    import datetime
    notif = {
        "id": f"notif-{_notification_counter:04d}",
        "title": req.title,
        "body": req.body,
        "level": req.level,
        "target": req.target,
        "channel": req.channel,
        "action_url": req.action_url,
        "read": False,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "read_at": None,
    }
    _notifications.append(notif)
    return notif


@app.post("/notifications/{nid}/read")
async def mark_notification_read(nid: str):
    """Mark a notification as read."""
    notif = next((n for n in _notifications if n["id"] == nid), None)
    if not notif:
        raise HTTPException(404, f"Notification '{nid}' not found")
    import datetime
    notif["read"] = True
    notif["read_at"] = datetime.datetime.utcnow().isoformat()
    return notif


# ---------------------------------------------------------------------------
# User Profile & Preferences
# ---------------------------------------------------------------------------

_user_profile: dict = {
    "id": "user-001",
    "username": "jarvis-admin",
    "display_name": "JARVIS Admin",
    "email": "admin@jarvis.local",
    "avatar_url": None,
    "role": "admin",
    "created_at": "2025-01-01T00:00:00Z",
    "last_login": None,
}

_user_preferences: dict = {
    "theme": "dark",
    "language": "en",
    "timezone": "UTC",
    "notifications_enabled": True,
    "auto_execute_specs": False,
    "default_agent": None,
    "page_size": 25,
    "show_debug_info": False,
    "keyboard_shortcuts": True,
    "compact_view": False,
}


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    avatar_url: str | None = None


class UpdatePreferencesRequest(BaseModel):
    theme: str | None = None
    language: str | None = None
    timezone: str | None = None
    notifications_enabled: bool | None = None
    auto_execute_specs: bool | None = None
    default_agent: str | None = None
    page_size: int | None = None
    show_debug_info: bool | None = None
    keyboard_shortcuts: bool | None = None
    compact_view: bool | None = None


@app.get("/user/profile")
async def get_user_profile():
    """Get the current user profile."""
    return _user_profile


@app.put("/user/profile")
async def update_user_profile(req: UpdateProfileRequest):
    """Update user profile fields."""
    import datetime
    if req.display_name is not None:
        _user_profile["display_name"] = req.display_name
    if req.email is not None:
        _user_profile["email"] = req.email
    if req.avatar_url is not None:
        _user_profile["avatar_url"] = req.avatar_url
    _user_profile["last_login"] = datetime.datetime.utcnow().isoformat()
    return _user_profile


@app.get("/user/preferences")
async def get_user_preferences():
    """Get user preferences."""
    return _user_preferences


@app.put("/user/preferences")
async def update_user_preferences(req: UpdatePreferencesRequest):
    """Update user preferences."""
    for field in (
        "theme", "language", "timezone", "notifications_enabled",
        "auto_execute_specs", "default_agent", "page_size",
        "show_debug_info", "keyboard_shortcuts", "compact_view",
    ):
        val = getattr(req, field, None)
        if val is not None:
            _user_preferences[field] = val
    return _user_preferences


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

@app.get("/diagnostics")
async def diagnostics():
    """Run system diagnostics and return status of all subsystems."""
    import platform
    import sys
    checks = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "cpu_count": platform.processor() or "unknown",
        "architecture": platform.machine(),
        "agents_healthy": len(jarvis.registry) > 0,
        "spec_engine_healthy": jarvis.spec_engine is not None,
        "tool_registry_healthy": jarvis._tool_registry is not None,
        "memory_initialized": hasattr(jarvis, '_memory_manager'),
        "knowledge_graph_initialized": jarvis.knowledge_graph is not None,
        "active_spec_count": len(jarvis.spec_engine.list_specs()),
        "registered_agent_count": len(jarvis.registry),
        "tool_count": len(jarvis._tool_registry.list_tools()) if jarvis._tool_registry else 0,
    }
    all_healthy = all(
        v for k, v in checks.items()
        if k.endswith("_healthy") or k.endswith("_initialized")
    )
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
    }


@app.get("/diagnostics/benchmark")
async def diagnostics_benchmark():
    """Run a quick performance benchmark of core operations."""
    import time
    results: dict[str, float] = {}

    # Benchmark spec creation
    start = time.perf_counter()
    for _ in range(10):
        await jarvis.spec_engine.create("benchmark test intent")
    results["spec_creation_10x_ms"] = round((time.perf_counter() - start) * 1000, 2)

    # Benchmark agent listing
    start = time.perf_counter()
    for _ in range(100):
        jarvis.registry.list_agents()
    results["agent_list_100x_ms"] = round((time.perf_counter() - start) * 1000, 2)

    # Benchmark tool listing
    if jarvis._tool_registry:
        start = time.perf_counter()
        for _ in range(100):
            jarvis._tool_registry.list_tools()
        results["tool_list_100x_ms"] = round((time.perf_counter() - start) * 1000, 2)

    return {
        "status": "completed",
        "benchmarks": results,
    }


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_spec_templates: dict[str, dict] = {
    "code_review": {
        "name": "code_review",
        "description": "Review code changes for quality and correctness",
        "intent_template": "Review the following code changes: {changes}",
        "variables": ["changes"],
        "tags": ["code", "review"],
        "constraints": ["Focus on correctness", "Check for security issues"],
    },
    "bug_fix": {
        "name": "bug_fix",
        "description": "Diagnose and fix a reported bug",
        "intent_template": "Fix the bug: {description}. Affected component: {component}",
        "variables": ["description", "component"],
        "tags": ["bug", "fix"],
        "constraints": ["Write tests for the fix", "Document root cause"],
    },
    "feature_implementation": {
        "name": "feature_implementation",
        "description": "Implement a new feature end-to-end",
        "intent_template": "Implement feature: {feature_name}. Requirements: {requirements}",
        "variables": ["feature_name", "requirements"],
        "tags": ["feature", "implementation"],
        "constraints": ["Follow existing patterns", "Add documentation"],
    },
    "data_analysis": {
        "name": "data_analysis",
        "description": "Analyze data and produce a report",
        "intent_template": "Analyze {dataset} and report on {metrics}",
        "variables": ["dataset", "metrics"],
        "tags": ["data", "analysis"],
        "constraints": ["Include visualizations", "Cite data sources"],
    },
    "documentation": {
        "name": "documentation",
        "description": "Generate or update documentation",
        "intent_template": "Document {target} with focus on {audience}",
        "variables": ["target", "audience"],
        "tags": ["docs", "documentation"],
        "constraints": ["Use clear language", "Include examples"],
    },
}

_prompt_templates: dict[str, dict] = {
    "system_prompt": {
        "name": "system_prompt",
        "description": "Base system prompt for JARVIS agents",
        "template": "You are {agent_name}, a specialist in {domain}. {extra_instructions}",
        "variables": ["agent_name", "domain", "extra_instructions"],
    },
    "task_decomposition": {
        "name": "task_decomposition",
        "description": "Decompose a complex task into subtasks",
        "template": "Break down the following task into 3-7 concrete steps: {task}",
        "variables": ["task"],
    },
    "code_generation": {
        "name": "code_generation",
        "description": "Generate code from requirements",
        "template": "Generate {language} code that: {requirements}\nConstraints: {constraints}",
        "variables": ["language", "requirements", "constraints"],
    },
    "summarization": {
        "name": "summarization",
        "description": "Summarize text content",
        "template": "Summarize the following in {max_words} words or fewer:\n{content}",
        "variables": ["max_words", "content"],
    },
}


class RenderTemplateRequest(BaseModel):
    variables: dict[str, str] = {}


@app.get("/templates/specs")
async def list_spec_templates():
    """List available spec templates."""
    return list(_spec_templates.values())


@app.get("/templates/prompts")
async def list_prompt_templates():
    """List available prompt templates."""
    return list(_prompt_templates.values())


@app.post("/templates/specs/{name}/render")
async def render_spec_template(name: str, req: RenderTemplateRequest):
    """Render a spec template with provided variables."""
    template = _spec_templates.get(name)
    if not template:
        raise HTTPException(404, f"Spec template '{name}' not found")
    try:
        rendered_intent = template["intent_template"].format(**req.variables)
    except KeyError as exc:
        raise HTTPException(
            422, f"Missing required variable: {exc}. Required: {template['variables']}"
        )
    return {
        "template": name,
        "rendered_intent": rendered_intent,
        "constraints": template.get("constraints", []),
        "variables_used": req.variables,
    }


@app.get("/templates/specs/{name}")
async def get_spec_template(name: str):
    """Get a specific spec template by name."""
    template = _spec_templates.get(name)
    if not template:
        raise HTTPException(404, f"Spec template '{name}' not found")
    return template


@app.get("/templates/prompts/{name}")
async def get_prompt_template(name: str):
    """Get a specific prompt template by name."""
    template = _prompt_templates.get(name)
    if not template:
        raise HTTPException(404, f"Prompt template '{name}' not found")
    return template


@app.post("/templates/prompts/{name}/render")
async def render_prompt_template(name: str, req: RenderTemplateRequest):
    """Render a prompt template with provided variables."""
    template = _prompt_templates.get(name)
    if not template:
        raise HTTPException(404, f"Prompt template '{name}' not found")
    try:
        rendered = template["template"].format(**req.variables)
    except KeyError as exc:
        raise HTTPException(
            422, f"Missing required variable: {exc}. Required: {template['variables']}"
        )
    return {
        "template": name,
        "rendered": rendered,
        "variables_used": req.variables,
    }


# --- Skill Eval API ---

class AddEvalRequest(BaseModel):
    name: str
    prompt: str
    expected: list[str] = []
    must_not: list[str] = []
    eval_type: str = "validation"


@app.post("/skills/{skill_name}/evals")
async def add_skill_eval(skill_name: str, req: AddEvalRequest):
    from jarvis.skills.eval import EvalCase, EvalType
    skill = jarvis.skill_registry.get(skill_name)
    if not skill:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    case = EvalCase(
        name=req.name,
        prompt=req.prompt,
        expected=req.expected,
        must_not=req.must_not,
        eval_type=EvalType(req.eval_type),
    )
    jarvis.skill_evaluator.add_eval(skill_name, case)
    return {"success": True, "eval_id": case.id}


@app.post("/skills/{skill_name}/evals/run")
async def run_skill_evals(skill_name: str):
    skill = jarvis.skill_registry.get(skill_name)
    if not skill:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    suite = jarvis.skill_evaluator.get_suite(skill_name)
    if not suite or not suite.cases:
        raise HTTPException(400, f"No eval cases for skill '{skill_name}'")
    suite = await jarvis.skill_evaluator.run_suite(skill, suite)
    return {
        "skill": skill_name,
        "total": len(suite.cases),
        "passed": sum(1 for r in suite.results if r.passed),
        "pass_rate": suite.pass_rate,
        "results": [r.model_dump(mode="json") for r in suite.results],
    }


@app.get("/skills/{skill_name}/evals/results")
async def get_skill_eval_results(skill_name: str):
    suite = jarvis.skill_evaluator.get_suite(skill_name)
    if not suite:
        return {"skill": skill_name, "results": [], "pass_rate": 0.0}
    return {
        "skill": skill_name,
        "total": len(suite.cases),
        "pass_rate": suite.pass_rate,
        "results": [r.model_dump(mode="json") for r in suite.results],
    }


@app.post("/skills/{skill_name}/evolve")
async def evolve_skill(skill_name: str):
    skill = jarvis.skill_registry.get(skill_name)
    if not skill:
        raise HTTPException(404, f"Skill '{skill_name}' not found")
    await jarvis._evolve_skill(skill)
    updated = jarvis.skill_registry.get(skill_name)
    return {
        "success": True,
        "skill": skill_name,
        "version": updated.metadata.version if updated else "unknown",
    }


# --- Static frontend (must be last so it doesn't shadow API routes) ---

from jarvis.server.static import mount_static  # noqa: E402
mount_static(app)
