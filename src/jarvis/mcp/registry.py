"""MCP Registry -- manages multiple MCP server connections."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from jarvis.llm.provider import ToolDefinition
from jarvis.mcp.client import MCPClient, MCPServerConfig, MCPTool

logger = logging.getLogger(__name__)


class MCPRegistry:
    """Manages multiple MCP server connections.

    Loads MCP server configurations from a config file and manages their
    lifecycle.  All MCP tools are automatically surfaced as
    ``ToolDefinition`` / ``MCPTool`` instances for agent use.
    """

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}

    # ------------------------------------------------------------------
    # Server management
    # ------------------------------------------------------------------

    async def add_server(self, config: MCPServerConfig) -> MCPClient:
        """Start an MCP server and register its tools."""
        if config.name in self._clients:
            logger.warning(
                "MCP server '%s' already registered; removing first", config.name
            )
            await self.remove_server(config.name)

        client = MCPClient(config)
        await client.start()
        self._clients[config.name] = client
        logger.info(
            "MCP server '%s' added (%d tools)",
            config.name,
            client.tool_count,
        )
        return client

    async def remove_server(self, name: str) -> None:
        """Stop and remove an MCP server."""
        client = self._clients.pop(name, None)
        if client:
            await client.stop()
            logger.info("MCP server '%s' removed", name)

    def get_client(self, name: str) -> MCPClient | None:
        """Return the client for a given server name, or ``None``."""
        return self._clients.get(name)

    def list_servers(self) -> list[dict[str, Any]]:
        """List all connected MCP servers with their tool counts."""
        return [
            {
                "name": name,
                "running": client.is_running,
                "tools": client.tool_count,
            }
            for name, client in self._clients.items()
        ]

    # ------------------------------------------------------------------
    # Aggregated tool access
    # ------------------------------------------------------------------

    def get_all_tool_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions from all connected MCP servers."""
        definitions: list[ToolDefinition] = []
        for client in self._clients.values():
            definitions.extend(client.get_tool_definitions())
        return definitions

    def get_all_tools(self) -> list[MCPTool]:
        """Get all MCP tools for registration in ToolRegistry."""
        tools: list[MCPTool] = []
        for client in self._clients.values():
            tools.extend(client.get_tools())
        return tools

    # ------------------------------------------------------------------
    # Configuration loading
    # ------------------------------------------------------------------

    async def load_config(self, config_path: str | Path) -> int:
        """Load MCP server configs from a YAML or JSON file.

        Expected format (YAML shown, JSON equivalent accepted)::

            mcp_servers:
              - name: filesystem
                command: npx
                args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
              - name: postgres
                command: npx
                args: ["-y", "@modelcontextprotocol/server-postgres"]
                env:
                  DATABASE_URL: "postgresql://..."

        Returns the number of servers successfully started.
        """
        path = Path(config_path)
        if not path.exists():
            logger.warning("MCP config file not found: %s", path)
            return 0

        raw = path.read_text(encoding="utf-8")

        if path.suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore[import-untyped]

                data = yaml.safe_load(raw)
            except ImportError:
                logger.error(
                    "PyYAML is required to load YAML MCP configs; "
                    "install it or use JSON format instead."
                )
                return 0
        else:
            data = json.loads(raw)

        servers = data.get("mcp_servers", [])
        started = 0
        for entry in servers:
            try:
                config = MCPServerConfig.from_dict(entry)
                await self.add_server(config)
                started += 1
            except Exception:
                logger.exception(
                    "Failed to start MCP server '%s'", entry.get("name", "?")
                )

        logger.info(
            "Loaded %d / %d MCP servers from %s", started, len(servers), path
        )
        return started

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    async def shutdown_all(self) -> None:
        """Stop all MCP servers."""
        names = list(self._clients.keys())
        for name in names:
            await self.remove_server(name)
        logger.info("All MCP servers shut down")
