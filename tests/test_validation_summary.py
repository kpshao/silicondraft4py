from pathlib import Path

from silicondraft import validate_scenario


def test_validation_reports_die_and_item_summary(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\n",
        encoding="utf-8",
    )

    result = validate_scenario(path)

    assert result.ok is True
    assert result.issues == ()
    assert result.summary is not None
    summary = result.summary
    assert summary.schema_version == 1
    assert summary.product == "GEN55LOGIC"
    assert summary.lots == 1
    assert summary.wafers_per_lot == 25
    assert summary.wafers == 25
    assert summary.dies_per_wafer == 2700
    assert summary.dies_total == 67500
    assert summary.cp_items == 21
    assert summary.wat_items == 15
    assert summary.items_total == 36
