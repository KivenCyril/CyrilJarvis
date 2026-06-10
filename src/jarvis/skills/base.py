"""Skill definition — a reusable, version-tracked procedure.

A :class:`Skill` is the unit of procedural memory in JARVIS.  It captures
*how* to accomplish a category of tasks, tracks execution history, and
exposes statistics that the :class:`~jarvis.skills.evolve.SkillEvolver`
uses to decide when and how to improve it.

The on-disk format is YAML, compatible with the agentskills.io schema so
that skills can be shared via the Skills Hub.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class SkillStatus(str, Enum):
    """Lifecycle status of a skill."""

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class SkillMetadata(BaseModel):
    """Descriptive metadata attached to every skill."""

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "jarvis"
    created_by: str = "agent"  # "agent" or "human"
    tags: list[str] = Field(default_factory=list)
    domain: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SkillStep(BaseModel):
    """A single step in a skill's procedure."""

    order: int
    action: str  # human-readable description of what to do
    tool: str | None = None  # tool name (e.g. "shell_execute", "read_file")
    tool_args_template: dict[str, Any] = Field(default_factory=dict)
    expected_output: str = ""
    error_handling: str = ""


class SkillExecution(BaseModel):
    """Record of a single skill execution for learning."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_context: str = ""
    output: str = ""
    success: bool = True
    duration_ms: int = 0
    feedback: str = ""  # user or curator feedback
    score: float = 0.0  # 0.0–1.0 quality score


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

class Skill(BaseModel):
    """A reusable, self-improving procedural skill.

    Skills are the bridge between Streaming Specs and persistent knowledge.
    When an Agent completes a Spec successfully, the Spec can be distilled
    into a Skill for future reuse.

    Attributes:
        id: Unique identifier (auto-generated hex string).
        metadata: Descriptive metadata (name, version, tags, ...).
        status: Lifecycle status controlling discoverability.
        system_prompt: System prompt injected when an agent uses this skill.
        steps: Ordered procedure the agent should follow.
        constraints: Hard rules the agent must obey while executing.
        executions: In-memory execution log (excluded from serialisation).
        success_rate: Rolling success ratio across recorded executions.
        avg_score: Rolling average quality score.
        use_count: Total number of recorded executions.
        last_used_at: Timestamp of the most recent execution.
        parent_skill_id: If this skill was evolved from another, its ID.
        parent_spec_id: If this skill was distilled from a Spec, its ID.
        improvement_notes: Free-form notes added during evolution.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    metadata: SkillMetadata
    status: SkillStatus = SkillStatus.DRAFT

    # Procedure -----------------------------------------------------------
    system_prompt: str = ""
    steps: list[SkillStep] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)

    # Learning ------------------------------------------------------------
    executions: list[SkillExecution] = Field(default_factory=list, exclude=True)
    success_rate: float = 0.0
    avg_score: float = 0.0
    use_count: int = 0
    last_used_at: datetime | None = None

    # Eval ---------------------------------------------------------------
    eval_cases: list[dict] = Field(default_factory=list)
    eval_pass_rate: float = 0.0

    # Evolution -----------------------------------------------------------
    parent_skill_id: str | None = None
    parent_spec_id: str | None = None
    improvement_notes: list[str] = Field(default_factory=list)
    reflection_log: list[dict] = Field(default_factory=list, exclude=True)

    # ------------------------------------------------------------------
    # Execution tracking
    # ------------------------------------------------------------------

    def record_execution(self, execution: SkillExecution) -> None:
        """Record an execution and update rolling statistics."""
        self.executions.append(execution)
        self.use_count += 1
        self.last_used_at = execution.timestamp

        successful = [e for e in self.executions if e.success]
        self.success_rate = (
            len(successful) / len(self.executions) if self.executions else 0.0
        )
        scored = [e for e in self.executions if e.score > 0]
        self.avg_score = (
            sum(e.score for e in scored) / len(scored) if scored else 0.0
        )

        self.metadata.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Serialisation — agentskills.io compatible YAML
    # ------------------------------------------------------------------

    def to_yaml(self) -> str:
        """Export the skill in agentskills.io compatible YAML format."""
        data: dict[str, Any] = {
            "kind": "Skill",
            "metadata": {
                "name": self.metadata.name,
                "version": self.metadata.version,
                "description": self.metadata.description,
                "author": self.metadata.author,
                "tags": self.metadata.tags,
                "domain": self.metadata.domain,
            },
            "spec": {
                "system_prompt": self.system_prompt,
                "steps": [
                    {
                        "order": s.order,
                        "action": s.action,
                        "tool": s.tool,
                        "tool_args": s.tool_args_template,
                    }
                    for s in self.steps
                ],
                "constraints": self.constraints,
            },
            "stats": {
                "use_count": self.use_count,
                "success_rate": round(self.success_rate, 2),
                "avg_score": round(self.avg_score, 2),
            },
        }
        return yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Skill:
        """Load a skill from an agentskills.io YAML file.

        Args:
            path: Filesystem path to the ``.yaml`` file.

        Returns:
            A fully hydrated :class:`Skill` instance with status ``ACTIVE``.

        Raises:
            FileNotFoundError: If *path* does not exist.
            yaml.YAMLError: If the file is not valid YAML.
        """
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"Empty YAML file: {path}")

        meta = data.get("metadata", {})
        spec = data.get("spec", {})
        stats = data.get("stats", {})

        return cls(
            metadata=SkillMetadata(
                name=meta.get("name", path.stem),
                version=meta.get("version", "1.0.0"),
                description=meta.get("description", ""),
                author=meta.get("author", "jarvis"),
                tags=meta.get("tags", []),
                domain=meta.get("domain", ""),
            ),
            system_prompt=spec.get("system_prompt", ""),
            steps=[
                SkillStep(
                    order=s.get("order", i),
                    action=s.get("action", ""),
                    tool=s.get("tool"),
                    tool_args_template=s.get("tool_args", {}),
                    expected_output=s.get("expected_output", ""),
                    error_handling=s.get("error_handling", ""),
                )
                for i, s in enumerate(spec.get("steps", []))
            ],
            constraints=spec.get("constraints", []),
            status=SkillStatus.ACTIVE,
            use_count=stats.get("use_count", 0),
            success_rate=stats.get("success_rate", 0.0),
            avg_score=stats.get("avg_score", 0.0),
        )

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def save(self, directory: str | Path) -> Path:
        """Save the skill to a YAML file (plus execution history as JSON).

        Args:
            directory: Target directory.  Created if it does not exist.

        Returns:
            Path to the written YAML file.
        """
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)

        filepath = directory / f"{self.metadata.name}.yaml"
        filepath.write_text(self.to_yaml(), encoding="utf-8")
        logger.debug("Saved skill '%s' to %s", self.metadata.name, filepath)

        # Execution history is stored separately because it can grow large.
        if self.executions:
            hist_path = directory / f"{self.metadata.name}.history.json"
            hist_path.write_text(
                json.dumps(
                    [e.model_dump(mode="json") for e in self.executions],
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            logger.debug(
                "Saved %d execution records to %s",
                len(self.executions),
                hist_path,
            )

        return filepath
