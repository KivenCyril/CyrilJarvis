from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class UserPreferences(BaseModel):
    """User preferences that shape agent behavior."""

    language: str = "en"
    timezone: str = "UTC"
    communication_style: str = "concise"  # concise, detailed, casual, formal
    code_language: str = ""  # preferred programming language
    framework_preferences: list[str] = Field(default_factory=list)
    response_format: str = "markdown"  # markdown, plain, structured
    auto_execute: bool = False  # auto-execute tool calls without confirmation
    notification_level: str = "important"  # all, important, none
    custom: dict[str, Any] = Field(default_factory=dict)


class UserExpertise(BaseModel):
    """Track what the user knows to tailor explanations."""

    domain: str
    level: str = "intermediate"  # beginner, intermediate, advanced, expert
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    notes: str = ""


class InteractionPattern(BaseModel):
    """Learned patterns about how the user interacts."""

    most_used_agents: dict[str, int] = Field(default_factory=dict)
    most_used_tools: dict[str, int] = Field(default_factory=dict)
    common_intents: list[str] = Field(default_factory=list)
    active_hours: list[int] = Field(default_factory=list)  # hours of day
    avg_session_length_minutes: float = 0
    total_interactions: int = 0
    total_specs_created: int = 0


class UserProfile(BaseModel):
    """Complete user profile built over time.

    Inspired by Hermes Agent's user modeling system.
    Tracks preferences, expertise, and interaction patterns
    to personalize the assistant experience.
    """

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    email: str = ""
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    preferences: UserPreferences = Field(default_factory=UserPreferences)
    expertise: list[UserExpertise] = Field(default_factory=list)
    interaction_patterns: InteractionPattern = Field(
        default_factory=InteractionPattern
    )

    # Relationship to JARVIS
    soul_description: str = ""  # free-text personality description (like Hermes SOUL.md)
    goals: list[str] = Field(default_factory=list)

    def add_expertise(
        self, domain: str, level: str = "intermediate", notes: str = ""
    ) -> None:
        for exp in self.expertise:
            if exp.domain == domain:
                exp.level = level
                exp.notes = notes
                exp.last_updated = datetime.now(timezone.utc)
                self.updated_at = datetime.now(timezone.utc)
                return
        self.expertise.append(
            UserExpertise(domain=domain, level=level, notes=notes)
        )
        self.updated_at = datetime.now(timezone.utc)

    def record_interaction(
        self,
        agent_name: str = "",
        tool_name: str = "",
        intent: str = "",
    ) -> None:
        self.interaction_patterns.total_interactions += 1
        if agent_name:
            self.interaction_patterns.most_used_agents[agent_name] = (
                self.interaction_patterns.most_used_agents.get(agent_name, 0)
                + 1
            )
        if tool_name:
            self.interaction_patterns.most_used_tools[tool_name] = (
                self.interaction_patterns.most_used_tools.get(tool_name, 0) + 1
            )
        if intent and intent not in self.interaction_patterns.common_intents:
            self.interaction_patterns.common_intents.append(intent)
            if len(self.interaction_patterns.common_intents) > 50:
                self.interaction_patterns.common_intents = (
                    self.interaction_patterns.common_intents[-50:]
                )

        hour = datetime.now().hour
        if hour not in self.interaction_patterns.active_hours:
            self.interaction_patterns.active_hours.append(hour)

        self.updated_at = datetime.now(timezone.utc)

    def get_expertise_level(self, domain: str) -> str:
        for exp in self.expertise:
            if exp.domain == domain:
                return exp.level
        return "unknown"

    def to_context_string(self) -> str:
        """Format user profile as context for agent prompts."""
        lines = [f"# User Profile: {self.name or 'Default User'}"]
        if self.soul_description:
            lines.append(f"Description: {self.soul_description}")
        if self.preferences.language != "en":
            lines.append(f"Language: {self.preferences.language}")
        lines.append(
            f"Communication style: {self.preferences.communication_style}"
        )
        if self.preferences.code_language:
            lines.append(
                f"Preferred language: {self.preferences.code_language}"
            )
        if self.expertise:
            lines.append(
                "Expertise: "
                + ", ".join(
                    f"{e.domain} ({e.level})" for e in self.expertise[:5]
                )
            )
        if self.goals:
            lines.append("Goals: " + "; ".join(self.goals[:3]))
        return "\n".join(lines)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            self.model_dump_json(indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> UserProfile:
        path = Path(path)
        if not path.exists():
            return cls()
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
