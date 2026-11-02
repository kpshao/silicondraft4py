import csv
import math
from pathlib import Path

import numpy as np
import pytest

from silicondraft import Scenario, ScenarioError, export, generate, load_scenario

SCENARIO = """\
schema_version: 1
product:
  name: GEN55LOGIC
lots:
  wafers_per_lot: 1
seed: 20260105
"""


def _write_scenario(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.yaml"
    path.write_text(SCENARIO, encoding="utf-8")
    return path


def test_generate_returns_one_row_per_die(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))

    result = generate(scenario)

    assert len(result.lots) == 1
    lot = result.lots[0]
    assert lot.lot_id == "GEN55LOGIC-L001"
    assert len(lot.wafers) == 1
    wafer = lot.wafers[0]
    assert wafer.wafer_id == "W01"
    assert len(wafer.x_mm) == 2700
    assert len(wafer.y_mm) == 2700
    assert len(wafer.grid_x) == 2700
    assert len(wafer.grid_y) == 2700
    assert len(wafer.test_site) == 2700
    assert len(wafer.hard_bin) == 2700
    assert len(wafer.passed) == 2700
    assert result.items
    assert [item.test_num for item in result.items] == sorted(
        item.test_num for item in result.items
    )
    assert all(item.phase == "CP" for item in result.items)
    for item in result.items:
        assert len(wafer.values[item.id]) == 2700


def test_export_writes_one_wide_csv_row_per_die(tmp_path: Path) -> None:
    result = generate(load_scenario(_write_scenario(tmp_path)))

    paths = export(result, tmp_path / "out")

    assert len(paths) == 1
    path = paths[0]
    assert path.exists()
    assert path.suffix == ".csv"
    assert "_CP_" in path.name
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))

    assert len(rows) == 2700
    expected_columns = [
        "lot_id",
        "wafer_id",
        "die_x_mm",
        "die_y_mm",
        "grid_x",
        "grid_y",
        "test_site",
        "hard_bin",
        "pass",
        *(item.id for item in result.items),
    ]
    assert list(rows[0]) == expected_columns
    assert {row["lot_id"] for row in rows} == {"GEN55LOGIC-L001"}
    assert {row["wafer_id"] for row in rows} == {"W01"}
    assert len({(row["grid_x"], row["grid_y"]) for row in rows}) == len(rows)

    wafer = result.lots[0].wafers[0]
    assert float(rows[0]["die_x_mm"]) == pytest.approx(float(wafer.x_mm[0]))
    assert int(rows[0]["hard_bin"]) == int(wafer.hard_bin[0])
    for item in result.items:
        assert float(rows[0][item.id]) == pytest.approx(float(wafer.values[item.id][0]), rel=1e-9)
    for row in rows:
        assert row["hard_bin"] in {"1", "2", "3", "4"}
        assert row["pass"] == ("1" if row["hard_bin"] == "1" else "0")
        assert math.isfinite(float(row["die_x_mm"]))
        assert math.isfinite(float(row["die_y_mm"]))
        for item in result.items:
            assert math.isfinite(float(row[item.id]))


def test_same_scenario_and_seed_produce_identical_data(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))

    first = generate(scenario)
    second = generate(scenario)

    first_wafer = first.lots[0].wafers[0]
    second_wafer = second.lots[0].wafers[0]
    np.testing.assert_array_equal(first_wafer.x_mm, second_wafer.x_mm)
    np.testing.assert_array_equal(first_wafer.grid_x, second_wafer.grid_x)
    np.testing.assert_array_equal(first_wafer.hard_bin, second_wafer.hard_bin)
    for item in first.items:
        np.testing.assert_array_equal(first_wafer.values[item.id], second_wafer.values[item.id])

    first_csv = export(first, tmp_path / "first")[0]
    second_csv = export(second, tmp_path / "second")[0]
    assert first_csv.read_bytes() == second_csv.read_bytes()


def test_different_seed_changes_cp_data(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    other = scenario.model_copy(update={"seed": scenario.seed + 1})

    first = generate(scenario)
    second = generate(other)

    first_values = first.lots[0].wafers[0].values["CP_VTHN"]
    second_values = second.lots[0].wafers[0].values["CP_VTHN"]
    assert not np.array_equal(first_values, second_values)


def test_generate_rejects_semantically_invalid_scenario() -> None:
    scenario = Scenario.model_validate(
        {
            "schema_version": 1,
            "product": {"name": "GEN55LOGIC"},
            "wafer": {"edge_exclusion_mm": 200},
            "seed": 1,
        }
    )

    with pytest.raises(ScenarioError) as exc_info:
        generate(scenario)

    assert [issue.code for issue in exc_info.value.issues] == ["EDGE_EXCLUSION_TOO_LARGE"]
