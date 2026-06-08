"""Tests for extended tool set added to JARVIS."""

from __future__ import annotations

import json
import os
import textwrap

import pytest

from jarvis.tools.base import ToolResult


# ---------------------------------------------------------------------------
# Git Operations
# ---------------------------------------------------------------------------

class TestGitStatusTool:
    @pytest.mark.asyncio
    async def test_status_non_repo(self, tmp_path):
        from jarvis.tools.builtin.git_ops import GitStatusTool
        tool = GitStatusTool()
        result = await tool.execute({"repo_path": str(tmp_path)})
        # tmp_path is not a git repo, so git should error
        assert not result.success

    @pytest.mark.asyncio
    async def test_status_clean_repo(self, tmp_path):
        from jarvis.tools.builtin.git_ops import GitStatusTool
        # Initialise a bare repo
        os.system(f"git -C {tmp_path} init -q")
        tool = GitStatusTool()
        result = await tool.execute({"repo_path": str(tmp_path)})
        assert result.success
        assert "clean" in result.output.lower() or result.output == "Working tree clean"


class TestGitDiffTool:
    @pytest.mark.asyncio
    async def test_diff_no_changes(self, tmp_path):
        from jarvis.tools.builtin.git_ops import GitDiffTool
        os.system(f"git -C {tmp_path} init -q")
        tool = GitDiffTool()
        result = await tool.execute({"repo_path": str(tmp_path)})
        assert result.success
        assert "no differences" in result.output.lower()

    @pytest.mark.asyncio
    async def test_diff_with_changes(self, tmp_path):
        from jarvis.tools.builtin.git_ops import GitDiffTool
        os.system(f"git -C {tmp_path} init -q")
        # Create and commit a file, then modify it
        test_file = tmp_path / "hello.txt"
        test_file.write_text("original\n")
        os.system(f"git -C {tmp_path} add . && git -C {tmp_path} commit -q -m init")
        test_file.write_text("modified\n")

        tool = GitDiffTool()
        result = await tool.execute({"repo_path": str(tmp_path)})
        assert result.success
        assert "modified" in result.output


class TestGitLogTool:
    @pytest.mark.asyncio
    async def test_log_empty_repo(self, tmp_path):
        from jarvis.tools.builtin.git_ops import GitLogTool
        os.system(f"git -C {tmp_path} init -q")
        tool = GitLogTool()
        result = await tool.execute({"repo_path": str(tmp_path)})
        # Empty repo has no commits; git log returns non-zero
        assert not result.success or "no commits" in result.output.lower()

    @pytest.mark.asyncio
    async def test_log_with_commits(self, tmp_path):
        from jarvis.tools.builtin.git_ops import GitLogTool
        os.system(f"git -C {tmp_path} init -q")
        (tmp_path / "a.txt").write_text("a")
        os.system(f"git -C {tmp_path} add . && git -C {tmp_path} commit -q -m 'first commit'")
        tool = GitLogTool()
        result = await tool.execute({"repo_path": str(tmp_path), "count": 5})
        assert result.success
        assert "first commit" in result.output


# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

class TestHttpRequestTool:
    @pytest.mark.asyncio
    async def test_request_bad_url(self):
        from jarvis.tools.builtin.http_client import HttpRequestTool
        tool = HttpRequestTool()
        result = await tool.execute({"url": "http://localhost:1", "timeout": 2})
        assert not result.success

    @pytest.mark.asyncio
    async def test_request_has_parameters(self):
        from jarvis.tools.builtin.http_client import HttpRequestTool
        tool = HttpRequestTool()
        assert "url" in tool.parameters["properties"]
        assert tool.name == "http_request"


class TestHttpDownloadTool:
    @pytest.mark.asyncio
    async def test_download_bad_url(self, tmp_path):
        from jarvis.tools.builtin.http_client import HttpDownloadTool
        tool = HttpDownloadTool()
        result = await tool.execute({
            "url": "http://localhost:1/file.bin",
            "save_path": str(tmp_path / "out.bin"),
            "timeout": 2,
        })
        assert not result.success

    @pytest.mark.asyncio
    async def test_download_definition(self):
        from jarvis.tools.builtin.http_client import HttpDownloadTool
        tool = HttpDownloadTool()
        defn = tool.to_llm_definition()
        assert defn.name == "http_download"
        assert "url" in defn.parameters["properties"]


# ---------------------------------------------------------------------------
# JSON / YAML Processing
# ---------------------------------------------------------------------------

