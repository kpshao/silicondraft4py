"""Tests for the export dialog's per-run format and ground-truth overrides."""

import json
from pathlib import Path

import yaml
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from silicondraft.gui.export_dialog import ExportDialog
from silicondraft.gui.main_window import MainWindow
from silicondraft.scenario.models import ExportOptions


def _write_export_scenario(
    tmp_path: Path,
    *,
    wafers_per_lot: int = 2,
    layout: str = "long",
    ground_truth: bool = True,
    include_die_truth: bool = True,
) -> Path:
    document: dict[str, object] = {
        "schema_version": 1,
        "product": {"name": "TEST55"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": 1, "wafers_per_lot": wafers_per_lot},
        "export": {
            "cp_csv": True,
            "cp_csv_layout": layout,
            "wat_csv": False,
            "ground_truth": ground_truth,
            "include_die_truth": include_die_truth,
        },
        "seed": 20260105,
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(window: MainWindow, qtbot: QtBot) -> None:
    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)


def test_export_dialog_defaults_to_the_scenario_options(qtbot: QtBot, tmp_path: Path) -> None:
    options = ExportOptions(cp_csv_layout="blocks", ground_truth=True, include_die_truth=True)
    dialog = ExportDialog(tmp_path, export_options=options)
    qtbot.addWidget(dialog)

    assert dialog.cp_csv_layout() == "blocks"
    assert dialog.include_ground_truth()
    assert dialog.include_die_truth()
    assert dialog.output_dir() == tmp_path


def test_export_dialog_overrides_layout_and_truth_options(qtbot: QtBot, tmp_path: Path) -> None:
    dialog = ExportDialog(tmp_path, export_options=ExportOptions())
    qtbot.addWidget(dialog)

    assert dialog.cp_csv_layout() == "long"
    assert dialog.set_cp_csv_layout("blocks")
    assert dialog.cp_csv_layout() == "blocks"
    assert not dialog.set_cp_csv_layout("spreadsheet")

    dialog.set_include_die_truth(False)
    assert dialog.include_ground_truth()
    assert not dialog.include_die_truth()

    dialog.set_include_ground_truth(False)
    assert not dialog.include_ground_truth()
    assert not dialog.include_die_truth()
    assert not dialog.die_truth_checkbox.isEnabled()

    dialog.set_include_ground_truth(True)
    assert dialog.die_truth_checkbox.isEnabled()
    assert not dialog.include_die_truth()

    dialog.set_include_die_truth(True)
    assert dialog.include_die_truth()


def test_main_window_export_overrides_layout_and_skips_die_truth(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_export_scenario(tmp_path))
    _generate(window, qtbot)
    out_dir = tmp_path / "exported"

    assert window.export_to_directory(
        out_dir,
        cp_csv_layout="blocks",
        include_ground_truth=True,
        include_die_truth=False,
    )

    names = sorted(path.name for path in window.last_export_paths)
    assert any("_W01_CP_" in name for name in names)
    assert any("_W02_CP_" in name for name in names)
    assert not any("_L001_CP_" in name for name in names)
    assert not any(name.endswith(".csv.gz") for name in names)
    manifest_path = next(path for path in window.last_export_paths if path.suffix == ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["die_truth_files"] == []
    assert "Exported" in window.statusBar().currentMessage()


def test_main_window_export_can_disable_ground_truth(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_export_scenario(tmp_path))
    _generate(window, qtbot)
    out_dir = tmp_path / "exported"

    assert window.export_to_directory(out_dir, include_ground_truth=False)

    assert window.last_export_paths
    assert all(path.suffix == ".csv" for path in window.last_export_paths)
    assert not list(out_dir.glob("*.json"))
    assert not list(out_dir.glob("*.csv.gz"))


def test_export_dialog_choices_drive_the_export(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_export_scenario(tmp_path))
    _generate(window, qtbot)
    out_dir = tmp_path / "dialog-export"
    problems: list[str] = []

    def fill_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, ExportDialog):
            problems.append(f"unexpected modal widget: {dialog!r}")
            fallback = window.findChild(ExportDialog)
            if fallback is not None:
                fallback.reject()
            return
        dialog.set_output_dir(out_dir)
        dialog.set_cp_csv_layout("blocks")
        dialog.set_include_die_truth(False)
        dialog.accept()

    QTimer.singleShot(0, fill_dialog)
    window.export_action.trigger()

    assert problems == []
    names = sorted(path.name for path in window.last_export_paths)
    assert any("_W01_CP_" in name for name in names)
    assert any("_W02_CP_" in name for name in names)
    assert not any(name.endswith(".csv.gz") for name in names)
    assert next(path for path in window.last_export_paths if path.suffix == ".json").exists()
