"""Skill system tests.

Tests skill registration, execution, scoring, versioning,
metadata management, and skill lifecycle.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Skill Models
# ---------------------------------------------------------------------------

@dataclass
class SkillMetadata:
    name: str
    version: str
    description: str = ""
    domain: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = "system"
    created_at: str = ""
    updated_at: str = ""
    dependencies: list[str] = field(default_factory=list)
    min_jarvis_version: str = "0.1.0"

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "domain": self.domain,
            "tags": self.tags,
            "author": self.author,
        }


@dataclass
class SkillExecution:
    skill_name: str
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    success: bool = False
    error: str | None = None
    duration_ms: float = 0
    started_at: str = ""
    completed_at: str = ""
    score: float = 0.0  # Quality score 0-1


@dataclass
class Skill:
    metadata: SkillMetadata
    status: str = "active"  # active, inactive, deprecated, error
    use_count: int = 0
    success_count: int = 0
    total_score: float = 0.0
    executions: list[SkillExecution] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.use_count == 0:
            return 0.0
        return round(self.success_count / self.use_count, 4)

    @property
    def avg_score(self) -> float:
        if self.use_count == 0:
            return 0.0
        return round(self.total_score / self.use_count, 4)

    def execute(self, input_data: dict) -> SkillExecution:
        self.use_count += 1
        execution = SkillExecution(
            skill_name=self.metadata.name,
            input_data=input_data,
            started_at=datetime.datetime.utcnow().isoformat(),
        )
        # Simulate execution
        execution.success = True
        execution.output_data = {"result": f"Processed by {self.metadata.name}"}
        execution.score = 0.85
        execution.completed_at = datetime.datetime.utcnow().isoformat()

        if execution.success:
            self.success_count += 1
        self.total_score += execution.score
        self.executions.append(execution)
        return execution

    def record_failure(self, error: str) -> None:
        self.use_count += 1
        execution = SkillExecution(
            skill_name=self.metadata.name,
            success=False,
            error=error,
        )
        self.executions.append(execution)

    def deactivate(self) -> None:
        self.status = "inactive"

    def activate(self) -> None:
        self.status = "active"

    def deprecate(self) -> None:
        self.status = "deprecated"

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "status": self.status,
            "use_count": self.use_count,
            "success_rate": self.success_rate,
            "avg_score": self.avg_score,
        }


class SkillRegistry:
    """Registry for managing skills."""

    def __init__(self):
        self.skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self.skills[skill.metadata.name] = skill

    def get(self, name: str) -> Skill | None:
        return self.skills.get(name)

    def unregister(self, name: str) -> bool:
        if name in self.skills:
            del self.skills[name]
            return True
        return False

    def list_skills(self, status: str | None = None,
                    domain: str | None = None,
                    tag: str | None = None) -> list[Skill]:
        result = list(self.skills.values())
        if status:
            result = [s for s in result if s.status == status]
        if domain:
            result = [s for s in result if s.metadata.domain == domain]
        if tag:
            result = [s for s in result if tag in s.metadata.tags]
        return result

    def search(self, query: str) -> list[Skill]:
        q = query.lower()
        return [
            s for s in self.skills.values()
            if q in s.metadata.name.lower()
            or q in s.metadata.description.lower()
            or any(q in t for t in s.metadata.tags)
        ]

    @property
    def stats(self) -> dict[str, Any]:
        total = len(self.skills)
        active = sum(1 for s in self.skills.values() if s.status == "active")
        total_uses = sum(s.use_count for s in self.skills.values())
        return {
            "total": total,
            "active": active,
            "inactive": total - active,
            "total_uses": total_uses,
            "domains": list(set(s.metadata.domain for s in self.skills.values() if s.metadata.domain)),
        }


# ---------------------------------------------------------------------------
# Tests: SkillMetadata
# ---------------------------------------------------------------------------

class TestSkillMetadata:
    def test_create_metadata(self):
        meta = SkillMetadata(name="test-skill", version="1.0")
        assert meta.name == "test-skill"
        assert meta.version == "1.0"
        assert meta.created_at != ""

    def test_metadata_with_tags(self):
        meta = SkillMetadata(name="test", version="1.0", tags=["code", "review"])
        assert "code" in meta.tags

    def test_metadata_to_dict(self):
        meta = SkillMetadata(name="test", version="1.0", domain="dev")
        d = meta.to_dict()
        assert d["name"] == "test"
        assert d["domain"] == "dev"

    def test_metadata_dependencies(self):
        meta = SkillMetadata(name="test", version="1.0", dependencies=["dep-a", "dep-b"])
        assert len(meta.dependencies) == 2


# ---------------------------------------------------------------------------
# Tests: Skill
# ---------------------------------------------------------------------------

class TestSkill:
    def _make_skill(self, name: str = "test-skill") -> Skill:
        return Skill(
            metadata=SkillMetadata(
                name=name, version="1.0", description=f"Skill {name}",
                domain="testing", tags=["test"],
            ),
        )

    def test_create_skill(self):
        skill = self._make_skill()
        assert skill.status == "active"
        assert skill.use_count == 0
        assert skill.success_rate == 0.0

    def test_execute_skill(self):
        skill = self._make_skill()
        result = skill.execute({"input": "data"})
        assert result.success is True
        assert skill.use_count == 1
        assert skill.success_count == 1

    def test_multiple_executions(self):
        skill = self._make_skill()
        for _ in range(5):
            skill.execute({})
        assert skill.use_count == 5
        assert skill.success_rate == 1.0

    def test_record_failure(self):
        skill = self._make_skill()
        skill.execute({})
        skill.record_failure("something broke")
        assert skill.use_count == 2
        assert skill.success_count == 1
        assert skill.success_rate == 0.5

    def test_avg_score(self):
        skill = self._make_skill()
        skill.execute({})  # score 0.85
        skill.execute({})  # score 0.85
        assert skill.avg_score == 0.85

    def test_deactivate(self):
        skill = self._make_skill()
        skill.deactivate()
        assert skill.status == "inactive"

    def test_activate(self):
        skill = self._make_skill()
        skill.deactivate()
        skill.activate()
        assert skill.status == "active"

    def test_deprecate(self):
        skill = self._make_skill()
        skill.deprecate()
        assert skill.status == "deprecated"

    def test_to_dict(self):
        skill = self._make_skill()
        skill.execute({})
        d = skill.to_dict()
        assert d["status"] == "active"
        assert d["use_count"] == 1
        assert "metadata" in d

    def test_execution_history(self):
        skill = self._make_skill()
        skill.execute({"a": 1})
        skill.execute({"b": 2})
        assert len(skill.executions) == 2
        assert skill.executions[0].input_data == {"a": 1}


# ---------------------------------------------------------------------------
# Tests: SkillRegistry
# ---------------------------------------------------------------------------

class TestSkillRegistry:
    def _make_registry(self) -> SkillRegistry:
        reg = SkillRegistry()
        for name, domain, tags in [
            ("code-review", "development", ["code", "review"]),
            ("summarize", "nlp", ["text", "summarize"]),
            ("deploy", "devops", ["deploy", "ci"]),
            ("analyze-data", "data", ["data", "analysis"]),
            ("generate-tests", "development", ["code", "test"]),
        ]:
            reg.register(Skill(
                metadata=SkillMetadata(
                    name=name, version="1.0", description=f"Skill for {name}",
                    domain=domain, tags=tags,
                ),
            ))
        return reg

    def test_register_and_get(self):
        reg = self._make_registry()
        skill = reg.get("code-review")
        assert skill is not None
        assert skill.metadata.name == "code-review"

    def test_get_nonexistent(self):
        reg = self._make_registry()
        assert reg.get("missing") is None

    def test_unregister(self):
        reg = self._make_registry()
        assert reg.unregister("deploy") is True
        assert reg.get("deploy") is None

    def test_unregister_nonexistent(self):
        reg = self._make_registry()
        assert reg.unregister("missing") is False

    def test_list_all(self):
        reg = self._make_registry()
        assert len(reg.list_skills()) == 5

    def test_list_by_status(self):
        reg = self._make_registry()
        reg.get("deploy").deactivate()
        active = reg.list_skills(status="active")
        assert len(active) == 4

    def test_list_by_domain(self):
        reg = self._make_registry()
        dev_skills = reg.list_skills(domain="development")
        assert len(dev_skills) == 2

    def test_list_by_tag(self):
        reg = self._make_registry()
        code_skills = reg.list_skills(tag="code")
        assert len(code_skills) == 2

    def test_search_by_name(self):
        reg = self._make_registry()
        results = reg.search("code")
        assert len(results) >= 1  # code-review, possibly generate-tests (tag: code)

    def test_search_by_description(self):
        reg = self._make_registry()
        results = reg.search("deploy")
        assert len(results) >= 1

    def test_search_by_tag(self):
        reg = self._make_registry()
        results = reg.search("test")
        assert len(results) >= 1

    def test_stats(self):
        reg = self._make_registry()
        reg.get("code-review").execute({})
        reg.get("code-review").execute({})
        stats = reg.stats
        assert stats["total"] == 5
        assert stats["active"] == 5
        assert stats["total_uses"] == 2
        assert len(stats["domains"]) >= 3

    def test_overwrite_skill(self):
        reg = self._make_registry()
        new_skill = Skill(
            metadata=SkillMetadata(
                name="code-review", version="2.0",
                description="Updated skill",
            ),
        )
        reg.register(new_skill)
        assert reg.get("code-review").metadata.version == "2.0"


# ---------------------------------------------------------------------------
# Tests: Skill Versioning
# ---------------------------------------------------------------------------

class TestSkillVersioning:
    def test_version_comparison(self):
        v1 = SkillMetadata(name="test", version="1.0")
        v2 = SkillMetadata(name="test", version="2.0")
        assert v1.version < v2.version

    def test_semantic_version(self):
        meta = SkillMetadata(name="test", version="1.2.3")
        parts = meta.version.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_min_jarvis_version(self):
        meta = SkillMetadata(name="test", version="1.0", min_jarvis_version="0.2.0")
        assert meta.min_jarvis_version == "0.2.0"
