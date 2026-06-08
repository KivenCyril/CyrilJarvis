"""Template system tests.

Tests spec templates, prompt templates, variable rendering,
validation, and template management.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Template Models
# ---------------------------------------------------------------------------

@dataclass
class TemplateVariable:
    name: str
    description: str = ""
    required: bool = True
    default: str | None = None
    var_type: str = "string"  # string, integer, boolean, list
    validation: str | None = None  # regex pattern for validation

    def validate_value(self, value: str) -> tuple[bool, str]:
        if self.required and (value is None or value == ""):
            return False, f"Variable '{self.name}' is required"
        if self.var_type == "integer":
            try:
                int(value)
            except (ValueError, TypeError):
                return False, f"Variable '{self.name}' must be an integer"
        if self.validation:
            import re
            if not re.match(self.validation, str(value)):
                return False, f"Variable '{self.name}' does not match pattern '{self.validation}'"
        return True, ""


@dataclass
class SpecTemplate:
    name: str
    description: str
    intent_template: str
    variables: list[TemplateVariable] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    category: str = "general"
    version: str = "1.0"
    author: str = "system"

    def validate_variables(self, values: dict[str, str]) -> tuple[bool, list[str]]:
        errors = []
        for var in self.variables:
            value = values.get(var.name, var.default)
            valid, error = var.validate_value(value)
            if not valid:
                errors.append(error)
        return len(errors) == 0, errors

    def render(self, values: dict[str, str]) -> str:
        valid, errors = self.validate_variables(values)
        if not valid:
            raise ValueError(f"Validation errors: {'; '.join(errors)}")
        # Apply defaults
        all_values = {}
        for var in self.variables:
            all_values[var.name] = values.get(var.name, var.default or "")
        return self.intent_template.format(**all_values)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "intent_template": self.intent_template,
            "variables": [v.name for v in self.variables],
            "tags": self.tags,
            "constraints": self.constraints,
            "category": self.category,
            "version": self.version,
        }


@dataclass
class PromptTemplate:
    name: str
    description: str
    template: str
    variables: list[TemplateVariable] = field(default_factory=list)
    model_hint: str | None = None  # Suggested model for this prompt
    max_tokens: int | None = None
    temperature: float | None = None

    def render(self, values: dict[str, str]) -> str:
        all_values = {}
        for var in self.variables:
            all_values[var.name] = values.get(var.name, var.default or "")
        return self.template.format(**all_values)

    @property
    def estimated_tokens(self) -> int:
        return len(self.template) // 4

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "variables": [v.name for v in self.variables],
            "model_hint": self.model_hint,
        }


class TemplateRegistry:
    """Registry for spec and prompt templates."""

    def __init__(self):
        self.spec_templates: dict[str, SpecTemplate] = {}
        self.prompt_templates: dict[str, PromptTemplate] = {}

    def register_spec(self, template: SpecTemplate) -> None:
        self.spec_templates[template.name] = template

    def register_prompt(self, template: PromptTemplate) -> None:
        self.prompt_templates[template.name] = template

    def get_spec(self, name: str) -> SpecTemplate | None:
        return self.spec_templates.get(name)

    def get_prompt(self, name: str) -> PromptTemplate | None:
        return self.prompt_templates.get(name)

    def list_specs(self, category: str | None = None,
                   tag: str | None = None) -> list[SpecTemplate]:
        result = list(self.spec_templates.values())
        if category:
            result = [t for t in result if t.category == category]
        if tag:
            result = [t for t in result if tag in t.tags]
        return result

    def list_prompts(self) -> list[PromptTemplate]:
        return list(self.prompt_templates.values())

    def search(self, query: str) -> dict[str, list]:
        q = query.lower()
        spec_matches = [
            t for t in self.spec_templates.values()
            if q in t.name.lower() or q in t.description.lower()
        ]
        prompt_matches = [
            t for t in self.prompt_templates.values()
            if q in t.name.lower() or q in t.description.lower()
        ]
        return {"specs": spec_matches, "prompts": prompt_matches}

    @property
    def stats(self) -> dict[str, int]:
        return {
            "spec_templates": len(self.spec_templates),
            "prompt_templates": len(self.prompt_templates),
            "total": len(self.spec_templates) + len(self.prompt_templates),
        }


# ---------------------------------------------------------------------------
# Tests: TemplateVariable
# ---------------------------------------------------------------------------

class TestTemplateVariable:
    def test_create_variable(self):
        v = TemplateVariable(name="task", description="The task to do")
        assert v.name == "task"
        assert v.required is True

    def test_validate_required_present(self):
        v = TemplateVariable(name="task", required=True)
        valid, error = v.validate_value("something")
        assert valid is True

    def test_validate_required_missing(self):
        v = TemplateVariable(name="task", required=True)
        valid, error = v.validate_value("")
        assert valid is False
        assert "required" in error

    def test_validate_optional_missing(self):
        v = TemplateVariable(name="task", required=False)
        valid, error = v.validate_value("")
        assert valid is True

    def test_validate_integer_type(self):
        v = TemplateVariable(name="count", var_type="integer")
        valid, _ = v.validate_value("42")
        assert valid is True

    def test_validate_integer_type_invalid(self):
        v = TemplateVariable(name="count", var_type="integer")
        valid, error = v.validate_value("not a number")
        assert valid is False
        assert "integer" in error

    def test_validate_with_regex(self):
        v = TemplateVariable(name="email", validation=r"^[\w.]+@[\w.]+$")
        valid, _ = v.validate_value("test@example.com")
        assert valid is True

    def test_validate_regex_fail(self):
        v = TemplateVariable(name="email", validation=r"^[\w.]+@[\w.]+$")
        valid, error = v.validate_value("not-an-email")
        assert valid is False

    def test_default_value(self):
        v = TemplateVariable(name="lang", default="python")
        assert v.default == "python"


# ---------------------------------------------------------------------------
# Tests: SpecTemplate
# ---------------------------------------------------------------------------

class TestSpecTemplate:
    def _make_template(self) -> SpecTemplate:
        return SpecTemplate(
            name="code_review",
            description="Review code changes",
            intent_template="Review the code in {repo}: {description}",
            variables=[
                TemplateVariable(name="repo", description="Repository name"),
                TemplateVariable(name="description", description="What to review"),
            ],
            tags=["code", "review"],
            constraints=["Be thorough", "Check for security"],
            category="development",
        )

    def test_create_template(self):
        t = self._make_template()
        assert t.name == "code_review"
        assert len(t.variables) == 2

    def test_render(self):
        t = self._make_template()
        result = t.render({"repo": "jarvis", "description": "auth module"})
        assert result == "Review the code in jarvis: auth module"

    def test_render_missing_variable(self):
        t = self._make_template()
        with pytest.raises(ValueError, match="required"):
            t.render({"repo": "jarvis"})

    def test_validate_all_present(self):
        t = self._make_template()
        valid, errors = t.validate_variables({"repo": "jarvis", "description": "test"})
        assert valid is True
        assert errors == []

    def test_validate_missing(self):
        t = self._make_template()
        valid, errors = t.validate_variables({})
        assert valid is False
        assert len(errors) == 2

    def test_to_dict(self):
        t = self._make_template()
        d = t.to_dict()
        assert d["name"] == "code_review"
        assert "repo" in d["variables"]
        assert "review" in d["tags"]

    def test_template_with_defaults(self):
        t = SpecTemplate(
            name="test",
            description="test",
            intent_template="Run {type} tests for {target}",
            variables=[
                TemplateVariable(name="type", default="unit"),
                TemplateVariable(name="target", required=True),
            ],
        )
        result = t.render({"target": "auth module"})
        assert "unit" in result
        assert "auth module" in result

    def test_template_constraints(self):
        t = self._make_template()
        assert len(t.constraints) == 2
        assert "thorough" in t.constraints[0]

    def test_template_category(self):
        t = self._make_template()
        assert t.category == "development"

    def test_template_version(self):
        t = SpecTemplate(
            name="t", description="d", intent_template="x", version="2.0",
        )
        assert t.version == "2.0"


# ---------------------------------------------------------------------------
# Tests: PromptTemplate
# ---------------------------------------------------------------------------

class TestPromptTemplate:
    def _make_template(self) -> PromptTemplate:
        return PromptTemplate(
            name="system_prompt",
            description="Base system prompt",
            template="You are {agent_name}, an expert in {domain}.",
            variables=[
                TemplateVariable(name="agent_name"),
                TemplateVariable(name="domain"),
            ],
            model_hint="gpt-4",
            temperature=0.7,
        )

    def test_create(self):
        t = self._make_template()
        assert t.name == "system_prompt"

    def test_render(self):
        t = self._make_template()
        result = t.render({"agent_name": "CodeBot", "domain": "Python"})
        assert result == "You are CodeBot, an expert in Python."

    def test_estimated_tokens(self):
        t = self._make_template()
        assert t.estimated_tokens > 0

    def test_model_hint(self):
        t = self._make_template()
        assert t.model_hint == "gpt-4"

    def test_to_dict(self):
        t = self._make_template()
        d = t.to_dict()
        assert d["name"] == "system_prompt"
        assert d["model_hint"] == "gpt-4"


# ---------------------------------------------------------------------------
# Tests: TemplateRegistry
# ---------------------------------------------------------------------------

class TestTemplateRegistry:
    def test_register_and_get_spec(self):
        reg = TemplateRegistry()
        t = SpecTemplate(name="test", description="d", intent_template="x")
        reg.register_spec(t)
        assert reg.get_spec("test") is not None

    def test_register_and_get_prompt(self):
        reg = TemplateRegistry()
        t = PromptTemplate(name="test", description="d", template="x")
        reg.register_prompt(t)
        assert reg.get_prompt("test") is not None

    def test_get_nonexistent(self):
        reg = TemplateRegistry()
        assert reg.get_spec("missing") is None
        assert reg.get_prompt("missing") is None

    def test_list_specs(self):
        reg = TemplateRegistry()
        reg.register_spec(SpecTemplate(name="a", description="d", intent_template="x"))
        reg.register_spec(SpecTemplate(name="b", description="d", intent_template="x"))
        assert len(reg.list_specs()) == 2

    def test_list_specs_by_category(self):
        reg = TemplateRegistry()
        reg.register_spec(SpecTemplate(name="a", description="d", intent_template="x", category="dev"))
        reg.register_spec(SpecTemplate(name="b", description="d", intent_template="x", category="ops"))
        dev = reg.list_specs(category="dev")
        assert len(dev) == 1

    def test_list_specs_by_tag(self):
        reg = TemplateRegistry()
        reg.register_spec(SpecTemplate(name="a", description="d", intent_template="x", tags=["code"]))
        reg.register_spec(SpecTemplate(name="b", description="d", intent_template="x", tags=["docs"]))
        code = reg.list_specs(tag="code")
        assert len(code) == 1

    def test_list_prompts(self):
        reg = TemplateRegistry()
        reg.register_prompt(PromptTemplate(name="a", description="d", template="x"))
        assert len(reg.list_prompts()) == 1

    def test_search(self):
        reg = TemplateRegistry()
        reg.register_spec(SpecTemplate(name="code_review", description="Review code", intent_template="x"))
        reg.register_spec(SpecTemplate(name="bug_fix", description="Fix bugs", intent_template="x"))
        reg.register_prompt(PromptTemplate(name="code_gen", description="Generate code", template="x"))
        results = reg.search("code")
        assert len(results["specs"]) == 1
        assert len(results["prompts"]) == 1

    def test_stats(self):
        reg = TemplateRegistry()
        reg.register_spec(SpecTemplate(name="a", description="d", intent_template="x"))
        reg.register_spec(SpecTemplate(name="b", description="d", intent_template="x"))
        reg.register_prompt(PromptTemplate(name="c", description="d", template="x"))
        stats = reg.stats
        assert stats["spec_templates"] == 2
        assert stats["prompt_templates"] == 1
        assert stats["total"] == 3

    def test_overwrite_template(self):
        reg = TemplateRegistry()
        reg.register_spec(SpecTemplate(name="test", description="v1", intent_template="x"))
        reg.register_spec(SpecTemplate(name="test", description="v2", intent_template="y"))
        t = reg.get_spec("test")
        assert t.description == "v2"


# ---------------------------------------------------------------------------
# Tests: Complex Template Scenarios
# ---------------------------------------------------------------------------

class TestComplexTemplateScenarios:
    def test_template_with_many_variables(self):
        vars = [
            TemplateVariable(name=f"var_{i}", description=f"Var {i}")
            for i in range(10)
        ]
        t = SpecTemplate(
            name="complex",
            description="Complex template",
            intent_template=" ".join(f"{{{v.name}}}" for v in vars),
            variables=vars,
        )
        values = {v.name: f"value_{i}" for i, v in enumerate(vars)}
        result = t.render(values)
        for i in range(10):
            assert f"value_{i}" in result

    def test_template_with_multiline(self):
        t = PromptTemplate(
            name="multi",
            description="Multiline",
            template="Line 1: {a}\nLine 2: {b}\nLine 3: {c}",
            variables=[
                TemplateVariable(name="a"),
                TemplateVariable(name="b"),
                TemplateVariable(name="c"),
            ],
        )
        result = t.render({"a": "X", "b": "Y", "c": "Z"})
        assert result.count("\n") == 2
        assert "Line 1: X" in result
        assert "Line 3: Z" in result

    def test_template_serialization_roundtrip(self):
        t = SpecTemplate(
            name="roundtrip",
            description="Test roundtrip",
            intent_template="Do {task} in {language}",
            variables=[
                TemplateVariable(name="task"),
                TemplateVariable(name="language", default="Python"),
            ],
            tags=["test"],
            constraints=["Be fast"],
        )
        d = t.to_dict()
        serialized = json.dumps(d)
        restored = json.loads(serialized)
        assert restored["name"] == "roundtrip"
        assert "task" in restored["variables"]

    def test_multiple_renders_same_template(self):
        t = SpecTemplate(
            name="reusable",
            description="d",
            intent_template="Process {item} with {method}",
            variables=[
                TemplateVariable(name="item"),
                TemplateVariable(name="method"),
            ],
        )
        r1 = t.render({"item": "file.txt", "method": "grep"})
        r2 = t.render({"item": "data.csv", "method": "awk"})
        assert "file.txt" in r1
        assert "data.csv" in r2
        assert "grep" in r1
        assert "awk" in r2
