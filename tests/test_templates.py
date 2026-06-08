"""Tests for the JARVIS template system."""

from __future__ import annotations

import pytest

from jarvis.templates.spec_templates import (
    BUILTIN_SPEC_TEMPLATES,
    SpecTemplate,
    StepTemplate,
    TemplateParameter,
    _substitute,
)
from jarvis.templates.prompt_templates import PromptLibrary, PromptTemplate
from jarvis.templates.engine import TemplateEngine, TemplateRegistry


# ======================================================================
# TemplateParameter tests
# ======================================================================


class TestTemplateParameter:
    def test_validate_required_missing(self):
        p = TemplateParameter(name="x", required=True)
        assert not p.validate_value(None)

    def test_validate_optional_missing(self):
        p = TemplateParameter(name="x", required=False)
        assert p.validate_value(None)

    def test_validate_choices_valid(self):
        p = TemplateParameter(name="env", choices=["dev", "prod"])
        assert p.validate_value("dev")

    def test_validate_choices_invalid(self):
        p = TemplateParameter(name="env", choices=["dev", "prod"])
        assert not p.validate_value("staging")

    def test_validate_no_choices(self):
        p = TemplateParameter(name="x")
        assert p.validate_value("anything")


# ======================================================================
# StepTemplate tests
# ======================================================================


class TestStepTemplate:
    def test_render_basic(self):
        s = StepTemplate(
            order=1,
            name_template="Deploy {service}",
            description_template="Push {service} to {env}",
            agent="deployer",
        )
        result = s.render({"service": "auth", "env": "prod"})
        assert result["name"] == "Deploy auth"
        assert result["description"] == "Push auth to prod"
        assert result["agent"] == "deployer"
        assert result["order"] == 1

    def test_render_missing_param_kept(self):
        s = StepTemplate(order=1, name_template="Build {name}")
        result = s.render({})
        assert result["name"] == "Build {name}"  # placeholder kept


# ======================================================================
# SpecTemplate tests
# ======================================================================


class TestSpecTemplate:
    def _make_template(self) -> SpecTemplate:
        return SpecTemplate(
            name="test-deploy",
            description="Test deployment",
            category="devops",
            intent_template="Deploy {service} to {env}",
            parameters=[
                TemplateParameter(name="service", description="service name"),
                TemplateParameter(name="env", choices=["dev", "staging", "prod"]),
            ],
            steps_template=[
                StepTemplate(order=1, name_template="Build {service}", agent="builder"),
                StepTemplate(order=2, name_template="Deploy to {env}", agent="deployer",
                             depends_on_indices=[0]),
            ],
            constraints_template=["Zero downtime in {env}"],
            tags=["deploy"],
        )

    def test_render_success(self):
        tpl = self._make_template()
        result = tpl.render({"service": "auth", "env": "prod"})
        assert result["intent"] == "Deploy auth to prod"
        assert len(result["steps"]) == 2
        assert result["steps"][0]["name"] == "Build auth"
        assert result["steps"][1]["name"] == "Deploy to prod"
        assert result["constraints"] == ["Zero downtime in prod"]
        assert "deploy" in result["tags"]
        assert result["template_name"] == "test-deploy"

    def test_render_missing_required(self):
        tpl = self._make_template()
        with pytest.raises(ValueError, match="Missing required parameter"):
            tpl.render({"service": "auth"})  # missing env

    def test_render_invalid_choice(self):
        tpl = self._make_template()
        with pytest.raises(ValueError, match="Invalid value"):
            tpl.render({"service": "auth", "env": "moon"})

    def test_list_parameters(self):
        tpl = self._make_template()
        params = tpl.list_parameters()
        assert len(params) == 2
        assert params[0]["name"] == "service"

    def test_default_values(self):
        tpl = SpecTemplate(
            name="t",
            intent_template="{x} and {y}",
            parameters=[
                TemplateParameter(name="x", default="hello"),
                TemplateParameter(name="y", default="world"),
            ],
        )
        result = tpl.render({})
        assert result["intent"] == "hello and world"

    def test_extra_params_pass_through(self):
        tpl = SpecTemplate(
            name="t",
            intent_template="{a} {extra}",
            parameters=[TemplateParameter(name="a")],
        )
        result = tpl.render({"a": "x", "extra": "bonus"})
        assert result["intent"] == "x bonus"


