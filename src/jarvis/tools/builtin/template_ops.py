"""Template rendering tool: render templates with variable substitution."""

from __future__ import annotations

import re
from string import Template
from typing import Any

from jarvis.tools.base import BaseTool, ToolResult


def _render_conditionals(text: str, variables: dict[str, Any]) -> str:
    """Process simple {{#if var}}...{{/if}} and {{#if var}}...{{#else}}...{{/if}} blocks."""

    def _replace_conditional(match: re.Match) -> str:
        var_name = match.group(1).strip()
        body = match.group(2)

        # Check for {{#else}} inside the body
        else_parts = re.split(r"\{\{#else\}\}", body, maxsplit=1)
        true_block = else_parts[0]
        false_block = else_parts[1] if len(else_parts) > 1 else ""

        value = variables.get(var_name)
        # Truthy check: exists and is not empty/None/False/0
        if value and value != "" and value != 0:
            return true_block
        return false_block

    # Process conditionals from innermost to outermost
    pattern = r"\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}"
    max_iterations = 10  # Prevent infinite loops
    for _ in range(max_iterations):
        new_text = re.sub(pattern, _replace_conditional, text, flags=re.DOTALL)
        if new_text == text:
            break
        text = new_text

    return text


def _render_loops(text: str, variables: dict[str, Any]) -> str:
    """Process simple {{#each items}}...{{/each}} blocks."""

    def _replace_loop(match: re.Match) -> str:
        var_name = match.group(1).strip()
        body = match.group(2)

        items = variables.get(var_name, [])
        if not isinstance(items, (list, tuple)):
            return ""

        parts = []
        for item in items:
            rendered = body.replace("{{.}}", str(item))
            # Support {{@index}} for loop index
            parts.append(rendered)

        for i, part in enumerate(parts):
            parts[i] = part.replace("{{@index}}", str(i))

        return "".join(parts)

    pattern = r"\{\{#each\s+(\w+)\}\}(.*?)\{\{/each\}\}"
    return re.sub(pattern, _replace_loop, text, flags=re.DOTALL)


class TemplateTool(BaseTool):
    """Render a template with variable substitution."""

    name = "render_template"
    description = (
        "Render a template string with variable substitution. Supports:\n"
        "- {{var}} for simple variable replacement\n"
        "- {{#if var}}...{{/if}} for conditionals\n"
        "- {{#if var}}...{{#else}}...{{/if}} for if/else\n"
        "- {{#each list}}{{.}}{{/each}} for iterating over lists\n"
        "- $var and ${var} as alternative Python Template syntax"
    )
    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "template": {
                "type": "string",
                "description": "The template string with placeholders.",
            },
            "variables": {
                "type": "object",
                "description": "Dictionary of variable names to values.",
            },
        },
        "required": ["template", "variables"],
    }

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        template_str: str = arguments["template"]
        variables: dict[str, Any] = arguments.get("variables", {})

        try:
            result = template_str

            # 1. Process conditionals first
            result = _render_conditionals(result, variables)

            # 2. Process loops
            result = _render_loops(result, variables)

            # 3. Replace {{var}} placeholders
            for key, value in variables.items():
                result = result.replace("{{" + key + "}}", str(value))

            # 4. Try Python string.Template for $var syntax (if any $ present)
            if "$" in result:
                try:
                    tmpl = Template(result)
                    result = tmpl.safe_substitute(variables)
                except (ValueError, KeyError):
                    pass  # Leave unresolved $vars as-is

            return ToolResult(
                success=True,
                output=result,
                data={"rendered": result, "variables_used": list(variables.keys())},
            )
        except Exception as exc:
            return ToolResult(success=False, output=f"Template error: {exc}")
