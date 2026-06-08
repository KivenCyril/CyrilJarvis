"""Internationalization core for JARVIS.

Provides locale-based string loading with fallback, interpolation, and
lazy singleton initialization.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class I18n:
    """Internationalization support for JARVIS.

    Provides multi-language string management with:
    - Locale-based string loading
    - Fallback to default locale (en)
    - Interpolation support  ({key} placeholders)
    - Lazy loading of built-in string tables
    - Plugin extensibility via ``add_strings``
    """

    _instance: I18n | None = None
    _locale: str = "en"
    _strings: dict[str, dict[str, str]] = {}  # locale -> {key -> value}
    _fallback_locale: str = "en"
    _loaded: bool = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls) -> I18n:
        """Return the singleton I18n instance, creating it on first use."""
        if cls._instance is None:
            cls._instance = cls()
            cls._instance._load_builtins()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (mainly for testing)."""
        cls._instance = None
        cls._strings = {}
        cls._locale = "en"
        cls._loaded = False

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_builtins(self) -> None:
        """Load built-in string tables from the strings_*.py modules."""
        if self._loaded:
            return

        try:
            from jarvis.i18n.strings_en import STRINGS as en_strings
            self._strings["en"] = dict(en_strings)
        except ImportError:
            logger.warning("English string table not found")
            self._strings["en"] = {}

        try:
            from jarvis.i18n.strings_zh import STRINGS as zh_strings
            self._strings["zh"] = dict(zh_strings)
        except ImportError:
            logger.debug("Chinese string table not found")

        self._loaded = True

    def load_locale_file(self, locale: str, strings: dict[str, str]) -> None:
        """Load a complete string table for a locale, replacing any existing one."""
        self._strings[locale] = dict(strings)

    # ------------------------------------------------------------------
    # Translation
    # ------------------------------------------------------------------

    def t(self, key: str, **kwargs: Any) -> str:
        """Translate a key to the current locale with optional interpolation.

        Falls back to the fallback locale (en) if the key is not found in
        the current locale.  If the key is not found in any locale, returns
        the key itself.
        """
        # Look up in current locale, then fallback
        text = self._strings.get(self._locale, {}).get(key)
        if text is None:
            text = self._strings.get(self._fallback_locale, {}).get(key)
        if text is None:
            return key

        # Interpolate
        if kwargs:
            try:
                text = text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                pass
        return text

    def has_key(self, key: str, locale: str | None = None) -> bool:
        """Check whether a key exists in the given (or current) locale."""
        loc = locale or self._locale
        return key in self._strings.get(loc, {})

    # ------------------------------------------------------------------
    # Locale management
    # ------------------------------------------------------------------

    def set_locale(self, locale: str) -> None:
        """Set the active locale."""
        self._locale = locale

    def get_locale(self) -> str:
        """Return the current locale."""
        return self._locale

    def set_fallback_locale(self, locale: str) -> None:
        """Set the fallback locale (default: 'en')."""
        self._fallback_locale = locale

    def available_locales(self) -> list[str]:
        """Return a sorted list of loaded locale codes."""
        return sorted(self._strings.keys())

    # ------------------------------------------------------------------
    # Extensibility
    # ------------------------------------------------------------------

    def add_strings(self, locale: str, strings: dict[str, str]) -> None:
        """Merge additional strings into an existing locale table.

        Existing keys are overwritten.  Useful for plugins that want to
        contribute their own translated strings.
        """
        if locale not in self._strings:
            self._strings[locale] = {}
        self._strings[locale].update(strings)

    def remove_key(self, key: str, locale: str | None = None) -> bool:
        """Remove a single key from a locale table.  Returns True if removed."""
        loc = locale or self._locale
        table = self._strings.get(loc, {})
        if key in table:
            del table[key]
            return True
        return False

    def keys(self, locale: str | None = None) -> list[str]:
        """Return all keys in a locale table."""
        loc = locale or self._locale
        return sorted(self._strings.get(loc, {}).keys())

    def key_count(self, locale: str | None = None) -> int:
        """Return the number of keys in a locale table."""
        loc = locale or self._locale
        return len(self._strings.get(loc, {}))

    # ------------------------------------------------------------------
    # Coverage analysis
    # ------------------------------------------------------------------

    def missing_keys(self, locale: str) -> list[str]:
        """Return keys present in the fallback locale but missing in *locale*."""
        fallback_keys = set(self._strings.get(self._fallback_locale, {}).keys())
        locale_keys = set(self._strings.get(locale, {}).keys())
        return sorted(fallback_keys - locale_keys)

    def coverage(self, locale: str) -> float:
        """Return translation coverage as a fraction (0.0 to 1.0)."""
        fallback_count = len(self._strings.get(self._fallback_locale, {}))
        if fallback_count == 0:
            return 1.0
        locale_count = len(
            set(self._strings.get(locale, {}).keys())
            & set(self._strings.get(self._fallback_locale, {}).keys())
        )
        return locale_count / fallback_count


# ------------------------------------------------------------------
# Module-level convenience functions
# ------------------------------------------------------------------


def t(key: str, **kwargs: Any) -> str:
    """Translate a key using the global I18n instance."""
    return I18n.instance().t(key, **kwargs)


def set_locale(locale: str) -> None:
    """Set the active locale on the global I18n instance."""
    I18n.instance().set_locale(locale)


def get_locale() -> str:
    """Return the active locale from the global I18n instance."""
    return I18n.instance().get_locale()
