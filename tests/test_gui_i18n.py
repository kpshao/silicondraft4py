"""GUI language switching and persistence smoke tests."""

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QDialogButtonBox
from pytestqt.qtbot import QtBot

from silicondraft.gui.export_dialog import ExportDialog
from silicondraft.gui.i18n import (
    DEFAULT_LANGUAGE,
    LANGUAGE_SETTINGS_KEY,
    LanguageManager,
    language_manager,
    load_language,
    save_language,
)
from silicondraft.gui.main_window import MainWindow


def test_gui_starts_in_english(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.language == DEFAULT_LANGUAGE
    assert window.generate_action.text() == "Generate"
    assert window.preview_tabs.tabText(0) == "Wafer Map"
    assert window.tree.headerItem().text(0) == "Setting"


def test_gui_switches_language_without_restart(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.statusBar().currentMessage() == "Ready"

    window.language_actions["zh_CN"].trigger()
    assert window.language == "zh_CN"
    assert window.generate_action.text() == "生成"
    assert window.preview_tabs.tabText(0) == "晶圆图"
    assert window.tree.headerItem().text(0) == "设置"
    assert window.wafer_map_panel.overlay_checkbox.text() == "真值叠加"
    assert window.settings_menu.title() == "设置(&S)"
    assert window.language_menu.title() == "语言"
    assert window.statusBar().currentMessage() == "就绪"
    assert window.language_actions["zh_CN"].isChecked()

    window.language_actions["en"].trigger()
    assert window.generate_action.text() == "Generate"
    assert window.preview_tabs.tabText(0) == "Wafer Map"
    assert window.wafer_map_panel.overlay_checkbox.text() == "Ground truth"
    assert window.statusBar().currentMessage() == "Ready"
    assert window.language_actions["en"].isChecked()


def test_standard_dialog_buttons_follow_the_language(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = ExportDialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "Export Data"

    assert window.set_language("zh_CN")
    assert dialog.windowTitle() == "导出数据"

    buttons = dialog.findChild(QDialogButtonBox)
    assert buttons is not None
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    assert cancel is not None
    assert cancel.text() == "取消"


def test_window_starts_in_the_saved_language(qtbot: QtBot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    save_language(settings, "zh_CN")
    settings.sync()
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    manager = language_manager(app)
    manager.restore(settings)
    try:
        window = MainWindow()
        qtbot.addWidget(window)
        assert window.language == "zh_CN"
        assert window.generate_action.text() == "生成"
    finally:
        manager.set_language("en")


def test_language_choice_round_trips_through_settings(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    assert load_language(settings) == DEFAULT_LANGUAGE

    save_language(settings, "zh_CN")
    settings.sync()

    reloaded = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    assert load_language(reloaded) == "zh_CN"


def test_unknown_saved_language_falls_back_to_english(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    settings.setValue("ui/language", "fr")
    settings.sync()

    assert load_language(settings) == DEFAULT_LANGUAGE


def test_language_manager_saves_and_restores_the_choice(qtbot: QtBot, tmp_path: Path) -> None:
    app = QApplication.instance()
    assert isinstance(app, QApplication)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(app, settings, parent=app)
    try:
        assert manager.set_language("zh_CN")
        assert settings.value(LANGUAGE_SETTINGS_KEY) == "zh_CN"
        settings.sync()

        reloaded_settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
        restored = LanguageManager(app, parent=app)
        restored.restore(reloaded_settings)
        assert restored.language == "zh_CN"
        restored.set_language("en")
        restored.deleteLater()
    finally:
        manager.set_language("en")
        manager.deleteLater()
