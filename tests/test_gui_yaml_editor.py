"""Tests for the GUI YAML editor dialog and its text validation seam."""

from pathlib import Path

import yaml
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from silicondraft import load_scenario, scenario_from_preset
from silicondraft.cli import main
from silicondraft.gui.i18n import language_manager
from silicondraft.gui.main_window import MainWindow
from silicondraft.gui.yaml_editor import YamlEditorDialog
from silicondraft.scenario import validate_scenario_text


def _write_scenario(tmp_path: Path, *, seed: int = 20260105) -> Path:
    document: dict[str, object] = {
        "schema_version": 1,
        "product": {"name": "TEST55"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": 1, "wafers_per_lot": 1},
        "export": {
            "cp_csv": True,
            "cp_csv_layout": "long",
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": seed,
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _line_text(dialog: YamlEditorDialog) -> str:
    cursor = dialog.editor.textCursor()
    block = cursor.document().findBlockByNumber(cursor.blockNumber())
    return block.text()


def test_validate_scenario_text_reports_locatable_issues() -> None:
    result = validate_scenario_text(
        "schema_version: 1\nproduct:\n  name: TEST55\nwafer:\n  edge_exclusion_mm: 200.0\nseed: 1\n"
    )

    assert result.ok is False
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("EDGE_EXCLUSION_TOO_LARGE", "wafer.edge_exclusion_mm")
    ]
    assert result.summary is None


def test_yaml_editor_preloads_the_expanded_scenario(qtbot: QtBot, tmp_path: Path) -> None:
    path = _write_scenario(tmp_path)
    scenario = load_scenario(path)
    dialog = YamlEditorDialog(scenario, path)
    qtbot.addWidget(dialog)

    document = yaml.safe_load(dialog.text())
    assert document["schema_version"] == 1
    assert document["seed"] == 20260105
    assert "preset" in document
    assert dialog.issues == ()
    assert dialog.validate()
    assert dialog.issues == ()


def test_yaml_editor_edits_and_validates_the_text(qtbot: QtBot, tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)

    dialog.set_text(dialog.text().replace("seed: 20260105", "seed: 7"))

    assert dialog.validate()
    assert yaml.safe_load(dialog.text())["seed"] == 7


def test_invalid_semantic_yaml_moves_the_cursor_to_the_issue(qtbot: QtBot, tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_text(
        "schema_version: 1\nproduct:\n  name: TEST55\nwafer:\n  edge_exclusion_mm: 200.0\nseed: 1\n"
    )

    assert not dialog.validate()

    assert [(issue.code, issue.path) for issue in dialog.issues] == [
        ("EDGE_EXCLUSION_TOO_LARGE", "wafer.edge_exclusion_mm")
    ]
    assert "edge_exclusion_mm" in _line_text(dialog)
    assert "wafer.edge_exclusion_mm" in dialog.issues_list.item(0).text()
    assert "EDGE_EXCLUSION_TOO_LARGE" in dialog.issues_list.item(0).text()


def test_invalid_pattern_issue_moves_the_cursor_into_the_list_item(
    qtbot: QtBot, tmp_path: Path
) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.set_text(
        "schema_version: 1\n"
        "product:\n"
        "  name: TEST55\n"
        "patterns:\n"
        "  - kind: center_high\n"
        "    target_item: CP_NOPE\n"
        "    amplitude: 0.05\n"
        "    radius_mm: 40.0\n"
        "seed: 1\n"
    )

    assert not dialog.validate()

    assert [(issue.code, issue.path) for issue in dialog.issues] == [
        ("ITEM_REFERENCE_UNKNOWN", "patterns[0].target_item")
    ]
    assert "target_item: CP_NOPE" in _line_text(dialog)


def test_invalid_yaml_syntax_moves_the_cursor_to_the_parse_error(
    qtbot: QtBot, tmp_path: Path
) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_text("schema_version: 1\n\tproduct: TEST55\n")

    assert not dialog.validate()

    assert dialog.issues[0].code == "YAML_PARSE_ERROR"
    assert dialog.editor.textCursor().blockNumber() + 1 == 2
    assert "line 2" in dialog.issues_list.item(0).text()


def test_yaml_parse_error_keeps_its_location_in_chinese(qtbot: QtBot, tmp_path: Path) -> None:
    assert language_manager().set_language("zh_CN")
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_text("schema_version: 1\n\tproduct: TEST55\n")

    assert not dialog.validate()

    assert dialog.issues[0].code == "YAML_PARSE_ERROR"
    assert dialog.editor.textCursor().blockNumber() + 1 == 2
    assert "第 2 行" in dialog.issues_list.item(0).text()


def test_yaml_editor_expands_presets_and_keeps_edits_authoritative(
    qtbot: QtBot, tmp_path: Path
) -> None:
    scenario = scenario_from_preset("demo", 7)
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    document = yaml.safe_load(dialog.text())
    assert document["preset"] is None
    assert document["patterns"]
    document["patterns"] = []
    dialog.set_text(yaml.safe_dump(document, sort_keys=False))
    target = tmp_path / "demo-edited.yaml"

    assert dialog.save_to_path(target)

    saved = load_scenario(target)
    assert saved.preset is None
    assert saved.patterns == []


def test_yaml_editor_saves_a_valid_scenario(qtbot: QtBot, tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    target = tmp_path / "edited.yaml"
    dialog.set_text(dialog.text().replace("seed: 20260105", "seed: 7"))

    assert dialog.save_to_path(target)

    assert dialog.saved_path == target
    assert dialog.saved_scenario is not None
    assert dialog.saved_scenario.seed == 7
    saved_document = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert saved_document["seed"] == 7
    assert "preset" in saved_document
    assert load_scenario(target) == dialog.saved_scenario


def test_yaml_editor_does_not_save_invalid_yaml(qtbot: QtBot, tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    target = tmp_path / "edited.yaml"
    dialog.set_text("schema_version: 1\nproduct: [\n")

    assert not dialog.save_to_path(target)

    assert not target.exists()
    assert dialog.saved_path is None
    assert dialog.issues[0].code == "YAML_PARSE_ERROR"


def test_save_button_writes_the_file_and_accepts(qtbot: QtBot, tmp_path: Path) -> None:
    path = _write_scenario(tmp_path)
    scenario = load_scenario(path)
    dialog = YamlEditorDialog(scenario, path)
    qtbot.addWidget(dialog)
    dialog.set_text(dialog.text().replace("seed: 20260105", "seed: 7"))

    dialog.save_button.click()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert load_scenario(path).seed == 7


def test_saved_scenario_is_directly_usable_by_the_cli(qtbot: QtBot, tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    dialog = YamlEditorDialog(scenario)
    qtbot.addWidget(dialog)
    target = tmp_path / "cli.yaml"
    out_dir = tmp_path / "out"
    dialog.set_text(dialog.text().replace("seed: 20260105", "seed: 7"))

    assert dialog.save_to_path(target)

    exit_code = main(["generate", "-c", str(target), "-o", str(out_dir)])
    assert exit_code == 0
    paths = list(out_dir.glob("*.csv"))
    assert len(paths) == 1
    assert paths[0].name.endswith(".csv")


def test_main_window_yaml_editor_action_loads_the_saved_scenario(
    qtbot: QtBot, tmp_path: Path
) -> None:
    path = _write_scenario(tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(path)
    problems: list[str] = []

    def edit_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        if not isinstance(dialog, YamlEditorDialog):
            problems.append(f"unexpected modal widget: {dialog!r}")
            fallback = window.findChild(YamlEditorDialog)
            if fallback is not None:
                fallback.reject()
            return
        dialog.set_text(dialog.text().replace("seed: 20260105", "seed: 7"))
        dialog.save_to_path(path)
        dialog.accept()

    QTimer.singleShot(0, edit_dialog)
    window.yaml_editor_action.trigger()

    assert problems == []
    assert window.scenario is not None
    assert window.scenario.seed == 7
    assert window.scenario_path == path
    assert "Loaded scenario" in window.statusBar().currentMessage()
