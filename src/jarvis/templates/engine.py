"""Unified template engine that manages all template types."""

from __future__ import annotations

from typing import Any

from jarvis.templates.prompt_templates import PromptLibrary, PromptTemplate
from jarvis.templates.spec_templates import (
    BUILTIN_SPEC_TEMPLATES,
    SpecTemplate,
)


class TemplateRegistry:
    """Central registry for spec templates with add/remove/search."""

    def __init__(self) -> None:
        self._templates: dict[str, SpecTemplate] = {}

    def register(self, template: SpecTemplate) -> None:
        """Add or overwrite a spec template."""
        self._templates[template.name] = template

    def unregister(self, name: str) -> bool:
        """Remove a template by name. Returns True if it existed."""
        return self._templates.pop(name, None) is not None

    def get(self, name: str) -> SpecTemplate | None:
        return self._templates.get(name)

    def list(self, category: str | None = None) -> list[SpecTemplate]:
        templates = list(self._templates.values())
        if category:
            templates = [t for t in templates if t.category == category]
        return sorted(templates, key=lambda t: t.name)

    def search(self, query: str) -> list[SpecTemplate]:
        q = query.lower()
        results: list[SpecTemplate] = []
        for t in self._templates.values():
            haystack = f"{t.name} {t.description} {t.category} {' '.join(t.tags)}".lower()
            if q in haystack:
                results.append(t)
        return sorted(results, key=lambda t: t.name)

    def __len__(self) -> int:
        return len(self._templates)

    def __contains__(self, name: str) -> bool:
        return name in self._templates


class TemplateEngine:
    """Unified template engine that manages all template types.

    Provides:
    - Spec template rendering
    - Prompt template rendering
    - Template discovery and search
    - Template composition (combine multiple templates)
    """

    def __init__(self) -> None:
        self._registry = TemplateRegistry()
        self._prompt_library = PromptLibrary()
        self._load_builtin_spec_templates()

    # ------------------------------------------------------------------
    # Spec templates
    # ------------------------------------------------------------------

    def render_spec(self, template_name: str, params: dict[str, Any]) -> dict[str, Any]:
        """Render a spec template by name.

        Raises ``KeyError`` if the template is not found.
        """
        tpl = self._registry.get(template_name)
        if tpl is None:
            raise KeyError(f"Spec template not found: {template_name}")
        return tpl.render(params)

    def register_spec_template(self, template: SpecTemplate) -> None:
        """Register a custom spec template."""
        self._registry.register(template)

    def list_spec_templates(self, category: str | None = None) -> list[dict[str, Any]]:
        """List spec templates as summary dicts."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "parameters": t.list_parameters(),
                "tags": t.tags,
            }
            for t in self._registry.list(category)
        ]

    # ------------------------------------------------------------------
    # Prompt templates
    # ------------------------------------------------------------------

    def render_prompt(self, template_name: str, **kwargs: Any) -> str:
        """Render a prompt template by name.

        Raises ``KeyError`` if the template is not found.
        """
        return self._prompt_library.render(template_name, **kwargs)

    def register_prompt_template(self, template: PromptTemplate) -> None:
        """Register a custom prompt template."""
        self._prompt_library.add(template)

    def list_prompt_templates(self, category: str | None = None) -> list[dict[str, Any]]:
        """List prompt templates as summary dicts."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "category": t.category,
                "variables": t.variables,
            }
            for t in self._prompt_library.list_templates(category)
        ]

    # ------------------------------------------------------------------
    # Cross-type search
    # ------------------------------------------------------------------

    def search(self, query: str) -> dict[str, Any]:
        """Search across all template types."""
        return {
            "spec_templates": [
                {"name": t.name, "description": t.description, "category": t.category}
                for t in self._registry.search(query)
            ],
            "prompt_templates": [
                {"name": t.name, "description": t.description, "category": t.category}
                for t in self._prompt_library.search(query)
            ],
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def spec_registry(self) -> TemplateRegistry:
        """Direct access to the spec template registry."""
        return self._registry

    @property
    def prompt_library(self) -> PromptLibrary:
        """Direct access to the prompt library."""
        return self._prompt_library

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_builtin_spec_templates(self) -> None:
        for tpl in BUILTIN_SPEC_TEMPLATES:
            self._registry.register(tpl)
