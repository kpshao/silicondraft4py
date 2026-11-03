"""Binning, pass/fail derivation, yields, and item overrides through the public API."""

import csv
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from silicondraft import GenerationResult, export, generate, load_scenario


def _write_scenario(
    tmp_path: Path,
    *,
    overrides: list[dict[str, Any]] | None = None,
    wafers_per_lot: int = 1,
    seed: int = 20260105,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "lots": {"wafers_per_lot": wafers_per_lot},
        "defects": {"enabled": False},
        "export": {
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": seed,
    }
    if overrides is not None:
        document["items"] = {"overrides": overrides}
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(
    tmp_path: Path,
    *,
    overrides: list[dict[str, Any]] | None = None,
    wafers_per_lot: int = 1,
    seed: int = 20260105,
) -> tuple[GenerationResult, tuple[Path, ...]]:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            overrides=overrides,
            wafers_per_lot=wafers_per_lot,
            seed=seed,
        )
    )
    result = generate(scenario)
    return result, export(result, tmp_path / "out")


def _read_blocks(path: Path) -> dict[str, list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))

    blocks: dict[str, list[list[str]]] = {}
    current: str | None = None
    for row in rows:
        if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]"):
            current = row[0]
            blocks[current] = []
        else:
            assert current is not None
            blocks[current].append(row)
    return blocks


_CP_ITEM_IDS = [
    "CP_CONT",
    "CP_FUNC",
    "CP_SCAN",
    "CP_IDDQ",
    "CP_VTHN",
    "CP_VTHP",
    "CP_IONN",
    "CP_IONP",
    "CP_IOFFN",
    "CP_IOFFP",
    "CP_IGATE",
    "CP_IIL",
    "CP_IIH",
    "CP_IOZ",
    "CP_VIL",
    "CP_VIH",
    "CP_VOL",
    "CP_VOH",
    "CP_FRO",
    "CP_RCONT",
    "CP_VDDMIN",
]


def test_csv_contains_all_21_cp_items(tmp_path: Path) -> None:
    result, paths = _generate(tmp_path)

    assert [item.id for item in result.items] == _CP_ITEM_IDS
    assert [item.test_num for item in result.items] == list(range(2001, 2022))

    blocks = _read_blocks(paths[0])
    assert [row[1] for row in blocks["[TEST_ITEMS]"][1:]] == _CP_ITEM_IDS
    assert blocks["[TEST_DATA]"][0][8:] == _CP_ITEM_IDS


def test_csv_test_data_has_hard_and_soft_bin_columns(tmp_path: Path) -> None:
    result, paths = _generate(tmp_path)
    wafer = result.lots[0].wafers[0]

    blocks = _read_blocks(paths[0])
    header = blocks["[TEST_DATA]"][0]

    assert header[:8] == [
        "die_x_mm",
        "die_y_mm",
        "grid_x",
        "grid_y",
        "test_site",
        "hard_bin",
        "soft_bin",
        "pass",
    ]
    assert len(wafer.soft_bin) == wafer.die_count
    assert int(blocks["[TEST_DATA]"][1][6]) == int(wafer.soft_bin[0])


def test_bin_definitions_include_hard_and_soft_bins(tmp_path: Path) -> None:
    _, paths = _generate(tmp_path)
    blocks = _read_blocks(paths[0])

    rows = blocks["[BIN_DEFINITIONS]"][1:]
    hard = [row for row in rows if row[0] == "HARD"]
    soft = [row for row in rows if row[0] == "SOFT"]

    assert [(row[1], row[2], row[3], row[4]) for row in hard] == [
        ("1", "PASS", "P", "1"),
        ("2", "PARAMETRIC_FAIL", "F", "2"),
        ("3", "FUNCTIONAL_FAIL", "F", "3"),
        ("4", "CONTINUITY_FAIL", "F", "4"),
    ]
    assert [(row[1], row[2], row[3], row[4]) for row in soft] == [
        ("100", "PASS", "P", "1"),
        ("201", "CONTINUITY", "F", "4"),
        ("202", "LEAKAGE", "F", "2"),
        ("203", "IDDQ", "F", "2"),
        ("204", "VTH", "F", "2"),
        ("205", "FREQUENCY", "F", "2"),
        ("206", "FUNCTIONAL_SCAN", "F", "3"),
        ("207", "OTHER_PARAMETRIC", "F", "2"),
    ]


