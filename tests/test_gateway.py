"""Tests for the Gateway and Channel system."""

from __future__ import annotations

import asyncio
import time

import pytest

from jarvis.gateway.channel import (
    Channel,
    ChannelConfig,
    ChannelMessage,
    ChannelType,
    MessageType,
)
from jarvis.gateway.channels.cli_channel import CLIChannel
from jarvis.gateway.channels.webhook_channel import WebhookChannel
from jarvis.gateway.gateway import Gateway


# ---------------------------------------------------------------
# ChannelMessage
# ---------------------------------------------------------------

class TestChannelMessage:
    def test_create_basic_message(self):
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            content="hello",
        )
        assert msg.channel_type == ChannelType.CLI
        assert msg.content == "hello"
        assert msg.message_type == MessageType.TEXT
        assert len(msg.id) == 12

    def test_message_defaults(self):
        msg = ChannelMessage(channel_type=ChannelType.WEB)
        assert msg.sender_id == ""
        assert msg.content == ""
        assert msg.metadata == {}
        assert msg.attachments == []
        assert msg.reply_to is None
        assert msg.thread_id is None

    def test_message_with_all_fields(self):
        msg = ChannelMessage(
            channel_type=ChannelType.TELEGRAM,
            channel_id="chat_123",
            sender_id="user_456",
            sender_name="Alice",
            content="look at this",
            message_type=MessageType.IMAGE,
            metadata={"source": "telegram"},
            attachments=[{"url": "https://img.example.com/a.png"}],
            reply_to="msg_789",
            thread_id="thread_001",
        )
        assert msg.sender_name == "Alice"
        assert msg.message_type == MessageType.IMAGE
        assert msg.attachments[0]["url"] == "https://img.example.com/a.png"
        assert msg.reply_to == "msg_789"


# ---------------------------------------------------------------
# CLIChannel
# ---------------------------------------------------------------

class TestCLIChannel:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        ch = CLIChannel()
        assert not ch.is_running
        await ch.start()
        assert ch.is_running
        await ch.stop()
        assert not ch.is_running

    @pytest.mark.asyncio
    async def test_send(self, capsys):
        ch = CLIChannel()
        result = await ch.send("user1", "Hello from JARVIS")
        assert result is True
        captured = capsys.readouterr()
        assert "[JARVIS] Hello from JARVIS" in captured.out

    @pytest.mark.asyncio
    async def test_handle_incoming_no_handler(self):
        ch = CLIChannel()
        msg = ChannelMessage(channel_type=ChannelType.CLI, content="hi")
        resp = await ch.handle_incoming(msg)
        assert resp == "No message handler configured"

    @pytest.mark.asyncio
    async def test_handle_incoming_with_handler(self):
        ch = CLIChannel()

        async def handler(message: ChannelMessage) -> str:
            return f"echo: {message.content}"

        ch.set_handler(handler)
        msg = ChannelMessage(channel_type=ChannelType.CLI, content="ping")
        resp = await ch.handle_incoming(msg)
        assert resp == "echo: ping"


# ---------------------------------------------------------------
# Gateway
# ---------------------------------------------------------------

class TestGateway:
    def test_register_channel(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)
        assert gw.get_channel("cli") is ch
        channels = gw.list_channels()
        assert len(channels) == 1
        assert channels[0]["name"] == "cli"
        assert channels[0]["type"] == "cli"
        assert channels[0]["status"] == "stopped"

    def test_unregister_channel(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)
        gw.unregister_channel("cli")
        assert gw.get_channel("cli") is None
        assert gw.list_channels() == []

    def test_get_channel_missing(self):
        gw = Gateway()
        assert gw.get_channel("nonexistent") is None

    @pytest.mark.asyncio
    async def test_message_handling(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)

        async def handler(message: ChannelMessage) -> str:
            return f"handled: {message.content}"

        gw.set_message_handler(handler)

        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            sender_id="user1",
            content="test message",
        )
        resp = await gw._handle_message(msg)
        assert resp == "handled: test message"

    @pytest.mark.asyncio
    async def test_message_logging(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)

        async def handler(msg: ChannelMessage) -> str:
            return "ok"

        gw.set_message_handler(handler)

        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            sender_id="user1",
            content="log me",
        )
        await gw._handle_message(msg)
        assert len(gw._message_log) == 1
        assert gw._message_log[0].content == "log me"

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)

        async def handler(msg: ChannelMessage) -> str:
            return "ok"

        gw.set_message_handler(handler)

        # Send 30 messages (at the limit)
        for i in range(30):
            msg = ChannelMessage(
                channel_type=ChannelType.CLI,
                sender_id="spammer",
                content=f"msg {i}",
            )
            resp = await gw._handle_message(msg)
            assert resp == "ok"

        # 31st should be rate limited
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            sender_id="spammer",
            content="one too many",
        )
        resp = await gw._handle_message(msg)
        assert "Rate limit" in resp

    @pytest.mark.asyncio
    async def test_no_handler(self):
        gw = Gateway()
        msg = ChannelMessage(
            channel_type=ChannelType.CLI,
            sender_id="user1",
            content="no handler",
        )
        resp = await gw._handle_message(msg)
        assert resp == "No message handler configured"

    @pytest.mark.asyncio
    async def test_broadcast(self):
        gw = Gateway()
        ch1 = CLIChannel(ChannelConfig(name="cli1", channel_type=ChannelType.CLI))
        ch2 = CLIChannel(ChannelConfig(name="cli2", channel_type=ChannelType.CLI))
        gw.register_channel(ch1)
        gw.register_channel(ch2)

        await gw.start_all()
        sent = await gw.broadcast("hello everyone")
        assert sent == 2
        await gw.stop_all()

    @pytest.mark.asyncio
    async def test_broadcast_filtered(self):
        gw = Gateway()
        ch_cli = CLIChannel(ChannelConfig(name="cli1", channel_type=ChannelType.CLI))
        ch_web = WebhookChannel(
            ChannelConfig(name="webhook1", channel_type=ChannelType.WEBHOOK)
        )
        gw.register_channel(ch_cli)
        gw.register_channel(ch_web)

        await gw.start_all()
        sent = await gw.broadcast("cli only", channel_types=[ChannelType.CLI])
        assert sent == 1
        await gw.stop_all()

    @pytest.mark.asyncio
    async def test_start_stop_all(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)
        assert not ch.is_running
        await gw.start_all()
        assert ch.is_running
        await gw.stop_all()
        assert not ch.is_running

    def test_get_stats(self):
        gw = Gateway()
        ch = CLIChannel()
        gw.register_channel(ch)
        stats = gw.get_stats()
        assert stats["total_channels"] == 1
        assert stats["running_channels"] == 0
        assert stats["total_messages"] == 0


# ---------------------------------------------------------------
# WebhookChannel
# ---------------------------------------------------------------

class TestWebhookChannel:
    @pytest.mark.asyncio
    async def test_receive_webhook(self):
        ch = WebhookChannel()

        async def handler(msg: ChannelMessage) -> str:
            return f"got: {msg.content}"

        ch.set_handler(handler)

        resp = await ch.receive_webhook({
            "sender_id": "user1",
            "content": "webhook test",
        })
        assert resp == "got: webhook test"

    @pytest.mark.asyncio
    async def test_send_queues_response(self):
        ch = WebhookChannel()
        await ch.send("chan1", "queued response")
        result = await ch.get_pending(timeout=1.0)
        assert result is not None
        assert result["content"] == "queued response"

    @pytest.mark.asyncio
    async def test_get_pending_timeout(self):
        ch = WebhookChannel()
        result = await ch.get_pending(timeout=0.1)
        assert result is None
