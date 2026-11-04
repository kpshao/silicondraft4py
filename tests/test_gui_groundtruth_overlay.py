"""Tests for the wafer-map ground-truth pattern overlay."""

from pathlib import Path

import numpy as np
import pytest
import yaml
from pytestqt.qtbot import QtBot

from silicondraft.gui.main_window import MainWindow
from silicondraft.gui.wafer_map import WaferMapPanel, WaferMapView


def _write_overlay_scenario(
    tmp_path: Path,
    patterns: list[dict[str, object]],
    *,
    wafers_per_lot: int = 1,
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
        "patterns": patterns,
        "export": {
            "cp_csv": False,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": 20260105,
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate_result(
    qtbot: QtBot,
    tmp_path: Path,
    patterns: list[dict[str, object]],
    *,
    wafers_per_lot: int = 1,
) -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(
        _write_overlay_scenario(tmp_path, patterns, wafers_per_lot=wafers_per_lot)
    )
    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)
    return window


def test_pattern_overlays_match_the_injected_extents(qtbot: QtBot, tmp_path: Path) -> None:
    patterns = [
        {
            "kind": "center_high",
            "target_item": "CP_VTHN",
            "amplitude": 0.4,
            "radius_mm": 45.0,
        },
        {
            "kind": "edge_high",
            "target_item": "CP_VTHN",
            "amplitude": 0.4,
            "extent_mm": 10.0,
        },
    ]
    window = _generate_result(qtbot, tmp_path, patterns)
    view = window.wafer_map_panel.map_view
    wafer = view.wafer
    assert wafer is not None

    overlays = view.pattern_overlays
    assert [(overlay.pattern_id, overlay.kind) for overlay in overlays] == [
        ("pattern_1", "center_high"),
        ("pattern_2", "edge_high"),
    ]
    center_overlay, edge_overlay = overlays
    assert center_overlay.center_mm == (0.0, 0.0)
    assert center_overlay.inner_radius_mm == 0.0
    assert center_overlay.outer_radius_mm == pytest.approx(45.0)
    assert edge_overlay.center_mm == (0.0, 0.0)
    assert edge_overlay.inner_radius_mm == pytest.approx(72.0 - 10.0)
    assert edge_overlay.outer_radius_mm == pytest.approx(72.0)

    radius = np.hypot(wafer.x_mm, wafer.y_mm)
    assert np.array_equal(wafer.pattern_hits["pattern_1"], radius < 45.0)
    assert np.array_equal(wafer.pattern_hits["pattern_2"], radius > 62.0)
    assert np.array_equal(wafer.pattern_hits["pattern_1"], radius < center_overlay.outer_radius_mm)
    assert np.array_equal(wafer.pattern_hits["pattern_2"], radius > edge_overlay.inner_radius_mm)


def test_overlay_toggle_adds_and_removes_the_overlay_layer(qtbot: QtBot, tmp_path: Path) -> None:
    patterns = [
        {
            "kind": "center_high",
            "target_item": "CP_VTHN",
            "amplitude": 0.4,
            "radius_mm": 30.0,
        }
    ]
    window = _generate_result(qtbot, tmp_path, patterns)
    view = window.wafer_map_panel.map_view

    assert not view.ground_truth_overlay
    assert len(view.scene().items()) == 1
    assert len(view.pattern_overlays) == 1

    view.set_ground_truth_overlay(True)

    assert view.ground_truth_overlay
    assert len(view.scene().items()) == 2
    assert "pattern_1" in view.overlay_text

    view.set_ground_truth_overlay(False)

    assert not view.ground_truth_overlay
    assert len(view.scene().items()) == 1
    assert view.overlay_text == ""


def test_wafer_map_panel_toggles_the_ground_truth_overlay(qtbot: QtBot, tmp_path: Path) -> None:
    patterns = [
        {
            "kind": "ring",
            "target_item": "CP_VTHN",
            "amplitude": 0.4,
            "radius_mm": 30.0,
            "width_mm": 8.0,
        }
    ]
    window = _generate_result(qtbot, tmp_path, patterns)
    panel = window.wafer_map_panel

    assert panel.overlay_checkbox.isEnabled()
    assert not panel.overlay_checkbox.isChecked()

    panel.overlay_checkbox.setChecked(True)

    assert panel.map_view.ground_truth_overlay
    assert "pattern_1" in panel.overlay_label.text()

    panel.overlay_checkbox.setChecked(False)

    assert not panel.map_view.ground_truth_overlay
    assert panel.overlay_label.text() == ""


def test_overlay_only_shows_patterns_active_on_the_current_wafer(
    qtbot: QtBot, tmp_path: Path
) -> None:
    patterns = [
        {
            "kind": "center_high",
            "scope": "wafer",
            "target_item": "CP_VTHN",
            "amplitude": 0.4,
            "radius_mm": 30.0,
        }
    ]
    window = _generate_result(qtbot, tmp_path, patterns, wafers_per_lot=2)
    view = window.wafer_map_panel.map_view
    assert view.wafer_count == 2

    active_counts = []
    for index in range(view.wafer_count):
        assert view.set_wafer(index)
        wafer = view.wafer
        assert wafer is not None
        active_counts.append(len(view.pattern_overlays))
        assert len(view.pattern_overlays) == int("pattern_1" in wafer.pattern_hits)

    assert active_counts.count(1) == 1
    assert active_counts.count(0) == 1


def test_no_patterns_means_no_overlay(qtbot: QtBot) -> None:
    panel = WaferMapPanel()
    qtbot.addWidget(panel)

    assert panel.map_view.pattern_overlays == ()
    assert not panel.overlay_checkbox.isEnabled()
    assert panel.overlay_label.text() == ""

    view = WaferMapView()
    qtbot.addWidget(view)
    view.set_ground_truth_overlay(True)
    assert view.pattern_overlays == ()
    assert len(view.scene().items()) == 1
