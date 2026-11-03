"""Tests for the GUI wafer map and distribution previews."""

import csv
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
import yaml
from pytestqt.qtbot import QtBot

from silicondraft.catalog import CatalogItem
from silicondraft.dataset import CPLot, CPWafer, GenerationResult
from silicondraft.exporters.common import format_float
from silicondraft.gui.main_window import MainWindow
from silicondraft.scenario.models import Product, Scenario

_TIMESTAMP = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def _item(item_id: str, test_num: int, *, lsl: float, usl: float) -> CatalogItem:
    return CatalogItem(
        id=item_id,
        phase="CP",
        test_num=test_num,
        description=f"{item_id} measurement",
        unit="V",
        typical=0.5,
        lsl=lsl,
        usl=usl,
        distribution="normal",
    )


def _wafer(
    wafer_id: str,
    *,
    x_mm: list[float],
    y_mm: list[float],
    hard_bin: list[int],
    soft_bin: list[int],
    values: dict[str, list[float]],
) -> CPWafer:
    die_count = len(x_mm)
    return CPWafer(
        wafer_id=wafer_id,
        x_mm=np.array(x_mm, dtype=np.float64),
        y_mm=np.array(y_mm, dtype=np.float64),
        grid_x=np.arange(die_count, dtype=np.int64),
        grid_y=np.zeros(die_count, dtype=np.int64),
        test_site=np.ones(die_count, dtype=np.int64),
        hard_bin=np.array(hard_bin, dtype=np.int64),
        soft_bin=np.array(soft_bin, dtype=np.int64),
        passed=np.array(hard_bin, dtype=np.int64) == 1,
        values={item_id: np.array(column, dtype=np.float64) for item_id, column in values.items()},
        factors=np.zeros((2, die_count), dtype=np.float64),
        pattern_hits={},
        defect_failure=np.zeros(die_count, dtype=bool),
        defect_clusters=(),
        tested_at=_TIMESTAMP,
    )


