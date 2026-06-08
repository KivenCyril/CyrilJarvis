from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from jarvis.gateway.channel import Channel, ChannelMessage, ChannelType

logger = logging.getLogger(__name__)

# Rate-limit defaults
_RATE_LIMIT_WINDOW = 60.0  # seconds
_RATE_LIMIT_MAX = 30  # messages per window


class Gateway:
    """Central message routing hub.

    Routes messages from any channel to JARVIS core (Orchestrator),
    and sends responses back to the originating channel.

    Features:
    - Multi-channel message normalization
    - Message routing and dispatch
    - Rate limiting per channel
    - Message logging
    - Channel health monitoring
    """

    def __init__(self) -> None:
        self._channels: dict[str, Channel] = {}
        self._message_handler: Callable[[ChannelMessage], Awaitable[str]] | None = None
        self._message_log: list[ChannelMessage] = []
        self._rate_limits: dict[str, list[float]] = {}  # channel_id -> timestamps
        self._message_counts: dict[str, int] = {}  # channel name -> count

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------

    def register_channel(self, channel: Channel) -> None:
        """Register a channel with the gateway."""
        name = channel.name
        if name in self._channels:
            logger.warning("Channel %s already registered, replacing", name)
        self._channels[name] = channel
        self._message_counts.setdefault(name, 0)
        # Wire up the handler if one is already set
        if self._message_handler is not None:
            channel.set_handler(self._handle_message)
        logger.info("Registered channel: %s (%s)", name, channel.channel_type.value)

    def unregister_channel(self, name: str) -> None:
        """Remove a channel from the gateway."""
        if name in self._channels:
            del self._channels[name]
            self._message_counts.pop(name, None)
            logger.info("Unregistered channel: %s", name)

    def get_channel(self, name: str) -> Channel | None:
        return self._channels.get(name)

    def list_channels(self) -> list[dict[str, Any]]:
        """Return info dicts for every registered channel."""
        return [
            {
                "name": ch.name,
                "type": ch.channel_type.value,
                "status": "running" if ch.is_running else "stopped",
                "message_count": self._message_counts.get(ch.name, 0),
            }
            for ch in self._channels.values()
        ]

    # ------------------------------------------------------------------
    # Message handler
    # ------------------------------------------------------------------

    def set_message_handler(
        self,
        handler: Callable[[ChannelMessage], Awaitable[str]],
    ) -> None:
        """Set the handler (usually JarvisApp.chat) for incoming messages."""
        self._message_handler = handler
        for channel in self._channels.values():
            channel.set_handler(self._handle_message)

    async def _handle_message(self, message: ChannelMessage) -> str:
        """Process a message: rate limit check, log, route to handler."""
        sender_key = f"{message.channel_type.value}:{message.sender_id}"

        # --- Rate limiting ---
        now = time.monotonic()
        timestamps = self._rate_limits.setdefault(sender_key, [])
        # Purge old entries outside the window
        timestamps[:] = [t for t in timestamps if now - t < _RATE_LIMIT_WINDOW]
        if len(timestamps) >= _RATE_LIMIT_MAX:
            logger.warning("Rate limit exceeded for %s", sender_key)
            return "Rate limit exceeded. Please wait before sending more messages."
        timestamps.append(now)

        # --- Log ---
        self._message_log.append(message)
        # Bump per-channel counter (match by channel_type since channel_id may vary)
        for ch in self._channels.values():
            if ch.channel_type == message.channel_type:
                self._message_counts[ch.name] = self._message_counts.get(ch.name, 0) + 1
                break

        # --- Route to handler ---
        if self._message_handler is None:
            return "No message handler configured"
        try:
            return await self._message_handler(message)
        except Exception as exc:
            logger.exception("Handler error for message %s", message.id)
            return f"Error processing message: {exc}"

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    async def broadcast(
        self,
        content: str,
        channel_types: list[ChannelType] | None = None,
    ) -> int:
        """Send a message to all (or filtered) channels. Returns send count."""
        sent = 0
        for channel in self._channels.values():
            if channel_types and channel.channel_type not in channel_types:
                continue
            if not channel.is_running:
                continue
            try:
                ok = await channel.send("broadcast", content)
                if ok:
                    sent += 1
            except Exception:
                logger.exception("Broadcast failed on channel %s", channel.name)
        return sent

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start_all(self) -> None:
        """Start all registered channels."""
        for channel in self._channels.values():
            if not channel.is_running:
                try:
                    await channel.start()
                    logger.info("Started channel: %s", channel.name)
                except Exception:
                    logger.exception("Failed to start channel %s", channel.name)

    async def stop_all(self) -> None:
        """Stop all registered channels."""
        for channel in self._channels.values():
            if channel.is_running:
                try:
                    await channel.stop()
                    logger.info("Stopped channel: %s", channel.name)
                except Exception:
                    logger.exception("Failed to stop channel %s", channel.name)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Channel statistics."""
        return {
            "total_channels": len(self._channels),
            "running_channels": sum(1 for ch in self._channels.values() if ch.is_running),
            "total_messages": len(self._message_log),
            "channels": self.list_channels(),
        }
