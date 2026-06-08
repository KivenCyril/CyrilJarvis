"""Tests for batch 3 tools: cron_ops, markdown_ops, jwt_ops, env_ops, uuid_ops."""

from __future__ import annotations

import base64
import json
import os
import uuid

import pytest

from jarvis.tools.base import ToolResult


# ============================================================================
# Cron Operations
# ============================================================================

class TestCronParseTool:
    @pytest.mark.asyncio
    async def test_every_minute(self):
        from jarvis.tools.builtin.cron_ops import CronParseTool
        tool = CronParseTool()
        result = await tool.execute({"expression": "* * * * *"})
        assert result.success
        assert result.data is not None
        assert result.data["expression"] == "* * * * *"
        assert "every" in result.data["description"].lower()

    @pytest.mark.asyncio
    async def test_specific_time(self):
        from jarvis.tools.builtin.cron_ops import CronParseTool
        tool = CronParseTool()
        result = await tool.execute({"expression": "0 9 * * 1-5"})
        assert result.success
        assert len(result.data["fields"]) == 5

    @pytest.mark.asyncio
    async def test_next_runs_computed(self):
        from jarvis.tools.builtin.cron_ops import CronParseTool
        tool = CronParseTool()
        result = await tool.execute({"expression": "0 * * * *"})
        assert result.success
        assert len(result.data["next_runs"]) > 0

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        from jarvis.tools.builtin.cron_ops import CronParseTool
        tool = CronParseTool()
        result = await tool.execute({"expression": "invalid"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_too_few_fields(self):
        from jarvis.tools.builtin.cron_ops import CronParseTool
        tool = CronParseTool()
        result = await tool.execute({"expression": "0 9 *"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_step_expression(self):
        from jarvis.tools.builtin.cron_ops import CronParseTool
        tool = CronParseTool()
        result = await tool.execute({"expression": "*/15 * * * *"})
        assert result.success
        assert "15" in result.output


class TestCronValidateTool:
    @pytest.mark.asyncio
    async def test_valid_expression(self):
        from jarvis.tools.builtin.cron_ops import CronValidateTool
        tool = CronValidateTool()
        result = await tool.execute({"expression": "0 9 * * 1-5"})
        assert result.success
        assert result.data["valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        from jarvis.tools.builtin.cron_ops import CronValidateTool
        tool = CronValidateTool()
        result = await tool.execute({"expression": "60 25 32 13 8"})
        assert result.success
        assert result.data["valid"] is False

    @pytest.mark.asyncio
    async def test_wrong_field_count(self):
        from jarvis.tools.builtin.cron_ops import CronValidateTool
        tool = CronValidateTool()
        result = await tool.execute({"expression": "* *"})
        assert result.success
        assert result.data["valid"] is False

    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.cron_ops import CronValidateTool
        tool = CronValidateTool()
        assert tool.name == "cron_validate"
        defn = tool.to_llm_definition()
        assert "expression" in defn.parameters["properties"]


# ============================================================================
# Markdown Operations
# ============================================================================

class TestMarkdownToHTMLTool:
    @pytest.mark.asyncio
    async def test_heading(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool
        tool = MarkdownToHTMLTool()
        result = await tool.execute({"markdown": "# Hello World"})
        assert result.success
        assert "<h1>Hello World</h1>" in result.output

    @pytest.mark.asyncio
    async def test_bold_and_italic(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool
        tool = MarkdownToHTMLTool()
        result = await tool.execute({"markdown": "**bold** and *italic*"})
        assert result.success
        assert "<strong>bold</strong>" in result.output
        assert "<em>italic</em>" in result.output

    @pytest.mark.asyncio
    async def test_link(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool
        tool = MarkdownToHTMLTool()
        result = await tool.execute({"markdown": "[Click](https://example.com)"})
        assert result.success
        assert '<a href="https://example.com">Click</a>' in result.output

    @pytest.mark.asyncio
    async def test_unordered_list(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool
        tool = MarkdownToHTMLTool()
        result = await tool.execute({"markdown": "- item 1\n- item 2"})
        assert result.success
        assert "<ul>" in result.output
        assert "<li>item 1</li>" in result.output

    @pytest.mark.asyncio
    async def test_code_block(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool
        tool = MarkdownToHTMLTool()
        result = await tool.execute({"markdown": "```python\nprint('hello')\n```"})
        assert result.success
        assert "<pre><code" in result.output
        assert "print" in result.output

    @pytest.mark.asyncio
    async def test_inline_code(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownToHTMLTool
        tool = MarkdownToHTMLTool()
        result = await tool.execute({"markdown": "Use `pip install` to install."})
        assert result.success
        assert "<code>pip install</code>" in result.output


class TestMarkdownTableTool:
    @pytest.mark.asyncio
    async def test_basic_table(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownTableTool
        tool = MarkdownTableTool()
        result = await tool.execute({
            "headers": ["Name", "Age"],
            "rows": [["Alice", "30"], ["Bob", "25"]],
        })
        assert result.success
        assert "Name" in result.output
        assert "Alice" in result.output
        assert "|" in result.output
        assert result.data["columns"] == 2
        assert result.data["rows"] == 2

    @pytest.mark.asyncio
    async def test_empty_headers(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownTableTool
        tool = MarkdownTableTool()
        result = await tool.execute({"headers": [], "rows": []})
        assert not result.success

    @pytest.mark.asyncio
    async def test_alignment_center(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownTableTool
        tool = MarkdownTableTool()
        result = await tool.execute({
            "headers": ["Col"],
            "rows": [["val"]],
            "alignment": "center",
        })
        assert result.success
        assert ":" in result.output  # center alignment uses colons

    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.markdown_ops import MarkdownTableTool
        tool = MarkdownTableTool()
        assert tool.name == "markdown_table"
        defn = tool.to_llm_definition()
        assert "headers" in defn.parameters["properties"]
        assert "rows" in defn.parameters["properties"]


# ============================================================================
# JWT Operations
# ============================================================================

def _make_jwt(header: dict, payload: dict, sig: str = "fakesig") -> str:
    """Create a fake JWT for testing."""
    h = base64.urlsafe_b64encode(json.dumps(header).encode()).rstrip(b"=").decode()
    p = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    s = base64.urlsafe_b64encode(sig.encode()).rstrip(b"=").decode()
    return f"{h}.{p}.{s}"


class TestJWTDecodeTool:
    @pytest.mark.asyncio
    async def test_decode_valid(self):
        from jarvis.tools.builtin.jwt_ops import JWTDecodeTool
        tool = JWTDecodeTool()
        token = _make_jwt({"alg": "HS256", "typ": "JWT"}, {"sub": "user123", "exp": 9999999999})
        result = await tool.execute({"token": token})
        assert result.success
        assert result.data["header"]["alg"] == "HS256"
        assert result.data["payload"]["sub"] == "user123"
        assert result.data["analysis"]["is_expired"] is False

    @pytest.mark.asyncio
    async def test_decode_expired(self):
        from jarvis.tools.builtin.jwt_ops import JWTDecodeTool
        tool = JWTDecodeTool()
        token = _make_jwt({"alg": "HS256"}, {"sub": "user", "exp": 1000000000})
        result = await tool.execute({"token": token})
        assert result.success
        assert result.data["analysis"]["is_expired"] is True

    @pytest.mark.asyncio
    async def test_decode_invalid(self):
        from jarvis.tools.builtin.jwt_ops import JWTDecodeTool
        tool = JWTDecodeTool()
        result = await tool.execute({"token": "not.a.jwt"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_decode_missing_parts(self):
        from jarvis.tools.builtin.jwt_ops import JWTDecodeTool
        tool = JWTDecodeTool()
        result = await tool.execute({"token": "only.two"})
        assert not result.success


class TestJWTValidateTool:
    @pytest.mark.asyncio
    async def test_valid_jwt(self):
        from jarvis.tools.builtin.jwt_ops import JWTValidateTool
        tool = JWTValidateTool()
        token = _make_jwt({"alg": "HS256", "typ": "JWT"}, {"sub": "user"})
        result = await tool.execute({"token": token})
        assert result.success
        assert result.data["valid"] is True

    @pytest.mark.asyncio
    async def test_invalid_parts(self):
        from jarvis.tools.builtin.jwt_ops import JWTValidateTool
        tool = JWTValidateTool()
        result = await tool.execute({"token": "one.two"})
        assert result.success
        assert result.data["valid"] is False

    @pytest.mark.asyncio
    async def test_missing_alg(self):
        from jarvis.tools.builtin.jwt_ops import JWTValidateTool
        tool = JWTValidateTool()
        token = _make_jwt({"typ": "JWT"}, {"sub": "user"})  # no alg
        result = await tool.execute({"token": token})
        assert result.success
        assert result.data["valid"] is False
        assert any("alg" in issue for issue in result.data["issues"])

    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.jwt_ops import JWTValidateTool
        tool = JWTValidateTool()
        assert tool.name == "jwt_validate"
        defn = tool.to_llm_definition()
        assert "token" in defn.parameters["properties"]


# ============================================================================
# Environment Variable Operations
# ============================================================================

class TestEnvVarTool:
    @pytest.mark.asyncio
    async def test_get_existing(self, monkeypatch):
        from jarvis.tools.builtin.env_ops import EnvVarTool
        monkeypatch.setenv("JARVIS_TEST_VAR", "hello_world")
        tool = EnvVarTool()
        result = await tool.execute({"name": "JARVIS_TEST_VAR"})
        assert result.success
        assert result.data["is_set"] is True
        assert result.data["value"] == "hello_world"

    @pytest.mark.asyncio
    async def test_get_missing_with_default(self):
        from jarvis.tools.builtin.env_ops import EnvVarTool
        tool = EnvVarTool()
        result = await tool.execute({"name": "JARVIS_NONEXISTENT_VAR_12345", "default": "fallback"})
        assert result.success
        assert result.data["is_set"] is False
        assert result.data["value"] == "fallback"

    @pytest.mark.asyncio
    async def test_get_missing_no_default(self):
        from jarvis.tools.builtin.env_ops import EnvVarTool
        tool = EnvVarTool()
        result = await tool.execute({"name": "JARVIS_NONEXISTENT_VAR_12345"})
        assert result.success
        assert result.data["is_set"] is False

    @pytest.mark.asyncio
    async def test_empty_name(self):
        from jarvis.tools.builtin.env_ops import EnvVarTool
        tool = EnvVarTool()
        result = await tool.execute({"name": ""})
        assert not result.success

    @pytest.mark.asyncio
    async def test_sensitive_masking(self, monkeypatch):
        from jarvis.tools.builtin.env_ops import EnvVarTool
        monkeypatch.setenv("MY_API_KEY", "supersecretvalue123")
        tool = EnvVarTool()
        result = await tool.execute({"name": "MY_API_KEY"})
        assert result.success
        assert "masked" in result.output.lower()
        assert "supersecretvalue123" not in result.output


class TestEnvListTool:
    @pytest.mark.asyncio
    async def test_list_path(self):
        from jarvis.tools.builtin.env_ops import EnvListTool
        tool = EnvListTool()
        result = await tool.execute({"pattern": "PATH"})
        assert result.success
        assert result.data["count"] >= 1

    @pytest.mark.asyncio
    async def test_list_all(self):
        from jarvis.tools.builtin.env_ops import EnvListTool
        tool = EnvListTool()
        result = await tool.execute({"pattern": "*"})
        assert result.success
        assert result.data["count"] > 0

    @pytest.mark.asyncio
    async def test_list_no_match(self):
        from jarvis.tools.builtin.env_ops import EnvListTool
        tool = EnvListTool()
        result = await tool.execute({"pattern": "ZZZZZ_NONEXISTENT_*"})
        assert result.success
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_list_with_custom_var(self, monkeypatch):
        from jarvis.tools.builtin.env_ops import EnvListTool
        monkeypatch.setenv("JARVIS_TEST_A", "1")
        monkeypatch.setenv("JARVIS_TEST_B", "2")
        tool = EnvListTool()
        result = await tool.execute({"pattern": "JARVIS_TEST_*"})
        assert result.success
        assert result.data["count"] >= 2


# ============================================================================
# UUID Operations
# ============================================================================

class TestUUIDGenerateTool:
    @pytest.mark.asyncio
    async def test_generate_single_v4(self):
        from jarvis.tools.builtin.uuid_ops import UUIDGenerateTool
        tool = UUIDGenerateTool()
        result = await tool.execute({})
        assert result.success
        assert len(result.data["uuids"]) == 1
        # Validate the generated UUID
        parsed = uuid.UUID(result.data["uuids"][0])
        assert parsed.version == 4

    @pytest.mark.asyncio
    async def test_generate_multiple(self):
        from jarvis.tools.builtin.uuid_ops import UUIDGenerateTool
        tool = UUIDGenerateTool()
        result = await tool.execute({"count": 5})
        assert result.success
        assert len(result.data["uuids"]) == 5
        # All should be unique
        assert len(set(result.data["uuids"])) == 5

    @pytest.mark.asyncio
    async def test_generate_v1(self):
        from jarvis.tools.builtin.uuid_ops import UUIDGenerateTool
        tool = UUIDGenerateTool()
        result = await tool.execute({"version": 1})
        assert result.success
        parsed = uuid.UUID(result.data["uuids"][0])
        assert parsed.version == 1

    @pytest.mark.asyncio
    async def test_invalid_version(self):
        from jarvis.tools.builtin.uuid_ops import UUIDGenerateTool
        tool = UUIDGenerateTool()
        result = await tool.execute({"version": 3})
        assert not result.success

    @pytest.mark.asyncio
    async def test_count_too_large(self):
        from jarvis.tools.builtin.uuid_ops import UUIDGenerateTool
        tool = UUIDGenerateTool()
        result = await tool.execute({"count": 101})
        assert not result.success


class TestUUIDValidateTool:
    @pytest.mark.asyncio
    async def test_valid_v4(self):
        from jarvis.tools.builtin.uuid_ops import UUIDValidateTool
        tool = UUIDValidateTool()
        test_uuid = str(uuid.uuid4())
        result = await tool.execute({"value": test_uuid})
        assert result.success
        assert result.data["valid"] is True
        assert result.data["version"] == 4

    @pytest.mark.asyncio
    async def test_valid_v1(self):
        from jarvis.tools.builtin.uuid_ops import UUIDValidateTool
        tool = UUIDValidateTool()
        test_uuid = str(uuid.uuid1())
        result = await tool.execute({"value": test_uuid})
        assert result.success
        assert result.data["valid"] is True
        assert result.data["version"] == 1

    @pytest.mark.asyncio
    async def test_invalid_format(self):
        from jarvis.tools.builtin.uuid_ops import UUIDValidateTool
        tool = UUIDValidateTool()
        result = await tool.execute({"value": "not-a-uuid"})
        assert result.success
        assert result.data["valid"] is False

    @pytest.mark.asyncio
    async def test_missing_dashes(self):
        from jarvis.tools.builtin.uuid_ops import UUIDValidateTool
        tool = UUIDValidateTool()
        test_uuid = uuid.uuid4().hex  # no dashes
        result = await tool.execute({"value": test_uuid})
        assert result.success
        assert result.data["valid"] is False
        assert "dashes" in result.output.lower()

    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.uuid_ops import UUIDValidateTool
        tool = UUIDValidateTool()
        assert tool.name == "uuid_validate"
        defn = tool.to_llm_definition()
        assert "value" in defn.parameters["properties"]


# ============================================================================
# Registration sanity check -- all 53 tools present
# ============================================================================

class TestBatch3AllRegistered:
    def test_registry_has_batch3_tools(self):
        """After importing builtin, batch 3 tools should be in the registry."""
        import jarvis.tools.builtin  # noqa: F401
        from jarvis.tools.registry import tool_registry

        tools = tool_registry.list_tools()
        names = {t.name for t in tools}

        batch3_expected = {
            "cron_parse", "cron_validate",
            "markdown_to_html", "markdown_table",
            "jwt_decode", "jwt_validate",
            "env_get", "env_list",
            "uuid_generate", "uuid_validate",
        }

        missing = batch3_expected - names
        assert not missing, f"Missing batch 3 tools in registry: {missing}"
        assert len(names) >= 53, f"Expected at least 53 tools, got {len(names)}"
