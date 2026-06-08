"""Advanced tests for the JARVIS template subsystem.

Covers all 10 built-in spec templates, template parameter validation,
all 8 prompt library templates, prompt template variable substitution,
TemplateEngine cross-type search, spec template with complex step
dependencies, TemplateRegistry CRUD, PromptLibrary category filtering,
missing variable detection, and templates with no parameters.
"""

from __future__ import annotations

from typing import Any

import pytest

from jarvis.templates.engine import TemplateEngine, TemplateRegistry
from jarvis.templates.prompt_templates import PromptLibrary, PromptTemplate
from jarvis.templates.spec_templates import (
    BUILTIN_SPEC_TEMPLATES,
    SpecTemplate,
    StepTemplate,
    TemplateParameter,
)


# ===========================================================================
# 1. All 10 built-in spec templates render correctly
# ===========================================================================


class TestBuiltinSpecTemplates:
    """Verify every built-in spec template can render with valid params."""

    def _required_params(self, tpl: SpecTemplate) -> dict[str, Any]:
        """Build a minimal valid param dict for a template."""
        params: dict[str, Any] = {}
        for p in tpl.parameters:
            if p.required and p.default is None:
                if p.param_type == "list":
                    params[p.name] = ["item1"]
                elif p.param_type == "number":
                    params[p.name] = 42
                elif p.param_type == "boolean":
                    params[p.name] = True
                elif p.choices:
                    params[p.name] = p.choices[0]
                else:
                    params[p.name] = f"test_{p.name}"
        return params

    def test_correct_count(self):
        assert len(BUILTIN_SPEC_TEMPLATES) == 10

    @pytest.mark.parametrize(
        "tpl",
        BUILTIN_SPEC_TEMPLATES,
        ids=[t.name for t in BUILTIN_SPEC_TEMPLATES],
    )
    def test_template_renders(self, tpl: SpecTemplate):
        params = self._required_params(tpl)
        result = tpl.render(params)
        assert "intent" in result
        assert "steps" in result
        assert isinstance(result["steps"], list)
        assert len(result["steps"]) > 0
        assert result["template_name"] == tpl.name

    @pytest.mark.parametrize(
        "tpl",
        BUILTIN_SPEC_TEMPLATES,
        ids=[t.name for t in BUILTIN_SPEC_TEMPLATES],
    )
    def test_template_has_tags(self, tpl: SpecTemplate):
        assert len(tpl.tags) > 0

    @pytest.mark.parametrize(
        "tpl",
        BUILTIN_SPEC_TEMPLATES,
        ids=[t.name for t in BUILTIN_SPEC_TEMPLATES],
    )
    def test_template_has_category(self, tpl: SpecTemplate):
        assert tpl.category != ""


# ===========================================================================
# 2. Template parameter validation
# ===========================================================================


class TestTemplateParameterValidation:
    def test_required_param_missing_raises(self):
        tpl = SpecTemplate(
            name="needs-param",
            intent_template="Do {thing}",
            parameters=[
                TemplateParameter(name="thing", required=True),
            ],
        )
        with pytest.raises(ValueError, match="Missing required"):
            tpl.render({})

    def test_choice_param_invalid_raises(self):
        tpl = SpecTemplate(
            name="choice-tpl",
            intent_template="Use {mode}",
            parameters=[
                TemplateParameter(
                    name="mode",
                    required=True,
                    choices=["fast", "slow"],
                ),
            ],
        )
        with pytest.raises(ValueError, match="Invalid value"):
            tpl.render({"mode": "medium"})

    def test_choice_param_valid(self):
        tpl = SpecTemplate(
            name="choice-tpl",
            intent_template="Use {mode}",
            parameters=[
                TemplateParameter(
                    name="mode",
                    required=True,
                    choices=["fast", "slow"],
                ),
            ],
        )
        result = tpl.render({"mode": "fast"})
        assert "fast" in result["intent"]

    def test_default_param_used(self):
        tpl = SpecTemplate(
            name="default-tpl",
            intent_template="Deploy to {env}",
            parameters=[
                TemplateParameter(name="env", default="staging"),
            ],
        )
        result = tpl.render({})
        assert "staging" in result["intent"]

    def test_optional_param_none_ok(self):
        param = TemplateParameter(name="opt", required=False)
        assert param.validate_value(None) is True

    def test_required_param_none_not_ok(self):
        param = TemplateParameter(name="req", required=True)
        assert param.validate_value(None) is False