# ======================================================================
# Built-in spec templates
# ======================================================================


class TestBuiltinSpecTemplates:
    def test_count(self):
        assert len(BUILTIN_SPEC_TEMPLATES) == 10

    def test_all_have_names(self):
        names = [t.name for t in BUILTIN_SPEC_TEMPLATES]
        assert len(set(names)) == 10  # all unique

    @pytest.mark.parametrize(
        "name",
        [
            "api-development",
            "bug-fix",
            "code-refactor",
            "deploy",
            "data-pipeline",
            "documentation",
            "security-review",
            "migration",
            "monitoring-setup",
            "performance-test",
        ],
    )
    def test_builtin_exists(self, name: str):
        found = [t for t in BUILTIN_SPEC_TEMPLATES if t.name == name]
        assert len(found) == 1

    def test_api_development_render(self):
        tpl = [t for t in BUILTIN_SPEC_TEMPLATES if t.name == "api-development"][0]
        result = tpl.render({"name": "Users", "framework": "FastAPI"})
        assert "Users" in result["intent"]
        assert "FastAPI" in result["intent"]
        assert len(result["steps"]) >= 3

    def test_deploy_render(self):
        tpl = [t for t in BUILTIN_SPEC_TEMPLATES if t.name == "deploy"][0]
        result = tpl.render({"service": "gateway", "environment": "staging"})
        assert "gateway" in result["intent"]
        assert "staging" in result["intent"]


# ======================================================================
# _substitute helper
# ======================================================================


class TestSubstitute:
    def test_basic(self):
        assert _substitute("hello {name}", {"name": "world"}) == "hello world"

    def test_missing_key_kept(self):
        assert _substitute("{a} {b}", {"a": "x"}) == "x {b}"

    def test_empty_dict(self):
        assert _substitute("{x}", {}) == "{x}"

    def test_no_placeholders(self):
        assert _substitute("no vars", {"a": "b"}) == "no vars"


# ======================================================================
# PromptTemplate tests
# ======================================================================


class TestPromptTemplate:
    def test_render(self):
        pt = PromptTemplate(
            name="test",
            template="Hello {name}, you are {role}.",
            variables=["name", "role"],
        )
        result = pt.render(name="Alice", role="admin")
        assert result == "Hello Alice, you are admin."

    def test_render_partial(self):
        pt = PromptTemplate(name="t", template="{a} {b}", variables=["a", "b"])
        result = pt.render(a="x")
        assert result == "x {b}"

    def test_missing_variables(self):
        pt = PromptTemplate(name="t", template="{a} {b}", variables=["a", "b"])
        assert pt.missing_variables(a="x") == ["b"]
        assert pt.missing_variables(a="x", b="y") == []


# ======================================================================
# PromptLibrary tests
# ======================================================================


class TestPromptLibrary:
    @pytest.fixture()
    def lib(self) -> PromptLibrary:
        return PromptLibrary()

    def test_builtins_loaded(self, lib: PromptLibrary):
        assert len(lib) >= 8

    def test_get_existing(self, lib: PromptLibrary):
        tpl = lib.get("code_review_detailed")
        assert tpl is not None
        assert "focus_areas" in tpl.variables

    def test_get_missing(self, lib: PromptLibrary):
        assert lib.get("nonexistent") is None

    def test_list_all(self, lib: PromptLibrary):
        all_templates = lib.list_templates()
        assert len(all_templates) >= 8

    def test_list_by_category(self, lib: PromptLibrary):
        code_templates = lib.list_templates(category="code")
        assert all(t.category == "code" for t in code_templates)
        assert len(code_templates) >= 2

    def test_search(self, lib: PromptLibrary):
        results = lib.search("security")
        assert any(t.name == "security_report" for t in results)

    def test_add_custom(self, lib: PromptLibrary):
        custom = PromptTemplate(name="custom1", template="Hi {name}", category="test")
        lib.add(custom)
        assert lib.get("custom1") is not None

    def test_remove(self, lib: PromptLibrary):
        assert lib.remove("code_review_detailed")
        assert lib.get("code_review_detailed") is None

    def test_remove_missing(self, lib: PromptLibrary):
        assert not lib.remove("does_not_exist")

    def test_render_shorthand(self, lib: PromptLibrary):
        result = lib.render(
            "bug_analysis",
            description="crash",
            expected="no crash",
            actual="crash",
            steps="click button",
            logs="NullPointerException",
        )
        assert "crash" in result
        assert "NullPointerException" in result

    def test_render_missing_template(self, lib: PromptLibrary):
        with pytest.raises(KeyError):
            lib.render("nope")

    def test_categories(self, lib: PromptLibrary):
        cats = lib.categories
        assert "code" in cats
        assert "security" in cats


