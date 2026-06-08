"""Tests for the jarvis.skills module — loading, registry, evolution, and stats."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jarvis.skills.base import Skill, SkillExecution, SkillMetadata, SkillStatus, SkillStep
from jarvis.skills.registry import SkillRegistry
from jarvis.skills.evolve import SkillEvolver


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BUILTIN_DIR = Path(__file__).resolve().parent.parent / "skills" / "builtin"

ALL_YAML_FILES = sorted(BUILTIN_DIR.glob("*.yaml"))

# Sanity-check: we expect at least 26 builtin skills (11 original + 15 new)
assert len(ALL_YAML_FILES) >= 26, (
    f"Expected at least 26 YAML skill files in {BUILTIN_DIR}, found {len(ALL_YAML_FILES)}"
)


# ---------------------------------------------------------------------------
# 1. Loading all builtin YAML skills
# ---------------------------------------------------------------------------

class TestLoadBuiltinSkills:
    """Verify every YAML file in skills/builtin/ loads without errors."""

    @pytest.mark.parametrize(
        "yaml_path",
        ALL_YAML_FILES,
        ids=[p.stem for p in ALL_YAML_FILES],
    )
    def test_load_skill_from_yaml(self, yaml_path: Path):
        skill = Skill.from_yaml(yaml_path)

        # Basic invariants every skill must satisfy
        assert skill.metadata.name, f"{yaml_path.name}: name must not be empty"
        assert skill.metadata.version, f"{yaml_path.name}: version must not be empty"
        assert skill.metadata.description, f"{yaml_path.name}: description must not be empty"
        assert skill.metadata.tags, f"{yaml_path.name}: tags must not be empty"
        assert skill.metadata.domain, f"{yaml_path.name}: domain must not be empty"
        assert skill.steps, f"{yaml_path.name}: must have at least one step"
        assert skill.system_prompt, f"{yaml_path.name}: system_prompt must not be empty"
        assert skill.status == SkillStatus.ACTIVE

    def test_load_all_skills_count(self):
        """We should be able to load every file without any failures."""
        loaded = []
        for p in ALL_YAML_FILES:
            loaded.append(Skill.from_yaml(p))
        assert len(loaded) == len(ALL_YAML_FILES)

    def test_no_duplicate_skill_names(self):
        names = [Skill.from_yaml(p).metadata.name for p in ALL_YAML_FILES]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"


# ---------------------------------------------------------------------------
# 1b. Verify all expected builtin skill names are present
# ---------------------------------------------------------------------------

EXPECTED_SKILL_NAMES = sorted([
    # Original 11
    "api-design",
    "code-review",
    "data-analysis",
    "deploy-checklist",
    "git-workflow",
    "incident-response",
    "meeting-notes",
    "performance-optimization",
    "project-setup",
    "security-audit",
    "web-research",
    # New 15
    "database-migration",
    "docker-compose-setup",
    "test-generation",
    "code-documentation",
    "dependency-audit",
    "api-testing",
    "monitoring-setup",
    "code-migration",
    "architecture-review",
    "onboarding-guide",
    "release-notes",
    "load-testing",
    "error-handling",
    "logging-setup",
    "caching-strategy",
])


class TestAllExpectedSkillsPresent:
    """Verify every expected skill name is loadable from the builtin directory."""

    @pytest.mark.parametrize("expected_name", EXPECTED_SKILL_NAMES)
    def test_expected_skill_exists(self, expected_name: str):
        yaml_path = BUILTIN_DIR / f"{expected_name}.yaml"
        assert yaml_path.exists(), f"Missing skill file: {yaml_path}"
        skill = Skill.from_yaml(yaml_path)
        assert skill.metadata.name == expected_name

    def test_total_skill_count(self):
        assert len(ALL_YAML_FILES) >= len(EXPECTED_SKILL_NAMES), (
            f"Expected at least {len(EXPECTED_SKILL_NAMES)} skills, "
            f"found {len(ALL_YAML_FILES)}"
        )


# ---------------------------------------------------------------------------
# 2. Skill model serialisation round-trip
# ---------------------------------------------------------------------------

class TestSkillSerialisation:
    """Verify Skill -> YAML -> Skill round-trip preserves key data."""

    def _make_skill(self, name: str = "test-skill") -> Skill:
        return Skill(
            metadata=SkillMetadata(
                name=name,
                version="2.3.1",
                description="A test skill for round-trip checks",
                author="tester",
                tags=["test", "roundtrip"],
                domain="testing",
            ),
            system_prompt="You are a test bot.",
            steps=[
                SkillStep(order=0, action="Step one", tool="read_file"),
                SkillStep(order=1, action="Step two", tool=None),
            ],
            constraints=["Be deterministic", "No side-effects"],
            status=SkillStatus.ACTIVE,
            use_count=5,
            success_rate=0.8,
            avg_score=0.75,
        )

    def test_roundtrip_via_yaml_string(self, tmp_path: Path):
        original = self._make_skill()
        yaml_text = original.to_yaml()

        # Write -> read back
        path = tmp_path / "roundtrip.yaml"
        path.write_text(yaml_text)
        loaded = Skill.from_yaml(path)

        assert loaded.metadata.name == original.metadata.name
        assert loaded.metadata.version == original.metadata.version
        assert loaded.metadata.description == original.metadata.description
        assert loaded.metadata.tags == original.metadata.tags
        assert loaded.metadata.domain == original.metadata.domain
        assert loaded.system_prompt == original.system_prompt
        assert len(loaded.steps) == len(original.steps)
        assert loaded.constraints == original.constraints
        assert loaded.use_count == original.use_count
        assert loaded.success_rate == original.success_rate
        assert loaded.avg_score == original.avg_score

    def test_roundtrip_step_details(self, tmp_path: Path):
        original = self._make_skill()
        path = tmp_path / "step_details.yaml"
        path.write_text(original.to_yaml())
        loaded = Skill.from_yaml(path)

        for orig_step, loaded_step in zip(original.steps, loaded.steps):
            assert loaded_step.order == orig_step.order
            assert loaded_step.action == orig_step.action
            assert loaded_step.tool == orig_step.tool

    def test_save_and_reload(self, tmp_path: Path):
        original = self._make_skill("save-reload")
        saved_path = original.save(tmp_path)
        assert saved_path.exists()
        loaded = Skill.from_yaml(saved_path)
        assert loaded.metadata.name == "save-reload"

    def test_to_yaml_produces_valid_yaml(self):
        skill = self._make_skill()
        text = skill.to_yaml()
        data = yaml.safe_load(text)
        assert data["kind"] == "Skill"
        assert data["metadata"]["name"] == "test-skill"
        assert len(data["spec"]["steps"]) == 2

    def test_from_yaml_empty_file_raises(self, tmp_path: Path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("")
        with pytest.raises(ValueError, match="Empty YAML"):
            Skill.from_yaml(empty)


# ---------------------------------------------------------------------------
# 3. SkillRegistry search by tags / domain
# ---------------------------------------------------------------------------

class TestSkillRegistrySearch:
    """Test registry CRUD, tag search, domain search, and keyword search."""

    @pytest.fixture()
    def registry(self) -> SkillRegistry:
        reg = SkillRegistry()
        reg.load_directory(BUILTIN_DIR)
        return reg

    def test_load_directory_count(self, registry: SkillRegistry):
        assert len(registry) >= 26

    def test_get_existing_skill(self, registry: SkillRegistry):
        skill = registry.get("code-review")
        assert skill is not None
        assert skill.metadata.name == "code-review"

    def test_get_nonexistent_returns_none(self, registry: SkillRegistry):
        assert registry.get("nonexistent-skill") is None

    def test_find_by_tags_single(self, registry: SkillRegistry):
        results = registry.find_by_tags(["security"])
        names = {s.metadata.name for s in results}
        assert "code-review" in names
        assert "security-audit" in names

    def test_find_by_tags_multiple(self, registry: SkillRegistry):
        results = registry.find_by_tags(["git", "workflow"])
        names = {s.metadata.name for s in results}
        assert "git-workflow" in names

    def test_find_by_tags_no_match(self, registry: SkillRegistry):
        results = registry.find_by_tags(["nonexistent-tag-xyz"])
        assert results == []

    def test_find_by_domain_development(self, registry: SkillRegistry):
        results = registry.find_by_domain("development")
        names = {s.metadata.name for s in results}
        assert "code-review" in names
        assert "api-design" in names
        assert "git-workflow" in names
        assert "project-setup" in names
        assert "performance-optimization" in names

    def test_find_by_domain_operations(self, registry: SkillRegistry):
        results = registry.find_by_domain("operations")
        names = {s.metadata.name for s in results}
        assert "deploy-checklist" in names
        assert "incident-response" in names

    def test_find_by_domain_case_insensitive(self, registry: SkillRegistry):
        results_lower = registry.find_by_domain("data")
        results_upper = registry.find_by_domain("Data")
        assert len(results_lower) == len(results_upper)

    def test_find_by_domain_no_match(self, registry: SkillRegistry):
        results = registry.find_by_domain("nonexistent-domain")
        assert results == []

    def test_search_keyword(self, registry: SkillRegistry):
        results = registry.search("security vulnerability")
        assert len(results) > 0
        # security-audit should rank high since it matches both terms
        names = [s.metadata.name for s in results]
        assert "security-audit" in names

    def test_search_empty_query(self, registry: SkillRegistry):
        assert registry.search("") == []

    def test_list_skills_all(self, registry: SkillRegistry):
        all_skills = registry.list_skills()
        assert len(all_skills) >= 11

    def test_list_skills_by_status(self, registry: SkillRegistry):
        active = registry.list_skills(status=SkillStatus.ACTIVE)
        assert len(active) >= 11
        deprecated = registry.list_skills(status=SkillStatus.DEPRECATED)
        assert len(deprecated) == 0

    def test_deprecate_skill(self, registry: SkillRegistry):
        registry.deprecate("code-review")
        skill = registry.get("code-review")
        assert skill is not None
        assert skill.status == SkillStatus.DEPRECATED
        # Deprecated skills should not appear in find_by_tags
        results = registry.find_by_tags(["code"])
        names = {s.metadata.name for s in results}
        assert "code-review" not in names

    def test_register_replaces_existing(self, registry: SkillRegistry):
        old = registry.get("code-review")
        assert old is not None
        new_skill = Skill(
            metadata=SkillMetadata(
                name="code-review",
                version="2.0.0",
                description="Updated",
                tags=["code"],
                domain="development",
            ),
            status=SkillStatus.ACTIVE,
        )
        registry.register(new_skill)
        replaced = registry.get("code-review")
        assert replaced is not None
        assert replaced.metadata.version == "2.0.0"

    def test_contains_operator(self, registry: SkillRegistry):
        assert "code-review" in registry
        assert "nonexistent" not in registry


# ---------------------------------------------------------------------------
# 4. SkillEvolver should_evolve logic
# ---------------------------------------------------------------------------

class TestSkillEvolverShouldEvolve:
    """Test the evolution trigger heuristics."""

    def _make_skill_with_executions(
        self,
        n: int,
        success_rate: float = 1.0,
        scores: list[float] | None = None,
    ) -> Skill:
        skill = Skill(
            metadata=SkillMetadata(name="evolvable", tags=["test"], domain="test"),
            status=SkillStatus.ACTIVE,
        )
        for i in range(n):
            success = i < int(n * success_rate)
            score = scores[i] if scores and i < len(scores) else 0.9
            ex = SkillExecution(
                success=success,
                score=score,
                input_context=f"input-{i}",
                output=f"output-{i}",
                feedback="ok" if success else "failed",
            )
            skill.record_execution(ex)
        return skill

    @pytest.mark.asyncio
    async def test_no_evolve_below_min_executions(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = self._make_skill_with_executions(2)
        assert await evolver.should_evolve(skill) is False

    @pytest.mark.asyncio
    async def test_no_evolve_when_healthy(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = self._make_skill_with_executions(5, success_rate=1.0)
        assert await evolver.should_evolve(skill) is False

    @pytest.mark.asyncio
    async def test_evolve_on_low_success_rate(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        # 3 executions, 1 success => 33% success rate
        skill = self._make_skill_with_executions(3, success_rate=0.33)
        assert await evolver.should_evolve(skill) is True

    @pytest.mark.asyncio
    async def test_evolve_on_low_avg_score(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = self._make_skill_with_executions(
            4, success_rate=1.0, scores=[0.5, 0.6, 0.5, 0.6]
        )
        # avg_score = 0.55 < 0.7
        assert await evolver.should_evolve(skill) is True

    @pytest.mark.asyncio
    async def test_evolve_on_downward_trend(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        # Scores are declining: 0.95, 0.85, 0.80 — last three are strictly decreasing
        skill = self._make_skill_with_executions(
            3, success_rate=1.0, scores=[0.95, 0.85, 0.80]
        )
        # avg_score is (0.95+0.85+0.80)/3 ≈ 0.87 which is above 0.7
        # but the downward trend should trigger evolution
        assert await evolver.should_evolve(skill) is True

    @pytest.mark.asyncio
    async def test_no_evolve_flat_scores(self):
        registry = SkillRegistry()
        evolver = SkillEvolver(registry)
        skill = self._make_skill_with_executions(
            3, success_rate=1.0, scores=[0.85, 0.85, 0.85]
        )
        assert await evolver.should_evolve(skill) is False

    def test_bump_version(self):
        assert SkillEvolver._bump_version("1.0.0") == "1.1.0"
        assert SkillEvolver._bump_version("2.3.1") == "2.4.0"
        assert SkillEvolver._bump_version("bad") == "1.1.0"


# ---------------------------------------------------------------------------
# 5. Skill execution recording and stats
# ---------------------------------------------------------------------------

class TestSkillExecutionRecording:
    """Test that record_execution properly updates rolling stats."""

    def test_record_single_success(self):
        skill = Skill(
            metadata=SkillMetadata(name="recorder", tags=["test"], domain="test"),
        )
        ex = SkillExecution(success=True, score=0.9)
        skill.record_execution(ex)

        assert skill.use_count == 1
        assert skill.success_rate == 1.0
        assert skill.avg_score == 0.9
        assert skill.last_used_at is not None

    def test_record_multiple_mixed(self):
        skill = Skill(
            metadata=SkillMetadata(name="recorder", tags=["test"], domain="test"),
        )
        skill.record_execution(SkillExecution(success=True, score=0.8))
        skill.record_execution(SkillExecution(success=False, score=0.0))
        skill.record_execution(SkillExecution(success=True, score=0.6))

        assert skill.use_count == 3
        assert skill.success_rate == pytest.approx(2 / 3)
        # avg_score only considers scored (> 0) executions: (0.8 + 0.6) / 2 = 0.7
        assert skill.avg_score == pytest.approx(0.7)

    def test_record_all_failures(self):
        skill = Skill(
            metadata=SkillMetadata(name="recorder", tags=["test"], domain="test"),
        )
        skill.record_execution(SkillExecution(success=False, score=0.0))
        skill.record_execution(SkillExecution(success=False, score=0.0))

        assert skill.use_count == 2
        assert skill.success_rate == 0.0
        assert skill.avg_score == 0.0

    def test_record_updates_last_used_at(self):
        skill = Skill(
            metadata=SkillMetadata(name="recorder", tags=["test"], domain="test"),
        )
        assert skill.last_used_at is None
        ex1 = SkillExecution(success=True, score=1.0)
        skill.record_execution(ex1)
        first_ts = skill.last_used_at

        ex2 = SkillExecution(success=True, score=1.0)
        skill.record_execution(ex2)
        assert skill.last_used_at >= first_ts  # type: ignore[operator]

    def test_executions_excluded_from_yaml(self):
        skill = Skill(
            metadata=SkillMetadata(name="recorder", tags=["test"], domain="test"),
        )
        skill.record_execution(SkillExecution(success=True, score=0.9))
        yaml_text = skill.to_yaml()
        data = yaml.safe_load(yaml_text)
        # Execution history should NOT be in the YAML output
        assert "executions" not in data
        # But stats should reflect the recorded execution
        assert data["stats"]["use_count"] == 1

    def test_execution_history_saved_as_json(self, tmp_path: Path):
        skill = Skill(
            metadata=SkillMetadata(name="hist-test", tags=["test"], domain="test"),
        )
        skill.record_execution(SkillExecution(success=True, score=0.9))
        skill.record_execution(SkillExecution(success=False, score=0.0, feedback="timeout"))
        skill.save(tmp_path)

        hist_path = tmp_path / "hist-test.history.json"
        assert hist_path.exists()
        import json
        history = json.loads(hist_path.read_text())
        assert len(history) == 2
        assert history[0]["success"] is True
        assert history[1]["feedback"] == "timeout"