# ===========================================================================
# 3. All 8 prompt library templates render
# ===========================================================================


class TestPromptLibraryBuiltins:
    def test_correct_count(self):
        lib = PromptLibrary()
        assert len(lib) >= 8

    def test_all_templates_retrievable(self):
        lib = PromptLibrary()
        expected_names = [
            "code_review_detailed",
            "bug_analysis",
            "refactoring_plan",
            "api_documentation",
            "data_analysis",
            "incident_summary",
            "meeting_agenda",
            "security_report",
        ]
        for name in expected_names:
            tpl = lib.get(name)
            assert tpl is not None, f"Template {name} not found"

    def test_code_review_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "code_review_detailed",
            focus_areas="security",
            language="Python",
            context="web app",
            security_level="high",
            code="print('hello')",
        )
        assert "security" in result
        assert "Python" in result

    def test_bug_analysis_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "bug_analysis",
            description="crash on login",
            expected="success",
            actual="500 error",
            steps="1. click login",
            logs="traceback...",
        )
        assert "crash on login" in result

    def test_refactoring_plan_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "refactoring_plan",
            code_structure="monolith",
            issues="coupling",
            goals="modularity",
            constraints="no downtime",
        )
        assert "monolith" in result

    def test_api_documentation_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "api_documentation",
            method="POST",
            path="/api/users",
            description="Create user",
            request_schema="{}",
            response_schema="{}",
        )
        assert "POST" in result

    def test_data_analysis_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "data_analysis",
            dataset_description="sales",
            columns="date, amount",
            sample="2024-01-01, 100",
            goals="trends",
        )
        assert "sales" in result

    def test_incident_summary_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "incident_summary",
            incident_id="INC-42",
            severity="P1",
            start_time="2024-01-01T00:00",
            duration="2 hours",
            services="auth",
            root_cause="OOM",
            resolution="restart",
        )
        assert "INC-42" in result

    def test_meeting_agenda_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "meeting_agenda",
            title="Sprint Planning",
            duration="1 hour",
            attendees="team",
            purpose="plan sprint",
            action_items="none",
        )
        assert "Sprint Planning" in result

    def test_security_report_renders(self):
        lib = PromptLibrary()
        result = lib.render(
            "security_report",
            target="web app",
            scope="full",
            assessment_type="pentest",
            findings="XSS found",
        )
        assert "web app" in result


# ===========================================================================
# 4. Prompt template variable substitution
# ===========================================================================


class TestPromptTemplateSubstitution:
    def test_simple_substitution(self):
        tpl = PromptTemplate(
            name="test",
            template="Hello {name}, you are {age}.",
            variables=["name", "age"],
        )
        result = tpl.render(name="Alice", age=30)
        assert result == "Hello Alice, you are 30."

    def test_missing_variable_left_intact(self):
        tpl = PromptTemplate(
            name="test",
            template="Hello {name}, welcome to {place}.",
            variables=["name", "place"],
        )
        result = tpl.render(name="Bob")
        assert "{place}" in result
        assert "Bob" in result

    def test_extra_variables_ignored(self):
        tpl = PromptTemplate(
            name="test",
            template="Hello {name}.",
            variables=["name"],
        )
        result = tpl.render(name="Eve", extra="ignored")
        assert result == "Hello Eve."


# ===========================================================================
# 5. TemplateEngine cross-type search
# ===========================================================================


class TestTemplateEngineCrossSearch:
    def test_search_finds_spec_templates(self):
        engine = TemplateEngine()
        results = engine.search("deploy")
        assert len(results["spec_templates"]) >= 1

    def test_search_finds_prompt_templates(self):
        engine = TemplateEngine()
        results = engine.search("code")
        assert len(results["prompt_templates"]) >= 1

    def test_search_both_types(self):
        engine = TemplateEngine()
        results = engine.search("security")
        assert "spec_templates" in results
        assert "prompt_templates" in results

    def test_search_no_match(self):
        engine = TemplateEngine()
        results = engine.search("zzzznonexistent")
        assert len(results["spec_templates"]) == 0
        assert len(results["prompt_templates"]) == 0


