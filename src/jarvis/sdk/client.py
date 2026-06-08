"""Async and sync Python SDK clients for the JARVIS API.

Provides typed dataclasses for API responses and two client flavors:

* ``AsyncJarvisClient`` -- for use in ``async`` / ``await`` code.
* ``JarvisClient`` -- thin synchronous wrapper for scripts and notebooks.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Response dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentInfo:
    """Metadata about a JARVIS agent."""

    name: str
    description: str
    domain: str
    skills: list[str]
    status: str


@dataclass
class SpecInfo:
    """A Streaming Spec -- the real-time editable task control panel."""

    id: str
    name: str
    intent: str
    status: str
    progress: str
    steps: list[dict]
    constraints: list[dict]
    changelog: list[dict] = field(default_factory=list)


@dataclass
class ToolInfo:
    """Metadata about a registered tool."""

    name: str
    description: str
    parameters: dict


@dataclass
class ChatResponse:
    """Result of a chat interaction with a JARVIS agent."""

    success: bool
    agent: str
    output: str
    error: str | None = None


@dataclass
class MemoryInfo:
    """A single memory entry."""

    id: str
    memory_type: str
    content: str
    importance: float
    created_at: str


@dataclass
class SkillInfo:
    """Metadata about a skill in the skill registry."""

    name: str
    version: str
    description: str
    domain: str
    tags: list[str]
    status: str
    use_count: int
    success_rate: float


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------

class AsyncJarvisClient:
    """Async Python SDK for the JARVIS API.

    Provides a clean, typed interface for all JARVIS operations:

    - Chat with agents
    - Create and manage Streaming Specs
    - List and inspect agents
    - List and execute tools
    - Manage memories
    - Browse skills
    - WebSocket spec streaming

    Usage::

        async with AsyncJarvisClient("http://localhost:8000") as client:
            # Chat
            response = await client.chat("review this code")
            print(response.output)

            # Create and execute spec
            spec = await client.create_spec("Deploy to production")
            result = await client.execute_spec(spec.id)

            # Stream spec updates
            async for event in client.stream_spec(spec.id):
                print(event)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: Any = None  # httpx.AsyncClient

    # -- Context manager -----------------------------------------------------

    async def __aenter__(self) -> "AsyncJarvisClient":
        import httpx

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._client is not None:
            await self._client.aclose()

    # -- Low-level HTTP helpers ----------------------------------------------

    async def _get(self, path: str) -> Any:
        resp = await self._client.get(path)
        resp.raise_for_status()
        return resp.json()

    async def _post(self, path: str, data: dict | None = None) -> Any:
        resp = await self._client.post(path, json=data or {})
        resp.raise_for_status()
        return resp.json()

    async def _delete(self, path: str) -> Any:
        resp = await self._client.delete(path)
        resp.raise_for_status()
        return resp.json()

    async def _patch(self, path: str, data: dict) -> Any:
        resp = await self._client.patch(path, json=data)
        resp.raise_for_status()
        return resp.json()

    # -- Health --------------------------------------------------------------

    async def health(self) -> dict:
        """Return system health information."""
        return await self._get("/health")

    async def system_info(self) -> dict:
        """Return detailed system information."""
        return await self._get("/system")

    # -- Chat ----------------------------------------------------------------

    async def chat(self, message: str) -> ChatResponse:
        """Send a message to the JARVIS chat endpoint.

        The system routes the message to the most appropriate agent and
        returns a typed ``ChatResponse``.
        """
        data = await self._post("/chat", {"message": message})
        return ChatResponse(
            success=data["success"],
            agent=data["agent"],
            output=data["output"],
            error=data.get("error"),
        )

    # -- Agents --------------------------------------------------------------

    async def list_agents(self) -> list[AgentInfo]:
        """List all registered agents."""
        data = await self._get("/agents")
        return [
            AgentInfo(
                name=a["name"],
                description=a["description"],
                domain=a["domain"],
                skills=a["skills"],
                status=a["status"],
            )
            for a in data
        ]

    async def get_agent(self, name: str) -> AgentInfo:
        """Get details of a single agent by *name*."""
        data = await self._get(f"/agents/{name}")
        return AgentInfo(
            name=data["name"],
            description=data["description"],
            domain=data["domain"],
            skills=data["skills"],
            status=data["status"],
        )

    # -- Specs ---------------------------------------------------------------

    async def create_spec(
        self,
        intent: str,
        name: str | None = None,
    ) -> SpecInfo:
        """Create a new Streaming Spec from *intent*."""
        data = await self._post("/specs", {"intent": intent, "name": name})
        return self._parse_spec(data)

    async def get_spec(self, spec_id: str) -> SpecInfo:
        """Retrieve an existing spec by *spec_id*."""
        data = await self._get(f"/specs/{spec_id}")
        return self._parse_spec(data)

    async def list_specs(self) -> list[SpecInfo]:
        """List all specs."""
        data = await self._get("/specs")
        return [self._parse_spec(s) for s in data]

    async def execute_spec(self, spec_id: str) -> SpecInfo:
        """Execute the spec identified by *spec_id*."""
        data = await self._post(f"/specs/{spec_id}/execute")
        return self._parse_spec(data)

    async def add_constraint(
        self,
        spec_id: str,
        content: str,
    ) -> SpecInfo:
        """Add a constraint to a spec."""
        data = await self._post(
            f"/specs/{spec_id}/constraints",
            {"content": content},
        )
        return self._parse_spec(data)

    async def remove_constraint(
        self,
        spec_id: str,
        constraint_id: str,
    ) -> SpecInfo:
        """Remove a constraint from a spec."""
        data = await self._delete(
            f"/specs/{spec_id}/constraints/{constraint_id}",
        )
        return self._parse_spec(data)

    async def edit_step(
        self,
        spec_id: str,
        step_id: str,
        name: str | None = None,
        description: str | None = None,
    ) -> SpecInfo:
        """Edit a step within a spec."""
        data = await self._patch(
            f"/specs/{spec_id}/steps/{step_id}",
            {"name": name, "description": description},
        )
        return self._parse_spec(data)

    async def redirect_spec(
        self,
        spec_id: str,
        new_intent: str,
    ) -> SpecInfo:
        """Redirect a spec to a *new_intent*."""
        data = await self._post(
            f"/specs/{spec_id}/redirect",
            {"new_intent": new_intent},
        )
        return self._parse_spec(data)

    async def get_changelog(self, spec_id: str) -> list[dict]:
        """Return the changelog for a spec."""
        return await self._get(f"/specs/{spec_id}/changelog")

    # -- WebSocket Streaming -------------------------------------------------

    async def stream_spec(
        self,
        spec_id: str,
        client_id: str = "sdk",
    ) -> AsyncIterator[dict]:
        """Stream real-time spec updates via WebSocket.

        Yields parsed JSON messages as dictionaries.
        """
        import websockets

        ws_url = (
            self._base_url.replace("http", "ws")
            + f"/ws/specs/{spec_id}?client_id={client_id}"
        )
        async with websockets.connect(ws_url) as ws:
            async for message in ws:
                yield json.loads(message)

    # -- Tools ---------------------------------------------------------------

    async def list_tools(self) -> list[ToolInfo]:
        """List all available tools."""
        data = await self._get("/tools")
        return [
            ToolInfo(
                name=t["name"],
                description=t["description"],
                parameters=t["parameters"],
            )
            for t in data
        ]

    # -- Memory --------------------------------------------------------------

    async def add_memory(
        self,
        content: str,
        memory_type: str = "fact",
        metadata: dict | None = None,
    ) -> dict:
        """Store a new memory entry."""
        return await self._post(
            "/memory",
            {
                "content": content,
                "memory_type": memory_type,
                "metadata": metadata or {},
            },
        )

    async def search_memory(self, query: str, limit: int = 5) -> list[dict]:
        """Search memories by semantic *query*."""
        return await self._post(
            "/memory/search",
            {"query": query, "limit": limit},
        )

    async def list_memories(self) -> list[dict]:
        """List all stored memories."""
        return await self._get("/memory")

    # -- Knowledge -----------------------------------------------------------

    async def knowledge_stats(self) -> dict:
        """Return knowledge-graph statistics."""
        return await self._get("/knowledge/stats")

    async def knowledge_graph(self) -> dict:
        """Return the full knowledge graph."""
        return await self._get("/knowledge/graph")

    async def extract_knowledge(self, text: str) -> dict:
        """Extract knowledge entities / relations from *text*."""
        return await self._post("/knowledge/extract", {"text": text})

    # -- Skills --------------------------------------------------------------

    async def list_skills(self) -> list[SkillInfo]:
        """List all registered skills."""
        data = await self._get("/skills")
        return [SkillInfo(**s) for s in data]

    # -- Curator -------------------------------------------------------------

    async def review(
        self,
        request: str,
        output: str,
        constraints: list[str] | None = None,
    ) -> dict:
        """Submit an output for curator quality review."""
        return await self._post(
            "/curator/review",
            {
                "request": request,
                "output": output,
                "constraints": constraints or [],
            },
        )

    # -- Observability -------------------------------------------------------

    async def get_metrics(self) -> dict:
        """Return system metrics."""
        return await self._get("/metrics")

    async def list_traces(self) -> list[dict]:
        """List execution traces."""
        return await self._get("/traces")

    # -- Sessions ------------------------------------------------------------

    async def list_sessions(self) -> list[dict]:
        """List active sessions."""
        return await self._get("/sessions")

    async def session_metrics(self) -> dict:
        """Return session-level metrics."""
        return await self._get("/sessions/metrics")

    # -- Delegations ---------------------------------------------------------

    async def get_delegations(self) -> list[dict]:
        """Return current agent delegations."""
        return await self._get("/delegations")

    # -- MCP -----------------------------------------------------------------

    async def list_mcp_servers(self) -> list[dict]:
        """List configured MCP servers."""
        return await self._get("/mcp/servers")

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _parse_spec(data: dict) -> SpecInfo:
        """Convert a raw API dict into a typed ``SpecInfo``."""
        return SpecInfo(
            id=data["id"],
            name=data["name"],
            intent=data["intent"],
            status=data["status"],
            progress=data.get("progress", ""),
            steps=data.get("steps", []),
            constraints=data.get("constraints", []),
            changelog=data.get("changelog", []),
        )


