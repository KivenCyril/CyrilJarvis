"""Advanced tests for the JARVIS user modeling subsystem.

Covers UserProfile expertise tracking, interaction patterns,
UserModeler language inference and domain inference, profile context
string generation, save/load roundtrip, preferences defaults/overrides,
interaction recording statistics, active hours tracking, and common
intents capping.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jarvis.user.modeler import UserModeler
from jarvis.user.profile import (
    InteractionPattern,
    UserExpertise,
    UserPreferences,
    UserProfile,
)


# ===========================================================================
# 1. UserProfile expertise tracking
# ===========================================================================


class TestUserExpertiseTracking:
    def test_add_new_expertise(self):
        profile = UserProfile()
        profile.add_expertise("python", "advanced", "Very experienced")
        assert len(profile.expertise) == 1
        assert profile.expertise[0].domain == "python"
        assert profile.expertise[0].level == "advanced"
        assert profile.expertise[0].notes == "Very experienced"

    def test_update_existing_expertise(self):
        profile = UserProfile()
        profile.add_expertise("python", "intermediate")
        profile.add_expertise("python", "expert", "Upgraded")
        assert len(profile.expertise) == 1
        assert profile.expertise[0].level == "expert"
        assert profile.expertise[0].notes == "Upgraded"

    def test_multiple_expertise_domains(self):
        profile = UserProfile()
        profile.add_expertise("python", "advanced")
        profile.add_expertise("javascript", "intermediate")
        profile.add_expertise("devops", "beginner")
        assert len(profile.expertise) == 3

    def test_get_expertise_level(self):
        profile = UserProfile()
        profile.add_expertise("python", "expert")
        assert profile.get_expertise_level("python") == "expert"
        assert profile.get_expertise_level("unknown_domain") == "unknown"

    def test_expertise_updates_timestamp(self):
        profile = UserProfile()
        initial_updated = profile.updated_at
        profile.add_expertise("rust", "beginner")
        assert profile.updated_at >= initial_updated


# ===========================================================================
# 2. UserProfile interaction patterns
# ===========================================================================


class TestInteractionPatterns:
    def test_record_agent_usage(self):
        profile = UserProfile()
        profile.record_interaction(agent_name="code-agent")
        profile.record_interaction(agent_name="code-agent")
        profile.record_interaction(agent_name="data-agent")
        assert profile.interaction_patterns.most_used_agents["code-agent"] == 2
        assert profile.interaction_patterns.most_used_agents["data-agent"] == 1

    def test_record_tool_usage(self):
        profile = UserProfile()
        profile.record_interaction(tool_name="search")
        profile.record_interaction(tool_name="search")
        profile.record_interaction(tool_name="git")
        assert profile.interaction_patterns.most_used_tools["search"] == 2
        assert profile.interaction_patterns.most_used_tools["git"] == 1

    def test_total_interactions_counter(self):
        profile = UserProfile()
        for _ in range(5):
            profile.record_interaction(agent_name="x")
        assert profile.interaction_patterns.total_interactions == 5

    def test_record_intent(self):
        profile = UserProfile()
        profile.record_interaction(intent="code review")
        profile.record_interaction(intent="debug")
        assert "code review" in profile.interaction_patterns.common_intents
        assert "debug" in profile.interaction_patterns.common_intents

    def test_duplicate_intent_not_added(self):
        profile = UserProfile()
        profile.record_interaction(intent="deploy")
        profile.record_interaction(intent="deploy")
        assert profile.interaction_patterns.common_intents.count("deploy") == 1

    def test_empty_interaction_no_error(self):
        profile = UserProfile()
        profile.record_interaction()  # no args
        assert profile.interaction_patterns.total_interactions == 1


# ===========================================================================
# 3. UserModeler language inference
# ===========================================================================


class TestLanguageInference:
    @pytest.mark.asyncio
    async def test_infer_python(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "How do I use FastAPI for my project?")
        assert modeler.profile.preferences.code_language == "python"

    @pytest.mark.asyncio
    async def test_infer_javascript(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "I need help with React components")
        assert modeler.profile.preferences.code_language == "javascript"

    @pytest.mark.asyncio
    async def test_infer_go(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "My golang service has a bug")
        assert modeler.profile.preferences.code_language == "go"

    @pytest.mark.asyncio
    async def test_infer_rust(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "Help me with my rust and tokio async runtime")
        assert modeler.profile.preferences.code_language == "rust"

    @pytest.mark.asyncio
    async def test_infer_java(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "My spring boot app needs maven dependency")
        assert modeler.profile.preferences.code_language == "java"

    @pytest.mark.asyncio
    async def test_no_inference_on_generic_message(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "Hello, I need help")
        assert modeler.profile.preferences.code_language == ""

    @pytest.mark.asyncio
    async def test_first_language_wins(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "I use python with pandas")
        await modeler.on_interaction("code-agent", "Also some react work")
        assert modeler.profile.preferences.code_language == "python"


# ===========================================================================
# 4. UserModeler domain inference
# ===========================================================================


class TestDomainInference:
    @pytest.mark.asyncio
    async def test_infer_backend_domain(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "I need to build a REST API endpoint")
        assert modeler.profile.get_expertise_level("backend") == "intermediate"

    @pytest.mark.asyncio
    async def test_infer_frontend_domain(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "Fix the CSS styles on the frontend component")
        assert modeler.profile.get_expertise_level("frontend") == "intermediate"

    @pytest.mark.asyncio
    async def test_infer_devops_domain(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("devops-agent", "Help me set up kubernetes deployment")
        assert modeler.profile.get_expertise_level("devops") == "intermediate"

    @pytest.mark.asyncio
    async def test_infer_data_domain(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("data-agent", "Analyze this data with pandas")
        assert modeler.profile.get_expertise_level("data") == "intermediate"

    @pytest.mark.asyncio
    async def test_infer_security_domain(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("security-agent", "Run OWASP vulnerability scan")
        assert modeler.profile.get_expertise_level("security") == "intermediate"

    @pytest.mark.asyncio
    async def test_multiple_domains_inferred(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "Build API endpoint for backend")
        await modeler.on_interaction("code-agent", "Fix the react component in frontend")
        assert modeler.profile.get_expertise_level("backend") == "intermediate"
        assert modeler.profile.get_expertise_level("frontend") == "intermediate"

    @pytest.mark.asyncio
    async def test_existing_expertise_not_overwritten(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        modeler.profile.add_expertise("backend", "expert")
        await modeler.on_interaction("code-agent", "Build API endpoint for backend")
        # Should remain expert, not overwritten to intermediate
        assert modeler.profile.get_expertise_level("backend") == "expert"


# ===========================================================================
# 5. Profile context string generation
# ===========================================================================


class TestContextStringGeneration:
    def test_minimal_profile(self):
        profile = UserProfile()
        ctx = profile.to_context_string()
        assert "User Profile" in ctx
        assert "Communication style" in ctx

    def test_full_profile(self):
        profile = UserProfile(
            name="Alice",
            soul_description="A senior engineer",
        )
        profile.preferences.language = "zh"
        profile.preferences.code_language = "python"
        profile.preferences.communication_style = "detailed"
        profile.add_expertise("backend", "expert")
        profile.goals = ["build JARVIS", "learn rust"]

        ctx = profile.to_context_string()
        assert "Alice" in ctx
        assert "senior engineer" in ctx
        assert "zh" in ctx
        assert "python" in ctx
        assert "backend" in ctx
        assert "build JARVIS" in ctx

    def test_expertise_limited_to_five(self):
        profile = UserProfile()
        for i in range(10):
            profile.add_expertise(f"domain{i}", "intermediate")
        ctx = profile.to_context_string()
        # Should only show first 5
        assert "domain0" in ctx
        assert "domain4" in ctx

    def test_goals_limited_to_three(self):
        profile = UserProfile()
        profile.goals = [f"goal{i}" for i in range(10)]
        ctx = profile.to_context_string()
        assert "goal0" in ctx
        assert "goal2" in ctx


# ===========================================================================
# 6. Profile save/load roundtrip
# ===========================================================================


class TestSaveLoadRoundtrip:
    def test_save_and_load(self, tmp_path: Path):
        profile = UserProfile(name="Bob", email="bob@example.com")
        profile.add_expertise("python", "advanced")
        profile.preferences.code_language = "python"
        profile.goals = ["ship v1"]

        path = tmp_path / "profile.json"
        profile.save(path)

        loaded = UserProfile.load(path)
        assert loaded.name == "Bob"
        assert loaded.email == "bob@example.com"
        assert loaded.get_expertise_level("python") == "advanced"
        assert loaded.preferences.code_language == "python"
        assert "ship v1" in loaded.goals

    def test_load_nonexistent_returns_default(self, tmp_path: Path):
        profile = UserProfile.load(tmp_path / "missing.json")
        assert profile.name == ""
        assert len(profile.expertise) == 0

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        profile = UserProfile(name="Eve")
        path = tmp_path / "deep" / "nested" / "profile.json"
        profile.save(path)
        assert path.exists()

    def test_roundtrip_preserves_interactions(self, tmp_path: Path):
        profile = UserProfile()
        profile.record_interaction(agent_name="code-agent")
        profile.record_interaction(tool_name="search")

        path = tmp_path / "profile.json"
        profile.save(path)
        loaded = UserProfile.load(path)
        assert loaded.interaction_patterns.most_used_agents["code-agent"] == 1
        assert loaded.interaction_patterns.most_used_tools["search"] == 1


# ===========================================================================
# 7. Preferences defaults and overrides
# ===========================================================================


class TestPreferencesDefaults:
    def test_default_values(self):
        prefs = UserPreferences()
        assert prefs.language == "en"
        assert prefs.timezone == "UTC"
        assert prefs.communication_style == "concise"
        assert prefs.code_language == ""
        assert prefs.response_format == "markdown"
        assert prefs.auto_execute is False
        assert prefs.notification_level == "important"
        assert prefs.custom == {}

    def test_custom_overrides(self):
        prefs = UserPreferences(
            language="zh",
            communication_style="detailed",
            code_language="rust",
            auto_execute=True,
            custom={"theme": "dark"},
        )
        assert prefs.language == "zh"
        assert prefs.communication_style == "detailed"
        assert prefs.code_language == "rust"
        assert prefs.auto_execute is True
        assert prefs.custom["theme"] == "dark"

    def test_framework_preferences(self):
        prefs = UserPreferences(framework_preferences=["FastAPI", "React"])
        assert len(prefs.framework_preferences) == 2


# ===========================================================================
# 8. Interaction recording statistics
# ===========================================================================


class TestInteractionStats:
    def test_interaction_count_accurate(self):
        profile = UserProfile()
        for i in range(100):
            profile.record_interaction(agent_name="agent")
        assert profile.interaction_patterns.total_interactions == 100

    def test_multiple_agents_tracked(self):
        profile = UserProfile()
        for _ in range(10):
            profile.record_interaction(agent_name="code-agent")
        for _ in range(5):
            profile.record_interaction(agent_name="data-agent")
        agents = profile.interaction_patterns.most_used_agents
        assert agents["code-agent"] == 10
        assert agents["data-agent"] == 5

    def test_multiple_tools_tracked(self):
        profile = UserProfile()
        for _ in range(3):
            profile.record_interaction(tool_name="git")
        for _ in range(7):
            profile.record_interaction(tool_name="search")
        tools = profile.interaction_patterns.most_used_tools
        assert tools["git"] == 3
        assert tools["search"] == 7


# ===========================================================================
# 9. Active hours tracking
# ===========================================================================


class TestActiveHoursTracking:
    def test_hour_recorded(self):
        profile = UserProfile()
        profile.record_interaction(agent_name="x")
        # Current hour should be in active_hours
        from datetime import datetime
        current_hour = datetime.now().hour
        assert current_hour in profile.interaction_patterns.active_hours

    def test_duplicate_hours_not_added(self):
        profile = UserProfile()
        for _ in range(10):
            profile.record_interaction(agent_name="x")
        hours = profile.interaction_patterns.active_hours
        # Current hour should appear only once
        from datetime import datetime
        current_hour = datetime.now().hour
        assert hours.count(current_hour) == 1


# ===========================================================================
# 10. Common intents capping
# ===========================================================================


class TestCommonIntentsCapping:
    def test_intents_capped_at_50(self):
        profile = UserProfile()
        for i in range(60):
            profile.record_interaction(intent=f"intent_{i}")
        assert len(profile.interaction_patterns.common_intents) == 50

    def test_latest_intents_kept(self):
        profile = UserProfile()
        for i in range(60):
            profile.record_interaction(intent=f"intent_{i}")
        intents = profile.interaction_patterns.common_intents
        # Last 50 should be kept (intent_10 through intent_59)
        assert "intent_59" in intents
        assert "intent_10" in intents


# ===========================================================================
# 11. UserModeler save/load
# ===========================================================================


class TestUserModelerSaveLoad:
    @pytest.mark.asyncio
    async def test_modeler_saves_on_interaction(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        await modeler.on_interaction("code-agent", "Use python with flask")
        profile_path = tmp_path / "user" / "profile.json"
        assert profile_path.exists()

    def test_modeler_load(self, tmp_path: Path):
        # Create a profile manually
        profile = UserProfile(name="TestUser")
        profile.add_expertise("python", "expert")
        profile_dir = tmp_path / "user"
        profile_dir.mkdir(parents=True)
        profile.save(profile_dir / "profile.json")

        modeler = UserModeler(storage_path=str(profile_dir))
        modeler.load()
        assert modeler.profile.name == "TestUser"
        assert modeler.profile.get_expertise_level("python") == "expert"

    def test_get_context_for_agent(self, tmp_path: Path):
        modeler = UserModeler(storage_path=str(tmp_path / "user"))
        modeler.profile.name = "Alice"
        ctx = modeler.get_context_for_agent("code-agent")
        assert "Alice" in ctx


# ===========================================================================
# 12. UserExpertise model
# ===========================================================================


class TestUserExpertiseModel:
    def test_defaults(self):
        exp = UserExpertise(domain="python")
        assert exp.level == "intermediate"
        assert exp.notes == ""
        assert exp.last_updated is not None

    def test_custom_values(self):
        exp = UserExpertise(
            domain="rust",
            level="beginner",
            notes="Just started",
        )
        assert exp.domain == "rust"
        assert exp.level == "beginner"


# ===========================================================================
# 13. InteractionPattern model
# ===========================================================================


class TestInteractionPatternModel:
    def test_defaults(self):
        pattern = InteractionPattern()
        assert pattern.most_used_agents == {}
        assert pattern.most_used_tools == {}
        assert pattern.common_intents == []
        assert pattern.active_hours == []
        assert pattern.total_interactions == 0
        assert pattern.total_specs_created == 0

    def test_avg_session_length(self):
        pattern = InteractionPattern(avg_session_length_minutes=15.5)
        assert pattern.avg_session_length_minutes == 15.5