# ===========================================================================
# 6. Spec template with complex step dependencies
# ===========================================================================


class TestComplexStepDependencies:
    def test_diamond_dependency(self):
        tpl = SpecTemplate(
            name="diamond",
            intent_template="Diamond {name}",
            parameters=[TemplateParameter(name="name", required=True)],
            steps_template=[
                StepTemplate(order=1, name_template="Start"),
                StepTemplate(order=2, name_template="Left", depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Right", depends_on_indices=[0]),
                StepTemplate(order=4, name_template="Join", depends_on_indices=[1, 2]),
            ],
        )
        result = tpl.render({"name": "test"})
        steps = result["steps"]
        assert len(steps) == 4
        assert steps[3]["depends_on_indices"] == [1, 2]

    def test_linear_chain(self):
        tpl = SpecTemplate(
            name="chain",
            intent_template="Chain",
            steps_template=[
                StepTemplate(order=1, name_template="Step 1"),
                StepTemplate(order=2, name_template="Step 2", depends_on_indices=[0]),
                StepTemplate(order=3, name_template="Step 3", depends_on_indices=[1]),
            ],
        )
        result = tpl.render({})
        assert result["steps"][2]["depends_on_indices"] == [1]


# ===========================================================================
# 7. TemplateRegistry CRUD (spec templates)
# ===========================================================================


class TestSpecTemplateRegistryCRUD:
    def test_register_and_get(self):
        reg = TemplateRegistry()
        tpl = SpecTemplate(name="my-tpl", intent_template="Do {x}")
        reg.register(tpl)
        assert reg.get("my-tpl") is tpl

    def test_unregister(self):
        reg = TemplateRegistry()
        tpl = SpecTemplate(name="rm-me", intent_template="X")
        reg.register(tpl)
        assert reg.unregister("rm-me") is True
        assert reg.get("rm-me") is None
        assert reg.unregister("rm-me") is False

    def test_list_by_category(self):
        reg = TemplateRegistry()
        reg.register(SpecTemplate(name="a", category="dev", intent_template="A"))
        reg.register(SpecTemplate(name="b", category="ops", intent_template="B"))
        assert len(reg.list(category="dev")) == 1
        assert len(reg.list()) == 2

    def test_search(self):
        reg = TemplateRegistry()
        reg.register(SpecTemplate(name="deploy-svc", description="Deploy a service", intent_template="D"))
        reg.register(SpecTemplate(name="data-etl", description="ETL", intent_template="E"))
        results = reg.search("deploy")
        assert len(results) == 1

    def test_contains(self):
        reg = TemplateRegistry()
        reg.register(SpecTemplate(name="x", intent_template="X"))
        assert "x" in reg
        assert "y" not in reg

    def test_len(self):
        reg = TemplateRegistry()
        assert len(reg) == 0
        reg.register(SpecTemplate(name="a", intent_template="A"))
        assert len(reg) == 1


# ===========================================================================
# 8. PromptLibrary category filtering
# ===========================================================================


class TestPromptLibraryCategoryFiltering:
    def test_list_by_category(self):
        lib = PromptLibrary()
        code_tpls = lib.list_templates(category="code")
        assert len(code_tpls) >= 3  # code_review, bug_analysis, refactoring_plan

    def test_list_all(self):
        lib = PromptLibrary()
        all_tpls = lib.list_templates()
        assert len(all_tpls) >= 8

    def test_categories_list(self):
        lib = PromptLibrary()
        cats = lib.categories
        assert "code" in cats
        assert "documentation" in cats
        assert "data" in cats

    def test_search_by_keyword(self):
        lib = PromptLibrary()
        results = lib.search("bug")
        assert len(results) >= 1
        assert any("bug" in t.name for t in results)

    def test_add_and_remove(self):
        lib = PromptLibrary()
        initial = len(lib)
        tpl = PromptTemplate(
            name="custom_tpl",
            template="Custom: {x}",
            variables=["x"],
            category="custom",
        )
        lib.add(tpl)
        assert len(lib) == initial + 1
        assert lib.get("custom_tpl") is not None

        assert lib.remove("custom_tpl") is True
        assert len(lib) == initial
        assert lib.remove("custom_tpl") is False

    def test_render_nonexistent_raises(self):
        lib = PromptLibrary()
        with pytest.raises(KeyError):
            lib.render("nonexistent_template")


# ===========================================================================
# 9. Missing variable detection
# ===========================================================================


class TestMissingVariableDetection:
    def test_no_missing(self):
        tpl = PromptTemplate(
            name="test",
            template="Hi {name}",
            variables=["name"],
        )
        assert tpl.missing_variables(name="Alice") == []

    def test_one_missing(self):
        tpl = PromptTemplate(
            name="test",
            template="{a} and {b}",
            variables=["a", "b"],
        )
        missing = tpl.missing_variables(a="x")
        assert missing == ["b"]

    def test_all_missing(self):
        tpl = PromptTemplate(
            name="test",
            template="{x} {y}",
            variables=["x", "y"],
        )
        missing = tpl.missing_variables()
        assert set(missing) == {"x", "y"}


# ===========================================================================
# 10. Template with no parameters
# ===========================================================================


class TestNoParameters:
    def test_spec_template_no_params(self):
        tpl = SpecTemplate(
            name="no-params",
            intent_template="Run standard checks",
            steps_template=[
                StepTemplate(order=1, name_template="Check"),
            ],
        )
        result = tpl.render({})
        assert result["intent"] == "Run standard checks"

    def test_prompt_template_no_variables(self):
        tpl = PromptTemplate(
            name="static",
            template="This is a static prompt with no variables.",
        )
        result = tpl.render()
        assert result == "This is a static prompt with no variables."
        assert tpl.missing_variables() == []


# ===========================================================================
# 11. TemplateEngine lifecycle
# ===========================================================================


class TestTemplateEngine:
    def test_render_spec(self):
        engine = TemplateEngine()
        result = engine.render_spec("deploy", {"service": "api", "environment": "staging"})
        assert "api" in result["intent"]

    def test_render_spec_not_found(self):
        engine = TemplateEngine()
        with pytest.raises(KeyError):
            engine.render_spec("nonexistent", {})

    def test_render_prompt(self):
        engine = TemplateEngine()
        result = engine.render_prompt(
            "agent_system_base",
            role="code-agent",
            capabilities="coding",
            task="review code",
        )
        assert "code-agent" in result

    def test_render_prompt_not_found(self):
        engine = TemplateEngine()
        with pytest.raises(KeyError):
            engine.render_prompt("nonexistent")

    def test_register_custom_spec_template(self):
        engine = TemplateEngine()
        custom = SpecTemplate(name="custom-spec", intent_template="Custom {x}")
        engine.register_spec_template(custom)
        assert engine.spec_registry.get("custom-spec") is not None

    def test_register_custom_prompt_template(self):
        engine = TemplateEngine()
        custom = PromptTemplate(name="custom-prompt", template="Hello {y}")
        engine.register_prompt_template(custom)
        assert engine.prompt_library.get("custom-prompt") is not None

    def test_list_spec_templates(self):
        engine = TemplateEngine()
        specs = engine.list_spec_templates()
        assert len(specs) == 10
        assert all("name" in s for s in specs)

    def test_list_spec_templates_by_category(self):
        engine = TemplateEngine()
        dev = engine.list_spec_templates(category="development")
        assert len(dev) >= 2

    def test_list_prompt_templates(self):
        engine = TemplateEngine()
        prompts = engine.list_prompt_templates()
        assert len(prompts) >= 8

    def test_list_prompt_templates_by_category(self):
        engine = TemplateEngine()
        code = engine.list_prompt_templates(category="code")
        assert len(code) >= 3


# ===========================================================================
# 12. Spec template list_parameters
# ===========================================================================


class TestListParameters:
    def test_list_parameters(self):
        tpl = SpecTemplate(
            name="test",
            intent_template="T",
            parameters=[
                TemplateParameter(
                    name="x",
                    description="The X param",
                    param_type="string",
                    required=True,
                    choices=["a", "b"],
                ),
            ],
        )
        params = tpl.list_parameters()
        assert len(params) == 1
        p = params[0]
        assert p["name"] == "x"
        assert p["required"] is True
        assert p["choices"] == ["a", "b"]
        assert p["type"] == "string"

    def test_empty_parameters(self):
        tpl = SpecTemplate(name="empty", intent_template="T")
        assert tpl.list_parameters() == []
