from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class SpecConnection:
    """A single WebSocket connection watching a spec."""
    def __init__(self, websocket: WebSocket, spec_id: str, client_id: str):
        self.websocket = websocket
        self.spec_id = spec_id
        self.client_id = client_id

    async def send(self, event: dict[str, Any]) -> None:
        if self.websocket.client_state == WebSocketState.CONNECTED:
            await self.websocket.send_json(event)


class ConnectionManager:
    """Manages WebSocket connections for real-time Spec updates."""

    def __init__(self):
        self._connections: dict[str, list[SpecConnection]] = {}  # spec_id -> connections

    async def connect(self, websocket: WebSocket, spec_id: str, client_id: str) -> SpecConnection:
        await websocket.accept()
        conn = SpecConnection(websocket, spec_id, client_id)
        self._connections.setdefault(spec_id, []).append(conn)
        logger.info("Client %s connected to spec %s", client_id, spec_id)
        return conn

    def disconnect(self, conn: SpecConnection) -> None:
        conns = self._connections.get(conn.spec_id, [])
        if conn in conns:
            conns.remove(conn)
        logger.info("Client %s disconnected from spec %s", conn.client_id, conn.spec_id)

    async def broadcast(self, spec_id: str, event: dict[str, Any], exclude_client: str | None = None) -> None:
        """Broadcast an event to all connections watching a spec."""
        for conn in list(self._connections.get(spec_id, [])):
            if exclude_client and conn.client_id == exclude_client:
                continue
            try:
                await conn.send(event)
            except Exception:
                self.disconnect(conn)

    @property
    def active_connections(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


manager = ConnectionManager()
