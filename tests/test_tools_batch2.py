"""Tests for batch 2 tools added to JARVIS (docker, database, image, archive,
network, math, encoding, datetime, template)."""

from __future__ import annotations

import csv
import json
import os
import struct
import zipfile

import pytest

from jarvis.tools.base import ToolResult


# ---------------------------------------------------------------------------
# Docker Operations (structural / unit-level tests — no running Docker needed)
# ---------------------------------------------------------------------------


class TestDockerListTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.docker_ops import DockerListTool
        tool = DockerListTool()
        assert tool.name == "docker_ps"
        defn = tool.to_llm_definition()
        assert "all" in defn.parameters["properties"]

    @pytest.mark.asyncio
    async def test_docker_not_installed(self, monkeypatch):
        """When docker is missing we get a clear error."""
        from jarvis.tools.builtin.docker_ops import DockerListTool
        import asyncio

        async def _fake_exec(*args, **kwargs):
            raise FileNotFoundError("docker not found")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)
        tool = DockerListTool()
        result = await tool.execute({})
        assert not result.success
        assert "not installed" in result.output.lower() or "not found" in result.output.lower()


class TestDockerLogsTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.docker_ops import DockerLogsTool
        tool = DockerLogsTool()
        assert tool.name == "docker_logs"
        assert "container_id" in tool.parameters["properties"]


class TestDockerExecTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.docker_ops import DockerExecTool
        tool = DockerExecTool()
        assert tool.name == "docker_exec"
        assert "container_id" in tool.parameters["properties"]
        assert "command" in tool.parameters["properties"]


class TestDockerImagesTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.docker_ops import DockerImagesTool
        tool = DockerImagesTool()
        assert tool.name == "docker_images"


# ---------------------------------------------------------------------------
# Database Operations
# ---------------------------------------------------------------------------


class TestSQLiteQueryTool:
    @pytest.mark.asyncio
    async def test_select_query(self, tmp_path):
        from jarvis.tools.builtin.database_ops import SQLiteQueryTool
        import sqlite3

        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO users VALUES (1, 'Alice')")
        conn.execute("INSERT INTO users VALUES (2, 'Bob')")
        conn.commit()
        conn.close()

        tool = SQLiteQueryTool()
        result = await tool.execute({"db_path": db, "query": "SELECT * FROM users"})
        assert result.success
        assert result.data is not None
        assert result.data["count"] == 2
        assert "Alice" in result.output

    @pytest.mark.asyncio
    async def test_write_blocked_by_default(self, tmp_path):
        from jarvis.tools.builtin.database_ops import SQLiteQueryTool
        import sqlite3

        db = str(tmp_path / "test.db")
        sqlite3.connect(db).close()

        tool = SQLiteQueryTool()
        result = await tool.execute({
            "db_path": db,
            "query": "CREATE TABLE foo (id INTEGER)",
        })
        assert not result.success
        assert "blocked" in result.output.lower()

    @pytest.mark.asyncio
    async def test_write_allowed(self, tmp_path):
        from jarvis.tools.builtin.database_ops import SQLiteQueryTool
        import sqlite3

        db = str(tmp_path / "test.db")
        sqlite3.connect(db).close()

        tool = SQLiteQueryTool()
        result = await tool.execute({
            "db_path": db,
            "query": "CREATE TABLE foo (id INTEGER, name TEXT)",
            "allow_write": True,
        })
        assert result.success

    @pytest.mark.asyncio
    async def test_empty_result(self, tmp_path):
        from jarvis.tools.builtin.database_ops import SQLiteQueryTool
        import sqlite3

        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE items (id INTEGER)")
        conn.commit()
        conn.close()

        tool = SQLiteQueryTool()
        result = await tool.execute({"db_path": db, "query": "SELECT * FROM items"})
        assert result.success
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_invalid_sql(self, tmp_path):
        from jarvis.tools.builtin.database_ops import SQLiteQueryTool
        import sqlite3

        db = str(tmp_path / "test.db")
        sqlite3.connect(db).close()

        tool = SQLiteQueryTool()
        result = await tool.execute({"db_path": db, "query": "SELEKT * FORM xyz"})
        assert not result.success


