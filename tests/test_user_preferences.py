"""User preferences and profile tests.

Tests user profile management, preference storage, validation,
and serialization.
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# User Models
# ---------------------------------------------------------------------------

@dataclass
class UserProfile:
    id: str
    username: str
    display_name: str = ""
    email: str = ""
    avatar_url: str | None = None
    role: str = "user"
    created_at: str = ""
    last_login: str | None = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.datetime.utcnow().isoformat()
        if not self.display_name:
            self.display_name = self.username

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "display_name": self.display_name,
            "email": self.email,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }

    @property
    def initials(self) -> str:
        parts = self.display_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[1][0]).upper()
        return self.display_name[:2].upper()

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


@dataclass
class UserPreferences:
    theme: str = "dark"
    language: str = "en"
    timezone: str = "UTC"
    notifications_enabled: bool = True
    auto_execute_specs: bool = False
    default_agent: str | None = None
    page_size: int = 25
    show_debug_info: bool = False
    keyboard_shortcuts: bool = True
    compact_view: bool = False
    date_format: str = "YYYY-MM-DD"
    time_format: str = "24h"
    code_font_size: int = 14
    editor_theme: str = "monokai"
    auto_save: bool = True
    max_recent_specs: int = 10
    sidebar_collapsed: bool = False

    VALID_THEMES = {"dark", "light", "auto", "solarized", "nord"}
    VALID_LANGUAGES = {"en", "zh", "ja", "es", "fr", "de", "ko", "pt"}
    VALID_DATE_FORMATS = {"YYYY-MM-DD", "MM/DD/YYYY", "DD/MM/YYYY", "DD.MM.YYYY"}
    VALID_TIME_FORMATS = {"12h", "24h"}
    VALID_EDITOR_THEMES = {"monokai", "github", "dracula", "solarized", "nord", "one-dark"}

    def validate(self) -> tuple[bool, list[str]]:
        errors = []
        if self.theme not in self.VALID_THEMES:
            errors.append(f"Invalid theme: {self.theme}")
        if self.language not in self.VALID_LANGUAGES:
            errors.append(f"Invalid language: {self.language}")
        if self.date_format not in self.VALID_DATE_FORMATS:
            errors.append(f"Invalid date format: {self.date_format}")
        if self.time_format not in self.VALID_TIME_FORMATS:
            errors.append(f"Invalid time format: {self.time_format}")
        if self.editor_theme not in self.VALID_EDITOR_THEMES:
            errors.append(f"Invalid editor theme: {self.editor_theme}")
        if not (1 <= self.page_size <= 200):
            errors.append(f"Page size must be 1-200, got {self.page_size}")
        if not (8 <= self.code_font_size <= 32):
            errors.append(f"Font size must be 8-32, got {self.code_font_size}")
        if not (1 <= self.max_recent_specs <= 100):
            errors.append(f"Max recent specs must be 1-100, got {self.max_recent_specs}")
        return len(errors) == 0, errors

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key) and value is not None:
                setattr(self, key, value)

    def reset(self) -> None:
        default = UserPreferences()
        for field_name in vars(default):
            if not field_name.startswith("_") and not field_name.startswith("VALID"):
                setattr(self, field_name, getattr(default, field_name))

    def to_dict(self) -> dict:
        return {
            "theme": self.theme,
            "language": self.language,
            "timezone": self.timezone,
            "notifications_enabled": self.notifications_enabled,
            "auto_execute_specs": self.auto_execute_specs,
            "default_agent": self.default_agent,
            "page_size": self.page_size,
            "show_debug_info": self.show_debug_info,
            "keyboard_shortcuts": self.keyboard_shortcuts,
            "compact_view": self.compact_view,
            "date_format": self.date_format,
            "time_format": self.time_format,
            "code_font_size": self.code_font_size,
            "editor_theme": self.editor_theme,
            "auto_save": self.auto_save,
            "max_recent_specs": self.max_recent_specs,
            "sidebar_collapsed": self.sidebar_collapsed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UserPreferences":
        prefs = cls()
        for key, value in data.items():
            if hasattr(prefs, key):
                setattr(prefs, key, value)
        return prefs


# ---------------------------------------------------------------------------
# Tests: UserProfile
# ---------------------------------------------------------------------------

class TestUserProfile:
    def test_create_profile(self):
        p = UserProfile(id="u1", username="alice")
        assert p.username == "alice"
        assert p.display_name == "alice"
        assert p.role == "user"
        assert p.created_at != ""

    def test_custom_display_name(self):
        p = UserProfile(id="u1", username="alice", display_name="Alice Smith")
        assert p.display_name == "Alice Smith"

    def test_initials_two_words(self):
        p = UserProfile(id="u1", username="alice", display_name="Alice Smith")
        assert p.initials == "AS"

    def test_initials_one_word(self):
        p = UserProfile(id="u1", username="alice")
        assert p.initials == "AL"

    def test_is_admin(self):
        p = UserProfile(id="u1", username="admin", role="admin")
        assert p.is_admin is True

    def test_is_not_admin(self):
        p = UserProfile(id="u1", username="user", role="user")
        assert p.is_admin is False

    def test_update_profile(self):
        p = UserProfile(id="u1", username="alice")
        p.update(display_name="Alice Updated", email="alice@test.com")
        assert p.display_name == "Alice Updated"
        assert p.email == "alice@test.com"

    def test_update_ignores_none(self):
        p = UserProfile(id="u1", username="alice", email="old@test.com")
        p.update(email=None)
        assert p.email == "old@test.com"

    def test_to_dict(self):
        p = UserProfile(id="u1", username="alice", email="alice@test.com")
        d = p.to_dict()
        assert d["id"] == "u1"
        assert d["username"] == "alice"
        assert d["email"] == "alice@test.com"

    def test_serialization(self):
        p = UserProfile(id="u1", username="alice")
        j = json.dumps(p.to_dict())
        restored = json.loads(j)
        assert restored["username"] == "alice"

    def test_avatar_url(self):
        p = UserProfile(id="u1", username="alice", avatar_url="https://example.com/avatar.png")
        assert p.avatar_url == "https://example.com/avatar.png"

    def test_metadata(self):
        p = UserProfile(id="u1", username="alice", metadata={"source": "github"})
        assert p.metadata["source"] == "github"


# ---------------------------------------------------------------------------
# Tests: UserPreferences
# ---------------------------------------------------------------------------

class TestUserPreferences:
    def test_defaults(self):
        prefs = UserPreferences()
        assert prefs.theme == "dark"
        assert prefs.language == "en"
        assert prefs.page_size == 25
        assert prefs.notifications_enabled is True

    def test_validate_defaults(self):
        prefs = UserPreferences()
        valid, errors = prefs.validate()
        assert valid is True
        assert errors == []

    def test_validate_invalid_theme(self):
        prefs = UserPreferences(theme="neon")
        valid, errors = prefs.validate()
        assert valid is False
        assert any("theme" in e for e in errors)

    def test_validate_invalid_language(self):
        prefs = UserPreferences(language="xx")
        valid, errors = prefs.validate()
        assert valid is False

    def test_validate_invalid_page_size(self):
        prefs = UserPreferences(page_size=0)
        valid, errors = prefs.validate()
        assert valid is False

    def test_validate_invalid_font_size(self):
        prefs = UserPreferences(code_font_size=100)
        valid, errors = prefs.validate()
        assert valid is False

    def test_validate_invalid_date_format(self):
        prefs = UserPreferences(date_format="INVALID")
        valid, errors = prefs.validate()
        assert valid is False

    def test_validate_invalid_time_format(self):
        prefs = UserPreferences(time_format="36h")
        valid, errors = prefs.validate()
        assert valid is False

    def test_validate_invalid_editor_theme(self):
        prefs = UserPreferences(editor_theme="invalid")
        valid, errors = prefs.validate()
        assert valid is False

    def test_validate_max_recent_specs(self):
        prefs = UserPreferences(max_recent_specs=0)
        valid, errors = prefs.validate()
        assert valid is False

    def test_update(self):
        prefs = UserPreferences()
        prefs.update(theme="light", language="zh")
        assert prefs.theme == "light"
        assert prefs.language == "zh"

    def test_update_ignores_none(self):
        prefs = UserPreferences()
        prefs.update(theme=None)
        assert prefs.theme == "dark"

    def test_reset(self):
        prefs = UserPreferences(theme="light", language="zh", page_size=100)
        prefs.reset()
        assert prefs.theme == "dark"
        assert prefs.language == "en"
        assert prefs.page_size == 25

    def test_to_dict(self):
        prefs = UserPreferences()
        d = prefs.to_dict()
        assert "theme" in d
        assert "language" in d
        assert "page_size" in d
        assert len(d) >= 15

    def test_from_dict(self):
        data = {"theme": "light", "language": "ja", "page_size": 50}
        prefs = UserPreferences.from_dict(data)
        assert prefs.theme == "light"
        assert prefs.language == "ja"
        assert prefs.page_size == 50

    def test_from_dict_ignores_unknown(self):
        data = {"theme": "dark", "unknown_field": "value"}
        prefs = UserPreferences.from_dict(data)
        assert prefs.theme == "dark"

    def test_serialization_roundtrip(self):
        prefs = UserPreferences(
            theme="solarized",
            language="zh",
            page_size=50,
            compact_view=True,
            editor_theme="dracula",
        )
        j = json.dumps(prefs.to_dict())
        restored = UserPreferences.from_dict(json.loads(j))
        assert restored.theme == "solarized"
        assert restored.language == "zh"
        assert restored.compact_view is True

    def test_all_valid_themes(self):
        for theme in UserPreferences.VALID_THEMES:
            prefs = UserPreferences(theme=theme)
            valid, _ = prefs.validate()
            assert valid is True

    def test_all_valid_languages(self):
        for lang in UserPreferences.VALID_LANGUAGES:
            prefs = UserPreferences(language=lang)
            valid, _ = prefs.validate()
            assert valid is True

    def test_boolean_preferences(self):
        prefs = UserPreferences(
            notifications_enabled=False,
            auto_execute_specs=True,
            show_debug_info=True,
            keyboard_shortcuts=False,
            compact_view=True,
            auto_save=False,
            sidebar_collapsed=True,
        )
        assert prefs.notifications_enabled is False
        assert prefs.auto_execute_specs is True
        assert prefs.show_debug_info is True
        assert prefs.keyboard_shortcuts is False
        assert prefs.compact_view is True
        assert prefs.auto_save is False
        assert prefs.sidebar_collapsed is True

    def test_default_agent(self):
        prefs = UserPreferences(default_agent="code-agent")
        assert prefs.default_agent == "code-agent"
