"""Tests for the i18n package."""

from __future__ import annotations

import pytest

from jarvis.i18n.core import I18n, get_locale, set_locale, t


@pytest.fixture(autouse=True)
def _reset_i18n():
    """Reset I18n singleton before each test."""
    I18n.reset()
    yield
    I18n.reset()


# ── I18n singleton ─────────────────────────────────────────────────────


class TestI18nSingleton:
    def test_instance_returns_same_object(self):
        a = I18n.instance()
        b = I18n.instance()
        assert a is b

    def test_reset_clears_instance(self):
        a = I18n.instance()
        I18n.reset()
        b = I18n.instance()
        assert a is not b

    def test_default_locale_is_en(self):
        i = I18n.instance()
        assert i.get_locale() == "en"


# ── Translation (t) ───────────────────────────────────────────────────


class TestTranslation:
    def test_basic_key(self):
        result = I18n.instance().t("system.name")
        assert result == "JARVIS"

    def test_interpolation(self):
        result = I18n.instance().t(
            "system.ready", agent_count=10, tool_count=25
        )
        assert "10" in result
        assert "25" in result

    def test_missing_key_returns_key(self):
        result = I18n.instance().t("nonexistent.key")
        assert result == "nonexistent.key"

    def test_fallback_to_en(self):
        i = I18n.instance()
        i.set_locale("ja")  # Japanese has no strings loaded
        result = i.t("system.name")
        assert result == "JARVIS"  # Falls back to English

    def test_partial_interpolation_no_crash(self):
        # If kwargs are missing, the template should not crash
        result = I18n.instance().t("system.ready", agent_count=5)
        # Should still contain agent_count but not crash on missing tool_count
        assert isinstance(result, str)

    def test_chinese_translation(self):
        i = I18n.instance()
        i.set_locale("zh")
        result = i.t("system.goodbye")
        assert result != "system.goodbye"
        assert result != "Goodbye!"  # Should be Chinese


# ── Locale management ─────────────────────────────────────────────────


class TestLocaleManagement:
    def test_set_and_get_locale(self):
        i = I18n.instance()
        i.set_locale("zh")
        assert i.get_locale() == "zh"

    def test_available_locales(self):
        i = I18n.instance()
        locales = i.available_locales()
        assert "en" in locales
        assert "zh" in locales
        # Should be sorted
        assert locales == sorted(locales)

    def test_set_fallback_locale(self):
        i = I18n.instance()
        i.set_fallback_locale("zh")
        # Now if we set locale to something without strings, should fallback to zh
        i.set_locale("fr")
        result = i.t("system.goodbye")
        assert result != "system.goodbye"  # Should get Chinese


# ── String management ──────────────────────────────────────────────────


class TestStringManagement:
    def test_add_strings(self):
        i = I18n.instance()
        i.add_strings("en", {"custom.key": "Custom Value"})
        assert i.t("custom.key") == "Custom Value"

    def test_add_strings_new_locale(self):
        i = I18n.instance()
        i.add_strings("fr", {"system.name": "JARVIS", "greeting": "Bonjour"})
        i.set_locale("fr")
        assert i.t("greeting") == "Bonjour"

    def test_add_strings_overwrite(self):
        i = I18n.instance()
        original = i.t("system.name")
        i.add_strings("en", {"system.name": "J.A.R.V.I.S."})
        assert i.t("system.name") == "J.A.R.V.I.S."
        # restore
        i.add_strings("en", {"system.name": original})

    def test_has_key(self):
        i = I18n.instance()
        assert i.has_key("system.name")
        assert not i.has_key("nonexistent")

    def test_has_key_specific_locale(self):
        i = I18n.instance()
        assert i.has_key("system.name", locale="zh")
        assert not i.has_key("system.name", locale="fr")

    def test_remove_key(self):
        i = I18n.instance()
        i.add_strings("en", {"temp.key": "temporary"})
        assert i.has_key("temp.key")
        assert i.remove_key("temp.key")
        assert not i.has_key("temp.key")

    def test_remove_key_nonexistent(self):
        i = I18n.instance()
        assert not i.remove_key("does.not.exist")

    def test_keys(self):
        i = I18n.instance()
        keys = i.keys()
        assert isinstance(keys, list)
        assert len(keys) > 50  # we have 100+ keys
        assert "system.name" in keys
        assert keys == sorted(keys)

    def test_key_count(self):
        i = I18n.instance()
        count = i.key_count()
        assert count > 50


# ── Coverage analysis ──────────────────────────────────────────────────


class TestCoverageAnalysis:
    def test_coverage_en_is_full(self):
        i = I18n.instance()
        assert i.coverage("en") == pytest.approx(1.0)

    def test_coverage_zh_is_high(self):
        i = I18n.instance()
        cov = i.coverage("zh")
        assert cov >= 0.9  # Chinese should cover most English keys

    def test_coverage_unknown_locale_is_zero(self):
        i = I18n.instance()
        cov = i.coverage("xx")
        assert cov == pytest.approx(0.0)

    def test_missing_keys(self):
        i = I18n.instance()
        missing = i.missing_keys("en")
        assert missing == []  # English is the fallback; nothing should be missing

    def test_missing_keys_unknown_locale(self):
        i = I18n.instance()
        missing = i.missing_keys("xx")
        assert len(missing) > 50  # All English keys should be missing


# ── Module-level convenience functions ─────────────────────────────────


class TestConvenienceFunctions:
    def test_t_function(self):
        assert t("system.name") == "JARVIS"

    def test_t_with_interpolation(self):
        result = t("agent.registered", name="code")
        assert "code" in result

    def test_set_and_get_locale_functions(self):
        set_locale("zh")
        assert get_locale() == "zh"
        set_locale("en")
        assert get_locale() == "en"
