"""Tests for the user modeling system."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from jarvis.user.profile import (
    InteractionPattern,
    UserExpertise,
    UserPreferences,
    UserProfile,
)
from jarvis.user.modeler import UserModeler


# ---------------------------------------------------------------------------
# UserPreferences
# ---------------------------------------------------------------------------

class TestUserPreferences:
    def test_defaults(self):
        prefs = UserPreferences()
        assert prefs.language == "en"
        assert prefs.timezone == "UTC"
        assert prefs.communication_style == "concise"
        assert prefs.code_language == ""
        assert prefs.framework_preferences == []
        assert prefs.response_format == "markdown"
        assert prefs.auto_execute is False
        assert prefs.notification_level == "important"
        assert prefs.custom == {}

    def test_custom_values(self):
        prefs = UserPreferences(
            language="zh",
            communication_style="detailed",
            code_language="python",
            auto_execute=True,
            custom={"theme": "dark"},
        )
        assert prefs.language == "zh"
        assert prefs.communication_style == "detailed"
        assert prefs.code_language == "python"
        assert prefs.auto_execute is True
        assert prefs.custom["theme"] == "dark"


# ---------------------------------------------------------------------------
# UserProfile
# ---------------------------------------------------------------------------

class TestUserProfile:
    def test_creation(self):
        profile = UserProfile(name="Alice", email="alice@example.com")
        assert profile.name == "Alice"
        assert profile.email == "alice@example.com"
        assert len(profile.id) == 12
        assert profile.created_at is not None
        assert profile.updated_at is not None

    def test_add_expertise_new(self):
        profile = UserProfile()
        profile.add_expertise("backend", "advanced", "REST APIs")
        assert len(profile.expertise) == 1
        assert profile.expertise[0].domain == "backend"
        assert profile.expertise[0].level == "advanced"
        assert profile.expertise[0].notes == "REST APIs"

    def test_add_expertise_update(self):
        profile = UserProfile()
        profile.add_expertise("backend", "intermediate")
        profile.add_expertise("backend", "expert", "Promoted")
        assert len(profile.expertise) == 1
        assert profile.expertise[0].level == "expert"
        assert profile.expertise[0].notes == "Promoted"

    def test_get_expertise_level(self):
        profile = UserProfile()
        assert profile.get_expertise_level("frontend") == "unknown"
        profile.add_expertise("frontend", "beginner")
        assert profile.get_expertise_level("frontend") == "beginner"

    def test_record_interaction(self):
        profile = UserProfile()
        profile.record_interaction(agent_name="coder", tool_name="shell", intent="debug")
        assert profile.interaction_patterns.total_interactions == 1
        assert profile.interaction_patterns.most_used_agents["coder"] == 1
        assert profile.interaction_patterns.most_used_tools["shell"] == 1
        assert "debug" in profile.interaction_patterns.common_intents

    def test_record_interaction_accumulates(self):
        profile = UserProfile()
        profile.record_interaction(agent_name="coder")
        profile.record_interaction(agent_name="coder")
        profile.record_interaction(agent_name="planner")
        assert profile.interaction_patterns.most_used_agents["coder"] == 2
        assert profile.interaction_patterns.most_used_agents["planner"] == 1
        assert profile.interaction_patterns.total_interactions == 3

    def test_record_interaction_caps_intents(self):
        profile = UserProfile()
        for i in range(60):
            profile.record_interaction(intent=f"intent_{i}")
        assert len(profile.interaction_patterns.common_intents) == 50

    def test_to_context_string_basic(self):
        profile = UserProfile(name="Bob")
        ctx = profile.to_context_string()
        assert "Bob" in ctx
        assert "Communication style: concise" in ctx

    def test_to_context_string_rich(self):
        profile = UserProfile(
            name="Carol",
            soul_description="Loves clean code",
            goals=["Ship v1", "Learn Rust"],
        )
        profile.preferences.language = "zh"
        profile.preferences.code_language = "python"
        profile.add_expertise("backend", "expert")
        ctx = profile.to_context_string()
        assert "Carol" in ctx
        assert "Loves clean code" in ctx
        assert "Language: zh" in ctx
        assert "Preferred language: python" in ctx
        assert "backend (expert)" in ctx
        assert "Ship v1" in ctx

    def test_serialization_roundtrip(self):
        profile = UserProfile(name="Dave", email="dave@x.com")
        profile.add_expertise("frontend", "advanced")
        profile.record_interaction(agent_name="coder", intent="build")
        data = profile.model_dump_json()
        restored = UserProfile.model_validate_json(data)
        assert restored.name == "Dave"
        assert restored.email == "dave@x.com"
        assert len(restored.expertise) == 1
        assert restored.interaction_patterns.total_interactions == 1

    def test_save_load_roundtrip(self, tmp_path: Path):
        profile = UserProfile(name="Eve")
        profile.add_expertise("security", "expert")
        profile.record_interaction(agent_name="scanner")

        file_path = tmp_path / "profile.json"
        profile.save(file_path)

        assert file_path.exists()
        loaded = UserProfile.load(file_path)
        assert loaded.name == "Eve"
        assert loaded.get_expertise_level("security") == "expert"
        assert loaded.interaction_patterns.most_used_agents["scanner"] == 1

    def test_load_missing_file(self, tmp_path: Path):
        profile = UserProfile.load(tmp_path / "nonexistent.json")
        assert isinstance(profile, UserProfile)
        assert profile.name == ""


# ---------------------------------------------------------------------------
# UserModeler
# ---------------------------------------------------------------------------

class TestUserModeler:
    def test_infer_python(self):
        modeler = UserModeler()
        modeler._infer_from_message("I want to build a FastAPI server")
        assert modeler.profile.preferences.code_language == "python"

    def test_infer_javascript(self):
        modeler = UserModeler()
        modeler._infer_from_message("Set up a React component with npm")
        assert modeler.profile.preferences.code_language == "javascript"

    def test_infer_does_not_overwrite(self):
        profile = UserProfile()
        profile.preferences.code_language = "rust"
        modeler = UserModeler(profile=profile)
        modeler._infer_from_message("I also use python sometimes")
        assert modeler.profile.preferences.code_language == "rust"

    def test_infer_expertise_domain(self):
        modeler = UserModeler()
        modeler._infer_from_message("Deploy with docker and k8s")
        assert modeler.profile.get_expertise_level("devops") == "intermediate"

    @pytest.mark.asyncio
    async def test_on_interaction(self):
        modeler = UserModeler()
        await modeler.on_interaction("coder", "Write a python script", "shell")
        assert modeler.profile.interaction_patterns.total_interactions == 1
        assert modeler.profile.preferences.code_language == "python"

    def test_get_context_for_agent(self):
        profile = UserProfile(name="Test")
        modeler = UserModeler(profile=profile)
        ctx = modeler.get_context_for_agent("coder")
        assert "Test" in ctx

    def test_save_load(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path))
        modeler._profile.name = "Saved"
        modeler.save()

        modeler2 = UserModeler(storage_path=str(tmp_path))
        modeler2.load()
        assert modeler2.profile.name == "Saved"
