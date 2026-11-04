"""Tests for the GUI correlation scatter and lot/wafer trend previews."""

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from pytestqt.qtbot import QtBot

from silicondraft.catalog import CatalogItem
from silicondraft.dataset import (
    CPLot,
    CPWafer,
    GenerationResult,
    LinkageReportEntry,
    WatLot,
    WatWafer,
)
from silicondraft.scenario.models import Product, Scenario

_TIMESTAMP = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _item(item_id: str, phase: str, test_num: int, unit: str = "V") -> CatalogItem:
    return CatalogItem(
        id=item_id,
        phase=phase,  # type: ignore[arg-type]
        test_num=test_num,
        description=f"{item_id} measurement",
        unit=unit,
        typical=0.5,
        lsl=-1.0,
        usl=2.0,
        distribution="normal",
    )


def _wat_wafer(
    wafer_id: str,
    *,
    x_mm: list[float],
    y_mm: list[float],
    values: dict[str, list[float]],
) -> WatWafer:
    site_count = len(x_mm)
    return WatWafer(
        wafer_id=wafer_id,
        site_number=np.arange(1, site_count + 1, dtype=np.int64),
        x_mm=np.array(x_mm, dtype=np.float64),
        y_mm=np.array(y_mm, dtype=np.float64),
        values={item_id: np.array(column, dtype=np.float64) for item_id, column in values.items()},
        tested_at=_TIMESTAMP,
    )


def _cp_wafer(
    wafer_id: str,
    *,
    x_mm: list[float],
    y_mm: list[float],
    passed: list[bool],
    values: dict[str, list[float]],
) -> CPWafer:
    die_count = len(x_mm)
    passed_array = np.array(passed, dtype=bool)
    return CPWafer(
        wafer_id=wafer_id,
        x_mm=np.array(x_mm, dtype=np.float64),
        y_mm=np.array(y_mm, dtype=np.float64),
        grid_x=np.arange(die_count, dtype=np.int64),
        grid_y=np.zeros(die_count, dtype=np.int64),
        test_site=np.ones(die_count, dtype=np.int64),
        hard_bin=np.where(passed_array, 1, 2).astype(np.int64),
        soft_bin=np.where(passed_array, 100, 203).astype(np.int64),
        passed=passed_array,
        values={item_id: np.array(column, dtype=np.float64) for item_id, column in values.items()},
        factors=np.zeros((2, die_count), dtype=np.float64),
        pattern_hits={},
        defect_failure=np.zeros(die_count, dtype=bool),
        defect_clusters=(),
        tested_at=_TIMESTAMP,
    )


def _entry(
    wat_item: str,
    cp_item: str,
    *,
    target_r: float,
    achieved_r: float,
    observed_r: float,
    sample_count: int,
) -> LinkageReportEntry:
    return LinkageReportEntry(
        wat_item=wat_item,
        cp_item=cp_item,
        factor="F_VT",
        target_r=target_r,
        achieved_r=achieved_r,
        observed_r=observed_r,
        sample_count=sample_count,
    )