# ======================================================================
# TemplateRegistry tests
# ======================================================================


class TestTemplateRegistry:
    def test_register_and_get(self):
        reg = TemplateRegistry()
        tpl = SpecTemplate(name="mytest", intent_template="Do {thing}")
        reg.register(tpl)
        assert reg.get("mytest") is not None

    def test_unregister(self):
        reg = TemplateRegistry()
        tpl = SpecTemplate(name="mytest")
        reg.register(tpl)
        assert reg.unregister("mytest")
        assert reg.get("mytest") is None

    def test_contains(self):
        reg = TemplateRegistry()
        reg.register(SpecTemplate(name="a"))
        assert "a" in reg
        assert "b" not in reg

    def test_len(self):
        reg = TemplateRegistry()
        assert len(reg) == 0
        reg.register(SpecTemplate(name="a"))
        assert len(reg) == 1

    def test_search(self):
        reg = TemplateRegistry()
        reg.register(SpecTemplate(name="deploy-service", category="devops", tags=["deploy"]))
        reg.register(SpecTemplate(name="build-api", category="dev"))
        assert len(reg.search("deploy")) == 1
        assert len(reg.search("dev")) == 2  # both match


# ======================================================================
# TemplateEngine tests
# ======================================================================


class TestTemplateEngine:
    @pytest.fixture()
    def engine(self) -> TemplateEngine:
        return TemplateEngine()

    def test_builtins_loaded(self, engine: TemplateEngine):
        specs = engine.list_spec_templates()
        assert len(specs) == 10
        prompts = engine.list_prompt_templates()
        assert len(prompts) >= 8

    def test_render_spec(self, engine: TemplateEngine):
        result = engine.render_spec("bug-fix", {"description": "NPE on login", "severity": "high"})
        assert "NPE on login" in result["intent"]

    def test_render_spec_missing(self, engine: TemplateEngine):
        with pytest.raises(KeyError):
            engine.render_spec("nonexistent", {})

    def test_render_prompt(self, engine: TemplateEngine):
        result = engine.render_prompt("meeting_agenda",
                                       title="Sprint Review",
                                       duration="1h",
                                       attendees="team",
                                       purpose="review sprint",
                                       action_items="none")
        assert "Sprint Review" in result

    def test_render_prompt_missing(self, engine: TemplateEngine):
        with pytest.raises(KeyError):
            engine.render_prompt("nonexistent")

    def test_search_cross_type(self, engine: TemplateEngine):
        results = engine.search("security")
        assert len(results["spec_templates"]) >= 1
        assert len(results["prompt_templates"]) >= 1

    def test_register_custom_spec(self, engine: TemplateEngine):
        custom = SpecTemplate(name="custom-job", intent_template="Run {job}")
        engine.register_spec_template(custom)
        specs = engine.list_spec_templates()
        assert any(s["name"] == "custom-job" for s in specs)

    def test_register_custom_prompt(self, engine: TemplateEngine):
        custom = PromptTemplate(name="custom-prompt", template="Hello {x}")
        engine.register_prompt_template(custom)
        result = engine.render_prompt("custom-prompt", x="world")
        assert result == "Hello world"

    def test_list_spec_by_category(self, engine: TemplateEngine):
        devops = engine.list_spec_templates(category="devops")
        assert all(s["category"] == "devops" for s in devops)
        assert len(devops) >= 2  # deploy, monitoring-setup

    def test_list_prompt_by_category(self, engine: TemplateEngine):
        code = engine.list_prompt_templates(category="code")
        assert all(p["category"] == "code" for p in code)

    def test_registry_property(self, engine: TemplateEngine):
        assert isinstance(engine.spec_registry, TemplateRegistry)

    def test_prompt_library_property(self, engine: TemplateEngine):
        assert isinstance(engine.prompt_library, PromptLibrary)
