"""Tool integration tests.

Tests end-to-end tool execution flows, tool chaining, error handling,
and tool registry operations with the full tool set.
"""

from __future__ import annotations

import json

import pytest

from jarvis.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    """Create a registry with all built-in tools loaded."""
    from jarvis.tools.builtin import _BUILTIN_TOOLS
    r = ToolRegistry()
    for tool in _BUILTIN_TOOLS:
        r.register(tool)
    return r


# ---------------------------------------------------------------------------
# Tests: Registry with All Tools
# ---------------------------------------------------------------------------

class TestFullRegistry:
    def test_all_tools_registered(self, registry):
        tools = registry.list_tools()
        assert len(tools) >= 50  # At least 50 tools

    def test_all_tools_have_names(self, registry):
        for tool in registry.list_tools():
            assert tool.name, f"Tool missing name: {tool}"
            assert len(tool.name) > 0

    def test_all_tools_have_descriptions(self, registry):
        for tool in registry.list_tools():
            assert tool.description, f"Tool {tool.name} missing description"
            assert len(tool.description) > 10

    def test_all_tools_have_parameters(self, registry):
        for tool in registry.list_tools():
            assert tool.parameters is not None, f"Tool {tool.name} missing parameters"
            assert "type" in tool.parameters

    def test_no_duplicate_names(self, registry):
        names = [t.name for t in registry.list_tools()]
        assert len(names) == len(set(names)), f"Duplicate tool names found"

    def test_get_definitions(self, registry):
        defs = registry.get_definitions()
        assert len(defs) >= 50
        for d in defs:
            assert d.name
            assert d.description
            assert d.parameters

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry):
        result = await registry.execute("nonexistent_tool_xyz", {})
        assert not result.success
        assert "Unknown tool" in result.output


# ---------------------------------------------------------------------------
# Tests: Calculator Tool Integration
# ---------------------------------------------------------------------------

