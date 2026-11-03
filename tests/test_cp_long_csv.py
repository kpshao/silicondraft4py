"""CP long CSV export through the public API."""

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from silicondraft import (
    GenerationResult,
    export,
    generate,
    generate_to_directory,
    load_scenario,
)

_TIMESTAMP_PATTERN = r"\d{8}T\d{12}Z"
_LONG_HEADER = [
    "lot_id",
    "wafer_id",
    "die_x_mm",
    "die_y_mm",
    "grid_x",
    "grid_y",
    "test_site",
    "hard_bin",
    "hard_bin_name",
    "soft_bin",
    "soft_bin_name",
    "die_pass",
    "test_num",
    "item_id",
    "value",
    "unit",
    "lsl",
    "usl",
    "pass",
    "timestamp",
]


def _write_scenario(
    tmp_path: Path,
    *,
    layout: str | None = None,
    lots: int = 1,
    wafers_per_lot: int = 2,
    cp_csv: bool = True,
    encoding: str | None = None,
    defects: dict[str, Any] | None = None,
) -> Path:
    export_options: dict[str, Any] = {
        "cp_csv": cp_csv,
        "wat_csv": False,
        "ground_truth": False,
        "include_die_truth": False,
    }
    if layout is not None:
        export_options["cp_csv_layout"] = layout
    if encoding is not None:
        export_options["encoding"] = encoding
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
            "cp_sites": 2,
        },
        "lots": {
            "count": lots,
            "wafers_per_lot": wafers_per_lot,
            "start_date": "2026-01-05T08:00:00",
        },
        "defects": defects or {"enabled": False},
        "export": export_options,
        "seed": 20260105,
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate_and_export(
    tmp_path: Path, **kwargs: Any
) -> tuple[GenerationResult, tuple[Path, ...]]:
    scenario = load_scenario(_write_scenario(tmp_path, **kwargs))
    result = generate(scenario)
    return result, export(result, tmp_path / "out")


def _read_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.reader(stream))


def _read_blocks(path: Path) -> dict[str, list[list[str]]]:
    blocks: dict[str, list[list[str]]] = {}
    current: str | None = None
    for row in _read_rows(path):
        if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]"):
            current = row[0]
            blocks[current] = []
        else:
            assert current is not None
            blocks[current].append(row)
    return blocks


def test_default_layout_writes_one_long_csv_per_lot(tmp_path: Path) -> None:
    result, paths = _generate_and_export(tmp_path, lots=2, wafers_per_lot=2)

    assert len(paths) == 2
    names = sorted(path.name for path in paths)
    pattern = re.compile(rf"^GEN55LOGIC_GEN55LOGIC-L00[12]_CP_{_TIMESTAMP_PATTERN}\.csv$")
    assert all(pattern.fullmatch(name) for name in names)

    rows = _read_rows(paths[0])
    assert rows[0] == _LONG_HEADER
    expected_rows = sum(wafer.die_count for wafer in result.lots[0].wafers) * len(result.items)
    assert len(rows) - 1 == expected_rows


def test_long_csv_groups_rows_by_wafer_then_die_then_item(tmp_path: Path) -> None:
    result, paths = _generate_and_export(tmp_path, wafers_per_lot=2)

    rows = _read_rows(paths[0])
    header = rows[0]
    column = {name: index for index, name in enumerate(header)}
    lot = result.lots[0]
    items = result.items
    expected_wafer_ids = [
        wafer.wafer_id for wafer in lot.wafers for _ in range(wafer.die_count * len(items))
    ]

    assert [row[column["wafer_id"]] for row in rows[1:]] == expected_wafer_ids
    first_wafer_rows = rows[1 : 1 + lot.wafers[0].die_count * len(items)]
    assert [row[column["item_id"]] for row in first_wafer_rows[: len(items)]] == [
        item.id for item in items
    ]
    first_die_rows = first_wafer_rows[: len(items)]
    assert len({(row[column["grid_x"]], row[column["grid_y"]]) for row in first_die_rows}) == 1


