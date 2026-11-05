"""GUI persistence of the window layout and recent directories."""

from pathlib import Path

import pytest
import yaml
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog
from pytestqt.qtbot import QtBot

from silicondraft.gui.main_window import MainWindow
from silicondraft.gui.settings import OPEN_DIRECTORY_KEY


def _settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def _write_scenario(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "scenario.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "product": {"name": "GEN55LOGIC"},
                "wafer": {
                    "diameter_mm": 150,
                    "die_size_mm": [20.0, 20.0],
                    "edge_exclusion_mm": 3.0,
                },
                "lots": {"count": 1, "wafers_per_lot": 1},
                "export": {
                    "cp_stdf": True,
                    "cp_csv": False,
                    "wat_csv": False,
                    "ground_truth": False,
                    "include_die_truth": False,
                },
                "seed": 20260105,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_window_layout_is_saved_and_restored(qtbot: QtBot, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.show()
    window.resize(640, 480)
    window.splitter.setSizes([240, 400])
    # Some platforms enforce larger minimum sizes than requested; compare the
    # layout that was actually saved rather than the requested dimensions.
    qtbot.wait(50)
    saved_size = window.size()
    saved_sizes = window.splitter.sizes()

    window.close()
    settings.sync()

    restored = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(restored)
    restored.show()
    qtbot.wait(50)

    assert restored.size() == saved_size
    left, right = restored.splitter.sizes()
    assert left > 0 and right > 0
    assert restored.splitter.sizes() == saved_sizes


def test_recent_directories_are_saved_and_restored(qtbot: QtBot, tmp_path: Path) -> None:
    scenario = _write_scenario(tmp_path / "open")
    settings = _settings(tmp_path)
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    window.show()

    assert window.load_path(scenario)
    saved = tmp_path / "save" / "copy.yaml"
    saved.parent.mkdir()
    assert window.save_to_path(saved)

    with qtbot.waitSignal(window.generation_succeeded, timeout=30_000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3_000)
    export_dir = tmp_path / "export"
    assert window.export_to_directory(export_dir)
    settings.sync()

    restored = MainWindow(settings=_settings(tmp_path))
    qtbot.addWidget(restored)

    assert restored.open_directory == scenario.parent
    assert restored.save_directory == saved.parent
    assert restored.export_directory == export_dir


def test_open_dialog_starts_in_the_remembered_directory(
    qtbot: QtBot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    open_dir = tmp_path / "last-open"
    open_dir.mkdir()
    settings = _settings(tmp_path)
    settings.setValue(OPEN_DIRECTORY_KEY, str(open_dir))
    window = MainWindow(settings=settings)
    qtbot.addWidget(window)
    captured: dict[str, str] = {}

    def fake_get_open_file_name(
        parent: object, caption: str, directory: str, filter: str, *args: object
    ) -> tuple[str, str]:
        captured["directory"] = directory
        return "", ""

    monkeypatch.setattr(QFileDialog, "getOpenFileName", fake_get_open_file_name)
    window.open_action.trigger()

    assert captured["directory"] == str(open_dir)
