from __future__ import annotations

import pytest
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult
from jarvis.tools.registry import ToolRegistry


class EchoTool(BaseTool):
    name = "echo"
    description = "Echo the input"
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=arguments["text"])


class FailTool(BaseTool):
    name = "fail"
    description = "Always fails"
    parameters: dict[str, Any] = {"type": "object", "properties": {}}

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise RuntimeError("intentional failure")


class TestToolRegistry:
    @pytest.fixture
    def registry(self):
        r = ToolRegistry()
        r.register(EchoTool())
        return r

    def test_register_and_get(self, registry: ToolRegistry):
        tool = registry.get("echo")
        assert tool is not None
        assert tool.name == "echo"

    def test_register_duplicate_raises(self, registry: ToolRegistry):
        with pytest.raises(ValueError, match="already registered"):
            registry.register(EchoTool())

    def test_list_tools(self, registry: ToolRegistry):
        assert len(registry.list_tools()) == 1

    def test_get_definitions(self, registry: ToolRegistry):
        defs = registry.get_definitions()
        assert len(defs) == 1
        assert defs[0].name == "echo"

    @pytest.mark.asyncio
    async def test_execute(self, registry: ToolRegistry):
        result = await registry.execute("echo", {"text": "hello"})
        assert result.success
        assert result.output == "hello"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry: ToolRegistry):
        result = await registry.execute("nonexistent", {})
        assert not result.success
        assert "Unknown tool" in result.output

    @pytest.mark.asyncio
    async def test_execute_error_handled(self):
        r = ToolRegistry()
        r.register(FailTool())
        result = await r.execute("fail", {})
        assert not result.success
        assert "Tool error" in result.output

    def test_to_llm_definition(self):
        tool = EchoTool()
        defn = tool.to_llm_definition()
        assert defn.name == "echo"
        assert defn.description == "Echo the input"
        assert "properties" in defn.parameters


class TestShellTool:
    @pytest.mark.asyncio
    async def test_shell_echo(self):
        from jarvis.tools.builtin.shell import ShellTool
        tool = ShellTool()
        result = await tool.execute({"command": "echo hello"})
        assert result.success
        assert "hello" in result.output

    @pytest.mark.asyncio
    async def test_shell_blocked_command(self):
        from jarvis.tools.builtin.shell import ShellTool
        tool = ShellTool()
        result = await tool.execute({"command": "rm -rf /"})
        assert not result.success
        assert "Blocked" in result.output

    @pytest.mark.asyncio
    async def test_shell_timeout(self):
        from jarvis.tools.builtin.shell import ShellTool
        tool = ShellTool()
        result = await tool.execute({"command": "sleep 10", "timeout": 1})
        assert not result.success
        assert "timed out" in result.output


class TestFileTools:
    @pytest.mark.asyncio
    async def test_read_write_roundtrip(self, tmp_path):
        from jarvis.tools.builtin.file_ops import ReadFileTool, WriteFileTool

        test_file = str(tmp_path / "test.txt")
        write_tool = WriteFileTool()
        result = await write_tool.execute({"path": test_file, "content": "hello world"})
        assert result.success

        read_tool = ReadFileTool()
        result = await read_tool.execute({"path": test_file})
        assert result.success
        assert "hello world" in result.output

    @pytest.mark.asyncio
    async def test_read_nonexistent(self):
        from jarvis.tools.builtin.file_ops import ReadFileTool
        tool = ReadFileTool()
        result = await tool.execute({"path": "/nonexistent/file.txt"})
        assert not result.success


class TestPythonExecTool:
    @pytest.mark.asyncio
    async def test_python_exec(self):
        from jarvis.tools.builtin.python_exec import PythonExecTool
        tool = PythonExecTool()
        result = await tool.execute({"code": "print(2 + 3)"})
        assert result.success
        assert "5" in result.output
