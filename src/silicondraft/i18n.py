"""gettext translations for CLI and engine messages.

The engine stays Qt-free (ADR-0003): CLI and engine messages use gettext, while
the GUI uses Qt ``.ts``/``.qm`` catalogs. A process installs one catalog at a
time; the GUI language switch installs the same catalog so validation messages
shown in the GUI match the selected language.
"""

from __future__ import annotations

import gettext
from pathlib import Path

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "zh_CN")

_LOCALE_DIR = Path(__file__).parent / "locale"
_DOMAIN = "silicondraft"

_translation: gettext.NullTranslations = gettext.NullTranslations()


def normalize_language(language: str) -> str | None:
    """Map a user-facing language code onto a supported code, or ``None``."""
    normalized = language.strip().replace("-", "_").lower()
    if normalized == "en":
        return "en"
    if normalized in {"zh", "zh_cn"}:
        return "zh_CN"
    return None


def install(language: str) -> bool:
    """Install the gettext catalog for ``language``.

    Returns ``False`` for an unsupported language or a missing catalog, in
    which case messages fall back to their English source strings.
    """
    global _translation
    normalized = normalize_language(language)
    if normalized is None:
        return False
    if normalized == DEFAULT_LANGUAGE:
        _translation = gettext.NullTranslations()
        return True
    try:
        _translation = gettext.translation(
            _DOMAIN,
            localedir=str(_LOCALE_DIR),
            languages=[normalized],
        )
    except OSError:
        _translation = gettext.NullTranslations()
        return False
    return True


def reset() -> None:
    """Return to the untranslated English source strings."""
    install(DEFAULT_LANGUAGE)


def _(message: str) -> str:
    """Translate one gettext message id."""
    return _translation.gettext(message)


__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "_",
    "install",
    "normalize_language",
    "reset",
]