class TestJsonQueryTool:
    @pytest.mark.asyncio
    async def test_simple_query(self):
        from jarvis.tools.builtin.json_ops import JsonQueryTool
        tool = JsonQueryTool()
        data = json.dumps({"users": [{"name": "Alice"}, {"name": "Bob"}]})
        result = await tool.execute({"data": data, "query": "users.0.name"})
        assert result.success
        assert "Alice" in result.output

    @pytest.mark.asyncio
    async def test_invalid_json(self):
        from jarvis.tools.builtin.json_ops import JsonQueryTool
        tool = JsonQueryTool()
        result = await tool.execute({"data": "not json{", "query": "x"})
        assert not result.success
        assert "Invalid JSON" in result.output

    @pytest.mark.asyncio
    async def test_nested_dict_query(self):
        from jarvis.tools.builtin.json_ops import JsonQueryTool
        tool = JsonQueryTool()
        data = json.dumps({"a": {"b": {"c": 42}}})
        result = await tool.execute({"data": data, "query": "a.b.c"})
        assert result.success
        assert "42" in result.output


class TestYamlToJsonTool:
    @pytest.mark.asyncio
    async def test_yaml_to_json(self):
        from jarvis.tools.builtin.json_ops import YamlToJsonTool
        tool = YamlToJsonTool()
        yaml_input = "name: test\nvalue: 42\n"
        result = await tool.execute({"input": yaml_input, "direction": "yaml_to_json"})
        assert result.success
        parsed = json.loads(result.output)
        assert parsed["name"] == "test"
        assert parsed["value"] == 42

    @pytest.mark.asyncio
    async def test_json_to_yaml(self):
        from jarvis.tools.builtin.json_ops import YamlToJsonTool
        tool = YamlToJsonTool()
        json_input = json.dumps({"key": "value", "num": 3})
        result = await tool.execute({"input": json_input, "direction": "json_to_yaml"})
        assert result.success
        assert "key:" in result.output


# ---------------------------------------------------------------------------
# Text Processing
# ---------------------------------------------------------------------------

class TestRegexTool:
    @pytest.mark.asyncio
    async def test_find_matches(self):
        from jarvis.tools.builtin.text_processing import RegexTool
        tool = RegexTool()
        result = await tool.execute({
            "text": "Hello 123 world 456",
            "pattern": r"\d+",
        })
        assert result.success
        assert result.data is not None
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_replace(self):
        from jarvis.tools.builtin.text_processing import RegexTool
        tool = RegexTool()
        result = await tool.execute({
            "text": "Hello World",
            "pattern": r"World",
            "replace_with": "JARVIS",
        })
        assert result.success
        assert "JARVIS" in result.output

    @pytest.mark.asyncio
    async def test_invalid_regex(self):
        from jarvis.tools.builtin.text_processing import RegexTool
        tool = RegexTool()
        result = await tool.execute({"text": "abc", "pattern": "[invalid"})
        assert not result.success
        assert "Invalid regex" in result.output


class TestTextSummaryTool:
    @pytest.mark.asyncio
    async def test_summarize(self):
        from jarvis.tools.builtin.text_processing import TextSummaryTool
        tool = TextSummaryTool()
        text = (
            "Machine learning is a branch of artificial intelligence. "
            "It focuses on building systems that learn from data. "
            "Deep learning is a subset of machine learning. "
            "Neural networks are used in deep learning. "
            "These techniques have revolutionized many fields."
        )
        result = await tool.execute({"text": text, "max_sentences": 2})
        assert result.success
        assert len(result.output) > 0
        assert result.data is not None
        assert result.data["sentence_count"] == 2

    @pytest.mark.asyncio
    async def test_short_text(self):
        from jarvis.tools.builtin.text_processing import TextSummaryTool
        tool = TextSummaryTool()
        result = await tool.execute({"text": "Single sentence here."})
        assert result.success


class TestDiffTool:
    @pytest.mark.asyncio
    async def test_identical(self):
        from jarvis.tools.builtin.text_processing import DiffTool
        tool = DiffTool()
        result = await tool.execute({"text_a": "hello", "text_b": "hello"})
        assert result.success
        assert "no differences" in result.output.lower()

    @pytest.mark.asyncio
    async def test_different(self):
        from jarvis.tools.builtin.text_processing import DiffTool
        tool = DiffTool()
        result = await tool.execute({
            "text_a": "line1\nline2\nline3\n",
            "text_b": "line1\nmodified\nline3\n",
        })
        assert result.success
        assert result.data is not None
        assert result.data["has_diff"]
        assert "modified" in result.output


# ---------------------------------------------------------------------------
# System Information
# ---------------------------------------------------------------------------

class TestSystemInfoTool:
    @pytest.mark.asyncio
    async def test_get_info(self):
        from jarvis.tools.builtin.system_info import SystemInfoTool
        tool = SystemInfoTool()
        result = await tool.execute({})
        assert result.success
        assert "OS:" in result.output
        assert result.data is not None
        assert "cpu_count" in result.data

    @pytest.mark.asyncio
    async def test_custom_disk_path(self):
        from jarvis.tools.builtin.system_info import SystemInfoTool
        tool = SystemInfoTool()
        result = await tool.execute({"disk_path": "/"})
        assert result.success
        assert "Disk" in result.output


