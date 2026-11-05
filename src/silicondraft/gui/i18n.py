"""GUI translation loading, live switching, and persistence.

The GUI follows ADR-0003: user-visible strings go through Qt ``tr()`` and are
translated by ``.ts``/``.qm`` catalogs, while the engine's gettext catalog is
installed alongside so validation messages match the selected language.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QObject, QSettings, QTranslator, Signal
from PySide6.QtWidgets import QApplication

from ..i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, normalize_language
from ..i18n import install as install_engine_translation

LANGUAGE_LABELS: dict[str, str] = {"en": "English", "zh_CN": "中文"}
LANGUAGE_SETTINGS_KEY = "ui/language"

_TRANSLATIONS_DIR = Path(__file__).parent / "translations"


def language_label(language: str) -> str:
    """The native name shown in the language menu."""
    return LANGUAGE_LABELS.get(language, language)


def load_language(settings: QSettings) -> str:
    """The persisted language, falling back to English when absent or unknown."""
    stored = str(settings.value(LANGUAGE_SETTINGS_KEY, DEFAULT_LANGUAGE))
    normalized = normalize_language(stored)
    return normalized if normalized is not None else DEFAULT_LANGUAGE


def save_language(settings: QSettings, language: str) -> None:
    """Persist a supported language choice."""
    normalized = normalize_language(language)
    if normalized is not None:
        settings.setValue(LANGUAGE_SETTINGS_KEY, normalized)


class LanguageManager(QObject):
    """Own the installed Qt and gettext translators for one application."""

    language_changed = Signal()

    def __init__(
        self,
        app: QApplication,
        settings: QSettings | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app = app
        self._settings = settings
        self._language = DEFAULT_LANGUAGE
        self._translator: QTranslator | None = None
        self._qt_translator: QTranslator | None = None

    @property
    def language(self) -> str:
        """The language currently installed."""
        return self._language

    def restore(self, settings: QSettings) -> None:
        """Attach persistent settings and install the saved language."""
        self._settings = settings
        self.set_language(load_language(settings), persist=False)

    def set_language(self, language: str, *, persist: bool = True) -> bool:
        """Switch language live; return ``False`` for unknown or missing catalogs."""
        normalized = normalize_language(language)
        if normalized is None:
            return False
        changed = normalized != self._language
        if changed:
            translator: QTranslator | None = None
            if normalized != DEFAULT_LANGUAGE:
                candidate = QTranslator(self)
                catalog = _TRANSLATIONS_DIR / f"silicondraft_{normalized}.qm"
                if not candidate.load(str(catalog)):
                    return False
                translator = candidate

            self._remove_qt_translator()
            previous = self._translator
            if previous is not None:
                self._app.removeTranslator(previous)
                previous.deleteLater()
            self._translator = translator
            if translator is not None:
                self._install_qt_translator(normalized)
                self._app.installTranslator(translator)
            self._language = normalized

        install_engine_translation(normalized)
        if persist and self._settings is not None:
            save_language(self._settings, normalized)
        if changed:
            self.language_changed.emit()
        return True

    def _install_qt_translator(self, language: str) -> None:
        """Load Qt's own catalog so standard dialogs follow the UI language."""
        translator = QTranslator(self)
        directory = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if translator.load(f"qtbase_{language}", directory):
            self._qt_translator = translator
            self._app.installTranslator(translator)
        else:
            translator.deleteLater()

    def _remove_qt_translator(self) -> None:
        translator = self._qt_translator
        if translator is not None:
            self._app.removeTranslator(translator)
            translator.deleteLater()
            self._qt_translator = None


_MANAGER: LanguageManager | None = None


def language_manager(app: QApplication | None = None) -> LanguageManager:
    """Return the process-wide language manager, creating it when needed."""
    global _MANAGER
    application = app
    if application is None:
        instance = QApplication.instance()
        if not isinstance(instance, QApplication):
            raise RuntimeError("no QApplication is running")
        application = instance
    if _MANAGER is None or _MANAGER.parent() is not application:
        _MANAGER = LanguageManager(application, parent=application)
    return _MANAGER


__all__ = [
    "DEFAULT_LANGUAGE",
    "LANGUAGE_LABELS",
    "LANGUAGE_SETTINGS_KEY",
    "SUPPORTED_LANGUAGES",
    "LanguageManager",
    "language_label",
    "language_manager",
    "load_language",
    "save_language",
]