class TestSQLiteSchemasTool:
    @pytest.mark.asyncio
    async def test_schema(self, tmp_path):
        from jarvis.tools.builtin.database_ops import SQLiteSchemasTool
        import sqlite3

        db = str(tmp_path / "test.db")
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL, email TEXT)")
        conn.commit()
        conn.close()

        tool = SQLiteSchemasTool()
        result = await tool.execute({"db_path": db})
        assert result.success
        assert "users" in result.output
        assert "name" in result.output
        assert result.data is not None
        assert len(result.data["tables"]) == 1

    @pytest.mark.asyncio
    async def test_nonexistent_db(self):
        from jarvis.tools.builtin.database_ops import SQLiteSchemasTool
        tool = SQLiteSchemasTool()
        result = await tool.execute({"db_path": "/nonexistent/path.db"})
        assert not result.success


class TestCSVToSQLiteTool:
    @pytest.mark.asyncio
    async def test_import_csv(self, tmp_path):
        from jarvis.tools.builtin.database_ops import CSVToSQLiteTool

        csv_path = str(tmp_path / "data.csv")
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "age", "city"])
            writer.writerow(["Alice", "30", "NYC"])
            writer.writerow(["Bob", "25", "LA"])

        db_path = str(tmp_path / "imported.db")
        tool = CSVToSQLiteTool()
        result = await tool.execute({
            "csv_path": csv_path,
            "db_path": db_path,
            "table_name": "people",
        })
        assert result.success
        assert result.data["rows_imported"] == 2
        assert "people" in result.output

    @pytest.mark.asyncio
    async def test_csv_not_found(self, tmp_path):
        from jarvis.tools.builtin.database_ops import CSVToSQLiteTool
        tool = CSVToSQLiteTool()
        result = await tool.execute({
            "csv_path": "/nonexistent.csv",
            "db_path": str(tmp_path / "out.db"),
            "table_name": "t",
        })
        assert not result.success


# ---------------------------------------------------------------------------
# Image Operations
# ---------------------------------------------------------------------------