def _correlation_result() -> GenerationResult:
    """Two dies at x=0 and x=10; WAT sites sit next to their matching die."""
    cp_wafer = _cp_wafer(
        "W01",
        x_mm=[0.0, 10.0],
        y_mm=[0.0, 0.0],
        passed=[True, True],
        values={"CP_VTHN": [0.1, 0.9], "CP_IONN": [20.0, 40.0]},
    )
    wat_wafer = _wat_wafer(
        "W01",
        x_mm=[0.5, 9.5],
        y_mm=[0.0, 0.0],
        values={"WAT_VTN": [1.0, 2.0], "WAT_IDSATN": [50.0, 70.0]},
    )
    return GenerationResult(
        scenario=Scenario(schema_version=1, product=Product(name="TEST55"), seed=7),
        items=(
            _item("CP_VTHN", "CP", 2001),
            _item("CP_IONN", "CP", 2002, unit="uA/um"),
        ),
        wat_items=(
            _item("WAT_VTN", "WAT", 1001),
            _item("WAT_IDSATN", "WAT", 1003, unit="uA/um"),
        ),
        lots=(CPLot("TEST55-L001", (cp_wafer,)),),
        wat_lots=(WatLot("TEST55-L001", (wat_wafer,)),),
        linkage_report=(
            _entry(
                "WAT_VTN",
                "CP_VTHN",
                target_r=0.8,
                achieved_r=0.79,
                observed_r=1.0,
                sample_count=2,
            ),
            _entry(
                "WAT_IDSATN",
                "CP_IONN",
                target_r=-0.45,
                achieved_r=-0.44,
                observed_r=-1.0,
                sample_count=2,
            ),
        ),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def test_correlation_panel_plots_the_selected_pair_and_annotates_target_r(
    qtbot: QtBot,
) -> None:
    from silicondraft.gui.correlation import CorrelationPanel

    panel = CorrelationPanel()
    qtbot.addWidget(panel)

    panel.set_result(_correlation_result())

    assert panel.pair_keys == (("WAT_VTN", "CP_VTHN"), ("WAT_IDSATN", "CP_IONN"))
    assert panel.pair == ("WAT_VTN", "CP_VTHN")
    assert panel.pair_combo.currentText() == "WAT_VTN ↔ CP_VTHN"
    linkage = panel.linkage
    assert linkage is not None
    assert linkage.wat_values == pytest.approx([1.0, 2.0])
    assert linkage.cp_values == pytest.approx([0.1, 0.9])
    assert linkage.sample_count == 2
    assert np.corrcoef(linkage.wat_values, linkage.cp_values)[0, 1] == pytest.approx(
        panel.observed_r
    )
    assert panel.target_r == pytest.approx(0.8)
    assert panel.achieved_r == pytest.approx(0.79)
    assert panel.observed_r == pytest.approx(1.0)

    assert panel.target_label.text() == "target r = +0.800"
    assert "achieved r = +0.790" in panel.summary_label.text()
    assert "+0.800" in panel.annotation.toPlainText()
    assert panel.displayed_point_count == 2

    assert panel.select_pair("WAT_IDSATN", "CP_IONN")
    assert panel.pair == ("WAT_IDSATN", "CP_IONN")
    assert panel.pair_combo.currentText() == "WAT_IDSATN ↔ CP_IONN"
    linkage = panel.linkage
    assert linkage is not None
    assert linkage.wat_values == pytest.approx([50.0, 70.0])
    assert linkage.cp_values == pytest.approx([20.0, 40.0])
    assert panel.target_r == pytest.approx(-0.45)
    assert panel.target_label.text() == "target r = -0.450"

    assert not panel.select_pair("WAT_VTN", "CP_IONN")
    assert panel.pair == ("WAT_IDSATN", "CP_IONN")


def _empty_result() -> GenerationResult:
    source = _correlation_result()
    return GenerationResult(
        scenario=source.scenario,
        items=source.items,
        wat_items=(),
        lots=source.lots,
        wat_lots=(),
        linkage_report=(),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def _large_correlation_result(site_count: int) -> GenerationResult:
    coordinates = [float(index) for index in range(site_count)]
    cp_wafer = _cp_wafer(
        "W01",
        x_mm=coordinates,
        y_mm=[0.0] * site_count,
        passed=[True] * site_count,
        values={"CP_VTHN": [float(index) * 2.0 for index in range(site_count)]},
    )
    wat_wafer = _wat_wafer(
        "W01",
        x_mm=coordinates,
        y_mm=[0.0] * site_count,
        values={"WAT_VTN": [float(index) for index in range(site_count)]},
    )
    return GenerationResult(
        scenario=Scenario(schema_version=1, product=Product(name="TEST55"), seed=7),
        items=(_item("CP_VTHN", "CP", 2001),),
        wat_items=(_item("WAT_VTN", "WAT", 1001),),
        lots=(CPLot("TEST55-L001", (cp_wafer,)),),
        wat_lots=(WatLot("TEST55-L001", (wat_wafer,)),),
        linkage_report=(
            _entry(
                "WAT_VTN",
                "CP_VTHN",
                target_r=0.8,
                achieved_r=0.79,
                observed_r=1.0,
                sample_count=site_count,
            ),
        ),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def test_correlation_panel_shows_empty_states_and_clears(qtbot: QtBot) -> None:
    from silicondraft.gui.correlation import CorrelationPanel

    panel = CorrelationPanel()
    qtbot.addWidget(panel)

    assert panel.empty_message == "No generation result yet."
    panel.set_result(None)
    assert panel.message_label.text() == "No generation result yet."

    panel.set_result(_empty_result())

    assert panel.pair_keys == ()
    assert panel.pair is None
    assert panel.linkage is None
    assert panel.target_r is None
    assert panel.achieved_r is None
    assert panel.observed_r is None
    assert panel.displayed_point_count == 0
    assert panel.target_label.text() == ""
    assert panel.annotation.toPlainText() == ""
    assert panel.empty_message == "No WAT linkage data to preview."
    assert panel.message_label.text() == panel.empty_message
    assert panel.message_label.isVisibleTo(panel)

    panel.set_result(_correlation_result())
    assert panel.message_label.text() == ""
    assert not panel.message_label.isVisibleTo(panel)

    panel.set_result(None)
    assert panel.pair_keys == ()
    assert panel.linkage is None


def test_correlation_panel_downsamples_large_scatters(qtbot: QtBot) -> None:
    from silicondraft.gui.correlation import CorrelationPanel

    panel = CorrelationPanel(max_points=10)
    qtbot.addWidget(panel)

    panel.set_result(_large_correlation_result(100))

    assert panel.sample_count == 100
    assert panel.displayed_point_count == 10
    assert panel.observed_r == pytest.approx(1.0)
    assert panel.scatter_x.size == 10
    assert panel.scatter_y.size == 10
    assert panel.scatter_x[0] == pytest.approx(0.0)
    assert panel.scatter_x[-1] == pytest.approx(99.0)
    assert panel.scatter_y == pytest.approx(panel.scatter_x * 2.0)


def _trend_result() -> GenerationResult:
    lot_wafers = {
        "TEST55-L001": (
            _cp_wafer(
                "W01",
                x_mm=[0.0, 10.0, 20.0, 30.0],
                y_mm=[0.0, 0.0, 0.0, 0.0],
                passed=[True, True, False, False],
                values={"CP_VTHN": [10.0, 20.0, 30.0, 40.0]},
            ),
            _cp_wafer(
                "W02",
                x_mm=[0.0, 10.0, 20.0, 30.0],
                y_mm=[0.0, 0.0, 0.0, 0.0],
                passed=[True, True, True, True],
                values={"CP_VTHN": [50.0, 60.0, 70.0, 80.0]},
            ),
        ),
        "TEST55-L002": (
            _cp_wafer(
                "W01",
                x_mm=[0.0, 10.0, 20.0, 30.0],
                y_mm=[0.0, 0.0, 0.0, 0.0],
                passed=[True, False, False, False],
                values={"CP_VTHN": [90.0, 100.0, 110.0, 120.0]},
            ),
            _cp_wafer(
                "W02",
                x_mm=[0.0, 10.0, 20.0, 30.0],
                y_mm=[0.0, 0.0, 0.0, 0.0],
                passed=[True, True, True, False],
                values={"CP_VTHN": [130.0, 140.0, 150.0, 160.0]},
            ),
        ),
    }
    wat_values = {
        "TEST55-L001": ([1.0, 2.0], [3.0, 4.0]),
        "TEST55-L002": ([5.0, 6.0], [7.0, 8.0]),
    }
    lots: list[CPLot] = []
    wat_lots: list[WatLot] = []
    for lot_id, wafers in lot_wafers.items():
        lots.append(CPLot(lot_id, wafers))
        wat_lots.append(
            WatLot(
                lot_id,
                tuple(
                    _wat_wafer(
                        wafer.wafer_id,
                        x_mm=[0.0, 10.0],
                        y_mm=[0.0, 0.0],
                        values={"WAT_VTN": list(values)},
                    )
                    for wafer, values in zip(wafers, wat_values[lot_id], strict=True)
                ),
            )
        )
    return GenerationResult(
        scenario=Scenario(schema_version=1, product=Product(name="TEST55"), seed=7),
        items=(_item("CP_VTHN", "CP", 2001),),
        wat_items=(_item("WAT_VTN", "WAT", 1001),),
        lots=tuple(lots),
        wat_lots=tuple(wat_lots),
        linkage_report=(
            _entry(
                "WAT_VTN",
                "CP_VTHN",
                target_r=0.8,
                achieved_r=0.79,
                observed_r=0.9,
                sample_count=8,
            ),
        ),
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def _single_lot_result() -> GenerationResult:
    source = _trend_result()
    return GenerationResult(
        scenario=source.scenario,
        items=source.items,
        wat_items=source.wat_items,
        lots=source.lots[:1],
        wat_lots=source.wat_lots[:1],
        linkage_report=source.linkage_report,
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )


def test_trend_panel_switches_between_lot_and_wafer_yield(qtbot: QtBot) -> None:
    from silicondraft.gui.trend import TrendPanel

    panel = TrendPanel()
    qtbot.addWidget(panel)

    panel.set_result(_trend_result())

    assert panel.metric_keys == ("yield", "WAT_VTN|CP_VTHN")
    assert panel.metric_key == "yield"
    assert panel.view_combo.currentData() == "wafer"
    assert list(panel.labels) == [
        "TEST55-L001 / W01",
        "TEST55-L001 / W02",
        "TEST55-L002 / W01",
        "TEST55-L002 / W02",
    ]
    assert len(panel.series) == 1
    assert panel.series[0].name == "Yield"
    assert panel.series[0].values == pytest.approx([0.5, 1.0, 0.25, 0.75])
    assert panel.series[0].plot_values == pytest.approx([50.0, 100.0, 25.0, 75.0])
    assert panel.point_count == 4
    assert panel.empty_message is None

    assert panel.set_view_mode("lot")

    assert panel.view_mode == "lot"
    assert list(panel.labels) == ["TEST55-L001", "TEST55-L002"]
    assert panel.series[0].values == pytest.approx([0.75, 0.5])
    assert panel.point_count == 2
    assert panel.empty_message is None


def test_trend_panel_shows_empty_state_for_a_single_lot(qtbot: QtBot) -> None:
    from silicondraft.gui.trend import TrendPanel

    panel = TrendPanel()
    qtbot.addWidget(panel)

    panel.set_result(_single_lot_result())
    assert panel.point_count == 2
    assert panel.empty_message is None

    assert panel.set_view_mode("lot")

    assert list(panel.labels) == []
    assert panel.series == ()
    assert panel.point_count == 0
    assert panel.empty_message == "At least two lots are required for a lot-level trend."
    assert panel.message_label.text() == panel.empty_message
    assert panel.message_label.isVisibleTo(panel)

    assert panel.set_view_mode("wafer")
    assert panel.point_count == 2
    assert panel.empty_message is None
    assert not panel.message_label.isVisibleTo(panel)


def test_trend_panel_plots_linkage_pair_means_by_lot_and_wafer(qtbot: QtBot) -> None:
    from silicondraft.gui.trend import TrendPanel

    panel = TrendPanel()
    qtbot.addWidget(panel)

    panel.set_result(_trend_result())
    assert panel.set_metric("WAT_VTN|CP_VTHN")
    assert panel.metric_key == "WAT_VTN|CP_VTHN"
    assert [series.name for series in panel.series] == ["WAT_VTN", "CP_VTHN"]
    assert "WAT_VTN" in panel.series_label.text()
    assert "CP_VTHN" in panel.series_label.text()
    assert panel.series[0].values == pytest.approx([1.5, 3.5, 5.5, 7.5])
    assert panel.series[1].values == pytest.approx([15.0, 55.0, 95.0, 135.0])
    assert panel.series[0].unit == "V"
    assert panel.series[1].unit == "V"
    z_scores = np.array([-1.3416407865, -0.4472135955, 0.4472135955, 1.3416407865])
    assert panel.series[0].plot_values == pytest.approx(z_scores)
    assert panel.series[1].plot_values == pytest.approx(z_scores)
    assert panel.y_axis_label == "Standardized (z-score)"

    assert panel.set_view_mode("lot")

    assert list(panel.labels) == ["TEST55-L001", "TEST55-L002"]
    assert panel.series[0].values == pytest.approx([2.5, 6.5])
    assert panel.series[1].values == pytest.approx([35.0, 115.0])
    assert panel.series[0].plot_values == pytest.approx([-1.0, 1.0])
    assert panel.series[1].plot_values == pytest.approx([-1.0, 1.0])

    assert panel.set_metric("yield")
    assert panel.y_axis_label == "Yield (%)"
    assert panel.series[0].values == pytest.approx([0.75, 0.5])


def _write_gui_scenario(
    tmp_path: Path,
    *,
    lot_count: int = 2,
    wafers_per_lot: int = 1,
    preset: str | None = None,
) -> Path:
    import yaml

    document = {
        "schema_version": 1,
        "product": {"name": "TEST55"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": lot_count, "wafers_per_lot": wafers_per_lot},
        "export": {
            "cp_csv": False,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": 20260105,
    }
    if preset is not None:
        document["preset"] = preset
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_generation_fills_correlation_and_trend_tabs(qtbot: QtBot, tmp_path: Path) -> None:
    from silicondraft.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(_write_gui_scenario(tmp_path))

    titles = [window.preview_tabs.tabText(index) for index in range(window.preview_tabs.count())]
    assert "Correlation" in titles
    assert "Trend" in titles
    assert window.correlation_panel.pair_keys == ()
    assert window.trend_panel.point_count == 0

    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)

    result = window.last_result
    assert result is not None
    panel = window.correlation_panel
    assert panel.pair_keys == tuple(
        (entry.wat_item, entry.cp_item) for entry in result.linkage_report
    )
    entry = result.linkage_report[0]
    assert panel.pair == (entry.wat_item, entry.cp_item)
    assert panel.linkage is not None
    assert panel.linkage.sample_count == entry.sample_count
    assert panel.target_r == pytest.approx(entry.target_r)
    assert panel.achieved_r == pytest.approx(entry.achieved_r)
    assert panel.observed_r == pytest.approx(entry.observed_r, abs=1e-10)
    assert panel.target_label.text() == f"target r = {entry.target_r:+.3f}"

    trend = window.trend_panel
    assert trend.point_count == 2
    assert trend.set_view_mode("lot")
    assert list(trend.labels) == [lot.lot_id for lot in result.lots]
    assert trend.series[0].values == pytest.approx([lot.yield_fraction for lot in result.lots])

    other = tmp_path / "other"
    assert window.load_path(_write_gui_scenario(other, lot_count=1))
    assert window.correlation_panel.pair_keys == ()
    assert window.correlation_panel.linkage is None
    assert window.trend_panel.point_count == 0


def test_trend_preset_drives_the_lot_and_wafer_views(qtbot: QtBot, tmp_path: Path) -> None:
    from silicondraft.gui.main_window import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.load_path(
        _write_gui_scenario(tmp_path, lot_count=5, wafers_per_lot=25, preset="trend")
    )

    with qtbot.waitSignal(window.generation_succeeded, timeout=30000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3000)

    result = window.last_result
    assert result is not None
    assert len(result.lots) == 5
    assert sum(len(lot.wafers) for lot in result.lots) == 125
    trend = window.trend_panel
    assert trend.point_count == 125
    assert trend.labels[0] == f"{result.lots[0].lot_id} / {result.lots[0].wafers[0].wafer_id}"
    assert trend.labels[25] == f"{result.lots[1].lot_id} / {result.lots[1].wafers[0].wafer_id}"

    assert trend.set_view_mode("lot")
    assert list(trend.labels) == [lot.lot_id for lot in result.lots]
    assert trend.series[0].values == pytest.approx([lot.yield_fraction for lot in result.lots])

    assert trend.set_view_mode("wafer")
    assert trend.point_count == 125


def test_correlation_panel_reports_missing_wat_values_for_a_configured_pair(
    qtbot: QtBot,
) -> None:
    from silicondraft.gui.correlation import CorrelationPanel

    source = _correlation_result()
    result = GenerationResult(
        scenario=source.scenario,
        items=source.items,
        wat_items=source.wat_items,
        lots=source.lots,
        wat_lots=(),
        linkage_report=source.linkage_report,
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )
    panel = CorrelationPanel()
    qtbot.addWidget(panel)

    panel.set_result(result)

    assert panel.pair_keys == (("WAT_VTN", "CP_VTHN"), ("WAT_IDSATN", "CP_IONN"))
    assert panel.linkage is None
    assert panel.observed_r is None
    assert panel.empty_message == "No WAT data for this pair."
    assert panel.message_label.text() == panel.empty_message
    assert panel.message_label.isVisibleTo(panel)


def test_trend_panel_notes_missing_wat_linkage(qtbot: QtBot) -> None:
    from silicondraft.gui.trend import TrendPanel

    panel = TrendPanel()
    qtbot.addWidget(panel)

    panel.set_result(_empty_result())

    assert panel.metric_keys == ("yield",)
    assert panel.notice == "No WAT linkage data to trend."
    assert panel.notice_label.text() == panel.notice
    assert panel.notice_label.isVisibleTo(panel)
    assert panel.point_count == 1
    assert panel.empty_message is None

    panel.set_result(None)
    assert panel.notice is None
    assert not panel.notice_label.isVisibleTo(panel)


def test_correlation_panel_does_not_truncate_misaligned_wat_and_cp_lots(
    qtbot: QtBot,
) -> None:
    from silicondraft.gui.correlation import CorrelationPanel

    source = _trend_result()
    result = GenerationResult(
        scenario=source.scenario,
        items=source.items,
        wat_items=source.wat_items,
        lots=source.lots,
        wat_lots=source.wat_lots[:1],
        linkage_report=source.linkage_report,
        pattern_reports=(),
        generated_at=_TIMESTAMP,
    )
    panel = CorrelationPanel()
    qtbot.addWidget(panel)

    panel.set_result(result)

    assert panel.linkage is None
    assert panel.observed_r is None
    assert panel.empty_message == "No WAT data for this pair."


def test_trend_series_z_scores_preserve_direction_for_negative_means() -> None:
    from silicondraft.gui.trend import TrendSeries

    series = TrendSeries(
        name="WAT_VTP",
        unit="V",
        values=np.array([-0.40, -0.35, -0.30], dtype=np.float64),
        relative=True,
    )

    plot_values = series.plot_values
    assert plot_values[0] < plot_values[1] < plot_values[2]
    assert plot_values[1] == pytest.approx(0.0)

    flat = TrendSeries(
        name="FLAT",
        unit="V",
        values=np.array([0.0, 0.0, 0.0], dtype=np.float64),
        relative=True,
    )
    assert flat.plot_values == pytest.approx([0.0, 0.0, 0.0])