def _preview_result() -> GenerationResult:
    items = (
        _item("CP_A", 2001, lsl=0.0, usl=1.0),
        _item("CP_B", 2002, lsl=-1.0, usl=2.0),
    )
    wafer = _wafer(
        "W01",
        x_mm=[-5.0, 5.0, -5.0, 5.0],
        y_mm=[-5.0, -5.0, 5.0, 5.0],
        hard_bin=[1, 1, 2, 3],
        soft_bin=[100, 100, 203, 206],
        values={"CP_A": [0.1, 0.2, 0.3, 0.9], "CP_B": [0.9, 0.8, 0.7, 0.1]},
    )
    return GenerationResult(
        scenario=Scenario(schema_version=1, product=Product(name="TEST55"), seed=7),
        items=items,
        wat_items=(),
        lots=(CPLot(lot_id="TEST55-L001", wafers=(wafer,)),),
        wat_lots=(),
        linkage_report=(),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def test_wafer_map_shows_dies_and_switches_colour_modes(qtbot: QtBot) -> None:
    from silicondraft.gui.wafer_map import COLOR_MODES, WaferMapView

    view = WaferMapView()
    qtbot.addWidget(view)

    view.set_result(_preview_result())

    assert view.wafer_count == 1
    assert view.wafer is not None
    assert view.wafer.wafer_id == "W01"
    assert view.rendered_die_count == 4
    assert not view.downsampled
    assert view.color_mode == COLOR_MODES[0]

    rect = view.die_rect(2)
    assert rect.center().x() == pytest.approx(-5.0)
    assert rect.center().y() == pytest.approx(-5.0)

    assert view.die_color(0) == view.die_color(1)
    assert view.die_color(0) != view.die_color(2)
    assert view.die_color(2) != view.die_color(3)

    assert view.set_color_mode("soft_bin")
    assert view.color_mode == COLOR_MODES[1]
    assert view.die_color(2) != view.die_color(3)

    assert view.set_color_mode("item")
    assert view.set_item("CP_A")
    item_a_first = view.die_color(0)
    item_a_last = view.die_color(3)
    assert item_a_first != item_a_last

    assert view.set_item("CP_B")
    assert view.die_color(0) != item_a_first
    assert view.die_color(3) != item_a_last

    assert view.set_item("CP_A")
    tooltip = view.die_tooltip(0)
    assert "CP_A" in tooltip
    assert format_float(0.1) in tooltip


def test_wafer_map_paints_dies_in_their_bin_colour(qtbot: QtBot) -> None:
    from silicondraft.gui.wafer_map import WaferMapView

    view = WaferMapView()
    qtbot.addWidget(view)
    view.resize(420, 420)
    view.set_result(_preview_result())
    view.show()

    image = view.grab().toImage()
    point = view.mapFromScene(view.die_rect(0).center())
    assert image.pixelColor(point).name() == view.die_color(0).name()


def test_wafer_map_downsamples_large_wafers(qtbot: QtBot) -> None:
    from silicondraft.gui.sampling import sample_indices
    from silicondraft.gui.wafer_map import WaferMapView

    indices = sample_indices(1000, limit=10)
    assert indices.size == 10
    assert indices[0] == 0
    assert indices[-1] == 999
    assert np.all(np.diff(indices) > 0)

    die_count = 5_000
    wafer = _wafer(
        "BIG",
        x_mm=[float(index) for index in range(die_count)],
        y_mm=[0.0] * die_count,
        hard_bin=[1] * die_count,
        soft_bin=[100] * die_count,
        values={"CP_A": [0.0] * die_count, "CP_B": [0.0] * die_count},
    )
    source = _preview_result()
    result = GenerationResult(
        scenario=source.scenario,
        items=source.items,
        wat_items=(),
        lots=(CPLot(lot_id="TEST55-L001", wafers=(wafer,)),),
        wat_lots=(),
        linkage_report=(),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )
    view = WaferMapView(max_render_dies=100)
    qtbot.addWidget(view)

    view.set_result(result)

    assert view.wafer is not None
    assert view.wafer.die_count == die_count
    assert view.downsampled
    assert view.rendered_die_count == 100
    assert len(view.scene().items()) == 1


def test_distribution_histogram_shows_values_and_spec_limits(qtbot: QtBot) -> None:
    from silicondraft.gui.distribution import DistributionPanel, compute_histogram

    panel = DistributionPanel()
    qtbot.addWidget(panel)

    panel.set_result(_preview_result())

    assert panel.item_ids == ("CP_A", "CP_B")
    assert panel.item_id == "CP_A"
    histogram = panel.histogram
    assert histogram is not None
    assert histogram.sampled_count == 4
    assert int(histogram.counts.sum()) == 4
    assert histogram.edges[0] == pytest.approx(0.1)
    assert histogram.edges[-1] == pytest.approx(0.9)
    assert panel.spec_limit_values == (0.0, 1.0)
    assert [line.value() for line in panel.spec_lines] == pytest.approx([0.0, 1.0])

    assert panel.set_item("CP_B")
    assert panel.item_id == "CP_B"
    assert panel.spec_limit_values == (-1.0, 2.0)
    assert [line.value() for line in panel.spec_lines] == pytest.approx([-1.0, 2.0])
    assert panel.histogram is not None
    assert panel.histogram.sampled_count == 4

    sampled = compute_histogram(np.arange(1_000, dtype=np.float64), bins=10, max_samples=100)
    assert sampled is not None
    assert sampled.sampled_count == 100
    assert int(sampled.counts.sum()) == 100
    assert compute_histogram(np.empty(0, dtype=np.float64)) is None


def test_wafer_map_panel_switches_wafer_colour_mode_and_item(qtbot: QtBot) -> None:
    from silicondraft.gui.wafer_map import COLOR_MODES, WaferMapPanel

    source = _preview_result()
    first_wafer = source.lots[0].wafers[0]
    second_wafer = _wafer(
        "W02",
        x_mm=[-5.0, 5.0],
        y_mm=[0.0, 0.0],
        hard_bin=[1, 2],
        soft_bin=[100, 203],
        values={"CP_A": [0.2, 0.8], "CP_B": [0.7, 0.3]},
    )
    result = GenerationResult(
        scenario=source.scenario,
        items=source.items,
        wat_items=(),
        lots=(
            CPLot(lot_id="TEST55-L001", wafers=(first_wafer,)),
            CPLot(lot_id="TEST55-L002", wafers=(second_wafer,)),
        ),
        wat_lots=(),
        linkage_report=(),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )
    panel = WaferMapPanel()
    qtbot.addWidget(panel)

    panel.set_result(result)

    assert panel.wafer_combo.count() == 2
    assert panel.wafer_combo.currentText() == "TEST55-L001 / W01"
    assert panel.color_combo.currentData() == COLOR_MODES[0]
    assert not panel.item_combo.isEnabled()
    assert panel.map_view.color_mode == COLOR_MODES[0]

    assert panel.select_color_mode("item")
    assert panel.map_view.color_mode == COLOR_MODES[2]
    assert panel.item_combo.isEnabled()
    assert panel.map_view.item_id == "CP_A"

    assert panel.select_item("CP_B")
    assert panel.map_view.item_id == "CP_B"
    assert "CP_B" in panel.legend_label.text()

    panel.wafer_combo.setCurrentIndex(1)
    assert panel.map_view.wafer is not None
    assert panel.map_view.wafer.wafer_id == "W02"

    panel.set_result(None)
    assert panel.wafer_combo.count() == 0
    assert panel.map_view.wafer is None
    assert panel.map_view.wafer_radius_mm == 0.0


def _write_preview_scenario(
    tmp_path: Path,
    *,
    patterns: list[dict[str, object]] | None = None,
) -> Path:
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
        "seed": 20260105,
    }
    if patterns is not None:
        document["patterns"] = patterns
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(window: MainWindow, qtbot: QtBot) -> None:
    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)