def test_blocks_layout_keeps_the_multiblock_csv(tmp_path: Path) -> None:
    _, paths = _generate_and_export(tmp_path, layout="blocks", wafers_per_lot=2)

    assert len(paths) == 2
    names = sorted(path.name for path in paths)
    pattern = re.compile(rf"^GEN55LOGIC_GEN55LOGIC-L001_W0[12]_CP_{_TIMESTAMP_PATTERN}\.csv$")
    assert all(pattern.fullmatch(name) for name in names)
    for path in paths:
        rows = _read_rows(path)
        markers = [row[0] for row in rows if len(row) == 1 and row[0].startswith("[")]
        assert markers == ["[METADATA]", "[TEST_ITEMS]", "[BIN_DEFINITIONS]", "[TEST_DATA]"]


def test_both_layout_writes_long_and_blocks(tmp_path: Path) -> None:
    _, paths = _generate_and_export(tmp_path, layout="both", wafers_per_lot=2)

    assert len(paths) == 3
    long_pattern = re.compile(rf"^GEN55LOGIC_GEN55LOGIC-L001_CP_{_TIMESTAMP_PATTERN}\.csv$")
    block_pattern = re.compile(rf"^GEN55LOGIC_GEN55LOGIC-L001_W0[12]_CP_{_TIMESTAMP_PATTERN}\.csv$")
    long_paths = [path for path in paths if long_pattern.fullmatch(path.name)]
    block_paths = [path for path in paths if block_pattern.fullmatch(path.name)]
    assert len(long_paths) == 1
    assert len(block_paths) == 2
    assert _read_rows(long_paths[0])[0] == _LONG_HEADER


def test_long_and_blocks_agree_on_values_bins_and_passes(tmp_path: Path) -> None:
    _, paths = _generate_and_export(tmp_path, layout="both", wafers_per_lot=1)

    long_path = next(
        path
        for path in paths
        if re.fullmatch(rf"GEN55LOGIC_GEN55LOGIC-L001_CP_{_TIMESTAMP_PATTERN}\.csv", path.name)
    )
    block_path = next(
        path
        for path in paths
        if re.fullmatch(rf"GEN55LOGIC_GEN55LOGIC-L001_W01_CP_{_TIMESTAMP_PATTERN}\.csv", path.name)
    )
    long_rows = _read_rows(long_path)
    long_column = {name: index for index, name in enumerate(long_rows[0])}
    blocks = _read_blocks(block_path)
    item_ids = [row[1] for row in blocks["[TEST_ITEMS]"][1:]]
    wide_rows = blocks["[TEST_DATA]"]
    wide_column = {name: index for index, name in enumerate(wide_rows[0])}
    first_item_column = wide_column[item_ids[0]]

    assert len(long_rows) - 1 == (len(wide_rows) - 1) * len(item_ids)
    for die_index, wide in enumerate(wide_rows[1:]):
        for item_index, item_id in enumerate(item_ids):
            long_row = long_rows[1 + die_index * len(item_ids) + item_index]
            assert long_row[long_column["item_id"]] == item_id
            assert float(long_row[long_column["value"]]) == pytest.approx(
                float(wide[first_item_column + item_index]), rel=1e-9
            )
            assert int(long_row[long_column["hard_bin"]]) == int(wide[wide_column["hard_bin"]])
            assert int(long_row[long_column["soft_bin"]]) == int(wide[wide_column["soft_bin"]])
            assert int(long_row[long_column["die_pass"]]) == int(wide[wide_column["pass"]])


def test_streaming_default_long_matches_the_in_memory_export(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, wafers_per_lot=2))
    result = generate(scenario)
    in_memory_paths = export(result, tmp_path / "full")

    summary, stream_paths = generate_to_directory(scenario, tmp_path / "stream")

    assert summary.lot_count == 1
    assert len(in_memory_paths) == len(stream_paths) == 1
    assert _read_rows(in_memory_paths[0]) == _read_rows(stream_paths[0])


def test_long_csv_follows_the_export_encoding(tmp_path: Path) -> None:
    _, default_paths = _generate_and_export(tmp_path, wafers_per_lot=1)
    assert not default_paths[0].read_bytes().startswith(b"\xef\xbb\xbf")

    _, bom_paths = _generate_and_export(tmp_path, wafers_per_lot=1, encoding="utf-8-sig")
    data = bom_paths[0].read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig").startswith(",".join(_LONG_HEADER) + "\n")


def test_cp_csv_false_writes_no_cp_csv(tmp_path: Path) -> None:
    _, paths = _generate_and_export(tmp_path, layout="both", wafers_per_lot=2, cp_csv=False)

    assert paths == ()
    assert not list((tmp_path / "out").glob("*_CP_*.csv"))


