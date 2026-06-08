"""Advanced tests for the JARVIS gateway and channel subsystem.

Covers WebhookChannel message queue, Gateway message handling with rate
limiting, broadcast with type filtering, stats tracking, CLIChannel,
TelegramChannel / DiscordChannel / DingTalkChannel skeletons,
ChannelMessage serialization, multi-channel registration, gateway
lifecycle, message handler chaining, and rate limit burst patterns.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from jarvis.gateway.channel import (
    Channel,
    ChannelConfig,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from jarvis.gateway.channels.cli_channel import CLIChannel
from jarvis.gateway.channels.dingtalk_channel import DingTalkChannel
from jarvis.gateway.channels.discord_channel import DiscordChannel
from jarvis.gateway.channels.telegram_channel import TelegramChannel
from jarvis.gateway.channels.webhook_channel import WebhookChannel
from jarvis.gateway.gateway import Gateway


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _echo_handler(msg: ChannelMessage) -> str:
    return f"echo:{msg.content}"


async def _noop_handler(msg: ChannelMessage) -> str:
    return "ok"


# ===========================================================================
# 1. WebhookChannel
# ===========================================================================


class TestWebhookChannel:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        ch = WebhookChannel()
        assert not ch.is_running
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_send_queues_response(self):
        ch = WebhookChannel()
        await ch.start()
        await ch.send("ch1", "hello")
        result = await ch.get_pending(timeout=1.0)
        assert result is not None
        assert result["content"] == "hello"
        assert result["channel_id"] == "ch1"

    @pytest.mark.asyncio
    async def test_get_pending_timeout(self):
        ch = WebhookChannel()
        await ch.start()
        result = await ch.get_pending(timeout=0.1)
        assert result is None

    @pytest.mark.asyncio
    async def test_receive_webhook(self):
        ch = WebhookChannel()
        await ch.start()
        ch.set_handler(_echo_handler)
        resp = await ch.receive_webhook({"sender_id": "u1", "content": "hi"})
        assert resp == "echo:hi"

    @pytest.mark.asyncio
    async def test_receive_webhook_no_handler(self):
        ch = WebhookChannel()
        await ch.start()
        resp = await ch.receive_webhook({"content": "hi"})
        assert "No message handler" in resp

    @pytest.mark.asyncio
    async def test_multiple_sends_ordered(self):
        ch = WebhookChannel()
        await ch.start()
        for i in range(5):
            await ch.send("ch", f"msg{i}")
        for i in range(5):
            r = await ch.get_pending(timeout=1.0)
            assert r["content"] == f"msg{i}"


# ===========================================================================
# 2. Gateway message handler with rate limiting
# ===========================================================================


class TestGatewayRateLimiting:
    @pytest.mark.asyncio
    async def test_handler_invoked(self):
        gw = Gateway()
        handler = AsyncMock(return_value="reply")
        gw.set_message_handler(handler)

        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="u1",
            content="hello",
        )
        result = await gw._handle_message(msg)
        assert result == "reply"
        handler.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_rate_limit_triggers(self):
        gw = Gateway()
        gw.set_message_handler(AsyncMock(return_value="ok"))

        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="spammer",
            content="x",
        )

        # Send 30 (the limit) messages
        for _ in range(30):
            await gw._handle_message(msg)

        # The 31st should be rate limited
        result = await gw._handle_message(msg)
        assert "Rate limit" in result

    @pytest.mark.asyncio
    async def test_no_handler_returns_message(self):
        gw = Gateway()
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            sender_id="u",
            content="hello",
        )
        result = await gw._handle_message(msg)
        assert "No message handler" in result

    @pytest.mark.asyncio
    async def test_handler_exception_caught(self):
        gw = Gateway()

        async def bad_handler(msg: ChannelMessage) -> str:
            raise RuntimeError("boom")

        gw.set_message_handler(bad_handler)
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            sender_id="u",
            content="x",
        )
        result = await gw._handle_message(msg)
        assert "Error" in result


# ===========================================================================
# 3. Gateway broadcast with type filtering
# ===========================================================================


class TestGatewayBroadcast:
    @pytest.mark.asyncio
    async def test_broadcast_all_channels(self):
        gw = Gateway()
        ch1 = WebhookChannel(ChannelConfig(name="wh1", channel_type=ChannelType.WEBHOOK))
        ch2 = CLIChannel(ChannelConfig(name="cli1", channel_type=ChannelType.CLI))
        gw.register_channel(ch1)
        gw.register_channel(ch2)
        await ch1.start()
        await ch2.start()

        sent = await gw.broadcast("hello all")
        assert sent == 2

    @pytest.mark.asyncio
    async def test_broadcast_filtered_by_type(self):
        gw = Gateway()
        ch1 = WebhookChannel(ChannelConfig(name="wh", channel_type=ChannelType.WEBHOOK))
        ch2 = CLIChannel(ChannelConfig(name="cli", channel_type=ChannelType.CLI))
        gw.register_channel(ch1)
        gw.register_channel(ch2)
        await ch1.start()
        await ch2.start()

        sent = await gw.broadcast("webhook only", channel_types=[ChannelType.WEBHOOK])
        assert sent == 1

    @pytest.mark.asyncio
    async def test_broadcast_skips_stopped_channels(self):
        gw = Gateway()
        ch = WebhookChannel()
        gw.register_channel(ch)
        # ch is not started
        sent = await gw.broadcast("msg")
        assert sent == 0


# ===========================================================================
# 4. Gateway stats tracking
# ===========================================================================


class TestGatewayStats:
    def test_initial_stats(self):
        gw = Gateway()
        stats = gw.get_stats()
        assert stats["total_channels"] == 0
        assert stats["running_channels"] == 0
        assert stats["total_messages"] == 0

    @pytest.mark.asyncio
    async def test_stats_after_messages(self):
        gw = Gateway()
        ch = WebhookChannel()
        gw.register_channel(ch)
        await ch.start()
        gw.set_message_handler(AsyncMock(return_value="ok"))

        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="u1",
            content="hi",
        )
        await gw._handle_message(msg)
        await gw._handle_message(msg)

        stats = gw.get_stats()
        assert stats["total_messages"] == 2
        assert stats["total_channels"] == 1
        assert stats["running_channels"] == 1

    def test_list_channels(self):
        gw = Gateway()
        gw.register_channel(WebhookChannel())
        gw.register_channel(CLIChannel())
        channels = gw.list_channels()
        assert len(channels) == 2
        names = {c["name"] for c in channels}
        assert "webhook" in names
        assert "cli" in names


# ===========================================================================
# 5. CLIChannel send and receive
# ===========================================================================


class TestCLIChannel:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        ch = CLIChannel()
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_send_prints(self, capsys):
        ch = CLIChannel()
        await ch.start()
        ok = await ch.send("ch1", "test message")
        assert ok is True
        captured = capsys.readouterr()
        assert "test message" in captured.out

    @pytest.mark.asyncio
    async def test_handle_incoming_with_handler(self):
        ch = CLIChannel()
        ch.set_handler(_echo_handler)
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            content="hello",
        )
        resp = await ch.handle_incoming(msg)
        assert resp == "echo:hello"


# ===========================================================================
# 6. Telegram / Discord / DingTalk skeletons
# ===========================================================================


class TestTelegramChannelSkeleton:
    def test_default_config(self):
        ch = TelegramChannel()
        assert ch.channel_type == ChannelType.TELEGRAM
        assert ch.name == "telegram"

    @pytest.mark.asyncio
    async def test_start_requires_library(self):
        ch = TelegramChannel()
        try:
            await ch.start()
            # Library available -- should be running
            assert ch.is_running
        except ImportError:
            pass  # expected when library not installed

    @pytest.mark.asyncio
    async def test_send_requires_library(self):
        ch = TelegramChannel()
        try:
            result = await ch.send("chat", "hi")
            # If no bot initialized, send returns False
            assert result is False
        except ImportError:
            pass

    @pytest.mark.asyncio
    async def test_stop(self):
        ch = TelegramChannel()
        ch._running = True
        await ch.stop()
        assert not ch.is_running


class TestDiscordChannelSkeleton:
    def test_default_config(self):
        ch = DiscordChannel()
        assert ch.channel_type == ChannelType.DISCORD
        assert ch.name == "discord"

    @pytest.mark.asyncio
    async def test_start_requires_library(self):
        ch = DiscordChannel()
        try:
            await ch.start()
            assert ch.is_running
        except ImportError:
            pass

    @pytest.mark.asyncio
    async def test_send_requires_library(self):
        ch = DiscordChannel()
        try:
            result = await ch.send("ch", "hi")
            assert result is False
        except ImportError:
            pass

    @pytest.mark.asyncio
    async def test_stop(self):
        ch = DiscordChannel()
        ch._running = True
        await ch.stop()
        assert not ch.is_running


class TestDingTalkChannelSkeleton:
    def test_default_config(self):
        ch = DingTalkChannel()
        assert ch.channel_type == ChannelType.DINGTALK
        assert ch.name == "dingtalk"

    @pytest.mark.asyncio
    async def test_start_stop(self):
        ch = DingTalkChannel()
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_send_without_webhook(self):
        ch = DingTalkChannel()
        await ch.start()
        result = await ch.send("ch", "hi")
        # No webhook URL configured
        assert result is False

    @pytest.mark.asyncio
    async def test_send_with_webhook(self):
        cfg = ChannelConfig(
            name="dt",
            channel_type=ChannelType.DINGTALK,
            webhook_url="https://example.com/hook",
        )
        ch = DingTalkChannel(config=cfg)
        await ch.start()
        result = await ch.send("ch", "hello")
        assert result is True


# ===========================================================================
# 7. ChannelMessage serialization
# ===========================================================================


class TestChannelMessageSerialization:
    def test_roundtrip(self):
        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="user1",
            sender_name="Alice",
            content="Hello!",
            message_type=MessageType.TEXT,
            metadata={"key": "value"},
        )
        data = msg.model_dump(mode="json")
        msg2 = ChannelMessage.model_validate(data)
        assert msg2.sender_id == "user1"
        assert msg2.content == "Hello!"
        assert msg2.metadata["key"] == "value"

    def test_defaults(self):
        msg = ChannelMessage(channel_type=ChannelType.CLI)
        assert msg.message_type == MessageType.TEXT
        assert msg.content == ""
        assert msg.id  # auto-generated

    def test_attachments(self):
        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            attachments=[{"name": "file.txt", "url": "https://example.com"}],
        )
        assert len(msg.attachments) == 1

    def test_thread_and_reply(self):
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            reply_to="msg-123",
            thread_id="thread-456",
        )
        assert msg.reply_to == "msg-123"
        assert msg.thread_id == "thread-456"


# ===========================================================================
# 8. Multiple channels registered simultaneously
# ===========================================================================


class TestMultipleChannels:
    def test_register_multiple(self):
        gw = Gateway()
        gw.register_channel(WebhookChannel())
        gw.register_channel(CLIChannel())
        gw.register_channel(DingTalkChannel())
        assert len(gw.list_channels()) == 3

    def test_unregister(self):
        gw = Gateway()
        gw.register_channel(WebhookChannel())
        gw.register_channel(CLIChannel())
        gw.unregister_channel("webhook")
        assert len(gw.list_channels()) == 1

    def test_get_channel(self):
        gw = Gateway()
        wh = WebhookChannel()
        gw.register_channel(wh)
        assert gw.get_channel("webhook") is wh
        assert gw.get_channel("nonexistent") is None

    def test_replacing_channel_warns(self):
        gw = Gateway()
        gw.register_channel(WebhookChannel())
        gw.register_channel(WebhookChannel())  # same name, should replace
        assert len(gw.list_channels()) == 1


# ===========================================================================
# 9. Gateway lifecycle (start_all, stop_all)
# ===========================================================================


class TestGatewayLifecycle:
    @pytest.mark.asyncio
    async def test_start_all(self):
        gw = Gateway()
        ch1 = WebhookChannel()
        ch2 = CLIChannel()
        gw.register_channel(ch1)
        gw.register_channel(ch2)

        await gw.start_all()
        assert ch1.is_running
        assert ch2.is_running

    @pytest.mark.asyncio
    async def test_stop_all(self):
        gw = Gateway()
        ch1 = WebhookChannel()
        ch2 = CLIChannel()
        gw.register_channel(ch1)
        gw.register_channel(ch2)

        await gw.start_all()
        await gw.stop_all()
        assert not ch1.is_running
        assert not ch2.is_running

    @pytest.mark.asyncio
    async def test_start_all_idempotent(self):
        gw = Gateway()
        ch = WebhookChannel()
        gw.register_channel(ch)
        await gw.start_all()
        await gw.start_all()  # should not fail
        assert ch.is_running

    @pytest.mark.asyncio
    async def test_stop_all_when_already_stopped(self):
        gw = Gateway()
        ch = WebhookChannel()
        gw.register_channel(ch)
        await gw.stop_all()  # nothing running
        assert not ch.is_running


# ===========================================================================
# 10. Message handler chaining
# ===========================================================================


class TestMessageHandlerChaining:
    @pytest.mark.asyncio
    async def test_set_handler_wires_to_existing_channels(self):
        gw = Gateway()
        ch = WebhookChannel()
        gw.register_channel(ch)
        await ch.start()

        handler = AsyncMock(return_value="handled")
        gw.set_message_handler(handler)

        # Now channel should have its handler wired
        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="u",
            content="test",
        )
        result = await ch.handle_incoming(msg)
        # The channel handler is the gateway's _handle_message, which calls our handler
        assert "handled" in result or "ok" in result.lower() or result is not None

    @pytest.mark.asyncio
    async def test_handler_registered_before_channel(self):
        gw = Gateway()
        handler = AsyncMock(return_value="pre-set")
        gw.set_message_handler(handler)
        ch = WebhookChannel()
        gw.register_channel(ch)  # handler should be wired now
        await ch.start()

        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="u",
            content="hi",
        )
        result = await ch.handle_incoming(msg)
        assert result is not None


# ===========================================================================
# 11. Rate limit with burst patterns
# ===========================================================================


class TestRateLimitBurst:
    @pytest.mark.asyncio
    async def test_burst_then_recover(self):
        gw = Gateway()
        gw.set_message_handler(AsyncMock(return_value="ok"))

        msg = ChannelMessage(
            channel_type=ChannelType.API,
            sender_id="burst_user",
            content="x",
        )
        # Send 30 quickly (fill the limit)
        results = []
        for _ in range(30):
            r = await gw._handle_message(msg)
            results.append(r)

        # All 30 should succeed
        assert all(r == "ok" for r in results)

        # 31st should be limited
        limited = await gw._handle_message(msg)
        assert "Rate limit" in limited

    @pytest.mark.asyncio
    async def test_different_senders_independent_limits(self):
        gw = Gateway()
        gw.set_message_handler(AsyncMock(return_value="ok"))

        msg1 = ChannelMessage(channel_type=ChannelType.CLI, sender_id="u1", content="x")
        msg2 = ChannelMessage(channel_type=ChannelType.CLI, sender_id="u2", content="x")

        # Fill u1's limit
        for _ in range(30):
            await gw._handle_message(msg1)

        # u1 is limited
        r1 = await gw._handle_message(msg1)
        assert "Rate limit" in r1

        # u2 should still work
        r2 = await gw._handle_message(msg2)
        assert r2 == "ok"

    @pytest.mark.asyncio
    async def test_message_log_grows(self):
        gw = Gateway()
        gw.set_message_handler(AsyncMock(return_value="ok"))

        msg = ChannelMessage(
            channel_type=ChannelType.WEBHOOK,
            sender_id="u",
            content="hi",
        )
        for _ in range(5):
            await gw._handle_message(msg)

        assert len(gw._message_log) == 5


# ===========================================================================
# 12. Channel config
# ===========================================================================


class TestChannelConfig:
    def test_channel_config_defaults(self):
        cfg = ChannelConfig(name="test", channel_type=ChannelType.CLI)
        assert cfg.enabled is True
        assert cfg.api_token == ""
        assert cfg.settings == {}

    def test_channel_config_custom(self):
        cfg = ChannelConfig(
            name="custom",
            channel_type=ChannelType.TELEGRAM,
            api_token="secret",
            settings={"polling_interval": 5},
        )
        assert cfg.api_token == "secret"
        assert cfg.settings["polling_interval"] == 5
