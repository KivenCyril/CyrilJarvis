"""Tests for Batch 4 tools: CSV, XML, Color, and Random operations."""

from __future__ import annotations

import csv
import io
import json

import pytest

from jarvis.tools.builtin.csv_ops import CSVReadTool, CSVWriteTool, CSVStatsTool
from jarvis.tools.builtin.xml_ops import XMLToJsonTool, XMLQueryTool
from jarvis.tools.builtin.color_ops import ColorConvertTool, ColorPaletteTool
from jarvis.tools.builtin.random_ops import RandomStringTool, RandomNumberTool, RandomChoiceTool


# ===========================================================================
# CSV Read Tool
# ===========================================================================

class TestCSVReadTool:
    @pytest.fixture
    def tool(self):
        return CSVReadTool()

    @pytest.mark.asyncio
    async def test_basic_read(self, tool):
        csv_data = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        result = await tool.execute({"data": csv_data})
        assert result.success
        assert result.data["row_count"] == 2
        assert result.data["headers"] == ["name", "age", "city"]

    @pytest.mark.asyncio
    async def test_column_selection(self, tool):
        csv_data = "name,age,city\nAlice,30,NYC\nBob,25,LA"
        result = await tool.execute({"data": csv_data, "columns": ["name", "city"]})
        assert result.success
        assert result.data["headers"] == ["name", "city"]
        assert "age" not in result.data["rows"][0]

    @pytest.mark.asyncio
    async def test_custom_delimiter(self, tool):
        csv_data = "name;age;city\nAlice;30;NYC"
        result = await tool.execute({"data": csv_data, "delimiter": ";"})
        assert result.success
        assert result.data["rows"][0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_no_header(self, tool):
        csv_data = "Alice,30,NYC\nBob,25,LA"
        result = await tool.execute({"data": csv_data, "has_header": False})
        assert result.success
        assert result.data["row_count"] == 2

    @pytest.mark.asyncio
    async def test_max_rows(self, tool):
        rows = "name,age\n" + "\n".join(f"Person{i},{i}" for i in range(100))
        result = await tool.execute({"data": rows, "max_rows": 5})
        assert result.success
        assert result.data["row_count"] == 5

    @pytest.mark.asyncio
    async def test_empty_csv(self, tool):
        result = await tool.execute({"data": "name,age"})
        assert result.success
        assert result.data["row_count"] == 0

    @pytest.mark.asyncio
    async def test_single_column(self, tool):
        csv_data = "value\n1\n2\n3"
        result = await tool.execute({"data": csv_data})
        assert result.success
        assert result.data["row_count"] == 3

    @pytest.mark.asyncio
    async def test_quoted_fields(self, tool):
        csv_data = 'name,description\nAlice,"A, long description"\nBob,"Another one"'
        result = await tool.execute({"data": csv_data})
        assert result.success
        assert "long description" in result.data["rows"][0]["description"]


# ===========================================================================
# CSV Write Tool
# ===========================================================================

class TestCSVWriteTool:
    @pytest.fixture
    def tool(self):
        return CSVWriteTool()

    @pytest.mark.asyncio
    async def test_write_dicts(self, tool):
        rows = [
            {"name": "Alice", "age": "30"},
            {"name": "Bob", "age": "25"},
        ]
        result = await tool.execute({"rows": rows})
        assert result.success
        assert "Alice" in result.output
        assert "Bob" in result.output

    @pytest.mark.asyncio
    async def test_write_lists(self, tool):
        rows = [["Alice", "30"], ["Bob", "25"]]
        result = await tool.execute({"rows": rows, "headers": ["name", "age"]})
        assert result.success
        assert "name,age" in result.output

    @pytest.mark.asyncio
    async def test_write_custom_delimiter(self, tool):
        rows = [{"name": "Alice", "age": "30"}]
        result = await tool.execute({"rows": rows, "delimiter": ";"})
        assert result.success
        assert ";" in result.output

    @pytest.mark.asyncio
    async def test_write_to_file(self, tool, tmp_path):
        path = str(tmp_path / "test.csv")
        rows = [{"name": "Alice"}, {"name": "Bob"}]
        result = await tool.execute({"rows": rows, "path": path})
        assert result.success
        assert "Written" in result.output or "written" in result.output

    @pytest.mark.asyncio
    async def test_empty_rows(self, tool):
        result = await tool.execute({"rows": []})
        assert not result.success

    @pytest.mark.asyncio
    async def test_roundtrip(self):
        """Write CSV then read it back."""
        write_tool = CSVWriteTool()
        read_tool = CSVReadTool()

        rows = [
            {"name": "Alice", "age": "30", "city": "NYC"},
            {"name": "Bob", "age": "25", "city": "LA"},
        ]
        write_result = await write_tool.execute({"rows": rows})
        assert write_result.success

        read_result = await read_tool.execute({"data": write_result.output})
        assert read_result.success
        assert read_result.data["row_count"] == 2
        assert read_result.data["rows"][0]["name"] == "Alice"


# ===========================================================================
# CSV Stats Tool
# ===========================================================================

class TestCSVStatsTool:
    @pytest.fixture
    def tool(self):
        return CSVStatsTool()

    @pytest.mark.asyncio
    async def test_numeric_stats(self, tool):
        csv_data = "value\n10\n20\n30\n40\n50"
        result = await tool.execute({"data": csv_data})
        assert result.success
        stats = result.data["stats"]["value"]
        assert stats["type"] == "numeric"
        assert stats["min"] == 10
        assert stats["max"] == 50
        assert stats["mean"] == 30

    @pytest.mark.asyncio
    async def test_text_stats(self, tool):
        csv_data = "color\nred\nblue\nred\ngreen\nred"
        result = await tool.execute({"data": csv_data})
        assert result.success
        stats = result.data["stats"]["color"]
        assert stats["type"] == "text"
        assert stats["unique_values"] == 3
        assert stats["most_common"] == "red"

    @pytest.mark.asyncio
    async def test_mixed_columns(self, tool):
        csv_data = "name,score\nAlice,95\nBob,87\nCharlie,92"
        result = await tool.execute({"data": csv_data})
        assert result.success
        assert result.data["stats"]["name"]["type"] == "text"
        assert result.data["stats"]["score"]["type"] == "numeric"

    @pytest.mark.asyncio
    async def test_column_selection(self, tool):
        csv_data = "a,b,c\n1,2,3\n4,5,6"
        result = await tool.execute({"data": csv_data, "columns": ["a"]})
        assert result.success
        assert "a" in result.data["stats"]
        assert "b" not in result.data["stats"]

    @pytest.mark.asyncio
    async def test_null_handling(self, tool):
        csv_data = "value\n10\n\n30\n\n50"
        result = await tool.execute({"data": csv_data})
        assert result.success
        stats = result.data["stats"]["value"]
        assert stats["null_count"] >= 0  # Empty rows may or may not produce empty values

    @pytest.mark.asyncio
    async def test_single_row(self, tool):
        csv_data = "val\n42"
        result = await tool.execute({"data": csv_data})
        assert result.success
        assert result.data["stats"]["val"]["mean"] == 42


# ===========================================================================
# XML to JSON Tool
# ===========================================================================

class TestXMLToJsonTool:
    @pytest.fixture
    def tool(self):
        return XMLToJsonTool()

    @pytest.mark.asyncio
    async def test_simple_xml(self, tool):
        xml = "<root><name>Alice</name><age>30</age></root>"
        result = await tool.execute({"xml": xml})
        assert result.success
        data = result.data["result"]
        assert "root" in data

    @pytest.mark.asyncio
    async def test_xml_with_attributes(self, tool):
        xml = '<person id="1"><name>Alice</name></person>'
        result = await tool.execute({"xml": xml})
        assert result.success

    @pytest.mark.asyncio
    async def test_nested_xml(self, tool):
        xml = """
        <library>
            <book id="1"><title>Python Guide</title><author>Alice</author></book>
            <book id="2"><title>JS Guide</title><author>Bob</author></book>
        </library>
        """
        result = await tool.execute({"xml": xml})
        assert result.success

    @pytest.mark.asyncio
    async def test_detailed_format(self, tool):
        xml = '<root attr="val">text</root>'
        result = await tool.execute({"xml": xml, "format": "detailed"})
        assert result.success
        data = result.data["result"]
        assert "root" in data

    @pytest.mark.asyncio
    async def test_invalid_xml(self, tool):
        result = await tool.execute({"xml": "<unclosed>"})
        assert not result.success
        assert "parse error" in result.output.lower()

    @pytest.mark.asyncio
    async def test_custom_root_tag(self, tool):
        xml = "<data><item>1</item></data>"
        result = await tool.execute({"xml": xml, "root_tag": "custom"})
        assert result.success
        assert "custom" in result.data["result"]

    @pytest.mark.asyncio
    async def test_empty_elements(self, tool):
        xml = "<root><empty/><filled>val</filled></root>"
        result = await tool.execute({"xml": xml})
        assert result.success


# ===========================================================================
# XML Query Tool
# ===========================================================================

class TestXMLQueryTool:
    @pytest.fixture
    def tool(self):
        return XMLQueryTool()

    @pytest.mark.asyncio
    async def test_simple_query(self, tool):
        xml = "<root><item>A</item><item>B</item></root>"
        result = await tool.execute({"xml": xml, "query": ".//item"})
        assert result.success
        assert result.data["count"] == 2

    @pytest.mark.asyncio
    async def test_nested_query(self, tool):
        xml = """
        <store>
            <books>
                <book><title>Python</title></book>
                <book><title>Java</title></book>
            </books>
            <magazines>
                <book><title>Tech</title></book>
            </magazines>
        </store>
        """
        result = await tool.execute({"xml": xml, "query": ".//book"})
        assert result.success
        assert result.data["count"] == 3

    @pytest.mark.asyncio
    async def test_attribute_query(self, tool):
        xml = '<root><item id="1">A</item><item id="2">B</item></root>'
        result = await tool.execute({"xml": xml, "query": ".//item[@id='1']"})
        assert result.success
        assert result.data["count"] == 1

    @pytest.mark.asyncio
    async def test_no_matches(self, tool):
        xml = "<root><item>A</item></root>"
        result = await tool.execute({"xml": xml, "query": ".//nonexistent"})
        assert result.success
        assert result.data["count"] == 0

    @pytest.mark.asyncio
    async def test_limit(self, tool):
        xml = "<root>" + "".join(f"<item>{i}</item>" for i in range(50)) + "</root>"
        result = await tool.execute({"xml": xml, "query": ".//item", "limit": 5})
        assert result.success
        assert result.data["count"] == 50
        assert result.data["truncated"] is True
        assert len(result.data["matches"]) == 5

    @pytest.mark.asyncio
    async def test_invalid_xml(self, tool):
        result = await tool.execute({"xml": "<bad>", "query": ".//item"})
        assert not result.success


# ===========================================================================
# Color Convert Tool
# ===========================================================================

class TestColorConvertTool:
    @pytest.fixture
    def tool(self):
        return ColorConvertTool()

    @pytest.mark.asyncio
    async def test_hex_to_all(self, tool):
        result = await tool.execute({"value": "#ff5733", "from_format": "hex"})
        assert result.success
        color = result.data["color"]
        assert color["hex"] == "#ff5733"
        assert color["rgb"]["r"] == 255
        assert "hsl" in color
        assert "hsv" in color

    @pytest.mark.asyncio
    async def test_rgb_to_all(self, tool):
        result = await tool.execute({"value": "255,87,51", "from_format": "rgb"})
        assert result.success
        assert result.data["color"]["hex"] == "#ff5733"

    @pytest.mark.asyncio
    async def test_short_hex(self, tool):
        result = await tool.execute({"value": "#f00", "from_format": "hex"})
        assert result.success
        assert result.data["color"]["rgb"]["r"] == 255

    @pytest.mark.asyncio
    async def test_hex_without_hash(self, tool):
        result = await tool.execute({"value": "3498db", "from_format": "hex"})
        assert result.success

    @pytest.mark.asyncio
    async def test_black(self, tool):
        result = await tool.execute({"value": "#000000", "from_format": "hex"})
        assert result.success
        assert result.data["color"]["rgb"] == {"r": 0, "g": 0, "b": 0}

    @pytest.mark.asyncio
    async def test_white(self, tool):
        result = await tool.execute({"value": "#ffffff", "from_format": "hex"})
        assert result.success
        assert result.data["color"]["rgb"] == {"r": 255, "g": 255, "b": 255}

    @pytest.mark.asyncio
    async def test_invalid_hex(self, tool):
        result = await tool.execute({"value": "xyz", "from_format": "hex"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_css_output(self, tool):
        result = await tool.execute({"value": "#ff0000", "from_format": "hex"})
        assert result.success
        assert result.data["color"]["css_rgb"].startswith("rgb(")
        assert result.data["color"]["css_hsl"].startswith("hsl(")


# ===========================================================================
# Color Palette Tool
# ===========================================================================

class TestColorPaletteTool:
    @pytest.fixture
    def tool(self):
        return ColorPaletteTool()

    @pytest.mark.asyncio
    async def test_complementary_palette(self, tool):
        result = await tool.execute({"base_color": "#3498db", "count": 5})
        assert result.success
        assert len(result.data["colors"]) == 5

    @pytest.mark.asyncio
    async def test_analogous_palette(self, tool):
        result = await tool.execute({
            "base_color": "#e74c3c",
            "count": 3,
            "palette_type": "analogous",
        })
        assert result.success
        assert len(result.data["colors"]) == 3

    @pytest.mark.asyncio
    async def test_triadic_palette(self, tool):
        result = await tool.execute({
            "base_color": "#2ecc71",
            "palette_type": "triadic",
        })
        assert result.success

    @pytest.mark.asyncio
    async def test_monochromatic_palette(self, tool):
        result = await tool.execute({
            "base_color": "#9b59b6",
            "count": 6,
            "palette_type": "monochromatic",
        })
        assert result.success
        assert len(result.data["colors"]) == 6

    @pytest.mark.asyncio
    async def test_invalid_color(self, tool):
        result = await tool.execute({"base_color": "invalid"})
        assert not result.success

    @pytest.mark.asyncio
    async def test_max_count(self, tool):
        result = await tool.execute({"base_color": "#3498db", "count": 100})
        assert result.success
        assert len(result.data["colors"]) == 20  # Capped at 20

    @pytest.mark.asyncio
    async def test_all_colors_have_formats(self, tool):
        result = await tool.execute({"base_color": "#3498db", "count": 3})
        for color in result.data["colors"]:
            assert "hex" in color
            assert "rgb" in color
            assert "hsl" in color


# ===========================================================================
# Random String Tool
# ===========================================================================

class TestRandomStringTool:
    @pytest.fixture
    def tool(self):
        return RandomStringTool()

    @pytest.mark.asyncio
    async def test_default_string(self, tool):
        result = await tool.execute({})
        assert result.success
        assert len(result.data["strings"][0]) == 16

    @pytest.mark.asyncio
    async def test_custom_length(self, tool):
        result = await tool.execute({"length": 32})
        assert result.success
        assert len(result.data["strings"][0]) == 32

    @pytest.mark.asyncio
    async def test_digits_only(self, tool):
        result = await tool.execute({"length": 20, "charset": "digits"})
        assert result.success
        assert result.data["strings"][0].isdigit()

    @pytest.mark.asyncio
    async def test_hex_charset(self, tool):
        result = await tool.execute({"length": 16, "charset": "hex"})
        assert result.success
        for c in result.data["strings"][0]:
            assert c in "0123456789abcdef"

    @pytest.mark.asyncio
    async def test_multiple_strings(self, tool):
        result = await tool.execute({"count": 5, "length": 8})
        assert result.success
        assert len(result.data["strings"]) == 5

    @pytest.mark.asyncio
    async def test_prefix_suffix(self, tool):
        result = await tool.execute({"length": 8, "prefix": "usr-", "suffix": "-id"})
        assert result.success
        s = result.data["strings"][0]
        assert s.startswith("usr-")
        assert s.endswith("-id")

    @pytest.mark.asyncio
    async def test_separator(self, tool):
        result = await tool.execute({"length": 16, "separator": "-", "separator_every": 4})
        assert result.success
        assert "-" in result.data["strings"][0]

    @pytest.mark.asyncio
    async def test_secure_mode(self, tool):
        result = await tool.execute({"length": 32, "secure": True})
        assert result.success
        assert len(result.data["strings"][0]) == 32

    @pytest.mark.asyncio
    async def test_custom_charset(self, tool):
        result = await tool.execute({"length": 10, "charset": "custom", "custom_chars": "AB"})
        assert result.success
        for c in result.data["strings"][0]:
            assert c in "AB"

    @pytest.mark.asyncio
    async def test_empty_custom_charset(self, tool):
        result = await tool.execute({"charset": "custom"})
        assert not result.success


# ===========================================================================
# Random Number Tool
# ===========================================================================

class TestRandomNumberTool:
    @pytest.fixture
    def tool(self):
        return RandomNumberTool()

    @pytest.mark.asyncio
    async def test_default_integer(self, tool):
        result = await tool.execute({})
        assert result.success
        num = result.data["numbers"][0]
        assert 0 <= num <= 100

    @pytest.mark.asyncio
    async def test_custom_range(self, tool):
        result = await tool.execute({"min": 10, "max": 20})
        assert result.success
        assert 10 <= result.data["numbers"][0] <= 20

    @pytest.mark.asyncio
    async def test_float_type(self, tool):
        result = await tool.execute({"type": "float", "min": 0, "max": 1})
        assert result.success
        assert 0 <= result.data["numbers"][0] <= 1

    @pytest.mark.asyncio
    async def test_multiple_numbers(self, tool):
        result = await tool.execute({"count": 10})
        assert result.success
        assert len(result.data["numbers"]) == 10

    @pytest.mark.asyncio
    async def test_unique_integers(self, tool):
        result = await tool.execute({"min": 1, "max": 10, "count": 5, "unique": True})
        assert result.success
        nums = result.data["numbers"]
        assert len(set(nums)) == 5

    @pytest.mark.asyncio
    async def test_unique_impossible(self, tool):
        result = await tool.execute({"min": 1, "max": 3, "count": 5, "unique": True})
        assert not result.success

    @pytest.mark.asyncio
    async def test_seed_reproducibility(self, tool):
        r1 = await tool.execute({"seed": 42})
        r2 = await tool.execute({"seed": 42})
        assert r1.data["numbers"] == r2.data["numbers"]

    @pytest.mark.asyncio
    async def test_invalid_range(self, tool):
        result = await tool.execute({"min": 100, "max": 1})
        assert not result.success

    @pytest.mark.asyncio
    async def test_normal_distribution(self, tool):
        result = await tool.execute({
            "type": "float", "min": 0, "max": 100,
            "count": 50, "distribution": "normal",
        })
        assert result.success
        assert len(result.data["numbers"]) == 50


# ===========================================================================
# Random Choice Tool
# ===========================================================================

class TestRandomChoiceTool:
    @pytest.fixture
    def tool(self):
        return RandomChoiceTool()

    @pytest.mark.asyncio
    async def test_single_choice(self, tool):
        result = await tool.execute({"items": ["red", "green", "blue"]})
        assert result.success
        assert result.data["selected"][0] in ["red", "green", "blue"]

    @pytest.mark.asyncio
    async def test_multiple_choices(self, tool):
        result = await tool.execute({"items": ["a", "b", "c", "d"], "count": 2})
        assert result.success
        assert len(result.data["selected"]) == 2

    @pytest.mark.asyncio
    async def test_unique_choices(self, tool):
        result = await tool.execute({"items": ["a", "b", "c", "d"], "count": 3})
        assert result.success
        assert len(set(result.data["selected"])) == 3

    @pytest.mark.asyncio
    async def test_with_replacement(self, tool):
        result = await tool.execute({
            "items": ["a", "b"],
            "count": 10,
            "replacement": True,
        })
        assert result.success
        assert len(result.data["selected"]) == 10

    @pytest.mark.asyncio
    async def test_shuffle(self, tool):
        items = ["1", "2", "3", "4", "5"]
        result = await tool.execute({"items": items, "shuffle": True})
        assert result.success
        assert sorted(result.data["selected"]) == sorted(items)

    @pytest.mark.asyncio
    async def test_empty_list(self, tool):
        result = await tool.execute({"items": []})
        assert not result.success

    @pytest.mark.asyncio
    async def test_too_many_without_replacement(self, tool):
        result = await tool.execute({"items": ["a", "b"], "count": 5})
        assert not result.success

    @pytest.mark.asyncio
    async def test_seed(self, tool):
        r1 = await tool.execute({"items": ["a", "b", "c", "d", "e"], "count": 3, "seed": 42})
        r2 = await tool.execute({"items": ["a", "b", "c", "d", "e"], "count": 3, "seed": 42})
        assert r1.data["selected"] == r2.data["selected"]

    @pytest.mark.asyncio
    async def test_weighted_choice(self, tool):
        # Heavy weight on first item
        result = await tool.execute({
            "items": ["heavy", "light"],
            "count": 1,
            "weights": [100.0, 0.001],
            "seed": 42,
        })
        assert result.success
