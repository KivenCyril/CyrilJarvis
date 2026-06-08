"""Tests for the Plugin system."""

from __future__ import annotations

from typing import Any, Callable

import pytest

from jarvis.gateway.channel import Channel, ChannelConfig, ChannelType
from jarvis.gateway.channels.cli_channel import CLIChannel
from jarvis.plugins.base import Plugin, PluginHook, PluginMetadata
from jarvis.plugins.manager import PluginManager
from jarvis.tools.base import BaseTool, ToolResult


# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------

class SamplePlugin(Plugin):
    """A simple plugin for testing."""

    def __init__(self, name: str = "sample", hooks: dict | None = None):
        self._metadata = PluginMetadata(
            name=name,
            version="0.1.0",
            description="A test plugin",
            author="test",
        )
        self._hooks = hooks or {}
        self.loaded = False
        self.unloaded = False

    @property
    def metadata(self) -> PluginMetadata:
        return self._metadata

    async def on_load(self) -> None:
        self.loaded = True

    async def on_unload(self) -> None:
        self.unloaded = True

    def get_hooks(self) -> dict[PluginHook, Callable[..., Any]]:
        return self._hooks


class SampleTool(BaseTool):
    name = "sample_tool"
    description = "A test tool"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output="sample output")


class ToolPlugin(Plugin):
    """Plugin that provides a tool."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="tool-plugin", version="1.0.0")

    def get_tools(self) -> list[BaseTool]:
        return [SampleTool()]


class ChannelPlugin(Plugin):
    """Plugin that provides a channel."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(name="channel-plugin", version="1.0.0")

    def get_channels(self) -> list[Channel]:
        return [CLIChannel(ChannelConfig(name="plugin-cli", channel_type=ChannelType.CLI))]


# ---------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------

class TestPluginLifecycle:
    @pytest.mark.asyncio
    async def test_load_and_unload(self):
        mgr = PluginManager()
        plugin = SamplePlugin()

        await mgr.load(plugin)
        assert plugin.loaded
        assert mgr.get("sample") is plugin

        await mgr.unload("sample")
        assert plugin.unloaded
        assert mgr.get("sample") is None

    @pytest.mark.asyncio
    async def test_duplicate_load(self):
        mgr = PluginManager()
        plugin = SamplePlugin()
        await mgr.load(plugin)
        # Loading again should be silently skipped
        await mgr.load(plugin)
        assert len(mgr.list_plugins()) == 1

    @pytest.mark.asyncio
    async def test_unload_nonexistent(self):
        mgr = PluginManager()
        # Should not raise
        await mgr.unload("nonexistent")

    @pytest.mark.asyncio
    async def test_list_plugins(self):
        mgr = PluginManager()
        await mgr.load(SamplePlugin("alpha"))
        await mgr.load(SamplePlugin("beta"))
        plugins = mgr.list_plugins()
        assert len(plugins) == 2
        names = {p["name"] for p in plugins}
        assert names == {"alpha", "beta"}

    @pytest.mark.asyncio
    async def test_dependency_check(self):
        mgr = PluginManager()
        dep_plugin = SamplePlugin("child")
        dep_plugin._metadata.dependencies = ["parent"]

        with pytest.raises(RuntimeError, match="depends on 'parent'"):
            await mgr.load(dep_plugin)

    @pytest.mark.asyncio
    async def test_dependency_satisfied(self):
        mgr = PluginManager()
        parent = SamplePlugin("parent")
        child = SamplePlugin("child")
        child._metadata.dependencies = ["parent"]

        await mgr.load(parent)
        await mgr.load(child)
        assert mgr.get("child") is child


# ---------------------------------------------------------------
# Hook dispatch
# ---------------------------------------------------------------

class TestPluginHooks:
    @pytest.mark.asyncio
    async def test_sync_hook(self):
        calls: list[str] = []

        def on_message(**kwargs: Any) -> str:
            calls.append(kwargs.get("content", ""))
            return "processed"

        plugin = SamplePlugin(hooks={PluginHook.ON_MESSAGE: on_message})
        mgr = PluginManager()
        await mgr.load(plugin)

        results = await mgr.emit(PluginHook.ON_MESSAGE, content="hello")
        assert results == ["processed"]
        assert calls == ["hello"]

    @pytest.mark.asyncio
    async def test_async_hook(self):
        async def on_startup(**kwargs: Any) -> str:
            return "started"

        plugin = SamplePlugin(hooks={PluginHook.ON_STARTUP: on_startup})
        mgr = PluginManager()
        await mgr.load(plugin)

        results = await mgr.emit(PluginHook.ON_STARTUP)
        assert results == ["started"]

    @pytest.mark.asyncio
    async def test_multiple_hooks(self):
        results_a: list[str] = []
        results_b: list[str] = []

        def hook_a(**kwargs: Any) -> None:
            results_a.append("a")

        def hook_b(**kwargs: Any) -> None:
            results_b.append("b")

        pa = SamplePlugin("pa", hooks={PluginHook.ON_MESSAGE: hook_a})
        pb = SamplePlugin("pb", hooks={PluginHook.ON_MESSAGE: hook_b})

        mgr = PluginManager()
        await mgr.load(pa)
        await mgr.load(pb)

        await mgr.emit(PluginHook.ON_MESSAGE)
        assert results_a == ["a"]
        assert results_b == ["b"]

    @pytest.mark.asyncio
    async def test_hook_error_doesnt_break_others(self):
        def bad_hook(**kwargs: Any) -> None:
            raise ValueError("boom")

        def good_hook(**kwargs: Any) -> str:
            return "ok"

        pa = SamplePlugin("bad", hooks={PluginHook.ON_MESSAGE: bad_hook})
        pb = SamplePlugin("good", hooks={PluginHook.ON_MESSAGE: good_hook})

        mgr = PluginManager()
        await mgr.load(pa)
        await mgr.load(pb)

        results = await mgr.emit(PluginHook.ON_MESSAGE)
        # bad_hook's exception is logged but good_hook still runs
        assert results == ["ok"]

    @pytest.mark.asyncio
    async def test_hooks_removed_on_unload(self):
        def on_msg(**kwargs: Any) -> str:
            return "still here"

        plugin = SamplePlugin(hooks={PluginHook.ON_MESSAGE: on_msg})
        mgr = PluginManager()
        await mgr.load(plugin)
        await mgr.unload("sample")

        results = await mgr.emit(PluginHook.ON_MESSAGE)
        assert results == []

    @pytest.mark.asyncio
    async def test_emit_unused_hook(self):
        mgr = PluginManager()
        results = await mgr.emit(PluginHook.ON_SHUTDOWN)
        assert results == []


# ---------------------------------------------------------------
# Tool and Channel provision
# ---------------------------------------------------------------

class TestPluginProvision:
    def test_plugin_provides_tools(self):
        plugin = ToolPlugin()
        tools = plugin.get_tools()
        assert len(tools) == 1
        assert tools[0].name == "sample_tool"

    def test_plugin_provides_channels(self):
        plugin = ChannelPlugin()
        channels = plugin.get_channels()
        assert len(channels) == 1
        assert channels[0].name == "plugin-cli"
        assert channels[0].channel_type == ChannelType.CLI

    def test_base_plugin_empty_tools_and_channels(self):
        plugin = SamplePlugin()
        assert plugin.get_tools() == []
        assert plugin.get_channels() == []