# ---------------------------------------------------------------------------
# Synchronous wrapper
# ---------------------------------------------------------------------------

class JarvisClient:
    """Synchronous wrapper around :class:`AsyncJarvisClient`.

    Intended for use in non-async code such as scripts and notebooks.
    Each method opens a fresh ``AsyncJarvisClient`` context, executes the
    operation, and returns the result.

    Usage::

        client = JarvisClient("http://localhost:8000")
        response = client.chat("Hello JARVIS")
        print(response.output)
    """

    def __init__(self, base_url: str = "http://localhost:8000") -> None:
        self._base_url = base_url

    def _run(self, coro: Any) -> Any:
        import asyncio

        try:
            asyncio.get_running_loop()
            raise RuntimeError(
                "JarvisClient cannot be used inside an already-running "
                "event loop. Use AsyncJarvisClient instead."
            )
        except RuntimeError as exc:
            if "no current event loop" in str(exc).lower() or \
               "no running event loop" in str(exc).lower():
                return asyncio.run(coro)
            raise

    # -- Convenience helpers wrapping the async client -----------------------

    def health(self) -> dict:
        """Return system health information."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.health()
        return self._run(_do())

    def chat(self, message: str) -> ChatResponse:
        """Send a message to the JARVIS chat endpoint."""
        async def _do() -> ChatResponse:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.chat(message)
        return self._run(_do())

    def list_agents(self) -> list[AgentInfo]:
        """List all registered agents."""
        async def _do() -> list[AgentInfo]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_agents()
        return self._run(_do())

    def get_agent(self, name: str) -> AgentInfo:
        """Get details of a single agent by *name*."""
        async def _do() -> AgentInfo:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.get_agent(name)
        return self._run(_do())

    def create_spec(self, intent: str, name: str | None = None) -> SpecInfo:
        """Create a new Streaming Spec."""
        async def _do() -> SpecInfo:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.create_spec(intent, name=name)
        return self._run(_do())

    def get_spec(self, spec_id: str) -> SpecInfo:
        """Retrieve an existing spec."""
        async def _do() -> SpecInfo:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.get_spec(spec_id)
        return self._run(_do())

    def list_specs(self) -> list[SpecInfo]:
        """List all specs."""
        async def _do() -> list[SpecInfo]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_specs()
        return self._run(_do())

    def execute_spec(self, spec_id: str) -> SpecInfo:
        """Execute a spec."""
        async def _do() -> SpecInfo:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.execute_spec(spec_id)
        return self._run(_do())

    def add_constraint(self, spec_id: str, content: str) -> SpecInfo:
        """Add a constraint to a spec."""
        async def _do() -> SpecInfo:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.add_constraint(spec_id, content)
        return self._run(_do())

    def list_tools(self) -> list[ToolInfo]:
        """List all available tools."""
        async def _do() -> list[ToolInfo]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_tools()
        return self._run(_do())

    def add_memory(
        self,
        content: str,
        memory_type: str = "fact",
        metadata: dict | None = None,
    ) -> dict:
        """Store a new memory entry."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.add_memory(content, memory_type, metadata)
        return self._run(_do())

    def search_memory(self, query: str, limit: int = 5) -> list[dict]:
        """Search memories."""
        async def _do() -> list[dict]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.search_memory(query, limit)
        return self._run(_do())

    def list_memories(self) -> list[dict]:
        """List all stored memories."""
        async def _do() -> list[dict]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_memories()
        return self._run(_do())

    def list_skills(self) -> list[SkillInfo]:
        """List all registered skills."""
        async def _do() -> list[SkillInfo]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_skills()
        return self._run(_do())

    def review(
        self,
        request: str,
        output: str,
        constraints: list[str] | None = None,
    ) -> dict:
        """Submit an output for curator quality review."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.review(request, output, constraints)
        return self._run(_do())

    def get_metrics(self) -> dict:
        """Return system metrics."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.get_metrics()
        return self._run(_do())

    def list_traces(self) -> list[dict]:
        """List execution traces."""
        async def _do() -> list[dict]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_traces()
        return self._run(_do())

    def knowledge_stats(self) -> dict:
        """Return knowledge-graph statistics."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.knowledge_stats()
        return self._run(_do())

    def knowledge_graph(self) -> dict:
        """Return the full knowledge graph."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.knowledge_graph()
        return self._run(_do())

    def extract_knowledge(self, text: str) -> dict:
        """Extract knowledge entities / relations from *text*."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.extract_knowledge(text)
        return self._run(_do())

    def list_sessions(self) -> list[dict]:
        """List active sessions."""
        async def _do() -> list[dict]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_sessions()
        return self._run(_do())

    def session_metrics(self) -> dict:
        """Return session-level metrics."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.session_metrics()
        return self._run(_do())

    def get_delegations(self) -> list[dict]:
        """Return current agent delegations."""
        async def _do() -> list[dict]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.get_delegations()
        return self._run(_do())

    def list_mcp_servers(self) -> list[dict]:
        """List configured MCP servers."""
        async def _do() -> list[dict]:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.list_mcp_servers()
        return self._run(_do())

    def system_info(self) -> dict:
        """Return detailed system information."""
        async def _do() -> dict:
            async with AsyncJarvisClient(self._base_url) as c:
                return await c.system_info()
        return self._run(_do())