class TestImageInfoTool:
    @pytest.mark.asyncio
    async def test_png_info(self, tmp_path):
        from jarvis.tools.builtin.image_ops import ImageInfoTool

        # Create a minimal valid PNG
        png_path = str(tmp_path / "test.png")
        _write_minimal_png(png_path, 100, 80)

        tool = ImageInfoTool()
        result = await tool.execute({"path": png_path})
        assert result.success
        assert result.data is not None
        assert result.data["width"] == 100
        assert result.data["height"] == 80
        assert result.data["format"] == "PNG"

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        from jarvis.tools.builtin.image_ops import ImageInfoTool
        tool = ImageInfoTool()
        result = await tool.execute({"path": "/nonexistent/image.png"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_unknown_format(self, tmp_path):
        from jarvis.tools.builtin.image_ops import ImageInfoTool
        f = tmp_path / "test.xyz"
        f.write_bytes(b"not an image file at all")
        tool = ImageInfoTool()
        result = await tool.execute({"path": str(f)})
        # Should succeed but report unknown format
        assert result.success
        assert result.data["format"] == "unknown"


class TestImageResizeTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.image_ops import ImageResizeTool
        tool = ImageResizeTool()
        assert tool.name == "image_resize"
        assert "width" in tool.parameters["properties"]
        assert "height" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        from jarvis.tools.builtin.image_ops import ImageResizeTool
        tool = ImageResizeTool()
        result = await tool.execute({"path": "/nonexistent.png", "width": 100, "height": 100})
        assert not result.success

    @pytest.mark.asyncio
    async def test_invalid_dimensions(self, tmp_path):
        from jarvis.tools.builtin.image_ops import ImageResizeTool
        f = tmp_path / "test.png"
        _write_minimal_png(str(f), 10, 10)
        tool = ImageResizeTool()
        result = await tool.execute({"path": str(f), "width": 0, "height": -1})
        assert not result.success


class TestScreenshotTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.image_ops import ScreenshotTool
        tool = ScreenshotTool()
        assert tool.name == "screenshot"
        assert "output_path" in tool.parameters["properties"]


# ---------------------------------------------------------------------------
# Archive Operations
# ---------------------------------------------------------------------------


class TestZipCreateTool:
    @pytest.mark.asyncio
    async def test_zip_file(self, tmp_path):
        from jarvis.tools.builtin.archive_ops import ZipCreateTool

        src = tmp_path / "hello.txt"
        src.write_text("hello world")
        out = str(tmp_path / "out.zip")

        tool = ZipCreateTool()
        result = await tool.execute({"source_path": str(src), "output_path": out})
        assert result.success
        assert os.path.exists(out)
        assert result.data["file_count"] == 1

    @pytest.mark.asyncio
    async def test_zip_directory(self, tmp_path):
        from jarvis.tools.builtin.archive_ops import ZipCreateTool

        src_dir = tmp_path / "mydir"
        src_dir.mkdir()
        (src_dir / "a.txt").write_text("aaa")
        (src_dir / "b.txt").write_text("bbb")
        sub = src_dir / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("ccc")

        out = str(tmp_path / "dir.zip")
        tool = ZipCreateTool()
        result = await tool.execute({"source_path": str(src_dir), "output_path": out})
        assert result.success
        assert result.data["file_count"] == 3

    @pytest.mark.asyncio
    async def test_source_not_found(self, tmp_path):
        from jarvis.tools.builtin.archive_ops import ZipCreateTool
        tool = ZipCreateTool()
        result = await tool.execute({
            "source_path": "/nonexistent_path",
            "output_path": str(tmp_path / "out.zip"),
        })
        assert not result.success


class TestZipExtractTool:
    @pytest.mark.asyncio
    async def test_extract(self, tmp_path):
        from jarvis.tools.builtin.archive_ops import ZipExtractTool

        # Create a zip
        zip_path = str(tmp_path / "test.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("hello.txt", "hello world")
            zf.writestr("sub/data.txt", "data here")

        out_dir = str(tmp_path / "extracted")
        tool = ZipExtractTool()
        result = await tool.execute({"zip_path": zip_path, "output_dir": out_dir})
        assert result.success
        assert result.data["count"] == 2
        assert os.path.exists(os.path.join(out_dir, "hello.txt"))

    @pytest.mark.asyncio
    async def test_invalid_zip(self, tmp_path):
        from jarvis.tools.builtin.archive_ops import ZipExtractTool

        bad_zip = tmp_path / "bad.zip"
        bad_zip.write_bytes(b"this is not a zip file")

        tool = ZipExtractTool()
        result = await tool.execute({
            "zip_path": str(bad_zip),
            "output_dir": str(tmp_path / "out"),
        })
        assert not result.success


# ---------------------------------------------------------------------------
# Network Operations
# ---------------------------------------------------------------------------


class TestPingTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.network_ops import PingTool
        tool = PingTool()
        assert tool.name == "ping"
        assert "host" in tool.parameters["properties"]

    @pytest.mark.asyncio
    async def test_invalid_host(self):
        from jarvis.tools.builtin.network_ops import PingTool
        tool = PingTool()
        result = await tool.execute({"host": "", "count": 1})
        assert not result.success


class TestDNSLookupTool:
    @pytest.mark.asyncio
    async def test_definition(self):
        from jarvis.tools.builtin.network_ops import DNSLookupTool
        tool = DNSLookupTool()
        assert tool.name == "dns_lookup"
        assert "domain" in tool.parameters["properties"]
        assert "record_type" in tool.parameters["properties"]


class TestPortCheckTool:
    @pytest.mark.asyncio
    async def test_closed_port(self):
        from jarvis.tools.builtin.network_ops import PortCheckTool
        tool = PortCheckTool()
        # Port 1 on localhost is almost certainly closed
        result = await tool.execute({"host": "127.0.0.1", "port": 1, "timeout": 1})
        assert result.success  # Tool succeeds (reports status)
        assert result.data["open"] is False

    @pytest.mark.asyncio
    async def test_invalid_port(self):
        from jarvis.tools.builtin.network_ops import PortCheckTool
        tool = PortCheckTool()
        result = await tool.execute({"host": "localhost", "port": 99999})
        assert not result.success


# ---------------------------------------------------------------------------
# Math Operations
# ---------------------------------------------------------------------------


class TestCalculatorTool:
    @pytest.mark.asyncio
    async def test_basic_arithmetic(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 + 3 * 4"})
        assert result.success
        assert result.data["result"] == 14

    @pytest.mark.asyncio
    async def test_sqrt(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        tool = CalculatorTool()
        result = await tool.execute({"expression": "sqrt(144)"})
        assert result.success
        assert result.data["result"] == 12.0

    @pytest.mark.asyncio
    async def test_power(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 ** 10"})
        assert result.success
        assert result.data["result"] == 1024

    @pytest.mark.asyncio
    async def test_constants(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        import math
        tool = CalculatorTool()
        result = await tool.execute({"expression": "pi"})
        assert result.success
        assert abs(result.data["result"] - math.pi) < 0.0001

    @pytest.mark.asyncio
    async def test_invalid_expression(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        tool = CalculatorTool()
        result = await tool.execute({"expression": "import os"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_division_by_zero(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        tool = CalculatorTool()
        result = await tool.execute({"expression": "1 / 0"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_huge_exponent_blocked(self):
        from jarvis.tools.builtin.math_ops import CalculatorTool
        tool = CalculatorTool()
        result = await tool.execute({"expression": "2 ** 10000"})
        assert not result.success


class TestUnitConvertTool:
    @pytest.mark.asyncio
    async def test_length_km_to_mi(self):
        from jarvis.tools.builtin.math_ops import UnitConvertTool
        tool = UnitConvertTool()
        result = await tool.execute({"value": 1, "from_unit": "km", "to_unit": "mi"})
        assert result.success
        assert abs(result.data["result"] - 0.621371) < 0.001

    @pytest.mark.asyncio
    async def test_temperature_c_to_f(self):
        from jarvis.tools.builtin.math_ops import UnitConvertTool
        tool = UnitConvertTool()
        result = await tool.execute({"value": 100, "from_unit": "C", "to_unit": "F"})
        assert result.success
        assert abs(result.data["result"] - 212) < 0.1

    @pytest.mark.asyncio
    async def test_data_gb_to_mb(self):
        from jarvis.tools.builtin.math_ops import UnitConvertTool
        tool = UnitConvertTool()
        result = await tool.execute({"value": 1, "from_unit": "GB", "to_unit": "MB"})
        assert result.success
        assert result.data["result"] == 1024

    @pytest.mark.asyncio
    async def test_unknown_unit(self):
        from jarvis.tools.builtin.math_ops import UnitConvertTool
        tool = UnitConvertTool()
        result = await tool.execute({"value": 1, "from_unit": "xyz", "to_unit": "abc"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_incompatible_units(self):
        from jarvis.tools.builtin.math_ops import UnitConvertTool
        tool = UnitConvertTool()
        result = await tool.execute({"value": 1, "from_unit": "kg", "to_unit": "km"})
        assert not result.success
        assert "cannot convert" in result.output.lower()


# ---------------------------------------------------------------------------
# Encoding Operations
# ---------------------------------------------------------------------------


class TestBase64Tool:
    @pytest.mark.asyncio
    async def test_encode(self):
        from jarvis.tools.builtin.encoding_ops import Base64Tool
        tool = Base64Tool()
        result = await tool.execute({"input": "Hello World", "action": "encode"})
        assert result.success
        assert result.output == "SGVsbG8gV29ybGQ="

    @pytest.mark.asyncio
    async def test_decode(self):
        from jarvis.tools.builtin.encoding_ops import Base64Tool
        tool = Base64Tool()
        result = await tool.execute({"input": "SGVsbG8gV29ybGQ=", "action": "decode"})
        assert result.success
        assert result.output == "Hello World"

    @pytest.mark.asyncio
    async def test_roundtrip(self):
        from jarvis.tools.builtin.encoding_ops import Base64Tool
        tool = Base64Tool()
        original = "JARVIS tool system 2024!"
        enc = await tool.execute({"input": original, "action": "encode"})
        dec = await tool.execute({"input": enc.output, "action": "decode"})
        assert dec.output == original


class TestHashTool:
    @pytest.mark.asyncio
    async def test_sha256_text(self):
        from jarvis.tools.builtin.encoding_ops import HashTool
        tool = HashTool()
        result = await tool.execute({"input": "hello"})
        assert result.success
        # Known SHA256 for "hello"
        assert "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" in result.output

    @pytest.mark.asyncio
    async def test_md5_text(self):
        from jarvis.tools.builtin.encoding_ops import HashTool
        tool = HashTool()
        result = await tool.execute({"input": "hello", "algorithm": "md5"})
        assert result.success
        assert "5d41402abc4b2a76b9719d911017c592" in result.output

    @pytest.mark.asyncio
    async def test_hash_file(self, tmp_path):
        from jarvis.tools.builtin.encoding_ops import HashTool
        f = tmp_path / "test.txt"
        f.write_text("hello")
        tool = HashTool()
        result = await tool.execute({"input": str(f), "algorithm": "sha256", "is_file": True})
        assert result.success
        assert result.data["hash"] is not None

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        from jarvis.tools.builtin.encoding_ops import HashTool
        tool = HashTool()
        result = await tool.execute({"input": "/nonexistent/file", "is_file": True})
        assert not result.success


class TestURLEncodeTool:
    @pytest.mark.asyncio
    async def test_encode(self):
        from jarvis.tools.builtin.encoding_ops import URLEncodeTool
        tool = URLEncodeTool()
        result = await tool.execute({"input": "hello world&foo=bar", "action": "encode"})
        assert result.success
        assert "hello%20world" in result.output
        assert "%26" in result.output

    @pytest.mark.asyncio
    async def test_decode(self):
        from jarvis.tools.builtin.encoding_ops import URLEncodeTool
        tool = URLEncodeTool()
        result = await tool.execute({"input": "hello%20world%26foo%3Dbar", "action": "decode"})
        assert result.success
        assert "hello world" in result.output


# ---------------------------------------------------------------------------
# DateTime Operations
# ---------------------------------------------------------------------------


class TestDateTimeTool:
    @pytest.mark.asyncio
    async def test_utc(self):
        from jarvis.tools.builtin.datetime_ops import DateTimeTool
        tool = DateTimeTool()
        result = await tool.execute({})
        assert result.success
        assert "UTC" in result.output
        assert result.data is not None
        assert "iso" in result.data

    @pytest.mark.asyncio
    async def test_custom_format(self):
        from jarvis.tools.builtin.datetime_ops import DateTimeTool
        tool = DateTimeTool()
        result = await tool.execute({"format": "%Y-%m-%d"})
        assert result.success
        # Output should look like a date
        assert len(result.output) == 10

    @pytest.mark.asyncio
    async def test_timezone_pst(self):
        from jarvis.tools.builtin.datetime_ops import DateTimeTool
        tool = DateTimeTool()
        result = await tool.execute({"timezone": "PST"})
        assert result.success

    @pytest.mark.asyncio
    async def test_invalid_timezone(self):
        from jarvis.tools.builtin.datetime_ops import DateTimeTool
        tool = DateTimeTool()
        result = await tool.execute({"timezone": "INVALID_TZ"})
        assert not result.success


class TestDateCalcTool:
    @pytest.mark.asyncio
    async def test_add_days(self):
        from jarvis.tools.builtin.datetime_ops import DateCalcTool
        tool = DateCalcTool()
        result = await tool.execute({
            "date": "2024-01-01",
            "operation": "add",
            "days": 10,
        })
        assert result.success
        assert "2024-01-11" in result.output

    @pytest.mark.asyncio
    async def test_subtract_days(self):
        from jarvis.tools.builtin.datetime_ops import DateCalcTool
        tool = DateCalcTool()
        result = await tool.execute({
            "date": "2024-03-01",
            "operation": "subtract",
            "days": 1,
        })
        assert result.success
        assert "2024-02-29" in result.output  # 2024 is a leap year

    @pytest.mark.asyncio
    async def test_add_hours(self):
        from jarvis.tools.builtin.datetime_ops import DateCalcTool
        tool = DateCalcTool()
        result = await tool.execute({
            "date": "2024-01-01T10:00:00",
            "operation": "add",
            "hours": 5,
        })
        assert result.success
        assert "15:00:00" in result.data["result"]

    @pytest.mark.asyncio
    async def test_invalid_date(self):
        from jarvis.tools.builtin.datetime_ops import DateCalcTool
        tool = DateCalcTool()
        result = await tool.execute({
            "date": "not-a-date",
            "operation": "add",
            "days": 1,
        })
        assert not result.success


# ---------------------------------------------------------------------------
# Template Operations
# ---------------------------------------------------------------------------


class TestTemplateTool:
    @pytest.mark.asyncio
    async def test_simple_substitution(self):
        from jarvis.tools.builtin.template_ops import TemplateTool
        tool = TemplateTool()
        result = await tool.execute({
            "template": "Hello, {{name}}! Welcome to {{place}}.",
            "variables": {"name": "Alice", "place": "JARVIS"},
        })
        assert result.success
        assert "Alice" in result.output
        assert "JARVIS" in result.output

    @pytest.mark.asyncio
    async def test_conditional_true(self):
        from jarvis.tools.builtin.template_ops import TemplateTool
        tool = TemplateTool()
        result = await tool.execute({
            "template": "{{#if premium}}Premium user{{/if}}",
            "variables": {"premium": True},
        })
        assert result.success
        assert "Premium user" in result.output

    @pytest.mark.asyncio
    async def test_conditional_false(self):
        from jarvis.tools.builtin.template_ops import TemplateTool
        tool = TemplateTool()
        result = await tool.execute({
            "template": "{{#if premium}}Premium{{#else}}Free{{/if}}",
            "variables": {"premium": False},
        })
        assert result.success
        assert "Free" in result.output

    @pytest.mark.asyncio
    async def test_each_loop(self):
        from jarvis.tools.builtin.template_ops import TemplateTool
        tool = TemplateTool()
        result = await tool.execute({
            "template": "Items: {{#each items}}[{{.}}]{{/each}}",
            "variables": {"items": ["a", "b", "c"]},
        })
        assert result.success
        assert "[a]" in result.output
        assert "[b]" in result.output
        assert "[c]" in result.output

    @pytest.mark.asyncio
    async def test_dollar_syntax(self):
        from jarvis.tools.builtin.template_ops import TemplateTool
        tool = TemplateTool()
        result = await tool.execute({
            "template": "Hello $name",
            "variables": {"name": "Bob"},
        })
        assert result.success
        assert "Bob" in result.output


# ---------------------------------------------------------------------------
# Registration sanity check — all 43 tools present
# ---------------------------------------------------------------------------


class TestBatch2AllRegistered:
    def test_registry_has_batch2_tools(self):
        """After importing builtin, batch 2 tools should be in the registry."""
        import jarvis.tools.builtin  # noqa: F401
        from jarvis.tools.registry import tool_registry

        tools = tool_registry.list_tools()
        names = {t.name for t in tools}

        batch2_expected = {
            "docker_ps", "docker_logs", "docker_exec", "docker_images",
            "sqlite_query", "sqlite_schema", "csv_to_sqlite",
            "image_info", "image_resize", "screenshot",
            "zip_create", "zip_extract",
            "ping", "dns_lookup", "port_check",
            "calculator", "unit_convert",
            "base64_codec", "hash", "url_codec",
            "datetime_info", "date_calc",
            "render_template",
        }

        missing = batch2_expected - names
        assert not missing, f"Missing batch 2 tools in registry: {missing}"
        assert len(names) >= 43, f"Expected at least 43 tools, got {len(names)}"


# ---------------------------------------------------------------------------
# Helper to create minimal PNG for tests
# ---------------------------------------------------------------------------


def _write_minimal_png(path: str, width: int, height: int) -> None:
    """Write a minimal valid PNG file with the given dimensions."""
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    # IHDR: width, height, bit depth 8, color type 2 (RGB), compression 0, filter 0, interlace 0
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)

    # IDAT: minimal image data (all black)
    raw_row = b"\x00" + b"\x00\x00\x00" * width  # filter byte + RGB pixels
    raw_data = raw_row * height
    compressed = zlib.compress(raw_data)
    idat = _chunk(b"IDAT", compressed)

    iend = _chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(signature + ihdr + idat + iend)
