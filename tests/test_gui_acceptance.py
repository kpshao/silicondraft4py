"""End-to-end GUI acceptance test: configure → generate → preview → export."""

import json
from pathlib import Path
from typing import Any

import yaml
from pystdf.IO import Parser
from pytestqt.qtbot import QtBot

from silicondraft.gui.main_window import MainWindow


class _RecordSink:
    """Collect the record names of a parsed STDF file."""

    def __init__(self) -> None:
        self.names: list[str] = []

    def after_send(self, data_source: object, data: tuple[Any, list[Any]]) -> None:
        record, _values = data
        self.names.append(record.__class__.__name__.upper())


def _write_demo_scenario(tmp_path: Path) -> Path:
    document = {
        "schema_version": 1,
        "preset": "demo",
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {
            "count": 1,
            "wafers_per_lot": 2,
            "start_date": "2026-01-05T08:00:00",
        },
        "seed": 20260105,
    }
    path = tmp_path / "acceptance.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_gui_completes_configure_generate_preview_export(qtbot: QtBot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()

    # configure: load a preset-based scenario through the same path as Open...
    assert window.load_path(_write_demo_scenario(tmp_path))
    assert window.scenario is not None
    assert window.scenario.preset == "demo"
    assert window.export_action.isEnabled() is False

    # live language switch, no restart
    assert window.set_language("zh_CN")
    assert window.preview_tabs.tabText(0) == "晶圆图"
    assert window.set_language("en")
    assert window.preview_tabs.tabText(0) == "Wafer Map"

    # generate in the worker thread
    with qtbot.waitSignal(window.generation_succeeded, timeout=30_000):
        assert window.start_generation()
    qtbot.waitUntil(lambda: not window.generation_running, timeout=3_000)

    result = window.last_result
    assert result is not None
    assert len(result.lots) == 1
    assert len(result.lots[0].wafers) == 2

    # preview: every panel is populated from the generated result
    wafer = window.wafer_map_panel.map_view.wafer
    assert wafer is not None
    assert wafer.wafer_id == result.lots[0].wafers[0].wafer_id
    assert window.distribution_panel.histogram is not None
    assert window.correlation_panel.pair_keys
    assert window.trend_panel.point_count == 2
    assert window.results_panel.model.total_rows > 0

    # export: all artifacts the scenario enables
    out_dir = tmp_path / "exported"
    assert window.export_to_directory(out_dir)
    names = sorted(path.suffix for path in window.last_export_paths)
    assert len(window.last_export_paths) == 5
    assert names.count(".stdf") == 1
    assert names.count(".csv") == 2
    assert names.count(".gz") == 1
    assert names.count(".json") == 1

    stdf_path = next(path for path in window.last_export_paths if path.suffix == ".stdf")
    sink = _RecordSink()
    with stdf_path.open("rb") as stream:
        parser = Parser(inp=stream)
        parser.addSink(sink)
        parser.parse()
    assert sink.names[0] == "FAR"
    assert sink.names[-1] == "MRR"
    assert sink.names.count("WIR") == 2
    assert sink.names.count("PRR") == sum(
        wafer.die_count for lot in result.lots for wafer in lot.wafers
    )

    manifest_path = next(path for path in window.last_export_paths if path.suffix == ".json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["seed"] == 20260105
    assert len(manifest["die_truth_files"]) == 1
    assert {entry["id"] for entry in manifest["patterns"]} == {
        "pattern_1",
        "pattern_2",
        "pattern_3",
        "pattern_4",
    }

    assert "Exported" in window.statusBar().currentMessage()