class TestProcessListTool:
    @pytest.mark.asyncio
    async def test_list_processes(self):
        from jarvis.tools.builtin.system_info import ProcessListTool
        tool = ProcessListTool()
        result = await tool.execute({})
        assert result.success
        assert result.data is not None
        assert result.data["count"] > 0

    @pytest.mark.asyncio
    async def test_filter_processes(self):
        from jarvis.tools.builtin.system_info import ProcessListTool
        tool = ProcessListTool()
        # "python" should match the running test process
        result = await tool.execute({"filter": "python"})
        assert result.success


# ---------------------------------------------------------------------------
# Directory Operations
# ---------------------------------------------------------------------------

class TestListDirectoryTool:
    @pytest.mark.asyncio
    async def test_list_existing(self, tmp_path):
        from jarvis.tools.builtin.directory_ops import ListDirectoryTool
        # Create some files
        (tmp_path / "a.txt").write_text("aaa")
        (tmp_path / "b.py").write_text("bbb")
        (tmp_path / "sub").mkdir()

        tool = ListDirectoryTool()
        result = await tool.execute({"path": str(tmp_path)})
        assert result.success
        assert "a.txt" in result.output
        assert "b.py" in result.output
        assert result.data is not None
        assert result.data["count"] == 3  # 2 files + 1 dir

    @pytest.mark.asyncio
    async def test_list_nonexistent(self):
        from jarvis.tools.builtin.directory_ops import ListDirectoryTool
        tool = ListDirectoryTool()
        result = await tool.execute({"path": "/nonexistent_dir_xyz"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_list_with_pattern(self, tmp_path):
        from jarvis.tools.builtin.directory_ops import ListDirectoryTool
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.py").write_text("b")
        tool = ListDirectoryTool()
        result = await tool.execute({"path": str(tmp_path), "pattern": "*.py"})
        assert result.success
        assert "b.py" in result.output
        assert "a.txt" not in result.output


class TestFindFilesTool:
    @pytest.mark.asyncio
    async def test_find_by_pattern(self, tmp_path):
        from jarvis.tools.builtin.directory_ops import FindFilesTool
        (tmp_path / "hello.py").write_text("print('hi')")
        (tmp_path / "data.txt").write_text("data")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.py").write_text("import os")

        tool = FindFilesTool()
        result = await tool.execute({"directory": str(tmp_path), "pattern": "*.py"})
        assert result.success
        assert result.data is not None
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_find_with_content(self, tmp_path):
        from jarvis.tools.builtin.directory_ops import FindFilesTool
        (tmp_path / "a.py").write_text("import os\nimport sys\n")
        (tmp_path / "b.py").write_text("import json\n")

        tool = FindFilesTool()
        result = await tool.execute({
            "directory": str(tmp_path),
            "pattern": "*.py",
            "content_match": "import sys",
        })
        assert result.success
        assert result.data is not None
        assert result.data["count"] == 1
        assert "a.py" in result.output


# ---------------------------------------------------------------------------
# Clipboard
# ---------------------------------------------------------------------------

class TestClipboardTool:
    @pytest.mark.asyncio
    async def test_write_and_read(self):
        from jarvis.tools.builtin.clipboard import ClipboardTool
        tool = ClipboardTool()

        # Write
        result = await tool.execute({"action": "write", "content": "jarvis_test_clip"})
        if not result.success:
            pytest.skip("Clipboard not available in this environment")

        # Read back
        result = await tool.execute({"action": "read"})
        assert result.success
        assert "jarvis_test_clip" in result.output

    @pytest.mark.asyncio
    async def test_write_missing_content(self):
        from jarvis.tools.builtin.clipboard import ClipboardTool
        tool = ClipboardTool()
        result = await tool.execute({"action": "write"})
        assert not result.success
        assert "required" in result.output.lower()


# ---------------------------------------------------------------------------
# Registration sanity check
# ---------------------------------------------------------------------------

class TestAllToolsRegistered:
    def test_registry_has_all_tools(self):
        """After importing builtin, all 20 tools should be registered."""
        from jarvis.tools.registry import ToolRegistry

        # Create a fresh registry and register tools to avoid pollution
        import jarvis.tools.builtin  # noqa: F401 — triggers registration on the global registry
        from jarvis.tools.registry import tool_registry

        tools = tool_registry.list_tools()
        names = {t.name for t in tools}

        expected = {
            # Original 5
            "shell_execute", "read_file", "write_file", "web_search", "python_execute",
            # Git (3)
            "git_status", "git_diff", "git_log",
            # HTTP (2)
            "http_request", "http_download",
            # JSON/YAML (2)
            "json_query", "yaml_to_json",
            # Text (3)
            "regex_search", "text_summary", "text_diff",
            # System (2)
            "system_info", "process_list",
            # Directory (2)
            "list_directory", "find_files",
            # Clipboard (1)
            "clipboard",
        }
        missing = expected - names
        assert not missing, f"Missing tools in registry: {missing}"
        assert len(names) >= 20, f"Expected at least 20 tools, got {len(names)}"
