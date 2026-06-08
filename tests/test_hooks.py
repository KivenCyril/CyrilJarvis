from __future__ import annotations

import pytest

from jarvis.hooks.engine import HookEngine, HookEvent


class TestHookEngine:
    @pytest.fixture
    def engine(self):
        return HookEngine()

    @pytest.mark.asyncio
    async def test_emit_and_handle(self, engine: HookEngine):
        received = []

        async def handler(event: HookEvent):
            received.append(event)

        engine.on("test.event", handler)
        await engine.emit(HookEvent(source="test", event_type="test.event", payload={"key": "value"}))

        assert len(received) == 1
        assert received[0].payload["key"] == "value"

    @pytest.mark.asyncio
    async def test_wildcard_handler(self, engine: HookEngine):
        received = []

        async def handler(event: HookEvent):
            received.append(event)

        engine.on("*", handler)
        await engine.emit(HookEvent(source="a", event_type="any.event"))
        await engine.emit(HookEvent(source="b", event_type="other.event"))

        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_no_handler(self, engine: HookEngine):
        # Should not raise
        await engine.emit(HookEvent(source="test", event_type="unhandled"))

    @pytest.mark.asyncio
    async def test_handler_exception_isolated(self, engine: HookEngine):
        results = []

        async def bad_handler(event: HookEvent):
            raise RuntimeError("boom")

        async def good_handler(event: HookEvent):
            results.append("ok")

        engine.on("test", bad_handler)
        engine.on("test", good_handler)
        await engine.emit(HookEvent(source="t", event_type="test"))

        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_off(self, engine: HookEngine):
        received = []

        async def handler(event: HookEvent):
            received.append(event)

        engine.on("test", handler)
        engine.off("test", handler)
        await engine.emit(HookEvent(source="t", event_type="test"))
        assert len(received) == 0

    def test_add_cron(self, engine: HookEngine):
        async def handler(event: HookEvent):
            pass

        job = engine.add_cron("test-job", 60, handler)
        assert job.name == "test-job"
        assert len(engine.list_cron_jobs()) == 1

    def test_remove_cron(self, engine: HookEngine):
        async def handler(event: HookEvent):
            pass

        engine.add_cron("test-job", 60, handler)
        engine.remove_cron("test-job")
        assert len(engine.list_cron_jobs()) == 0

    @pytest.mark.asyncio
    async def test_event_log(self, engine: HookEngine):
        await engine.emit(HookEvent(source="a", event_type="e1"))
        await engine.emit(HookEvent(source="b", event_type="e2"))
        log = engine.event_log()
        assert len(log) == 2

    def test_registered_events(self, engine: HookEngine):
        async def handler(event: HookEvent):
            pass

        engine.on("event.a", handler)
        engine.on("event.b", handler)
        events = engine.registered_events()
        assert "event.a" in events
        assert "event.b" in events
