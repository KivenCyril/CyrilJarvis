"""MCP (Model Context Protocol) client implementation.

Provides a lightweight client that connects to MCP servers via stdio transport,
discovers their tools, and proxies tool calls through JSON-RPC 2.0.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from jarvis.llm.provider import ToolDefinition
from jarvis.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MCPTransport(str, Enum):
    STDIO = "stdio"
    SSE = "sse"


@dataclass
class MCPServerConfig:
    """Configuration for connecting to an MCP server."""

    name: str
    command: str  # e.g., "npx -y @modelcontextprotocol/server-filesystem /tmp"
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    transport: MCPTransport = MCPTransport.STDIO
    url: str = ""  # for SSE transport

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MCPServerConfig:
        return cls(
            name=data["name"],
            command=data.get("command", ""),
            args=data.get("args", []),
            env=data.get("env", {}),
            transport=MCPTransport(data.get("transport", "stdio")),
            url=data.get("url", ""),
        )


class MCPTool(BaseTool):
    """A tool proxied from an MCP server."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        client: MCPClient,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self._client = client

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return await self._client.call_tool(self.name, arguments)


class MCPClient:
    """Client for communicating with MCP (Model Context Protocol) servers.

    Supports:
    - stdio transport: launches server as subprocess, communicates via
      JSON-RPC 2.0 over stdin/stdout
    - Server lifecycle management (start/stop)
    - Tool discovery (list tools from server)
    - Tool execution (call tools on server)
    - Resource listing and reading
    """

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._process: asyncio.subprocess.Process | None = None
        self._request_id: int = 0
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._tools: dict[str, dict[str, Any]] = {}
        self._resources: list[dict[str, Any]] = []
        self._running = False
        self._read_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the MCP server process and initialize the connection."""
        if self.config.transport == MCPTransport.STDIO:
            await self._start_stdio()
        else:
            logger.warning("SSE transport not yet implemented for MCP client")
            return

        # Initialize: send initialize request per MCP spec
        result = await self._send_request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "jarvis", "version": "0.1.0"},
            },
        )

        if result:
            logger.info(
                "MCP server '%s' initialized: %s",
                self.config.name,
                result.get("serverInfo", {}),
            )

        # Send initialized notification
        await self._send_notification("notifications/initialized", {})

        # Discover tools
        await self._discover_tools()
        self._running = True

    async def stop(self) -> None:
        """Stop the MCP server process."""
        self._running = False
        if self._read_task:
            self._read_task.cancel()
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
            logger.info("MCP server '%s' stopped", self.config.name)

    # ------------------------------------------------------------------
    # stdio transport
    # ------------------------------------------------------------------

    async def _start_stdio(self) -> None:
        """Launch MCP server as subprocess with stdio transport."""
        cmd_parts = self.config.command.split()
        cmd = cmd_parts + self.config.args

        env = {**os.environ, **self.config.env}

        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Start reading responses in background
        self._read_task = asyncio.create_task(self._read_loop())
        logger.info(
            "MCP server '%s' started (pid=%s)",
            self.config.name,
            self._process.pid,
        )

    async def _read_loop(self) -> None:
        """Read JSON-RPC responses from the server's stdout."""
        if not self._process or not self._process.stdout:
            return

        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break

                decoded = line.decode("utf-8").strip()
                if not decoded:
                    continue

                try:
                    msg = json.loads(decoded)
                except json.JSONDecodeError:
                    # Handle Content-Length based framing (LSP-style)
                    if decoded.startswith("Content-Length:"):
                        length = int(decoded.split(":")[1].strip())
                        # consume the blank separator line
                        await self._process.stdout.readline()
                        data = await self._process.stdout.readexactly(length)
                        msg = json.loads(data.decode("utf-8"))
                    else:
                        continue

                # Dispatch response to waiting future
                if "id" in msg and msg["id"] in self._pending:
                    future = self._pending.pop(msg["id"])
                    if "error" in msg:
                        future.set_exception(
                            RuntimeError(
                                msg["error"].get("message", "Unknown error")
                            )
                        )
                    else:
                        future.set_result(msg.get("result"))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug("MCP read error: %s", e)
                continue

    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------

    async def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or not self._process.stdin:
            return None

        self._request_id += 1
        request_id = self._request_id

        msg = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }

        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        payload = json.dumps(msg) + "\n"
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            logger.warning("MCP request timed out: %s", method)
            return None

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._process or not self._process.stdin:
            return

        msg = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        payload = json.dumps(msg) + "\n"
        self._process.stdin.write(payload.encode("utf-8"))
        await self._process.stdin.drain()

    # ------------------------------------------------------------------
    # Tool discovery & execution
    # ------------------------------------------------------------------

    async def _discover_tools(self) -> None:
        """Fetch available tools from the MCP server."""
        result = await self._send_request("tools/list", {})
        if result and "tools" in result:
            for tool_data in result["tools"]:
                name = tool_data["name"]
                self._tools[name] = tool_data
            logger.info(
                "MCP server '%s' provides %d tools",
                self.config.name,
                len(self._tools),
            )

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call a tool on the MCP server."""
        # Strip the mcp_ prefix to get the raw tool name for the server
        raw_name = name
        prefix = f"mcp_{self.config.name}_"
        if raw_name.startswith(prefix):
            raw_name = raw_name[len(prefix) :]

        if raw_name not in self._tools:
            return ToolResult(
                success=False,
                output=f"Tool '{raw_name}' not found on MCP server '{self.config.name}'",
            )

        result = await self._send_request(
            "tools/call",
            {"name": raw_name, "arguments": arguments},
        )

        if result is None:
            return ToolResult(success=False, output="MCP server did not respond")

        # Parse MCP tool result content array
        content_parts = result.get("content", [])
        output_parts: list[str] = []
        for part in content_parts:
            if part.get("type") == "text":
                output_parts.append(part.get("text", ""))

        is_error = result.get("isError", False)
        return ToolResult(
            success=not is_error,
            output="\n".join(output_parts) or "(no output)",
        )

    # ------------------------------------------------------------------
    # Tool definitions for LLM integration
    # ------------------------------------------------------------------

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Convert MCP tools to LLM-compatible tool definitions."""
        definitions: list[ToolDefinition] = []
        for name, data in self._tools.items():
            definitions.append(
                ToolDefinition(
                    name=f"mcp_{self.config.name}_{name}",
                    description=data.get("description", ""),
                    parameters=data.get(
                        "inputSchema", {"type": "object", "properties": {}}
                    ),
                )
            )
        return definitions

    def get_tools(self) -> list[MCPTool]:
        """Get MCPTool instances that can be registered in ToolRegistry."""
        tools: list[MCPTool] = []
        for name, data in self._tools.items():
            tools.append(
                MCPTool(
                    name=f"mcp_{self.config.name}_{name}",
                    description=data.get("description", ""),
                    parameters=data.get(
                        "inputSchema", {"type": "object", "properties": {}}
                    ),
                    client=self,
                )
            )
        return tools

    # ------------------------------------------------------------------
    # Resources
    # ------------------------------------------------------------------

    async def list_resources(self) -> list[dict[str, Any]]:
        """List available resources from the MCP server."""
        result = await self._send_request("resources/list", {})
        if result and "resources" in result:
            self._resources = result["resources"]
        return self._resources

    async def read_resource(self, uri: str) -> str:
        """Read a resource from the MCP server."""
        result = await self._send_request("resources/read", {"uri": uri})
        if result and "contents" in result:
            for content in result["contents"]:
                if "text" in content:
                    return content["text"]
        return ""

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def tool_count(self) -> int:
        return len(self._tools)