@pytest.mark.parametrize(
    ("item_id", "override", "expected_hard", "expected_soft"),
    [
        ("CP_CONT", {"lsl": 10.0, "usl": 20.0}, 4, 201),
        ("CP_RCONT", {"lsl": 100.0, "usl": 200.0}, 4, 201),
        ("CP_FUNC", {"typical": 0.0}, 3, 206),
        ("CP_SCAN", {"typical": 0.0}, 3, 206),
        ("CP_IOFFN", {"typical": 1e6, "usl": 1.0}, 2, 202),
        ("CP_IDDQ", {"typical": 1e6, "usl": 1.0}, 2, 203),
        ("CP_VTHN", {"lsl": 1.0, "usl": 2.0}, 2, 204),
        ("CP_FRO", {"lsl": 1000.0, "usl": 1001.0}, 2, 205),
        ("CP_IONN", {"lsl": 1e6, "usl": 2e6}, 2, 207),
    ],
)
def test_failing_item_selects_the_matching_hard_and_soft_bin(
    tmp_path: Path,
    item_id: str,
    override: dict[str, Any],
    expected_hard: int,
    expected_soft: int,
) -> None:
    result, paths = _generate(tmp_path, overrides=[{"id": item_id, **override}])
    wafer = result.lots[0].wafers[0]

    assert not wafer.passed.any()
    assert np.all(wafer.hard_bin == expected_hard)
    assert np.all(wafer.soft_bin == expected_soft)

    blocks = _read_blocks(paths[0])
    rows = blocks["[TEST_DATA]"][1:]
    assert {row[5] for row in rows} == {str(expected_hard)}
    assert {row[6] for row in rows} == {str(expected_soft)}
    assert {row[7] for row in rows} == {"0"}


_CONT_FAIL = {"id": "CP_CONT", "lsl": 10.0, "usl": 20.0}
_FUNC_FAIL = {"id": "CP_FUNC", "typical": 0.0}
_LEAK_FAIL = {"id": "CP_IOFFN", "typical": 1e6, "usl": 1.0}
_IDDQ_FAIL = {"id": "CP_IDDQ", "typical": 1e6, "usl": 1.0}
_VTH_FAIL = {"id": "CP_VTHN", "lsl": 1.0, "usl": 2.0}
_FREQ_FAIL = {"id": "CP_FRO", "lsl": 1000.0, "usl": 1001.0}
_OTHER_FAIL = {"id": "CP_IONN", "lsl": 1e6, "usl": 2e6}


@pytest.mark.parametrize(
    ("overrides", "expected_hard", "expected_soft"),
    [
        ([_CONT_FAIL, _FUNC_FAIL, _VTH_FAIL], 4, 201),
        ([_FUNC_FAIL, _VTH_FAIL], 3, 206),
        ([_LEAK_FAIL, _IDDQ_FAIL, _VTH_FAIL, _FREQ_FAIL, _OTHER_FAIL], 2, 202),
        ([_IDDQ_FAIL, _VTH_FAIL, _FREQ_FAIL, _OTHER_FAIL], 2, 203),
        ([_VTH_FAIL, _FREQ_FAIL, _OTHER_FAIL], 2, 204),
        ([_FREQ_FAIL, _OTHER_FAIL], 2, 205),
        ([_OTHER_FAIL], 2, 207),
    ],
)
def test_bin_precedence_follows_hard_then_soft_severity(
    tmp_path: Path,
    overrides: list[dict[str, Any]],
    expected_hard: int,
    expected_soft: int,
) -> None:
    result, _ = _generate(tmp_path, overrides=overrides)
    wafer = result.lots[0].wafers[0]

    assert not wafer.passed.any()
    assert np.all(wafer.hard_bin == expected_hard)
    assert np.all(wafer.soft_bin == expected_soft)


