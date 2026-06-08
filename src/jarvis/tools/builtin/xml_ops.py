"""XML processing tools: conversion to JSON and XPath-like querying."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


def _element_to_dict(elem: ET.Element) -> dict[str, Any]:
    """Recursively convert an ElementTree element to a dict.

    Structure:
        {
            "tag": "person",
            "attrib": {"id": "1"},
            "text": "...",
            "children": [...]
        }
    If an element has no attributes, text, or children, those keys are omitted
    from the compact representation.
    """
    result: dict[str, Any] = {"tag": elem.tag}

    # Strip namespace if present
    if "}" in elem.tag:
        result["tag"] = elem.tag.split("}", 1)[1]
        result["namespace"] = elem.tag.split("}", 1)[0].lstrip("{")

    if elem.attrib:
        result["attrib"] = dict(elem.attrib)

    text = (elem.text or "").strip()
    if text:
        result["text"] = text

    tail = (elem.tail or "").strip()
    if tail:
        result["tail"] = tail

    children = [_element_to_dict(child) for child in elem]
    if children:
        result["children"] = children

    return result


def _element_to_simple_dict(elem: ET.Element) -> Any:
    """Convert an ElementTree element to a simplified JSON-friendly dict.

    When a tag has only text content and no children, it becomes a simple
    key-value pair.  When a tag has children, they are grouped by tag name;
    if multiple children share a tag they become a list.
    """
    result: dict[str, Any] = {}

    # Add attributes prefixed with @
    for k, v in elem.attrib.items():
        result[f"@{k}"] = v

    children_by_tag: dict[str, list[Any]] = {}
    for child in elem:
        tag = child.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]
        child_val = _element_to_simple_dict(child)
        children_by_tag.setdefault(tag, []).append(child_val)

    for tag, vals in children_by_tag.items():
        result[tag] = vals if len(vals) > 1 else vals[0]

    text = (elem.text or "").strip()
    if text and not result:
        return text
    if text:
        result["#text"] = text

    return result


class XMLToJsonTool(BaseTool):
    """Convert XML data to a JSON dictionary."""

    name = "xml_to_json"
    description = (
        "Parse an XML string and convert it to a JSON-compatible dictionary. "
        "Supports two output formats: 'simple' (tag-based nesting) and "
        "'detailed' (preserves tag/attrib/text/children structure). "
        "Handles namespaces by stripping namespace URIs from tag names."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "The XML content as a string.",
            },
            "format": {
                "type": "string",
                "enum": ["simple", "detailed"],
                "description": (
                    "Output format: 'simple' for compact key-value nesting, "
                    "'detailed' for full tag/attrib/text/children structure. "
                    "Default: 'simple'."
                ),
            },
            "root_tag": {
                "type": "string",
                "description": (
                    "If set, wraps the result under this key. "
                    "Otherwise the root element tag is used."
                ),
            },
        },
        "required": ["xml"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        xml_str: str = arguments["xml"]
        fmt: str = arguments.get("format", "simple")
        root_tag: str | None = arguments.get("root_tag")

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            return ToolResult(success=False, output=f"XML parse error: {exc}")

        if fmt == "detailed":
            result = _element_to_dict(root)
        else:
            result = _element_to_simple_dict(root)

        tag = root_tag or root.tag
        if "}" in tag:
            tag = tag.split("}", 1)[1]

        wrapped = {tag: result}

        output = json.dumps(wrapped, indent=2, ensure_ascii=False)
        return ToolResult(
            success=True,
            output=output,
            data={"result": wrapped},
        )


class XMLQueryTool(BaseTool):
    """Query XML data using XPath-like expressions."""

    name = "xml_query"
    description = (
        "Parse an XML string and query it using XPath expressions supported "
        "by Python's xml.etree.ElementTree (a subset of XPath 1.0). "
        "Returns matching elements as a list of dicts. "
        "Common patterns: './/tag', './tag/subtag', './/tag[@attr]', "
        "'.//tag[@attr=\"value\"]', './/' for all descendants."
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "xml": {
                "type": "string",
                "description": "The XML content as a string.",
            },
            "query": {
                "type": "string",
                "description": (
                    "XPath expression to match elements, e.g. './/book', "
                    "'.//item[@category=\"web\"]', './channel/item'."
                ),
            },
            "format": {
                "type": "string",
                "enum": ["simple", "detailed"],
                "description": "Output format for matched elements (default: 'simple').",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default: 100).",
            },
        },
        "required": ["xml", "query"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        xml_str: str = arguments["xml"]
        query: str = arguments["query"]
        fmt: str = arguments.get("format", "simple")
        limit: int = arguments.get("limit", 100)

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            return ToolResult(success=False, output=f"XML parse error: {exc}")

        try:
            matches = root.findall(query)
        except Exception as exc:
            return ToolResult(success=False, output=f"XPath query error: {exc}")

        if not matches:
            return ToolResult(
                success=True,
                output="No elements matched the query.",
                data={"matches": [], "count": 0},
            )

        results = []
        for elem in matches[:limit]:
            if fmt == "detailed":
                results.append(_element_to_dict(elem))
            else:
                results.append(_element_to_simple_dict(elem))

        total_found = len(matches)
        truncated = total_found > limit

        output_data = {
            "count": total_found,
            "truncated": truncated,
            "matches": results,
        }
        output = json.dumps(output_data, indent=2, ensure_ascii=False)

        summary = f"Found {total_found} matching element(s)"
        if truncated:
            summary += f" (showing first {limit})"

        return ToolResult(
            success=True,
            output=f"{summary}\n{output}",
            data=output_data,
        )
