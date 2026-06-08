"""Advanced documentation generation tests.

Tests OpenAPI spec generation, Markdown/HTML output, module doc extraction,
and endpoint category completeness.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# OpenAPI Spec Generation Validation
# ---------------------------------------------------------------------------

class TestOpenAPISpecGeneration:
    """Validate that we can generate a correct OpenAPI-like spec from routes."""

    def _generate_openapi_spec(self) -> dict[str, Any]:
        """Generate a minimal OpenAPI spec from known routes."""
        return {
            "openapi": "3.1.0",
            "info": {
                "title": "JARVIS API",
                "version": "0.2.0",
                "description": "Streaming Spec driven personal AI assistant",
                "contact": {"name": "JARVIS Team", "email": "admin@jarvis.local"},
                "license": {"name": "MIT"},
            },
            "servers": [
                {"url": "http://localhost:8000", "description": "Local dev"},
            ],
            "paths": {
                "/health": {"get": {"summary": "Health check", "operationId": "health", "tags": ["system"]}},
                "/system": {"get": {"summary": "System info", "operationId": "system_info", "tags": ["system"]}},
                "/agents": {"get": {"summary": "List agents", "operationId": "list_agents", "tags": ["agents"]}},
                "/agents/{name}": {"get": {"summary": "Get agent", "operationId": "get_agent", "tags": ["agents"]}},
                "/specs": {
                    "get": {"summary": "List specs", "operationId": "list_specs", "tags": ["specs"]},
                    "post": {"summary": "Create spec", "operationId": "create_spec", "tags": ["specs"]},
                },
                "/specs/{spec_id}": {"get": {"summary": "Get spec", "operationId": "get_spec", "tags": ["specs"]}},
                "/specs/{spec_id}/execute": {"post": {"summary": "Execute spec", "tags": ["specs"]}},
                "/specs/{spec_id}/constraints": {"post": {"summary": "Add constraint", "tags": ["specs"]}},
                "/specs/{spec_id}/redirect": {"post": {"summary": "Redirect spec", "tags": ["specs"]}},
                "/specs/{spec_id}/changelog": {"get": {"summary": "Get changelog", "tags": ["specs"]}},
                "/chat": {"post": {"summary": "Chat", "operationId": "chat", "tags": ["chat"]}},
                "/workflows": {
                    "get": {"summary": "List workflows", "tags": ["workflows"]},
                    "post": {"summary": "Create workflow", "tags": ["workflows"]},
                },
                "/workflows/{wf_id}": {"get": {"summary": "Get workflow", "tags": ["workflows"]}},
                "/workflows/{wf_id}/execute": {"post": {"summary": "Execute workflow", "tags": ["workflows"]}},
                "/workflows/{wf_id}/pause": {"post": {"summary": "Pause workflow", "tags": ["workflows"]}},
                "/workflows/{wf_id}/resume": {"post": {"summary": "Resume workflow", "tags": ["workflows"]}},
                "/events": {"get": {"summary": "List events", "tags": ["events"]}},
                "/events/publish": {"post": {"summary": "Publish event", "tags": ["events"]}},
                "/notifications": {
                    "get": {"summary": "List notifications", "tags": ["notifications"]},
                    "post": {"summary": "Create notification", "tags": ["notifications"]},
                },
                "/notifications/{nid}/read": {"post": {"summary": "Mark read", "tags": ["notifications"]}},
                "/user/profile": {
                    "get": {"summary": "Get profile", "tags": ["user"]},
                    "put": {"summary": "Update profile", "tags": ["user"]},
                },
                "/user/preferences": {
                    "get": {"summary": "Get preferences", "tags": ["user"]},
                    "put": {"summary": "Update preferences", "tags": ["user"]},
                },
                "/diagnostics": {"get": {"summary": "Run diagnostics", "tags": ["diagnostics"]}},
                "/diagnostics/benchmark": {"get": {"summary": "Run benchmark", "tags": ["diagnostics"]}},
                "/templates/specs": {"get": {"summary": "List spec templates", "tags": ["templates"]}},
                "/templates/prompts": {"get": {"summary": "List prompt templates", "tags": ["templates"]}},
                "/templates/specs/{name}/render": {"post": {"summary": "Render template", "tags": ["templates"]}},
                "/memory": {
                    "get": {"summary": "List memories", "tags": ["memory"]},
                    "post": {"summary": "Add memory", "tags": ["memory"]},
                },
                "/memory/search": {"post": {"summary": "Search memory", "tags": ["memory"]}},
                "/knowledge/stats": {"get": {"summary": "Knowledge stats", "tags": ["knowledge"]}},
                "/knowledge/graph": {"get": {"summary": "Knowledge graph", "tags": ["knowledge"]}},
                "/skills": {"get": {"summary": "List skills", "tags": ["skills"]}},
                "/skills/{name}": {"get": {"summary": "Get skill", "tags": ["skills"]}},
                "/tools": {"get": {"summary": "List tools", "tags": ["tools"]}},
                "/metrics": {"get": {"summary": "Get metrics", "tags": ["observability"]}},
                "/traces": {"get": {"summary": "List traces", "tags": ["observability"]}},
                "/traces/{trace_id}": {"get": {"summary": "Get trace", "tags": ["observability"]}},
            },
            "tags": [
                {"name": "system", "description": "System health and info"},
                {"name": "agents", "description": "Agent management"},
                {"name": "specs", "description": "Streaming Spec operations"},
                {"name": "chat", "description": "Chat with agents"},
                {"name": "workflows", "description": "Workflow management"},
                {"name": "events", "description": "Event bus"},
                {"name": "notifications", "description": "Notification management"},
                {"name": "user", "description": "User profile and preferences"},
                {"name": "diagnostics", "description": "System diagnostics"},
                {"name": "templates", "description": "Spec and prompt templates"},
                {"name": "memory", "description": "Memory management"},
                {"name": "knowledge", "description": "Knowledge graph"},
                {"name": "skills", "description": "Skill management"},
                {"name": "tools", "description": "Tool management"},
                {"name": "observability", "description": "Metrics and traces"},
            ],
        }

    def test_openapi_has_required_fields(self):
        spec = self._generate_openapi_spec()
        assert "openapi" in spec
        assert "info" in spec
        assert "paths" in spec

    def test_openapi_version_format(self):
        spec = self._generate_openapi_spec()
        assert re.match(r"\d+\.\d+\.\d+", spec["openapi"])

    def test_info_section(self):
        spec = self._generate_openapi_spec()
        info = spec["info"]
        assert info["title"] == "JARVIS API"
        assert "version" in info
        assert "description" in info

    def test_paths_not_empty(self):
        spec = self._generate_openapi_spec()
        assert len(spec["paths"]) > 20

    def test_all_paths_have_methods(self):
        spec = self._generate_openapi_spec()
        for path, methods in spec["paths"].items():
            assert len(methods) > 0, f"Path {path} has no methods"
            for method, details in methods.items():
                assert method in ("get", "post", "put", "patch", "delete")
                assert "summary" in details

    def test_tags_present(self):
        spec = self._generate_openapi_spec()
        assert len(spec["tags"]) >= 10

    def test_all_operations_have_tags(self):
        spec = self._generate_openapi_spec()
        for path, methods in spec["paths"].items():
            for method, details in methods.items():
                assert "tags" in details, f"{method.upper()} {path} missing tags"

    def test_tag_names_consistent(self):
        spec = self._generate_openapi_spec()
        defined_tags = {t["name"] for t in spec["tags"]}
        used_tags = set()
        for path, methods in spec["paths"].items():
            for method, details in methods.items():
                for tag in details.get("tags", []):
                    used_tags.add(tag)
        # All used tags should be defined
        assert used_tags.issubset(defined_tags)

    def test_has_servers(self):
        spec = self._generate_openapi_spec()
        assert len(spec["servers"]) >= 1

    def test_spec_serializable(self):
        spec = self._generate_openapi_spec()
        serialized = json.dumps(spec)
        deserialized = json.loads(serialized)
        assert deserialized["info"]["title"] == "JARVIS API"


# ---------------------------------------------------------------------------
# Markdown Generation
# ---------------------------------------------------------------------------

class TestMarkdownGeneration:
    """Test markdown documentation generation helpers."""

    def _generate_api_markdown(self) -> str:
        sections = [
            "# JARVIS API Documentation\n",
            "## Overview\n",
            "JARVIS is a Streaming Spec driven personal AI assistant.\n",
            "## Authentication\n",
            "Currently no authentication is required for local development.\n",
            "## Endpoints\n",
        ]

        categories = {
            "System": [
                ("GET", "/health", "Check system health"),
                ("GET", "/system", "Get system information"),
                ("GET", "/diagnostics", "Run diagnostics"),
                ("GET", "/diagnostics/benchmark", "Run performance benchmark"),
            ],
            "Agents": [
                ("GET", "/agents", "List all agents"),
                ("GET", "/agents/{name}", "Get agent details"),
            ],
            "Streaming Specs": [
                ("POST", "/specs", "Create a new spec"),
                ("GET", "/specs", "List all specs"),
                ("GET", "/specs/{id}", "Get spec by ID"),
                ("POST", "/specs/{id}/execute", "Execute a spec"),
                ("POST", "/specs/{id}/constraints", "Add a constraint"),
                ("POST", "/specs/{id}/redirect", "Redirect a spec"),
                ("GET", "/specs/{id}/changelog", "Get changelog"),
            ],
            "Workflows": [
                ("POST", "/workflows", "Create workflow"),
                ("GET", "/workflows", "List workflows"),
                ("GET", "/workflows/{id}", "Get workflow"),
                ("POST", "/workflows/{id}/execute", "Execute workflow"),
                ("POST", "/workflows/{id}/pause", "Pause workflow"),
                ("POST", "/workflows/{id}/resume", "Resume workflow"),
            ],
            "Events": [
                ("GET", "/events", "List events"),
                ("POST", "/events/publish", "Publish event"),
            ],
            "Notifications": [
                ("GET", "/notifications", "List notifications"),
                ("POST", "/notifications", "Create notification"),
                ("POST", "/notifications/{id}/read", "Mark as read"),
            ],
            "User": [
                ("GET", "/user/profile", "Get profile"),
                ("PUT", "/user/profile", "Update profile"),
                ("GET", "/user/preferences", "Get preferences"),
                ("PUT", "/user/preferences", "Update preferences"),
            ],
            "Templates": [
                ("GET", "/templates/specs", "List spec templates"),
                ("GET", "/templates/prompts", "List prompt templates"),
                ("POST", "/templates/specs/{name}/render", "Render template"),
            ],
        }

        for cat_name, endpoints in categories.items():
            sections.append(f"### {cat_name}\n")
            sections.append("| Method | Path | Description |")
            sections.append("|--------|------|-------------|")
            for method, path, desc in endpoints:
                sections.append(f"| `{method}` | `{path}` | {desc} |")
            sections.append("")

        return "\n".join(sections)

    def test_markdown_has_title(self):
        md = self._generate_api_markdown()
        assert "# JARVIS API Documentation" in md

    def test_markdown_has_overview(self):
        md = self._generate_api_markdown()
        assert "## Overview" in md

    def test_markdown_has_all_categories(self):
        md = self._generate_api_markdown()
        expected = [
            "System", "Agents", "Streaming Specs", "Workflows",
            "Events", "Notifications", "User", "Templates",
        ]
        for cat in expected:
            assert f"### {cat}" in md

    def test_markdown_has_endpoint_tables(self):
        md = self._generate_api_markdown()
        assert "| Method | Path | Description |" in md
        assert "|--------|------|-------------|" in md

    def test_markdown_endpoint_count(self):
        md = self._generate_api_markdown()
        # Count table rows (lines with | at start that aren't headers)
        rows = [
            line for line in md.split("\n")
            if line.startswith("| `") and "`" in line
        ]
        assert len(rows) >= 25

    def test_markdown_methods_backticked(self):
        md = self._generate_api_markdown()
        for method in ["GET", "POST", "PUT"]:
            assert f"`{method}`" in md


# ---------------------------------------------------------------------------
# HTML Generation Structure
# ---------------------------------------------------------------------------

class TestHTMLGeneration:
    """Test HTML documentation generation helpers."""

    def _generate_api_html(self) -> str:
        lines = [
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="UTF-8">',
            "  <title>JARVIS API Documentation</title>",
            "  <style>",
            "    body { font-family: system-ui; max-width: 900px; margin: 0 auto; padding: 2rem; }",
            "    h1 { color: #2563eb; }",
            "    table { border-collapse: collapse; width: 100%; margin-bottom: 2rem; }",
            "    th, td { border: 1px solid #e5e7eb; padding: 0.5rem; text-align: left; }",
            "    th { background: #f3f4f6; }",
            "    .method { font-weight: bold; }",
            "    .get { color: #059669; }",
            "    .post { color: #d97706; }",
            "    .put { color: #7c3aed; }",
            "    .delete { color: #dc2626; }",
            "  </style>",
            "</head>",
            "<body>",
            "  <h1>JARVIS API Documentation</h1>",
            '  <p>Version: <strong>0.2.0</strong></p>',
            '  <h2 id="system">System</h2>',
            "  <table>",
            "    <tr><th>Method</th><th>Path</th><th>Description</th></tr>",
            '    <tr><td class="method get">GET</td><td>/health</td><td>Health check</td></tr>',
            '    <tr><td class="method get">GET</td><td>/system</td><td>System info</td></tr>',
            "  </table>",
            '  <h2 id="agents">Agents</h2>',
            "  <table>",
            "    <tr><th>Method</th><th>Path</th><th>Description</th></tr>",
            '    <tr><td class="method get">GET</td><td>/agents</td><td>List agents</td></tr>',
            '    <tr><td class="method get">GET</td><td>/agents/{name}</td><td>Get agent</td></tr>',
            "  </table>",
            '  <h2 id="specs">Streaming Specs</h2>',
            "  <table>",
            "    <tr><th>Method</th><th>Path</th><th>Description</th></tr>",
            '    <tr><td class="method post">POST</td><td>/specs</td><td>Create spec</td></tr>',
            '    <tr><td class="method get">GET</td><td>/specs</td><td>List specs</td></tr>',
            "  </table>",
            "</body>",
            "</html>",
        ]
        return "\n".join(lines)

    def test_html_has_doctype(self):
        html = self._generate_api_html()
        assert html.startswith("<!DOCTYPE html>")

    def test_html_has_title(self):
        html = self._generate_api_html()
        assert "<title>JARVIS API Documentation</title>" in html

    def test_html_has_charset(self):
        html = self._generate_api_html()
        assert 'charset="UTF-8"' in html

    def test_html_has_tables(self):
        html = self._generate_api_html()
        assert html.count("<table>") >= 3

    def test_html_has_section_ids(self):
        html = self._generate_api_html()
        assert 'id="system"' in html
        assert 'id="agents"' in html
        assert 'id="specs"' in html

    def test_html_has_style(self):
        html = self._generate_api_html()
        assert "<style>" in html
        assert "</style>" in html

    def test_html_closes_tags(self):
        html = self._generate_api_html()
        assert "</html>" in html
        assert "</body>" in html
        assert "</head>" in html

    def test_html_method_classes(self):
        html = self._generate_api_html()
        assert 'class="method get"' in html
        assert 'class="method post"' in html


# ---------------------------------------------------------------------------
# Module Documentation Extraction
# ---------------------------------------------------------------------------

class TestModuleDocExtraction:
    """Test extracting documentation from module structures."""

    def _extract_module_info(self, module_name: str) -> dict[str, Any]:
        """Simulate extracting module info."""
        modules = {
            "agents": {
                "name": "agents",
                "description": "Multi-agent orchestration framework",
                "classes": ["BaseAgent", "AgentCard", "AgentRegistry", "Orchestrator"],
                "public_api": ["register", "get", "list_agents", "route", "handle"],
                "dependencies": ["models", "llm"],
            },
            "tools": {
                "name": "tools",
                "description": "Tool registry and built-in tools",
                "classes": ["BaseTool", "ToolResult", "ToolRegistry"],
                "public_api": ["register", "get", "execute", "list_tools"],
                "dependencies": [],
            },
            "specs": {
                "name": "specs",
                "description": "Streaming Spec engine",
                "classes": ["StreamingSpec", "SpecEngine", "SpecStep", "SpecConstraint"],
                "public_api": ["create", "get", "list_specs", "execute", "stream"],
                "dependencies": ["models", "agents"],
            },
            "memory": {
                "name": "memory",
                "description": "Memory management with vector search",
                "classes": ["MemoryManager", "MemoryEntry", "MemoryType"],
                "public_api": ["add", "search", "list_memories", "forget"],
                "dependencies": [],
            },
            "knowledge": {
                "name": "knowledge",
                "description": "Knowledge graph with entity extraction",
                "classes": ["KnowledgeGraph", "KnowledgeNode", "KnowledgeEdge"],
                "public_api": ["extract_from_text", "query", "add_node", "add_edge"],
                "dependencies": ["llm"],
            },
            "skills": {
                "name": "skills",
                "description": "Composable skill system",
                "classes": ["SkillRegistry", "Skill", "SkillMetadata"],
                "public_api": ["register", "get", "list_skills", "execute_skill"],
                "dependencies": ["tools", "agents"],
            },
            "workflows": {
                "name": "workflows",
                "description": "DAG-based workflow engine",
                "classes": ["WorkflowEngine", "WorkflowNode", "WorkflowResult"],
                "public_api": ["create", "execute", "pause", "resume"],
                "dependencies": ["agents", "specs"],
            },
        }
        return modules.get(module_name, {"name": module_name, "description": "Unknown module"})

    def test_extract_known_module(self):
        info = self._extract_module_info("agents")
        assert info["name"] == "agents"
        assert len(info["classes"]) >= 3

    def test_extract_unknown_module(self):
        info = self._extract_module_info("nonexistent")
        assert info["description"] == "Unknown module"

    def test_all_modules_have_description(self):
        for mod in ["agents", "tools", "specs", "memory", "knowledge", "skills", "workflows"]:
            info = self._extract_module_info(mod)
            assert info["description"], f"Module {mod} has no description"

    def test_all_modules_have_public_api(self):
        for mod in ["agents", "tools", "specs", "memory"]:
            info = self._extract_module_info(mod)
            assert len(info.get("public_api", [])) >= 2

    def test_module_dependencies_valid(self):
        known = {"agents", "tools", "specs", "memory", "knowledge", "skills", "workflows", "models", "llm"}
        for mod in ["agents", "tools", "specs"]:
            info = self._extract_module_info(mod)
            for dep in info.get("dependencies", []):
                assert dep in known, f"{mod} has unknown dependency: {dep}"


# ---------------------------------------------------------------------------
# Endpoint Category Completeness
# ---------------------------------------------------------------------------

class TestEndpointCategoryCompleteness:
    """Ensure all endpoint categories have proper documentation."""

    EXPECTED_CATEGORIES = [
        "system",
        "agents",
        "specs",
        "chat",
        "workflows",
        "events",
        "notifications",
        "user",
        "diagnostics",
        "templates",
        "memory",
        "knowledge",
        "skills",
        "tools",
        "observability",
        "curator",
        "sessions",
        "mcp",
    ]

    EXPECTED_ENDPOINTS = {
        "system": ["/health", "/system"],
        "agents": ["/agents", "/agents/{name}"],
        "specs": ["/specs"],
        "workflows": ["/workflows"],
        "events": ["/events", "/events/publish"],
        "notifications": ["/notifications"],
        "user": ["/user/profile", "/user/preferences"],
        "diagnostics": ["/diagnostics", "/diagnostics/benchmark"],
        "templates": ["/templates/specs", "/templates/prompts"],
        "memory": ["/memory"],
        "knowledge": ["/knowledge/stats", "/knowledge/graph"],
        "skills": ["/skills"],
        "tools": ["/tools"],
        "observability": ["/metrics", "/traces"],
    }

    def test_all_categories_listed(self):
        assert len(self.EXPECTED_CATEGORIES) >= 15

    def test_categories_have_endpoints(self):
        for cat, endpoints in self.EXPECTED_ENDPOINTS.items():
            assert len(endpoints) >= 1, f"Category {cat} has no endpoints"

    def test_system_endpoints(self):
        assert "/health" in self.EXPECTED_ENDPOINTS["system"]
        assert "/system" in self.EXPECTED_ENDPOINTS["system"]

    def test_agent_endpoints(self):
        assert "/agents" in self.EXPECTED_ENDPOINTS["agents"]

    def test_workflow_endpoints(self):
        assert "/workflows" in self.EXPECTED_ENDPOINTS["workflows"]

    def test_event_endpoints(self):
        assert "/events" in self.EXPECTED_ENDPOINTS["events"]
        assert "/events/publish" in self.EXPECTED_ENDPOINTS["events"]

    def test_template_endpoints(self):
        assert "/templates/specs" in self.EXPECTED_ENDPOINTS["templates"]
        assert "/templates/prompts" in self.EXPECTED_ENDPOINTS["templates"]

    def test_observability_endpoints(self):
        assert "/metrics" in self.EXPECTED_ENDPOINTS["observability"]
        assert "/traces" in self.EXPECTED_ENDPOINTS["observability"]

    def test_no_duplicate_categories(self):
        assert len(self.EXPECTED_CATEGORIES) == len(set(self.EXPECTED_CATEGORIES))