def test_bernoulli_items_still_respect_configured_spec_limits(tmp_path: Path) -> None:
    result, _ = _generate(
        tmp_path,
        overrides=[{"id": "CP_FUNC", "typical": 1.0, "usl": 0.5}],
    )
    wafer = result.lots[0].wafers[0]

    assert not wafer.passed.any()
    assert np.all(wafer.hard_bin == 3)
    assert np.all(wafer.soft_bin == 206)


def test_lot_wafer_and_die_yield_summaries_are_computed_and_emitted(tmp_path: Path) -> None:
    result, paths = _generate(
        tmp_path,
        overrides=[{"id": "CP_FUNC", "typical": 0.9}],
        wafers_per_lot=2,
    )
    lot = result.lots[0]

    assert lot.die_count == sum(wafer.die_count for wafer in lot.wafers)
    assert lot.pass_count == sum(wafer.pass_count for wafer in lot.wafers)
    assert 0 < lot.pass_count < lot.die_count
    assert lot.yield_fraction == pytest.approx(lot.pass_count / lot.die_count)

    for wafer in lot.wafers:
        assert wafer.pass_count == int(wafer.passed.sum())
        assert wafer.pass_count + int((~wafer.passed).sum()) == wafer.die_count
        assert wafer.yield_fraction == pytest.approx(wafer.pass_count / wafer.die_count)

    wafers = {wafer.wafer_id: wafer for wafer in lot.wafers}
    for path in paths:
        blocks = _read_blocks(path)
        metadata = dict(blocks["[METADATA]"][1:])
        rows = blocks["[TEST_DATA]"][1:]
        wafer = wafers[metadata["wafer_id"]]

        assert metadata["die_count"] == str(wafer.die_count)
        assert metadata["pass_count"] == str(wafer.pass_count)
        assert metadata["lot_die_count"] == str(lot.die_count)
        assert metadata["lot_pass_count"] == str(lot.pass_count)
        assert float(metadata["lot_yield"]) == pytest.approx(lot.yield_fraction)
        assert float(metadata["yield"]) == pytest.approx(
            int(metadata["pass_count"]) / int(metadata["die_count"])
        )
        assert sum(int(row[7]) for row in rows) == int(metadata["pass_count"])


def test_hard_and_soft_bin_pareto_are_complete_sorted_and_consistent_with_yield(
    tmp_path: Path,
) -> None:
    result, _ = _generate(tmp_path, overrides=[{"id": "CP_FUNC", "typical": 0.9}])
    wafer = result.lots[0].wafers[0]

    hard = wafer.hard_bin_pareto
    soft = wafer.soft_bin_pareto

    assert sum(entry.count for entry in hard) == wafer.die_count
    assert sum(entry.count for entry in soft) == wafer.die_count
    assert [entry.count for entry in hard] == sorted((entry.count for entry in hard), reverse=True)
    assert [entry.count for entry in soft] == sorted((entry.count for entry in soft), reverse=True)

    hard_pass = next(entry for entry in hard if entry.definition.number == 1)
    soft_pass = next(entry for entry in soft if entry.definition.number == 100)
    assert hard_pass.count == soft_pass.count == wafer.pass_count
    assert hard_pass.fraction_of_dies == pytest.approx(wafer.yield_fraction)
    assert soft_pass.fraction_of_dies == pytest.approx(wafer.yield_fraction)

    soft_by_hard: dict[int, int] = {}
    for entry in soft:
        hard_bin = entry.definition.hard_bin
        soft_by_hard[hard_bin] = soft_by_hard.get(hard_bin, 0) + entry.count
    assert soft_by_hard == {entry.definition.number: entry.count for entry in hard}


def test_removed_item_is_absent_from_the_generated_output(tmp_path: Path) -> None:
    result, paths = _generate(tmp_path, overrides=[{"id": "CP_FRO", "remove": True}])

    assert "CP_FRO" not in {item.id for item in result.items}
    assert len(result.items) == 20

    blocks = _read_blocks(paths[0])
    assert "CP_FRO" not in {row[1] for row in blocks["[TEST_ITEMS]"][1:]}
    assert "CP_FRO" not in blocks["[TEST_DATA]"][0]
    assert "CP_FRO" not in result.lots[0].wafers[0].values


