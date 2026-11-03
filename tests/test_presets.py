"""Built-in scenario presets: quick, trend, and demo."""

from pathlib import Path
from typing import Any

import yaml

from silicondraft import generate, load_scenario, validate_scenario
from silicondraft.cli import main


def _write_scenario(tmp_path: Path, document: dict[str, Any]) -> Path:
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _preset_document(preset: str, **lots: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 1,
        "preset": preset,
        "product": {"name": "GEN55LOGIC"},
        "seed": 20260105,
    }
    if lots:
        document["lots"] = lots
    return document


def test_quick_preset_defaults_to_one_lot_of_25_wafers(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, _preset_document("quick")))

    assert scenario.preset == "quick"
    assert scenario.lots.count == 1
    assert scenario.lots.wafers_per_lot == 25
    assert scenario.patterns == []


def test_trend_preset_spans_five_lots_across_dates(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, _preset_document("trend")))

    assert scenario.preset == "trend"
    assert scenario.lots.count == 5
    assert scenario.lots.wafers_per_lot == 25
    assert scenario.lots.start_date is not None
    assert scenario.lots.lot_interval_hours > 0
    assert scenario.patterns == []


def test_trend_preset_generates_five_lots_of_25_wafers(tmp_path: Path) -> None:
    document = _preset_document("trend")
    document["export"] = {
        "cp_csv": False,
        "wat_csv": False,
        "ground_truth": False,
        "include_die_truth": False,
    }
    result = generate(load_scenario(_write_scenario(tmp_path, document)))

    assert len(result.lots) == 5
    assert all(len(lot.wafers) == 25 for lot in result.lots)
    assert len(result.wat_lots) == 5


def test_demo_preset_injects_patterns_and_strong_linkage(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, _preset_document("demo")))

    assert scenario.preset == "demo"
    assert scenario.lots.count == 1
    assert scenario.lots.wafers_per_lot == 25
    assert len(scenario.patterns) >= 3
    assert {pattern.kind for pattern in scenario.patterns} >= {
        "edge_low",
        "center_high",
        "local_spot",
    }
    assert scenario.linkage.overrides
    assert scenario.export.ground_truth is True
    assert scenario.export.include_die_truth is True


def test_explicit_values_override_preset_defaults(tmp_path: Path) -> None:
    document = _preset_document("trend", count=2)
    document["patterns"] = [
        {
            "kind": "edge_low",
            "target": "yield",
            "amplitude": 0.2,
            "extent_mm": 20.0,
        }
    ]
    document["defects"] = {"enabled": False}
    scenario = load_scenario(_write_scenario(tmp_path, document))

    assert scenario.lots.count == 2
    assert scenario.lots.wafers_per_lot == 25
    assert len(scenario.patterns) == 1
    assert scenario.defects.enabled is False


def test_unknown_preset_is_rejected(tmp_path: Path) -> None:
    result = validate_scenario(_write_scenario(tmp_path, _preset_document("unknown")))

    assert result.ok is False
    assert [(issue.code, issue.path) for issue in result.issues] == [("INVALID_VALUE", "preset")]


def test_every_preset_generates_through_the_cli(tmp_path: Path, capsys: Any) -> None:
    for preset in ("quick", "trend", "demo"):
        document = _preset_document(preset, wafers_per_lot=1)
        document["export"] = {
            "cp_csv": False,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        }
        scenario_path = _write_scenario(tmp_path, document)
        output_dir = tmp_path / f"out-{preset}"
        exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])
        assert exit_code == 0, preset
        capsys.readouterr()


def test_preset_supplies_a_default_product(tmp_path: Path) -> None:
    path = _write_scenario(tmp_path, {"schema_version": 1, "preset": "quick", "seed": 20260105})

    scenario = load_scenario(path)

    assert scenario.product.name == "GEN55LOGIC"


def test_validate_reports_the_resolved_preset(tmp_path: Path) -> None:
    path = _write_scenario(tmp_path, {"schema_version": 1, "preset": "trend", "seed": 20260105})

    result = validate_scenario(path)

    assert result.ok is True
    assert result.summary is not None
    assert result.summary.preset == "trend"
    assert result.summary.lots == 5
    assert result.summary.wafers == 125


def test_custom_id_templates_apply_to_every_lot(tmp_path: Path) -> None:
    document = _preset_document("trend", count=2, wafers_per_lot=2)
    document["lots"].update(
        {
            "lot_id_template": "{product}-B{lot:02d}",
            "wafer_id_template": "L{lot}-W{wafer}",
        }
    )
    document["export"] = {
        "cp_csv": False,
        "wat_csv": False,
        "ground_truth": False,
        "include_die_truth": False,
    }
    result = generate(load_scenario(_write_scenario(tmp_path, document)))

    assert [lot.lot_id for lot in result.lots] == ["GEN55LOGIC-B01", "GEN55LOGIC-B02"]
    assert [wafer.wafer_id for wafer in result.lots[0].wafers] == ["L1-W1", "L1-W2"]
    assert [wafer.wafer_id for wafer in result.lots[1].wafers] == ["L2-W1", "L2-W2"]


def test_trend_preset_generates_5x25_through_the_cli(tmp_path: Path, capsys: Any) -> None:
    document = _preset_document("trend")
    document["export"] = {
        "cp_csv": False,
        "wat_csv": False,
        "ground_truth": False,
        "include_die_truth": False,
    }
    scenario_path = _write_scenario(tmp_path, document)

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(tmp_path / "out")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "generated: 5 lot(s), 125 wafer(s), 337500 die(s)" in captured.out
