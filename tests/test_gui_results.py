"""Tests for the GUI result table, pagination, and export flow."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QDialog
from pytestqt.qtbot import QtBot

from silicondraft.catalog import CatalogItem
from silicondraft.dataset import CPLot, CPWafer, GenerationResult
from silicondraft.gui.main_window import MainWindow
from silicondraft.scenario.models import Product, Scenario

_TIMESTAMP = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def _item(item_id: str, test_num: int, unit: str = "V") -> CatalogItem:
    return CatalogItem(
        id=item_id,
        phase="CP",
        test_num=test_num,
        description=f"{item_id} measurement",
        unit=unit,
        typical=0.5,
        lsl=0.0,
        usl=1.0,
        distribution="normal",
    )


def _wafer(wafer_id: str, start_x: int, die_count: int, values: dict[str, list[float]]) -> CPWafer:
    grid = np.arange(start_x, start_x + die_count, dtype=np.int64)
    return CPWafer(
        wafer_id=wafer_id,
        x_mm=(grid.astype(np.float64) * 5.0),
        y_mm=np.full(die_count, 2.5),
        grid_x=grid,
        grid_y=np.zeros(die_count, dtype=np.int64),
        test_site=(grid % 4).astype(np.int64),
        hard_bin=np.where(np.arange(die_count) % 2 == 0, 1, 2).astype(np.int64),
        soft_bin=np.where(np.arange(die_count) % 2 == 0, 100, 203).astype(np.int64),
        passed=(np.arange(die_count) % 2 == 0),
        values={item_id: np.array(column, dtype=np.float64) for item_id, column in values.items()},
        factors=np.zeros((2, die_count), dtype=np.float64),
        pattern_hits={},
        defect_failure=np.zeros(die_count, dtype=bool),
        defect_clusters=(),
        tested_at=_TIMESTAMP,
    )


def _result() -> GenerationResult:
    items = (_item("CP_VTHN", 2001), _item("CP_IDSAT", 2002, unit="uA/um"))
    values = {"CP_VTHN": [0.31, 0.42, 0.53], "CP_IDSAT": [500.0, 550.0, 600.0]}
    wafer_a = _wafer("W01", 0, 2, {key: column[:2] for key, column in values.items()})
    wafer_b = _wafer("W02", 10, 3, values)
    return GenerationResult(
        scenario=Scenario(schema_version=1, product=Product(name="TEST55"), seed=7),
        items=items,
        wat_items=(),
        lots=(CPLot(lot_id="TEST55-L001", wafers=(wafer_a,)), CPLot("TEST55-L002", (wafer_b,))),
        wat_lots=(),
        linkage_report=(),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def test_result_model_lists_die_level_rows() -> None:
    from silicondraft.gui.result_table import ResultTableModel

    model = ResultTableModel()
    model.set_result(_result())

    assert model.rowCount() == 5
    assert model.columnCount() == 12
    headers = [model.headerData(column, Qt.Orientation.Horizontal) for column in range(12)]
    assert headers == [
        "lot_id",
        "wafer_id",
        "grid_x",
        "grid_y",
        "die_x_mm",
        "die_y_mm",
        "test_site",
        "hard_bin",
        "soft_bin",
        "die_pass",
        "CP_VTHN",
        "CP_IDSAT",
    ]

    assert [model.data(model.index(row, 0)) for row in range(5)] == [
        "TEST55-L001",
        "TEST55-L001",
        "TEST55-L002",
        "TEST55-L002",
        "TEST55-L002",
    ]
    assert [model.data(model.index(row, 1)) for row in range(5)] == [
        "W01",
        "W01",
        "W02",
        "W02",
        "W02",
    ]
    assert model.data(model.index(0, 2)) == "0"
    assert model.data(model.index(2, 2)) == "10"
    assert model.data(model.index(0, 4)) == "0"
    assert model.data(model.index(2, 4)) == "50"
    assert model.data(model.index(1, 6)) == "1"
    assert model.data(model.index(0, 7)) == "1"
    assert model.data(model.index(1, 7)) == "2"
    assert model.data(model.index(0, 8)) == "100"
    assert model.data(model.index(1, 8)) == "203"
    assert model.data(model.index(0, 9)) == "Pass"
    assert model.data(model.index(1, 9)) == "Fail"
    assert model.data(model.index(0, 10)) == "0.31"
    assert model.data(model.index(4, 11)) == "600"
    assert model.headerData(0, Qt.Orientation.Vertical) == "1"
    assert model.headerData(4, Qt.Orientation.Vertical) == "5"


def test_result_model_paginates_die_rows() -> None:
    from silicondraft.gui.result_table import ResultTableModel

    model = ResultTableModel(page_size=2)
    model.set_result(_result())

    assert model.total_rows == 5
    assert model.page_count == 3
    assert model.page == 0
    assert model.rowCount() == 2
    assert model.headerData(0, Qt.Orientation.Vertical) == "1"

    assert model.set_page(2)
    assert model.page == 2
    assert model.rowCount() == 1
    assert model.data(model.index(0, 1)) == "W02"
    assert model.headerData(0, Qt.Orientation.Vertical) == "5"

    assert not model.set_page(2)
    assert not model.set_page(99)
    assert model.page == 2

    model.set_page(0)
    assert not model.set_page(-5)
    assert model.page == 0

    model.set_page(1)
    model.set_result(_result())
    assert model.page == 0

    model.set_page_size(5)
    assert model.page_size == 5
    assert model.page_count == 1
    assert model.rowCount() == 5


def test_result_model_is_empty_without_a_result() -> None:
    from silicondraft.gui.result_table import ResultTableModel

    model = ResultTableModel()

    assert model.rowCount() == 0
    assert model.total_rows == 0
    assert model.page_count == 1
    assert model.columnCount() == 10


def test_results_panel_pages_through_die_rows(qtbot: QtBot) -> None:
    from silicondraft.gui.result_table import ResultsPanel

    panel = ResultsPanel(page_size=2)
    qtbot.addWidget(panel)
    panel.show()

    model = panel.table.model()
    assert model is not None
    assert model.rowCount() == 0
    assert panel.page_label.text() == "Page 1 of 1"
    assert not panel.previous_button.isEnabled()
    assert not panel.next_button.isEnabled()

    panel.set_result(_result())
    assert model.rowCount() == 2
    assert panel.page_label.text() == "Page 1 of 3"
    assert not panel.previous_button.isEnabled()
    assert panel.next_button.isEnabled()
    assert model.data(model.index(0, 0)) == "TEST55-L001"

    panel.next_button.click()
    assert panel.page_label.text() == "Page 2 of 3"
    assert panel.previous_button.isEnabled()
    assert model.data(model.index(0, 1)) == "W02"

    panel.next_button.click()
    assert panel.page_label.text() == "Page 3 of 3"
    assert model.rowCount() == 1
    assert not panel.next_button.isEnabled()

    panel.previous_button.click()
    assert panel.page_label.text() == "Page 2 of 3"
    assert panel.next_button.isEnabled()

    panel.set_result(None)
    assert model.rowCount() == 0
    assert panel.page_label.text() == "Page 1 of 1"
    assert not panel.previous_button.isEnabled()
    assert not panel.next_button.isEnabled()


def test_export_dialog_collects_the_directory_and_csv(qtbot: QtBot, tmp_path: Path) -> None:
    from silicondraft.gui.export_dialog import ExportDialog

    dialog = ExportDialog(tmp_path)
    qtbot.addWidget(dialog)

    assert dialog.output_dir() == tmp_path
    assert dialog.format_label.text() == "CSV"

    dialog.set_output_dir(tmp_path / "nested")
    dialog.accept()

    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.output_dir() == tmp_path / "nested"


def test_export_dialog_requires_a_directory(qtbot: QtBot, tmp_path: Path) -> None:
    from silicondraft.gui.export_dialog import ExportDialog

    dialog = ExportDialog("")
    qtbot.addWidget(dialog)
    assert dialog.output_dir() is None

    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert "output directory" in dialog.error_label.text().lower()

    dialog.set_output_dir(tmp_path)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def _write_scenario(tmp_path: Path, *, csv_enabled: bool = True) -> Path:
    document = {
        "schema_version": 1,
        "product": {"name": "TEST55"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": 1, "wafers_per_lot": 1},
        "export": {
            "cp_csv": csv_enabled,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": 20260105,
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(window: MainWindow, qtbot: QtBot) -> None:
    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)


def test_export_is_disabled_before_generation(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    assert not window.export_action.isEnabled()
    assert not window.export_to_directory(tmp_path / "out")
    assert window.last_export_paths == ()

    assert window.load_path(_write_scenario(tmp_path))
    assert not window.export_action.isEnabled()


def test_generation_populates_the_table_and_enables_export(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))

    _generate(window, qtbot)

    result = window.last_result
    assert result is not None
    die_count = sum(lot.die_count for lot in result.lots)
    assert window.results_panel.model.total_rows == die_count
    assert window.results_panel.model.rowCount() > 0
    model = window.results_panel.model
    assert model.data(model.index(0, 0)) == result.lots[0].lot_id
    assert model.data(model.index(0, 1)) == result.lots[0].wafers[0].wafer_id
    assert window.export_action.isEnabled()
    assert window.preview_tabs.currentWidget() is window.wafer_map_panel

    window.results_panel.set_page_size(10)
    assert model.page_count > 1
    assert window.results_panel.page_label.text() == f"Page 1 of {model.page_count}"
    window.results_panel.next_button.click()
    assert model.page == 1
    assert model.headerData(0, Qt.Orientation.Vertical) == "11"
    assert window.results_panel.previous_button.isEnabled()


def test_results_panel_page_size_change_refreshes_the_view(qtbot: QtBot) -> None:
    from silicondraft.gui.result_table import ResultsPanel

    panel = ResultsPanel(page_size=2)
    qtbot.addWidget(panel)
    panel.set_result(_result())
    model = panel.model
    resets: list[bool] = []
    model.modelReset.connect(lambda: resets.append(True))

    panel.set_page_size(5)

    assert resets
    assert model.rowCount() == 5
    assert panel.page_label.text() == "Page 1 of 1"


def test_export_writes_csv_files_to_the_chosen_directory(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
    _generate(window, qtbot)
    out_dir = tmp_path / "exported"

    assert window.export_to_directory(out_dir)

    assert window.last_export_paths
    for path in window.last_export_paths:
        assert path.parent == out_dir
        assert path.suffix == ".csv"
        assert path.exists()
    assert any("_CP_" in path.name for path in window.last_export_paths)
    assert "Exported" in window.statusBar().currentMessage()
    assert window.issues_list.count() == 0


def test_export_failure_is_reported(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
    _generate(window, qtbot)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")

    assert not window.export_to_directory(blocked / "out")

    assert window.last_export_paths == ()
    assert "Export failed" in window.statusBar().currentMessage()
    assert window.issues_list.count() == 1
    assert "Export failed" in window.issues_list.item(0).text()
    assert window.preview_tabs.currentWidget() is window.issues_panel
    assert window.export_action.isEnabled()


def test_export_fails_clearly_when_no_csv_output_is_enabled(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path, csv_enabled=False))
    _generate(window, qtbot)
    out_dir = tmp_path / "exported"

    assert not window.export_to_directory(out_dir)

    assert window.last_export_paths == ()
    assert "no CSV export enabled" in window.statusBar().currentMessage()
    assert window.issues_list.count() == 1
    assert not out_dir.exists()
    assert window.export_action.isEnabled()


def test_export_action_opens_the_dialog_and_writes_files(qtbot: QtBot, tmp_path: Path) -> None:
    from silicondraft.gui.export_dialog import ExportDialog

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_scenario(tmp_path))
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
        dialog.accept()

    QTimer.singleShot(0, fill_dialog)
    window.export_action.trigger()

    assert problems == []
    assert window.last_export_paths
    assert all(path.exists() for path in window.last_export_paths)
    assert "Exported" in window.statusBar().currentMessage()