def test_generation_fills_wafer_map_and_distribution_tabs(
    qtbot: QtBot, tmp_path: Path
) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_preview_scenario(tmp_path))

    titles = [
        window.preview_tabs.tabText(index) for index in range(window.preview_tabs.count())
    ]
    assert "Wafer Map" in titles
    assert "Distribution" in titles
    assert window.wafer_map_panel.map_view.wafer is None
    assert window.distribution_panel.histogram is None

    _generate(window, qtbot)

    result = window.last_result
    assert result is not None
    wafer = window.wafer_map_panel.map_view.wafer
    assert wafer is not None
    assert wafer.wafer_id == result.lots[0].wafers[0].wafer_id
    assert window.distribution_panel.histogram is not None
    die_total = sum(each.die_count for lot in result.lots for each in lot.wafers)
    assert window.distribution_panel.histogram.sampled_count == die_total
    assert window.preview_tabs.currentWidget() is window.wafer_map_panel

    second_dir = tmp_path / "second"
    assert window.load_path(_write_preview_scenario(second_dir))
    assert window.wafer_map_panel.map_view.wafer is None
    assert window.distribution_panel.histogram is None


def test_preview_values_match_the_exported_csv(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_preview_scenario(tmp_path))
    _generate(window, qtbot)
    out_dir = tmp_path / "exported"
    assert window.export_to_directory(out_dir)

    panel = window.wafer_map_panel
    assert panel.select_color_mode("item")
    assert panel.select_item("CP_VTHN")
    view = panel.map_view
    wafer = view.wafer
    assert wafer is not None

    csv_path = next(
        path
        for path in window.last_export_paths
        if path.suffix == ".csv" and "_CP_" in path.name
    )
    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = [
            row
            for row in csv.DictReader(stream)
            if row["item_id"] == "CP_VTHN" and row["wafer_id"] == wafer.wafer_id
        ]
    assert len(rows) == wafer.die_count
    csv_values = {(int(row["grid_x"]), int(row["grid_y"])): row["value"] for row in rows}
    for die_index in range(wafer.die_count):
        key = (int(wafer.grid_x[die_index]), int(wafer.grid_y[die_index]))
        expected = csv_values[key]
        assert format_float(view.display_value(die_index)) == expected
        assert expected in view.die_tooltip(die_index)

    window.distribution_panel.set_item("CP_VTHN")
    histogram = window.distribution_panel.histogram
    assert histogram is not None
    assert histogram.sampled_count == len(rows)
    assert int(histogram.counts.sum()) == len(rows)


def test_injected_spatial_pattern_is_visible_on_the_map(
    qtbot: QtBot, tmp_path: Path
) -> None:
    patterns = [
        {
            "kind": "center_high",
            "scope": "lot",
            "target_item": "CP_VTHN",
            "amplitude": 0.6,
            "radius_mm": 45.0,
        }
    ]
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_preview_scenario(tmp_path, patterns=patterns))
    _generate(window, qtbot)

    panel = window.wafer_map_panel
    assert panel.select_color_mode("item")
    assert panel.select_item("CP_VTHN")
    view = panel.map_view
    wafer = view.wafer
    assert wafer is not None
    radius = np.hypot(wafer.x_mm, wafer.y_mm)
    values = np.array(
        [view.display_value(die_index) for die_index in range(wafer.die_count)]
    )
    centre = values[radius <= 20.0]
    edge = values[radius >= 55.0]
    assert centre.size > 0
    assert edge.size > 0
    assert centre.mean() > edge.mean() + 0.1

    centre_die = int(np.argmin(radius))
    edge_die = int(np.argmax(radius))
    centre_colour = view.die_color(centre_die)
    edge_colour = view.die_color(edge_die)
    assert centre_colour != edge_colour
    assert centre_colour.hue() < edge_colour.hue()
