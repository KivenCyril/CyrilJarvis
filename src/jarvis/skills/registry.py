"""Skill Registry — discovery, loading, and lifecycle management.

The :class:`SkillRegistry` is the single source of truth for all available
skills.  Skills can originate from three sources:

1. **Built-in skills** shipped with JARVIS (YAML files under ``skills/builtin/``).
2. **User-created skills** saved to ``~/.jarvis/skills/``.
3. **Agent-distilled skills** produced by :class:`~jarvis.skills.evolve.SkillEvolver`
   from completed Streaming Specs.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jarvis.skills.base import Skill, SkillStatus

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry for discovering, loading, and managing skills.

    Parameters:
        skills_dir: Root directory where user/agent skills are persisted.
            Defaults to ``~/.jarvis/skills``.
    """

    def __init__(self, skills_dir: str | Path = "~/.jarvis/skills") -> None:
        self._skills: dict[str, Skill] = {}
        self._skills_dir = Path(skills_dir).expanduser()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, skill: Skill) -> None:
        """Add or replace a skill in the registry.

        If a skill with the same name already exists it is silently replaced
        (use :meth:`deprecate` first for an auditable transition).
        """
        if skill.metadata.name in self._skills:
            logger.info(
                "Replacing existing skill '%s' (v%s -> v%s)",
                skill.metadata.name,
                self._skills[skill.metadata.name].metadata.version,
                skill.metadata.version,
            )
        self._skills[skill.metadata.name] = skill
        logger.info(
            "Registered skill '%s' v%s [%s]",
            skill.metadata.name,
            skill.metadata.version,
            skill.status.value,
        )

    def get(self, name: str) -> Skill | None:
        """Look up a skill by its canonical name."""
        return self._skills.get(name)

    def deprecate(self, name: str) -> None:
        """Mark a skill as deprecated so it stops appearing in search results."""
        skill = self._skills.get(name)
        if skill is None:
            logger.warning("Cannot deprecate unknown skill '%s'", name)
            return
        skill.status = SkillStatus.DEPRECATED
        logger.info("Deprecated skill '%s'", name)

    # ------------------------------------------------------------------
    # Query / Search
    # ------------------------------------------------------------------

    def list_skills(self, status: SkillStatus | None = None) -> list[Skill]:
        """Return all registered skills, optionally filtered by status."""
        skills = list(self._skills.values())
        if status is not None:
            skills = [s for s in skills if s.status == status]
        return skills

    def find_by_tags(self, tags: list[str]) -> list[Skill]:
        """Return skills that have *all* of the given tags."""
        tag_set = set(tags)
        return [
            s
            for s in self._skills.values()
            if s.status == SkillStatus.ACTIVE and tag_set.issubset(set(s.metadata.tags))
        ]

    def find_by_domain(self, domain: str) -> list[Skill]:
        """Return active skills whose domain matches *domain*."""
        domain_lower = domain.lower()
        return [
            s
            for s in self._skills.values()
            if s.status == SkillStatus.ACTIVE and s.metadata.domain.lower() == domain_lower
        ]

    def search(self, query: str) -> list[Skill]:
        """Fuzzy keyword search across name, description, and tags.

        Returns active skills ranked by a simple relevance score (number
        of query tokens found in the skill's searchable text).
        """
        tokens = query.lower().split()
        if not tokens:
            return []

        scored: list[tuple[Skill, int]] = []
        for skill in self._skills.values():
            if skill.status not in (SkillStatus.ACTIVE, SkillStatus.DRAFT):
                continue
            haystack = " ".join(
                [
                    skill.metadata.name,
                    skill.metadata.description,
                    " ".join(skill.metadata.tags),
                    skill.metadata.domain,
                ]
            ).lower()
            hits = sum(1 for t in tokens if t in haystack)
            if hits > 0:
                scored.append((skill, hits))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [s for s, _ in scored]

    def get_top_skills(self, limit: int = 10) -> list[Skill]:
        """Return the most effective active skills.

        Sorted by ``success_rate * log2(use_count + 1)`` so that both
        quality and usage volume are rewarded, with diminishing returns
        for very high use counts.
        """
        import math

        active = [s for s in self._skills.values() if s.status == SkillStatus.ACTIVE]
        active.sort(
            key=lambda s: s.success_rate * math.log2(s.use_count + 1),
            reverse=True,
        )
        return active[:limit]

    # ------------------------------------------------------------------
    # LLM-assisted matching
    # ------------------------------------------------------------------

    async def match_skill(self, intent: str, llm_registry: Any = None) -> Skill | None:
        """Find the best skill for a given intent.

        When *llm_registry* is provided the LLM is asked to pick from the
        available skills.  Otherwise falls back to keyword-based
        :meth:`search`.

        Args:
            intent: Natural-language description of what the user wants.
            llm_registry: Optional :class:`~jarvis.llm.registry.LLMRegistry`
                instance for semantic matching.

        Returns:
            The best-matching :class:`Skill`, or ``None`` if nothing fits.
        """
        if llm_registry is not None:
            return await self._llm_match(intent, llm_registry)

        results = self.search(intent)
        return results[0] if results else None

    async def _llm_match(self, intent: str, llm_registry: Any) -> Skill | None:
        """Use an LLM to semantically match *intent* to a skill."""
        active_skills = self.list_skills(status=SkillStatus.ACTIVE)
        if not active_skills:
            return None

        skill_descriptions = "\n".join(
            f"- {s.metadata.name}: {s.metadata.description} (tags: {', '.join(s.metadata.tags)})"
            for s in active_skills
        )

        prompt = (
            "Given the following user intent and list of available skills, "
            "return ONLY the name of the single best-matching skill. "
            "If none match well, return 'NONE'.\n\n"
            f"User intent: {intent}\n\n"
            f"Available skills:\n{skill_descriptions}\n\n"
            "Best matching skill name:"
        )

        try:
            provider = llm_registry.get()
            response = await provider.chat(
                messages=[{"role": "user", "content": prompt}],
            )
            chosen = response.content.strip().strip("'\"").strip()
            if chosen.upper() == "NONE":
                return None
            return self.get(chosen)
        except Exception:
            logger.exception("LLM skill matching failed, falling back to keyword search")
            results = self.search(intent)
            return results[0] if results else None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_directory(self, directory: str | Path | None = None) -> int:
        """Load all ``.yaml`` skill files from a directory.

        Args:
            directory: Directory to scan.  Defaults to the registry's
                configured ``skills_dir``.

        Returns:
            Number of skills successfully loaded.
        """
        target = Path(directory).expanduser() if directory else self._skills_dir
        if not target.is_dir():
            logger.debug("Skills directory does not exist: %s", target)
            return 0

        count = 0
        for yaml_file in sorted(target.glob("*.yaml")):
            # Skip history sidecar files
            if yaml_file.name.endswith(".history.yaml"):
                continue
            try:
                skill = Skill.from_yaml(yaml_file)
                self.register(skill)
                count += 1
            except Exception:
                logger.exception("Failed to load skill from %s", yaml_file)

        logger.info("Loaded %d skill(s) from %s", count, target)
        return count

    def save_all(self) -> None:
        """Persist every registered skill to the configured skills directory."""
        self._skills_dir.mkdir(parents=True, exist_ok=True)
        for skill in self._skills.values():
            try:
                skill.save(self._skills_dir)
            except Exception:
                logger.exception("Failed to save skill '%s'", skill.metadata.name)
        logger.info("Saved %d skill(s) to %s", len(self._skills), self._skills_dir)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._skills)

    def __contains__(self, name: str) -> bool:
        return name in self._skills

    def __repr__(self) -> str:
        return f"<SkillRegistry skills={len(self._skills)} dir={self._skills_dir}>"
