"""pytest-qt smoke tests for the GUI backbone."""

import time
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import yaml
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from silicondraft import (
    GenerationCancelled,
    GenerationProgress,
    GenerationResult,
    load_scenario,
)
from silicondraft.api import CancelCheck, ProgressCallback
from silicondraft.gui.app import create_application
from silicondraft.gui.main_window import MainWindow
from silicondraft.gui.worker import GenerateFn
from silicondraft.scenario.models import Scenario

_FAKE_RESULT = cast(GenerationResult, SimpleNamespace(lots=()))


def _write_scenario(tmp_path: Path, document: dict[str, object] | None = None) -> Path:
    if document is None:
        document = {
            "schema_version": 1,
            "product": {"name": "GEN55LOGIC"},
            "wafer": {
                "diameter_mm": 150,
                "die_size_mm": [20.0, 20.0],
                "edge_exclusion_mm": 3.0,
            },
            "lots": {"count": 1, "wafers_per_lot": 2},
            "export": {
                "cp_csv": False,
                "wat_csv": False,
                "ground_truth": False,
                "include_die_truth": False,
            },
            "seed": 20260105,
        }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _fake_generate(total: int = 3, delay: float = 0.0) -> GenerateFn:
    def generate_fn(
        scenario: Scenario,
        *,
        progress: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> GenerationResult:
        for completed in range(1, total + 1):
            if should_cancel is not None and should_cancel():
                raise GenerationCancelled
            if progress is not None:
                progress(
                    GenerationProgress(
                        lot_number=1,
                        lot_count=1,
                        wafer_number=completed,
                        wafers_per_lot=total,
                        completed_wafers=completed,
                        total_wafers=total,
                        lot_id="GEN55LOGIC-L001",
                        wafer_id=f"W{completed:02d}",
                    )
                )
            if delay:
                time.sleep(delay)
        return _FAKE_RESULT

    return generate_fn


def test_create_application_returns_the_qt_application(qtbot: QtBot) -> None:
    assert isinstance(create_application([]), QApplication)


def test_window_starts_empty_and_loads_a_scenario(qtbot: QtBot, tmp_path: Path) -> None:
    path = _write_scenario(tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert not window.generate_action.isEnabled()
    assert window.load_path(path)

    assert window.scenario == load_scenario(path)
    assert window.scenario_path == path
    assert window.tree.topLevelItemCount() > 0
    assert window.generate_action.isEnabled()
    assert window.save_action.isEnabled()
    assert window.issues_list.count() == 0
    assert "Loaded scenario" in window.statusBar().currentMessage()


def test_scenario_can_be_saved_and_loaded_again(qtbot: QtBot, tmp_path: Path) -> None:
    source = _write_scenario(tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.load_path(source)
    target = tmp_path / "saved.yaml"

    assert window.save_to_path(target)

    original = load_scenario(source)
    assert load_scenario(target) == original
    assert "Saved scenario" in window.statusBar().currentMessage()

    reloaded = MainWindow()
    qtbot.addWidget(reloaded)
    assert reloaded.load_path(target)
    assert reloaded.scenario == original


def test_preset_selection_builds_a_scenario(qtbot: QtBot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    index = window.preset_combo.findData("quick")
    assert index >= 0
    window.preset_combo.setCurrentIndex(index)

    assert window.scenario is not None
    assert window.scenario.preset == "quick"
    assert window.scenario.lots.wafers_per_lot == 25
    assert window.generate_action.isEnabled()
    assert "Applied preset" in window.statusBar().currentMessage()


def test_generate_runs_in_a_worker_and_reports_progress(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(generate_fn=_fake_generate())
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
    progress_events: list[GenerationProgress] = []
    window.generation_progress.connect(progress_events.append)

    with qtbot.waitSignal(window.generation_succeeded, timeout=3000) as blocker:
        assert window.start_generation()
        assert window.generation_running
        assert not window.generate_action.isEnabled()
        assert window.cancel_action.isEnabled()
        assert window.progress_bar.isVisible()

    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)

    assert blocker.args[0] is _FAKE_RESULT
    assert window.last_result is _FAKE_RESULT
    assert [event.completed_wafers for event in progress_events] == [1, 2, 3]
    assert window.progress_bar.value() == 3
    assert not window.progress_bar.isVisible()
    assert window.generate_action.isEnabled()
    assert not window.cancel_action.isEnabled()
    assert "Generation complete" in window.statusBar().currentMessage()


def test_real_generation_completes(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
    progress_events: list[GenerationProgress] = []
    window.generation_progress.connect(progress_events.append)

    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()

    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)
    assert window.last_result is not None
    assert len(window.last_result.lots) == 1
    assert [event.completed_wafers for event in progress_events] == [1, 2]


def test_cancel_after_completion_keeps_the_completion_status(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(generate_fn=_fake_generate())
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
    window.generation_succeeded.connect(lambda _result: window.cancel_generation())

    with qtbot.waitSignal(window.generation_succeeded, timeout=3000):
        assert window.start_generation()

    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)

    assert "Generation complete" in window.statusBar().currentMessage()
    assert window.generate_action.isEnabled()


def test_loading_a_scenario_discards_the_previous_result(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(generate_fn=_fake_generate())
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
    with qtbot.waitSignal(window.generation_succeeded, timeout=3000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)
    assert window.last_result is _FAKE_RESULT

    second_dir = tmp_path / "second"
    second_dir.mkdir()
    assert window.load_path(_write_scenario(second_dir))

    assert window.last_result is None


def test_cancel_stops_generation_and_restores_the_window(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow(generate_fn=_fake_generate(total=50, delay=0.01))
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))

    with qtbot.waitSignal(window.generation_progress, timeout=3000):
        assert window.start_generation()

    assert window.generation_running
    with qtbot.waitSignal(window.generation_cancelled, timeout=3000):
        window.cancel_generation()
        assert not window.cancel_action.isEnabled()
        assert "Cancelling" in window.statusBar().currentMessage()

    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)

    assert window.last_result is None
    assert "cancelled" in window.statusBar().currentMessage().lower()
    assert window.generate_action.isEnabled()
    assert not window.cancel_action.isEnabled()
    assert window.open_action.isEnabled()
    assert window.preset_combo.isEnabled()


def test_invalid_scenario_shows_readable_issues(qtbot: QtBot, tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        {
            "schema_version": 1,
            "product": {"name": "GEN55LOGIC"},
            "wafer": {"diameter_mm": 150, "edge_exclusion_mm": 200.0},
            "seed": 20260105,
        },
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert not window.load_path(path)

    assert window.scenario is None
    assert not window.generate_action.isEnabled()
    assert window.issues_list.count() == 1
    assert [issue.code for issue in window.last_issues] == ["EDGE_EXCLUSION_TOO_LARGE"]
    text = window.issues_list.item(0).text()
    assert "wafer.edge_exclusion_mm" in text
    assert "EDGE_EXCLUSION_TOO_LARGE" in text
    assert "Could not load scenario" in window.statusBar().currentMessage()


def test_generation_reports_invalid_scenario_issues(qtbot: QtBot, tmp_path: Path) -> None:
    valid = _write_scenario(tmp_path)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(valid)
    scenario = window.scenario
    assert scenario is not None
    broken = scenario.model_copy(
        update={"wafer": scenario.wafer.model_copy(update={"edge_exclusion_mm": 200.0})}
    )
    window.set_scenario(broken)

    with qtbot.waitSignal(window.generation_invalid, timeout=3000) as blocker:
        assert window.start_generation()

    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)

    issues = blocker.args[0]
    assert any(issue.code == "EDGE_EXCLUSION_TOO_LARGE" for issue in issues)
    assert window.last_issues == issues
    assert window.issues_list.count() == 1
    assert "wafer.edge_exclusion_mm" in window.issues_list.item(0).text()
    assert window.generate_action.isEnabled()
    assert not window.cancel_action.isEnabled()