def test_long_csv_bernoulli_item_pass_and_bin_names(tmp_path: Path) -> None:
    result, paths = _generate_and_export(
        tmp_path,
        wafers_per_lot=1,
        defects={
            "enabled": True,
            "model": "poisson",
            "failure_rate": 1.0,
            "target_items": ["CP_FUNC"],
        },
    )

    rows = _read_rows(paths[0])
    column = {name: index for index, name in enumerate(rows[0])}
    data = rows[1:]
    bernoulli_rows = [row for row in data if row[column["item_id"]] == "CP_FUNC"]

    assert len(bernoulli_rows) == result.lots[0].wafers[0].die_count
    assert all(row[column["die_pass"]] == "0" for row in data)
    assert all(
        row[column["hard_bin_name"]] in {"FUNCTIONAL_FAIL", "CONTINUITY_FAIL"} for row in data
    )
    assert all(row[column["soft_bin_name"]] in {"FUNCTIONAL_SCAN", "CONTINUITY"} for row in data)
    for row in bernoulli_rows:
        assert float(row[column["value"]]) == 0.0
        assert row[column["pass"]] == "0"


def test_long_csv_measurements_bins_and_passes_match_the_result(tmp_path: Path) -> None:
    result, paths = _generate_and_export(tmp_path, wafers_per_lot=1)

    rows = _read_rows(paths[0])
    column = {name: index for index, name in enumerate(rows[0])}
    lot = result.lots[0]
    wafer = lot.wafers[0]
    items = result.items
    hard_bin_names = {
        1: "PASS",
        2: "PARAMETRIC_FAIL",
        3: "FUNCTIONAL_FAIL",
        4: "CONTINUITY_FAIL",
    }
    soft_bin_names = {
        100: "PASS",
        201: "CONTINUITY",
        202: "LEAKAGE",
        203: "IDDQ",
        204: "VTH",
        205: "FREQUENCY",
        206: "FUNCTIONAL_SCAN",
        207: "OTHER_PARAMETRIC",
    }

    assert len(rows) - 1 == wafer.die_count * len(items)
    for die_index in range(wafer.die_count):
        hard_bin = int(wafer.hard_bin[die_index])
        soft_bin = int(wafer.soft_bin[die_index])
        for item_index, item in enumerate(items):
            row = rows[1 + die_index * len(items) + item_index]
            assert row[column["lot_id"]] == lot.lot_id
            assert row[column["wafer_id"]] == wafer.wafer_id
            assert float(row[column["die_x_mm"]]) == pytest.approx(float(wafer.x_mm[die_index]))
            assert float(row[column["die_y_mm"]]) == pytest.approx(float(wafer.y_mm[die_index]))
            assert int(row[column["grid_x"]]) == int(wafer.grid_x[die_index])
            assert int(row[column["grid_y"]]) == int(wafer.grid_y[die_index])
            assert int(row[column["test_site"]]) == int(wafer.test_site[die_index])
            assert int(row[column["hard_bin"]]) == hard_bin
            assert row[column["hard_bin_name"]] == hard_bin_names[hard_bin]
            assert int(row[column["soft_bin"]]) == soft_bin
            assert row[column["soft_bin_name"]] == soft_bin_names[soft_bin]
            assert int(row[column["die_pass"]]) == int(hard_bin == 1)
            assert int(row[column["test_num"]]) == item.test_num
            assert row[column["item_id"]] == item.id

            value = float(row[column["value"]])
            assert value == pytest.approx(float(wafer.values[item.id][die_index]), rel=1e-9)
            assert row[column["unit"]] == item.unit
            assert (row[column["lsl"]] == "") is (item.lsl is None)
            assert (row[column["usl"]] == "") is (item.usl is None)
            if item.lsl is not None:
                assert float(row[column["lsl"]]) == pytest.approx(item.lsl)
            if item.usl is not None:
                assert float(row[column["usl"]]) == pytest.approx(item.usl)

            expected_pass = (item.lsl is None or value >= item.lsl) and (
                item.usl is None or value <= item.usl
            )
            if item.distribution == "bernoulli":
                expected_pass = expected_pass and value != 0.0
            assert int(row[column["pass"]]) == int(expected_pass)
            assert datetime.fromisoformat(row[column["timestamp"]]) == wafer.tested_at
