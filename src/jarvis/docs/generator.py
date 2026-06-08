"""API Documentation Generator for JARVIS.

Generates comprehensive API documentation including OpenAPI 3.0 specs,
Markdown reference docs, and standalone HTML documentation pages by
introspecting FastAPI applications and Python modules.
"""

from __future__ import annotations

import inspect
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, get_type_hints

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ParameterDoc(BaseModel):
    """Documentation for a single API parameter."""

    name: str
    type: str
    required: bool = True
    description: str = ""
    default: Any = None
    example: Any = None


class EndpointDoc(BaseModel):
    """Documentation for a single API endpoint."""

    method: str  # GET, POST, PUT, DELETE, PATCH, WEBSOCKET
    path: str
    summary: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[ParameterDoc] = Field(default_factory=list)
    request_body: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    response_example: Any = None
    status_codes: dict[int, str] = Field(default_factory=dict)
    auth_required: bool = False
    rate_limited: bool = False


class ModuleDoc(BaseModel):
    """Documentation for a Python module."""

    name: str
    description: str = ""
    version: str = ""
    classes: list[dict[str, Any]] = Field(default_factory=list)
    functions: list[dict[str, Any]] = Field(default_factory=list)
    constants: list[dict[str, str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class APIDocGenerator:
    """Generates comprehensive API documentation for JARVIS.

    Features:
    - Auto-extracts endpoints from FastAPI app
    - Generates OpenAPI 3.0 spec
    - Generates Markdown documentation
    - Generates HTML documentation page
    - Module-level documentation from docstrings
    """

    def __init__(self) -> None:
        self._endpoints: list[EndpointDoc] = []
        self._modules: list[ModuleDoc] = []

    # -- properties --------------------------------------------------------

    @property
    def endpoints(self) -> list[EndpointDoc]:
        return list(self._endpoints)

    @property
    def modules(self) -> list[ModuleDoc]:
        return list(self._modules)

    # -- extraction --------------------------------------------------------

    def extract_from_fastapi(self, app: Any) -> list[EndpointDoc]:
        """Extract endpoint documentation from a FastAPI application.

        Iterates over all registered routes, extracting HTTP method, path,
        docstrings, path parameters, request body schemas (from Pydantic
        models), and standard status codes.
        """
        endpoints: list[EndpointDoc] = []

        for route in app.routes:
            # Regular HTTP routes
            if hasattr(route, "methods"):
                for method in route.methods:
                    doc = EndpointDoc(
                        method=method,
                        path=route.path,
                        summary=getattr(route, "summary", None) or getattr(route, "name", "") or "",
                        description=getattr(route, "description", None) or (
                            route.endpoint.__doc__ or "" if hasattr(route, "endpoint") else ""
                        ),
                        tags=list(route.tags) if hasattr(route, "tags") and route.tags else [],
                    )

                    # Extract path parameters
                    path_params = re.findall(r"\{(\w+)\}", route.path)
                    for param in path_params:
                        doc.parameters.append(
                            ParameterDoc(
                                name=param,
                                type="string",
                                required=True,
                                description=f"Path parameter: {param}",
                            )
                        )

                    # Extract request body schema from type hints
                    if hasattr(route, "endpoint") and method in ("POST", "PUT", "PATCH"):
                        hints: dict[str, Any] = {}
                        try:
                            hints = get_type_hints(route.endpoint)
                        except Exception:
                            pass
                        for param_name, param_type in hints.items():
                            if param_name == "return":
                                continue
                            if hasattr(param_type, "model_json_schema"):
                                doc.request_body = param_type.model_json_schema()

                    # Standard status codes
                    doc.status_codes = {
                        200: "Success",
                        404: "Resource not found",
                        422: "Validation error",
                    }
                    if method == "POST":
                        doc.status_codes[201] = "Created"

                    endpoints.append(doc)

            # WebSocket routes
            elif hasattr(route, "path") and "websocket" in str(type(route)).lower():
                endpoints.append(
                    EndpointDoc(
                        method="WEBSOCKET",
                        path=route.path,
                        summary=getattr(route, "name", "") or "WebSocket endpoint",
                        description=(
                            route.endpoint.__doc__ or ""
                            if hasattr(route, "endpoint")
                            else ""
                        ),
                    )
                )

        self._endpoints = endpoints
        return endpoints

    def add_endpoint(self, endpoint: EndpointDoc) -> None:
        """Manually register an endpoint."""
        self._endpoints.append(endpoint)

    def extract_module_docs(self, module_names: list[str]) -> list[ModuleDoc]:
        """Extract documentation from JARVIS modules by name.

        For each module name, imports ``jarvis.<name>`` and introspects its
        public classes, functions, and constants.
        """
        modules: list[ModuleDoc] = []

        for name in module_names:
            try:
                mod = __import__(f"jarvis.{name}", fromlist=[name])
                doc = ModuleDoc(
                    name=name,
                    description=mod.__doc__ or "",
                )

                for attr_name in dir(mod):
                    if attr_name.startswith("_"):
                        continue
                    attr = getattr(mod, attr_name)

                    if inspect.isclass(attr):
                        class_doc: dict[str, Any] = {
                            "name": attr_name,
                            "docstring": attr.__doc__ or "",
                            "methods": [],
                            "bases": [
                                b.__name__
                                for b in attr.__bases__
                                if b.__name__ != "object"
                            ],
                        }
                        for method_name in dir(attr):
                            if method_name.startswith("_"):
                                continue
                            method = getattr(attr, method_name, None)
                            if callable(method) and hasattr(method, "__doc__"):
                                class_doc["methods"].append(
                                    {
                                        "name": method_name,
                                        "docstring": (method.__doc__ or "").strip()[:200],
                                        "is_async": inspect.iscoroutinefunction(method),
                                    }
                                )
                        doc.classes.append(class_doc)

                    elif callable(attr) and not inspect.isclass(attr):
                        doc.functions.append(
                            {
                                "name": attr_name,
                                "docstring": (attr.__doc__ or "").strip()[:200],
                                "is_async": inspect.iscoroutinefunction(attr),
                            }
                        )

                modules.append(doc)
            except Exception as exc:
                logger.warning("Failed to document module %s: %s", name, exc)

        self._modules = modules
        return modules

    def add_module(self, module_doc: ModuleDoc) -> None:
        """Manually register a module doc."""
        self._modules.append(module_doc)

    # -- OpenAPI -----------------------------------------------------------

    def generate_openapi(
        self,
        title: str = "JARVIS API",
        version: str = "0.2.0",
        description: str | None = None,
    ) -> dict[str, Any]:
        """Generate an OpenAPI 3.0.3 specification dictionary."""
        paths: dict[str, Any] = {}

        for ep in self._endpoints:
            method_key = ep.method.lower()
            if method_key == "websocket":
                # OpenAPI doesn't have native WebSocket support; skip
                continue

            path_key = ep.path
            if path_key not in paths:
                paths[path_key] = {}

            operation: dict[str, Any] = {
                "summary": ep.summary,
                "description": ep.description,
                "tags": ep.tags or ["default"],
                "responses": {
                    str(code): {"description": desc}
                    for code, desc in ep.status_codes.items()
                },
            }

            if ep.parameters:
                operation["parameters"] = [
                    {
                        "name": p.name,
                        "in": "path" if f"{{{p.name}}}" in ep.path else "query",
                        "required": p.required,
                        "schema": {"type": p.type},
                        "description": p.description,
                    }
                    for p in ep.parameters
                ]

            if ep.request_body:
                operation["requestBody"] = {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": ep.request_body,
                        }
                    },
                }

            if ep.auth_required:
                operation["security"] = [{"bearerAuth": []}]

            paths[path_key][method_key] = operation

        spec: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": {
                "title": title,
                "version": version,
                "description": description or "JARVIS — Streaming Spec Driven Personal AI Assistant API",
            },
            "paths": paths,
            "tags": self._extract_tags(),
        }

        return spec

    def _extract_tags(self) -> list[dict[str, str]]:
        """Collect unique tags from all endpoints."""
        tag_set: set[str] = set()
        for ep in self._endpoints:
            for tag in ep.tags:
                tag_set.add(tag)
        return [{"name": t} for t in sorted(tag_set)]

    # -- Markdown ----------------------------------------------------------

    def generate_markdown(self) -> str:
        """Generate Markdown API documentation."""
        lines: list[str] = [
            "# JARVIS API Documentation\n",
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
            "## Table of Contents\n",
        ]

        # Group endpoints by tag
        by_tag: dict[str, list[EndpointDoc]] = {}
        for ep in self._endpoints:
            tag = ep.tags[0] if ep.tags else "Other"
            by_tag.setdefault(tag, []).append(ep)

        for tag in sorted(by_tag.keys()):
            lines.append(f"- [{tag}](#{tag.lower().replace(' ', '-')})")
        lines.append("")

        for tag, endpoints in sorted(by_tag.items()):
            lines.append(f"## {tag}\n")
            for ep in endpoints:
                lines.append(f"### `{ep.method} {ep.path}`\n")
                lines.append(f"{ep.summary}\n")
                if ep.description:
                    lines.append(f"{ep.description}\n")

                if ep.parameters:
                    lines.append("**Parameters:**\n")
                    lines.append("| Name | Type | Required | Description |")
                    lines.append("|------|------|----------|-------------|")
                    for p in ep.parameters:
                        req = "Yes" if p.required else "No"
                        lines.append(
                            f"| `{p.name}` | `{p.type}` | {req} | {p.description} |"
                        )
                    lines.append("")

                if ep.request_body:
                    lines.append("**Request Body:**\n")
                    lines.append(
                        f"```json\n{json.dumps(ep.request_body, indent=2)}\n```\n"
                    )

                if ep.response_example is not None:
                    lines.append("**Response Example:**\n")
                    lines.append(
                        f"```json\n{json.dumps(ep.response_example, indent=2)}\n```\n"
                    )

                if ep.status_codes:
                    lines.append("**Status Codes:**\n")
                    for code, desc in sorted(ep.status_codes.items()):
                        lines.append(f"- `{code}`: {desc}")
                    lines.append("")

        # Module documentation
        if self._modules:
            lines.append("## Module Reference\n")
            for mod in self._modules:
                lines.append(f"### `jarvis.{mod.name}`\n")
                if mod.description:
                    lines.append(f"{mod.description}\n")

                for cls in mod.classes:
                    lines.append(f"#### `{cls['name']}`\n")
                    if cls.get("docstring"):
                        lines.append(f"{cls['docstring'][:200]}\n")
                    if cls.get("methods"):
                        lines.append("**Methods:**\n")
                        for method in cls["methods"][:10]:
                            async_prefix = "async " if method.get("is_async") else ""
                            docstr = method.get("docstring", "")[:80]
                            lines.append(
                                f"- `{async_prefix}{method['name']}()` — {docstr}"
                            )
                        lines.append("")

                for fn in mod.functions:
                    async_prefix = "async " if fn.get("is_async") else ""
                    docstr = fn.get("docstring", "")[:80]
                    lines.append(f"- `{async_prefix}{fn['name']}()` — {docstr}")
                lines.append("")

        return "\n".join(lines)

    # -- HTML --------------------------------------------------------------

    def generate_html(self) -> str:
        """Generate a standalone HTML API documentation page."""
        markdown_content = self.generate_markdown()
        html_body = self._markdown_to_html(markdown_content)

        return (
            '<!DOCTYPE html>\n<html lang="en">\n<head>\n'
            '    <meta charset="UTF-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "    <title>JARVIS API Documentation</title>\n"
            "    <style>\n"
            "        * { margin: 0; padding: 0; box-sizing: border-box; }\n"
            "        body {\n"
            "            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;\n"
            "            background: #0f172a; color: #e2e8f0; line-height: 1.6;\n"
            "            max-width: 900px; margin: 0 auto; padding: 2rem;\n"
            "        }\n"
            "        h1 { color: #38bdf8; border-bottom: 2px solid #1e293b;\n"
            "             padding-bottom: 0.5rem; margin: 2rem 0 1rem; }\n"
            "        h2 { color: #818cf8; margin: 1.5rem 0 0.5rem; }\n"
            "        h3 { color: #a78bfa; margin: 1rem 0 0.3rem; }\n"
            "        h4 { color: #c4b5fd; margin: 0.8rem 0 0.2rem; }\n"
            "        code { background: #1e293b; padding: 2px 6px; border-radius: 4px;\n"
            "               font-size: 0.9em; }\n"
            "        pre { background: #1e293b; padding: 1rem; border-radius: 8px;\n"
            "              overflow-x: auto; margin: 0.5rem 0; }\n"
            "        pre code { background: none; padding: 0; }\n"
            "        table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; }\n"
            "        th, td { border: 1px solid #334155; padding: 8px 12px; text-align: left; }\n"
            "        th { background: #1e293b; color: #94a3b8; }\n"
            "        a { color: #38bdf8; text-decoration: none; }\n"
            "        a:hover { text-decoration: underline; }\n"
            "        ul, ol { padding-left: 1.5rem; }\n"
            "        li { margin: 0.2rem 0; }\n"
            "        .method {\n"
            "            display: inline-block; padding: 2px 8px; border-radius: 4px;\n"
            "            font-weight: bold; font-size: 0.85em; margin-right: 8px;\n"
            "        }\n"
            "        .get { background: #166534; color: #4ade80; }\n"
            "        .post { background: #854d0e; color: #fbbf24; }\n"
            "        .put { background: #1e3a5f; color: #60a5fa; }\n"
            "        .delete { background: #7f1d1d; color: #f87171; }\n"
            "        .patch { background: #4a1d96; color: #c084fc; }\n"
            "        .websocket { background: #164e63; color: #22d3ee; }\n"
            "        p { margin: 0.4rem 0; }\n"
            "    </style>\n"
            "</head>\n<body>\n"
            f"{html_body}\n"
            "</body>\n</html>"
        )

    @staticmethod
    def _markdown_to_html(md: str) -> str:
        """Basic markdown-to-HTML conversion (no external deps)."""
        lines = md.split("\n")
        html_lines: list[str] = []
        in_code_block = False
        in_table = False

        for line in lines:
            # Code fences
            if line.startswith("```"):
                if in_code_block:
                    html_lines.append("</code></pre>")
                    in_code_block = False
                else:
                    lang = line[3:].strip()
                    html_lines.append(f'<pre><code class="{lang}">')
                    in_code_block = True
                continue

            if in_code_block:
                html_lines.append(
                    line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                )
                continue

            # Tables
            if line.startswith("|") and "|" in line[1:]:
                if not in_table:
                    html_lines.append("<table>")
                    in_table = True
                if "---" in line:
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                tag = "th" if not any(c for c in cells if not c.startswith("**")) else "td"
                html_lines.append(
                    "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
                )
                continue
            elif in_table:
                html_lines.append("</table>")
                in_table = False

            # Headers
            if line.startswith("#### "):
                html_lines.append(f"<h4>{line[5:]}</h4>")
            elif line.startswith("### "):
                content = re.sub(
                    r"`([^`]+)`",
                    lambda m: f"<code>{m.group(1)}</code>",
                    line[4:],
                )
                html_lines.append(f"<h3>{content}</h3>")
            elif line.startswith("## "):
                anchor = line[3:].lower().replace(" ", "-")
                html_lines.append(f'<h2 id="{anchor}">{line[3:]}</h2>')
            elif line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("- "):
                content = re.sub(
                    r"`([^`]+)`",
                    lambda m: f"<code>{m.group(1)}</code>",
                    line[2:],
                )
                html_lines.append(f"<li>{content}</li>")
            elif line.strip():
                content = re.sub(
                    r"`([^`]+)`",
                    lambda m: f"<code>{m.group(1)}</code>",
                    line,
                )
                content = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", content)
                html_lines.append(f"<p>{content}</p>")
            else:
                html_lines.append("")

        if in_table:
            html_lines.append("</table>")

        return "\n".join(html_lines)

    # -- persistence -------------------------------------------------------

    def save_openapi(self, path: str = "docs/openapi.json") -> Path:
        """Write OpenAPI spec to *path* and return the ``Path``."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        spec = self.generate_openapi()
        p.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        logger.info("OpenAPI spec written to %s", p)
        return p

    def save_markdown(self, path: str = "docs/api.md") -> Path:
        """Write Markdown docs to *path*."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.generate_markdown(), encoding="utf-8")
        logger.info("Markdown docs written to %s", p)
        return p

    def save_html(self, path: str = "docs/api.html") -> Path:
        """Write HTML docs to *path*."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.generate_html(), encoding="utf-8")
        logger.info("HTML docs written to %s", p)
        return p


# ---------------------------------------------------------------------------
# Convenience helper
# ---------------------------------------------------------------------------

def generate_api_docs(output_dir: str = "docs") -> dict[str, Path]:
    """Generate all API documentation formats.

    Imports the JARVIS FastAPI app, extracts endpoints and module docs, then
    writes OpenAPI JSON, Markdown, and HTML files to *output_dir*.
    """
    from jarvis.server.app import app  # noqa: WPS433

    gen = APIDocGenerator()
    gen.extract_from_fastapi(app)
    gen.extract_module_docs(
        [
            "agents",
            "engine",
            "llm",
            "tools",
            "knowledge",
            "memory",
            "skills",
            "curator",
            "mcp",
            "gateway",
            "plugins",
            "security",
            "session",
            "observability",
            "hooks",
            "workflow",
            "notifications",
        ]
    )

    return {
        "openapi": gen.save_openapi(f"{output_dir}/openapi.json"),
        "markdown": gen.save_markdown(f"{output_dir}/api.md"),
        "html": gen.save_html(f"{output_dir}/api.html"),
    }