def test_added_item_appears_in_the_output_and_participates_in_binning(tmp_path: Path) -> None:
    result, paths = _generate(
        tmp_path,
        overrides=[
            {
                "id": "CP_CUSTOM",
                "phase": "CP",
                "test_num": 2100,
                "unit": "V",
                "typical": 5.0,
                "lsl": 10.0,
                "usl": 20.0,
                "distribution": "normal",
                "description": "Custom parametric check",
            }
        ],
    )
    wafer = result.lots[0].wafers[0]

    custom = next(item for item in result.items if item.id == "CP_CUSTOM")
    assert custom.test_num == 2100
    assert len(wafer.values["CP_CUSTOM"]) == wafer.die_count
    assert np.all(wafer.values["CP_CUSTOM"] < 10.0)
    assert np.all(wafer.hard_bin == 2)
    assert np.all(wafer.soft_bin == 207)

    blocks = _read_blocks(paths[0])
    item_rows = {row[1]: row for row in blocks["[TEST_ITEMS]"][1:]}
    assert item_rows["CP_CUSTOM"][:6] == ["2100", "CP_CUSTOM", "V", "5", "10", "20"]
    assert item_rows["CP_CUSTOM"][6] == "Custom parametric check"
    assert "CP_CUSTOM" in blocks["[TEST_DATA]"][0]


def test_modified_spec_limit_changes_failures_and_output(tmp_path: Path) -> None:
    baseline, baseline_paths = _generate(tmp_path)
    baseline_wafer = baseline.lots[0].wafers[0]
    baseline_path = baseline_paths[0]

    modified, modified_paths = _generate(
        tmp_path,
        overrides=[{"id": "CP_VTHN", "lsl": 1.0, "usl": 2.0}],
    )
    modified_wafer = modified.lots[0].wafers[0]

    assert baseline_wafer.pass_count > 0
    assert modified_wafer.pass_count == 0
    assert np.all(modified_wafer.soft_bin == 204)

    baseline_blocks = _read_blocks(baseline_path)
    modified_blocks = _read_blocks(modified_paths[0])
    baseline_items = {row[1]: row for row in baseline_blocks["[TEST_ITEMS]"][1:]}
    modified_items = {row[1]: row for row in modified_blocks["[TEST_ITEMS]"][1:]}
    assert baseline_items["CP_VTHN"][4:6] == ["0.28", "0.42"]
    assert modified_items["CP_VTHN"][4:6] == ["1", "2"]


_LOGNORMAL_CP_ITEMS = {
    "CP_IDDQ",
    "CP_IOFFN",
    "CP_IOFFP",
    "CP_IGATE",
    "CP_IIL",
    "CP_IIH",
    "CP_IOZ",
}


@pytest.mark.parametrize("seed", [0, 20260105, 2**64 - 1])
def test_builtin_lognormal_items_are_always_positive(tmp_path: Path, seed: int) -> None:
    result, _ = _generate(tmp_path, seed=seed, wafers_per_lot=2)

    lognormal_ids = {item.id for item in result.items if item.distribution == "lognormal"}
    assert lognormal_ids == _LOGNORMAL_CP_ITEMS
    for lot in result.lots:
        for wafer in lot.wafers:
            for item_id in lognormal_ids:
                values = wafer.values[item_id]
                assert np.all(values > 0)
                assert np.all(np.isfinite(values))


def test_extreme_lognormal_override_stays_positive_and_finite(tmp_path: Path) -> None:
    result, _ = _generate(
        tmp_path,
        overrides=[{"id": "CP_IOFFN", "typical": 1e-300, "usl": 1e8}],
    )

    values = result.lots[0].wafers[0].values["CP_IOFFN"]

    assert np.all(values > 0)
    assert np.all(np.isfinite(values))
