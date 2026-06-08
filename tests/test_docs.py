"""Tests for jarvis.docs — API documentation generator."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from jarvis.docs.generator import (
    APIDocGenerator,
    EndpointDoc,
    ModuleDoc,
    ParameterDoc,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_fake_app(routes: list[Any] | None = None) -> MagicMock:
    """Build a minimal mock that mimics a FastAPI ``app``."""
    app = MagicMock()
    if routes is None:
        routes = []
    app.routes = routes
    return app


def _make_http_route(
    path: str,
    methods: set[str],
    name: str = "",
    summary: str = "",
    description: str = "",
    tags: list[str] | None = None,
    endpoint=None,
):
    route = MagicMock()
    route.path = path
    route.methods = methods
    route.name = name or path.split("/")[-1]
    route.summary = summary
    route.description = description
    route.tags = tags
    if endpoint:
        route.endpoint = endpoint
    else:
        fn = lambda: None  # noqa: E731
        fn.__doc__ = description or ""
        route.endpoint = fn
    return route


def _make_ws_route(path: str, name: str = "ws"):
    route = MagicMock()
    route.path = path
    route.name = name
    # Ensure "websocket" appears in the type name (checked by generator)
    route.__class__.__name__ = "WebSocketRoute"
    route.__class__.__qualname__ = "WebSocketRoute"
    # No 'methods' attribute — the generator uses this to distinguish
    if hasattr(route, "methods"):
        del route.methods
    type(route).__str__ = lambda self: "WebSocketRoute"
    fn = lambda: None  # noqa: E731
    fn.__doc__ = "WS endpoint"
    route.endpoint = fn
    return route


# ---------------------------------------------------------------------------
# EndpointDoc / ModuleDoc creation
# ---------------------------------------------------------------------------

class TestEndpointDoc:
    def test_create_minimal(self):
        ep = EndpointDoc(method="GET", path="/health")
        assert ep.method == "GET"
        assert ep.path == "/health"
        assert ep.summary == ""
        assert ep.tags == []
        assert ep.parameters == []
        assert ep.status_codes == {}
        assert ep.auth_required is False
        assert ep.rate_limited is False

    def test_create_full(self):
        ep = EndpointDoc(
            method="POST",
            path="/items",
            summary="Create item",
            description="Creates a new item",
            tags=["items"],
            parameters=[ParameterDoc(name="x", type="int")],
            request_body={"type": "object"},
            response_schema={"type": "object"},
            response_example={"id": 1},
            status_codes={200: "OK", 201: "Created"},
            auth_required=True,
            rate_limited=True,
        )
        assert ep.method == "POST"
        assert ep.auth_required is True
        assert ep.rate_limited is True
        assert len(ep.parameters) == 1
        assert ep.status_codes[201] == "Created"

    def test_parameter_doc_defaults(self):
        p = ParameterDoc(name="id", type="string")
        assert p.required is True
        assert p.default is None
        assert p.example is None


class TestModuleDoc:
    def test_create_empty(self):
        m = ModuleDoc(name="mymod")
        assert m.name == "mymod"
        assert m.classes == []
        assert m.functions == []
        assert m.constants == []

    def test_create_populated(self):
        m = ModuleDoc(
            name="tools",
            description="Tool registry module",
            version="1.0",
            classes=[{"name": "ToolRegistry", "docstring": "Manages tools"}],
            functions=[{"name": "register", "docstring": "Register a tool"}],
        )
        assert len(m.classes) == 1
        assert m.classes[0]["name"] == "ToolRegistry"


# ---------------------------------------------------------------------------
# FastAPI extraction
# ---------------------------------------------------------------------------

class TestExtractFromFastAPI:
    def test_empty_app(self):
        gen = APIDocGenerator()
        result = gen.extract_from_fastapi(_make_fake_app())
        assert result == []

    def test_single_get_route(self):
        route = _make_http_route("/health", {"GET"}, summary="Health check")
        gen = APIDocGenerator()
        eps = gen.extract_from_fastapi(_make_fake_app([route]))
        assert len(eps) == 1
        assert eps[0].method == "GET"
        assert eps[0].path == "/health"
        assert eps[0].summary == "Health check"

    def test_path_params_extracted(self):
        route = _make_http_route("/items/{item_id}", {"GET"})
        gen = APIDocGenerator()
        eps = gen.extract_from_fastapi(_make_fake_app([route]))
        assert len(eps) == 1
        params = eps[0].parameters
        assert len(params) == 1
        assert params[0].name == "item_id"
        assert params[0].required is True

    def test_multiple_methods(self):
        route = _make_http_route("/resource", {"GET", "POST"})
        gen = APIDocGenerator()
        eps = gen.extract_from_fastapi(_make_fake_app([route]))
        methods = {ep.method for ep in eps}
        assert methods == {"GET", "POST"}

    def test_post_status_codes_include_201(self):
        route = _make_http_route("/items", {"POST"})
        gen = APIDocGenerator()
        eps = gen.extract_from_fastapi(_make_fake_app([route]))
        post_ep = [e for e in eps if e.method == "POST"][0]
        assert 201 in post_ep.status_codes

    def test_websocket_route(self):
        ws = _make_ws_route("/ws/specs/{spec_id}")
        # We need the type string to contain 'websocket'
        gen = APIDocGenerator()
        eps = gen.extract_from_fastapi(_make_fake_app([ws]))
        # Should detect the WebSocket route
        assert len(eps) == 1
        assert eps[0].method == "WEBSOCKET"

    def test_tags_propagated(self):
        route = _make_http_route("/tagged", {"GET"}, tags=["alpha", "beta"])
        gen = APIDocGenerator()
        eps = gen.extract_from_fastapi(_make_fake_app([route]))
        assert eps[0].tags == ["alpha", "beta"]

    def test_endpoints_stored_on_generator(self):
        route = _make_http_route("/a", {"GET"})
        gen = APIDocGenerator()
        gen.extract_from_fastapi(_make_fake_app([route]))
        assert len(gen.endpoints) == 1


# ---------------------------------------------------------------------------
# OpenAPI spec generation
# ---------------------------------------------------------------------------

class TestGenerateOpenAPI:
    def _gen_with_endpoints(self, endpoints: list[EndpointDoc]) -> dict:
        gen = APIDocGenerator()
        gen._endpoints = endpoints
        return gen.generate_openapi()

    def test_basic_structure(self):
        spec = self._gen_with_endpoints([])
        assert spec["openapi"] == "3.0.3"
        assert "info" in spec
        assert "paths" in spec
        assert "tags" in spec

    def test_info_defaults(self):
        spec = self._gen_with_endpoints([])
        assert spec["info"]["title"] == "JARVIS API"
        assert spec["info"]["version"] == "0.2.0"

    def test_custom_info(self):
        gen = APIDocGenerator()
        spec = gen.generate_openapi(title="Custom", version="1.0.0", description="Test")
        assert spec["info"]["title"] == "Custom"
        assert spec["info"]["version"] == "1.0.0"
        assert spec["info"]["description"] == "Test"

    def test_endpoint_in_paths(self):
        ep = EndpointDoc(
            method="GET",
            path="/health",
            summary="Check",
            status_codes={200: "OK"},
            tags=["system"],
        )
        spec = self._gen_with_endpoints([ep])
        assert "/health" in spec["paths"]
        assert "get" in spec["paths"]["/health"]
        assert spec["paths"]["/health"]["get"]["summary"] == "Check"

    def test_websocket_skipped_in_paths(self):
        ep = EndpointDoc(method="WEBSOCKET", path="/ws")
        spec = self._gen_with_endpoints([ep])
        assert "/ws" not in spec["paths"]

    def test_tags_collected(self):
        eps = [
            EndpointDoc(method="GET", path="/a", tags=["x"]),
            EndpointDoc(method="GET", path="/b", tags=["y", "x"]),
        ]
        spec = self._gen_with_endpoints(eps)
        tag_names = {t["name"] for t in spec["tags"]}
        assert tag_names == {"x", "y"}

    def test_parameters_in_spec(self):
        ep = EndpointDoc(
            method="GET",
            path="/items/{id}",
            parameters=[ParameterDoc(name="id", type="string", description="Item ID")],
            status_codes={200: "OK"},
        )
        spec = self._gen_with_endpoints([ep])
        params = spec["paths"]["/items/{id}"]["get"]["parameters"]
        assert len(params) == 1
        assert params[0]["name"] == "id"
        assert params[0]["in"] == "path"

    def test_request_body_in_spec(self):
        ep = EndpointDoc(
            method="POST",
            path="/create",
            request_body={"type": "object", "properties": {"name": {"type": "string"}}},
            status_codes={201: "Created"},
        )
        spec = self._gen_with_endpoints([ep])
        rb = spec["paths"]["/create"]["post"]["requestBody"]
        assert rb["required"] is True
        assert "application/json" in rb["content"]


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------

class TestGenerateMarkdown:
    def test_contains_header(self):
        gen = APIDocGenerator()
        md = gen.generate_markdown()
        assert "# JARVIS API Documentation" in md

    def test_contains_generated_date(self):
        gen = APIDocGenerator()
        md = gen.generate_markdown()
        assert "Generated:" in md

    def test_endpoint_rendered(self):
        gen = APIDocGenerator()
        gen._endpoints = [
            EndpointDoc(method="GET", path="/health", summary="Health check", tags=["system"]),
        ]
        md = gen.generate_markdown()
        assert "`GET /health`" in md
        assert "Health check" in md

    def test_parameters_table(self):
        gen = APIDocGenerator()
        gen._endpoints = [
            EndpointDoc(
                method="GET",
                path="/items/{id}",
                parameters=[ParameterDoc(name="id", type="string", description="Item ID")],
                tags=["items"],
            ),
        ]
        md = gen.generate_markdown()
        assert "| `id` |" in md
        assert "Item ID" in md

    def test_module_reference_section(self):
        gen = APIDocGenerator()
        gen._modules = [
            ModuleDoc(
                name="tools",
                description="Tool registry",
                classes=[{"name": "Registry", "docstring": "Manages tools", "methods": []}],
            ),
        ]
        md = gen.generate_markdown()
        assert "## Module Reference" in md
        assert "`jarvis.tools`" in md


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

class TestGenerateHTML:
    def test_contains_html_boilerplate(self):
        gen = APIDocGenerator()
        html = gen.generate_html()
        assert "<!DOCTYPE html>" in html
        assert "<title>JARVIS API Documentation</title>" in html
        assert "</html>" in html

    def test_contains_style_block(self):
        gen = APIDocGenerator()
        html = gen.generate_html()
        assert "<style>" in html

    def test_endpoint_appears_in_html(self):
        gen = APIDocGenerator()
        gen._endpoints = [
            EndpointDoc(method="POST", path="/chat", summary="Chat", tags=["chat"]),
        ]
        html = gen.generate_html()
        assert "POST /chat" in html or "POST" in html


# ---------------------------------------------------------------------------
# Module extraction (uses mocks)
# ---------------------------------------------------------------------------

class TestExtractModuleDocs:
    def test_unknown_module_logged_and_skipped(self):
        gen = APIDocGenerator()
        result = gen.extract_module_docs(["nonexistent_module_xyz"])
        assert result == []

    def test_modules_stored(self):
        gen = APIDocGenerator()
        gen._modules = [ModuleDoc(name="a"), ModuleDoc(name="b")]
        assert len(gen.modules) == 2


# ---------------------------------------------------------------------------
# Tag extraction
# ---------------------------------------------------------------------------

class TestTagExtraction:
    def test_empty_endpoints(self):
        gen = APIDocGenerator()
        assert gen._extract_tags() == []

    def test_deduplication(self):
        gen = APIDocGenerator()
        gen._endpoints = [
            EndpointDoc(method="GET", path="/a", tags=["x", "y"]),
            EndpointDoc(method="GET", path="/b", tags=["y", "z"]),
        ]
        tags = gen._extract_tags()
        names = [t["name"] for t in tags]
        assert sorted(names) == ["x", "y", "z"]


# ---------------------------------------------------------------------------
# add_endpoint / add_module helpers
# ---------------------------------------------------------------------------

class TestManualRegistration:
    def test_add_endpoint(self):
        gen = APIDocGenerator()
        ep = EndpointDoc(method="GET", path="/test")
        gen.add_endpoint(ep)
        assert len(gen.endpoints) == 1

    def test_add_module(self):
        gen = APIDocGenerator()
        m = ModuleDoc(name="custom")
        gen.add_module(m)
        assert len(gen.modules) == 1


# ---------------------------------------------------------------------------
# Markdown-to-HTML converter
# ---------------------------------------------------------------------------

class TestMarkdownToHtml:
    def test_header_conversion(self):
        result = APIDocGenerator._markdown_to_html("# Title")
        assert "<h1>Title</h1>" in result

    def test_code_fence(self):
        md = "```json\n{\"key\": \"val\"}\n```"
        result = APIDocGenerator._markdown_to_html(md)
        assert "<pre>" in result
        assert "</pre>" in result

    def test_inline_code(self):
        result = APIDocGenerator._markdown_to_html("Use `foo` here")
        assert "<code>foo</code>" in result

    def test_bold_text(self):
        result = APIDocGenerator._markdown_to_html("This is **bold** text")
        assert "<strong>bold</strong>" in result

    def test_table_conversion(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = APIDocGenerator._markdown_to_html(md)
        assert "<table>" in result
        assert "</table>" in result

    def test_list_items(self):
        result = APIDocGenerator._markdown_to_html("- item one\n- item two")
        assert "<li>item one</li>" in result
        assert "<li>item two</li>" in result