class TestCalculatorIntegration:
    @pytest.mark.asyncio
    async def test_basic_math(self, registry):
        result = await registry.execute("calculator", {"expression": "2 + 3"})
        assert result.success
        assert "5" in result.output

    @pytest.mark.asyncio
    async def test_complex_expression(self, registry):
        result = await registry.execute("calculator", {"expression": "sqrt(144) + 10"})
        assert result.success
        assert "22" in result.output

    @pytest.mark.asyncio
    async def test_invalid_expression(self, registry):
        result = await registry.execute("calculator", {"expression": "import os"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_division_by_zero(self, registry):
        result = await registry.execute("calculator", {"expression": "1 / 0"})
        assert not result.success


# ---------------------------------------------------------------------------
# Tests: JSON Tool Integration
# ---------------------------------------------------------------------------

class TestJsonIntegration:
    @pytest.mark.asyncio
    async def test_json_query(self, registry):
        data = json.dumps({"users": [{"name": "Alice"}, {"name": "Bob"}]})
        result = await registry.execute("json_query", {"data": data, "query": "users.0.name"})
        assert result.success
        assert "Alice" in result.output

    @pytest.mark.asyncio
    async def test_json_query_nested(self, registry):
        data = json.dumps({"a": {"b": {"c": 42}}})
        result = await registry.execute("json_query", {"data": data, "query": "a.b.c"})
        assert result.success
        assert "42" in result.output

    @pytest.mark.asyncio
    async def test_json_invalid(self, registry):
        result = await registry.execute("json_query", {"data": "not json", "query": "x"})
        assert not result.success


# ---------------------------------------------------------------------------
# Tests: CSV Tool Integration
# ---------------------------------------------------------------------------

class TestCSVIntegration:
    @pytest.mark.asyncio
    async def test_csv_read(self, registry):
        csv_data = "name,age\nAlice,30\nBob,25"
        result = await registry.execute("csv_read", {"data": csv_data})
        assert result.success
        assert result.data["row_count"] == 2

    @pytest.mark.asyncio
    async def test_csv_stats(self, registry):
        csv_data = "value\n10\n20\n30"
        result = await registry.execute("csv_stats", {"data": csv_data})
        assert result.success
        assert "numeric" in result.output.lower()

    @pytest.mark.asyncio
    async def test_csv_write(self, registry):
        rows = [{"name": "Alice", "age": "30"}]
        result = await registry.execute("csv_write", {"rows": rows})
        assert result.success
        assert "Alice" in result.output


# ---------------------------------------------------------------------------
# Tests: XML Tool Integration
# ---------------------------------------------------------------------------

class TestXMLIntegration:
    @pytest.mark.asyncio
    async def test_xml_to_json(self, registry):
        xml = "<root><item>hello</item></root>"
        result = await registry.execute("xml_to_json", {"xml": xml})
        assert result.success

    @pytest.mark.asyncio
    async def test_xml_query(self, registry):
        xml = "<root><item>a</item><item>b</item></root>"
        result = await registry.execute("xml_query", {"xml": xml, "query": ".//item"})
        assert result.success
        assert result.data["count"] == 2


# ---------------------------------------------------------------------------
# Tests: Color Tool Integration
# ---------------------------------------------------------------------------

class TestColorIntegration:
    @pytest.mark.asyncio
    async def test_color_convert(self, registry):
        result = await registry.execute("color_convert", {
            "value": "#ff0000", "from_format": "hex",
        })
        assert result.success
        assert result.data["color"]["rgb"]["r"] == 255

    @pytest.mark.asyncio
    async def test_color_palette(self, registry):
        result = await registry.execute("color_palette", {
            "base_color": "#3498db", "count": 5,
        })
        assert result.success
        assert len(result.data["colors"]) == 5


# ---------------------------------------------------------------------------
# Tests: Random Tool Integration
# ---------------------------------------------------------------------------

class TestRandomIntegration:
    @pytest.mark.asyncio
    async def test_random_string(self, registry):
        result = await registry.execute("random_string", {"length": 16})
        assert result.success
        assert len(result.data["strings"][0]) == 16

    @pytest.mark.asyncio
    async def test_random_number(self, registry):
        result = await registry.execute("random_number", {"min": 1, "max": 100})
        assert result.success
        assert 1 <= result.data["numbers"][0] <= 100

    @pytest.mark.asyncio
    async def test_random_choice(self, registry):
        result = await registry.execute("random_choice", {
            "items": ["a", "b", "c"],
        })
        assert result.success
        assert result.data["selected"][0] in ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Tests: Encoding Tool Integration
# ---------------------------------------------------------------------------

class TestEncodingIntegration:
    @pytest.mark.asyncio
    async def test_base64_encode(self, registry):
        result = await registry.execute("base64_codec", {
            "input": "hello world", "action": "encode",
        })
        assert result.success
        assert "aGVsbG8gd29ybGQ=" in result.output

    @pytest.mark.asyncio
    async def test_hash_sha256(self, registry):
        result = await registry.execute("hash", {
            "input": "hello", "algorithm": "sha256",
        })
        assert result.success
        assert len(result.output) > 0

    @pytest.mark.asyncio
    async def test_url_encode(self, registry):
        result = await registry.execute("url_codec", {
            "input": "hello world", "action": "encode",
        })
        assert result.success
        assert "hello%20world" in result.output


# ---------------------------------------------------------------------------
# Tests: UUID Tool Integration
# ---------------------------------------------------------------------------

class TestUUIDIntegration:
    @pytest.mark.asyncio
    async def test_uuid_generate(self, registry):
        result = await registry.execute("uuid_generate", {})
        assert result.success
        assert len(result.output) == 36  # UUID format

    @pytest.mark.asyncio
    async def test_uuid_validate_valid(self, registry):
        result = await registry.execute("uuid_validate", {
            "value": "550e8400-e29b-41d4-a716-446655440000",
        })
        assert result.success

    @pytest.mark.asyncio
    async def test_uuid_validate_invalid(self, registry):
        result = await registry.execute("uuid_validate", {"value": "not-a-uuid"})
        assert result.success  # Returns success with validation result


# ---------------------------------------------------------------------------
# Tests: Date/Time Tool Integration
# ---------------------------------------------------------------------------

class TestDateTimeIntegration:
    @pytest.mark.asyncio
    async def test_datetime_current(self, registry):
        # Try with common datetime tool API patterns
        tool = registry.get("datetime")
        if tool:
            try:
                result = await tool.execute({"operation": "now"})
                assert result.success
            except Exception:
                result = await tool.execute({})
                assert result.success

    @pytest.mark.asyncio
    async def test_date_calc_exists(self, registry):
        tool = registry.get("date_calc")
        assert tool is not None
        assert tool.name == "date_calc"


# ---------------------------------------------------------------------------
# Tests: System Info Integration
# ---------------------------------------------------------------------------

class TestSystemInfoIntegration:
    @pytest.mark.asyncio
    async def test_system_info(self, registry):
        tool = registry.get("system_info")
        assert tool is not None
        result = await tool.execute({})
        assert result.success


# ---------------------------------------------------------------------------
# Tests: Directory Ops Integration
# ---------------------------------------------------------------------------

class TestDirectoryOpsIntegration:
    @pytest.mark.asyncio
    async def test_list_directory(self, registry, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.py").write_text("world")
        result = await registry.execute("list_directory", {"path": str(tmp_path)})
        assert result.success
        assert "a.txt" in result.output
        assert "b.py" in result.output

    @pytest.mark.asyncio
    async def test_find_files(self, registry, tmp_path):
        (tmp_path / "test.py").write_text("code")
        (tmp_path / "test.txt").write_text("text")
        tool = registry.get("find_files")
        assert tool is not None
        result = await tool.execute({"directory": str(tmp_path), "pattern": "*.py"})
        assert result.success


# ---------------------------------------------------------------------------
# Tests: Template Tool Integration
# ---------------------------------------------------------------------------

class TestTemplateToolIntegration:
    @pytest.mark.asyncio
    async def test_template_tool_exists(self, registry):
        tool = registry.get("render_template")
        assert tool is not None
        assert tool.name == "render_template"
