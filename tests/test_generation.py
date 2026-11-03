import csv
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

import numpy as np
import pytest

from silicondraft import GenerationResult, Scenario, ScenarioError, export, generate, load_scenario

_METADATA_KEYS = [
    "csv_format_version",
    "scenario_schema_version",
    "phase",
    "lot_id",
    "product",
    "device_family",
    "process_node",
    "fab",
    "test_program",
    "tester_type",
    "exec_type",
    "exec_version",
    "generated_at",
    "seed",
    "scenario_sha256",
    "wafer_id",
    "lot_die_count",
    "lot_pass_count",
    "lot_yield",
    "diameter_mm",
    "die_size_x_mm",
    "die_size_y_mm",
    "edge_exclusion_mm",
    "notch",
    "cp_sites",
    "die_count",
    "pass_count",
    "yield",
]
_TIMESTAMP_PATTERN = r"\d{8}T\d{12}Z"


def _write_scenario(
    tmp_path: Path,
    *,
    wafers_per_lot: int = 1,
    test_program: str | None = None,
    cp_vthn_usl: float | None = None,
    encoding: str | None = None,
) -> Path:
    lines = [
        "schema_version: 1",
        "product:",
        "  name: GEN55LOGIC",
    ]
    if test_program is not None:
        lines.append(f"  test_program: {test_program}")
    lines.extend(
        [
            "lots:",
            f"  wafers_per_lot: {wafers_per_lot}",
        ]
    )
    if cp_vthn_usl is not None:
        lines.extend(
            [
                "items:",
                "  overrides:",
                "    - id: CP_VTHN",
                f"      usl: {cp_vthn_usl}",
            ]
        )
    lines.extend(
        [
            "export:",
            "  cp_csv_layout: blocks",
            "  wat_csv: false",
            "  ground_truth: false",
            "  include_die_truth: false",
        ]
    )
    if encoding is not None:
        lines.append(f"  encoding: {encoding}")
    lines.append("seed: 20260105")
    path = tmp_path / "tiny.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _read_blocks(path: Path) -> tuple[list[str], dict[str, list[list[str]]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))

    markers: list[str] = []
    blocks: dict[str, list[list[str]]] = {}
    current: str | None = None
    for row in rows:
        assert row, "CSV must not contain blank lines"
        if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]"):
            current = row[0]
            markers.append(current)
            blocks[current] = []
        else:
            assert current is not None, f"data row outside a block: {row!r}"
            blocks[current].append(row)
    return markers, blocks


def _single_csv(
    tmp_path: Path,
    *,
    wafers_per_lot: int = 1,
    test_program: str | None = None,
    cp_vthn_usl: float | None = None,
    encoding: str | None = None,
) -> tuple[Path, GenerationResult]:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=wafers_per_lot,
            test_program=test_program,
            cp_vthn_usl=cp_vthn_usl,
            encoding=encoding,
        )
    )
    result = generate(scenario)
    paths = export(result, tmp_path / "out")
    assert len(paths) == 1
    return paths[0], result


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


def test_export_writes_one_multiblock_csv_per_wafer(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, wafers_per_lot=2))
    result = generate(scenario)

    paths = export(result, tmp_path / "out")

    assert len(paths) == 2
    names = sorted(path.name for path in paths)
    name_pattern = re.compile(rf"^GEN55LOGIC_GEN55LOGIC-L001_W0[12]_CP_{_TIMESTAMP_PATTERN}\.csv$")
    assert all(name_pattern.fullmatch(name) for name in names)
    timestamps = {re.search(_TIMESTAMP_PATTERN, name).group() for name in names}  # type: ignore[union-attr]
    assert len(timestamps) == 1
    wafer_ids = set()
    for path in paths:
        markers, blocks = _read_blocks(path)
        assert markers == ["[METADATA]", "[TEST_ITEMS]", "[BIN_DEFINITIONS]", "[TEST_DATA]"]
        metadata = dict(blocks["[METADATA]"][1:])
        wafer_ids.add(metadata["wafer_id"])
        assert f"_{metadata['wafer_id']}_CP_" in path.name
        assert metadata["die_count"] == "2700"
        assert metadata["yield"] == f"{int(metadata['pass_count']) / 2700:.6f}"
    assert wafer_ids == {"W01", "W02"}


def test_export_encoding_controls_the_bom(tmp_path: Path) -> None:
    default_path, _ = _single_csv(tmp_path)
    assert not default_path.read_bytes().startswith(b"\xef\xbb\xbf")

    bom_path, _ = _single_csv(tmp_path, encoding="utf-8-sig")
    data = bom_path.read_bytes()
    assert data.startswith(b"\xef\xbb\xbf")
    assert data.decode("utf-8-sig").startswith("[METADATA]\n")


def test_metadata_block_contains_scenario_and_wafer_fields(tmp_path: Path) -> None:
    path, result = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    metadata = blocks["[METADATA]"]
    assert metadata[0] == ["key", "value"]
    assert [key for key, _ in metadata[1:]] == _METADATA_KEYS
    values = dict(metadata[1:])

    assert values["csv_format_version"] == "2"
    assert values["scenario_schema_version"] == "1"
    assert values["phase"] == "CP"
    assert values["lot_id"] == "GEN55LOGIC-L001"
    assert values["product"] == "GEN55LOGIC"
    assert values["device_family"] == ""
    assert values["process_node"] == ""
    assert values["fab"] == ""
    assert values["test_program"] == "generic_cmos_logic_55nm"
    assert values["tester_type"] == "SIM"
    assert values["exec_type"] == "SiliconDraft"
    assert values["exec_version"]
    generated_at = datetime.fromisoformat(values["generated_at"])
    assert generated_at.tzinfo is not None
    assert generated_at.utcoffset() == timedelta(0)
    assert values["seed"] == "20260105"
    assert re.fullmatch(r"[0-9a-f]{64}", values["scenario_sha256"])
    assert values["wafer_id"] == "W01"
    assert values["diameter_mm"] == "300"
    assert values["die_size_x_mm"] == "5"
    assert values["die_size_y_mm"] == "5"
    assert values["edge_exclusion_mm"] == "3"
    assert values["notch"] == "down"
    assert values["cp_sites"] == "4"
    assert values["die_count"] == "2700"

    lot = result.lots[0]
    assert values["lot_die_count"] == str(lot.die_count)
    assert values["lot_pass_count"] == str(lot.pass_count)
    assert values["lot_yield"] == f"{lot.yield_fraction:.6f}"

    wafer = lot.wafers[0]
    assert values["pass_count"] == str(wafer.pass_count)
    assert values["yield"] == f"{wafer.yield_fraction:.6f}"


def test_metadata_yield_is_a_fraction_with_six_decimals(tmp_path: Path) -> None:
    path, result = _single_csv(tmp_path, cp_vthn_usl=0.36)
    _, blocks = _read_blocks(path)

    values = dict(blocks["[METADATA]"][1:])
    wafer = result.lots[0].wafers[0]

    assert 0 < wafer.pass_count < wafer.die_count
    assert values["pass_count"] == str(wafer.pass_count)
    assert values["yield"] == f"{wafer.yield_fraction:.6f}"
    assert re.fullmatch(r"0\.\d{6}", values["yield"])


def test_test_program_falls_back_to_items_preset(tmp_path: Path) -> None:
    path, _ = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    values = dict(blocks["[METADATA]"][1:])

    assert values["test_program"] == "generic_cmos_logic_55nm"


def test_configured_test_program_is_used(tmp_path: Path) -> None:
    path, _ = _single_csv(tmp_path, test_program="GEN55LOGIC_CP")
    _, blocks = _read_blocks(path)

    values = dict(blocks["[METADATA]"][1:])

    assert values["test_program"] == "GEN55LOGIC_CP"


def test_test_items_block_lists_every_enabled_cp_item(tmp_path: Path) -> None:
    path, result = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    test_items = blocks["[TEST_ITEMS]"]
    assert test_items[0] == [
        "test_num",
        "item_id",
        "unit",
        "typical",
        "lsl",
        "usl",
        "description",
    ]
    assert [row[1] for row in test_items[1:]] == [item.id for item in result.items]
    for row, item in zip(test_items[1:], result.items, strict=True):
        assert int(row[0]) == item.test_num
        assert row[2] == item.unit
        assert float(row[3]) == pytest.approx(item.typical)
        assert (row[4] == "") is (item.lsl is None)
        assert (row[5] == "") is (item.usl is None)
        if item.lsl is not None:
            assert float(row[4]) == pytest.approx(item.lsl)
        if item.usl is not None:
            assert float(row[5]) == pytest.approx(item.usl)
        assert row[6] == item.description


def test_test_items_block_units_are_ascii(tmp_path: Path) -> None:
    path, result = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    units = [row[2] for row in blocks["[TEST_ITEMS]"][1:]]
    assert units == [item.unit for item in result.items]
    assert all(unit.isascii() for unit in units)


def test_test_items_block_leaves_unbounded_limits_empty(tmp_path: Path) -> None:
    path, _ = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    rows = {row[1]: row for row in blocks["[TEST_ITEMS]"][1:]}

    assert rows["CP_CONT"][4] == ""
    assert rows["CP_CONT"][5] == "100"
    assert rows["CP_VTHN"][4] == "0.28"
    assert rows["CP_VTHN"][5] == "0.42"
    assert rows["CP_FUNC"][4] == ""
    assert rows["CP_FUNC"][5] == ""


def test_bin_definitions_block_lists_hard_and_soft_bins(tmp_path: Path) -> None:
    path, _ = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    definitions = blocks["[BIN_DEFINITIONS]"]
    assert definitions[0] == [
        "bin_type",
        "bin_number",
        "bin_name",
        "pass_fail",
        "hard_bin",
        "description",
    ]
    assert [(row[0], row[1], row[2], row[3], row[4]) for row in definitions[1:]] == [
        ("HARD", "1", "PASS", "P", "1"),
        ("HARD", "2", "PARAMETRIC_FAIL", "F", "2"),
        ("HARD", "3", "FUNCTIONAL_FAIL", "F", "3"),
        ("HARD", "4", "CONTINUITY_FAIL", "F", "4"),
        ("SOFT", "100", "PASS", "P", "1"),
        ("SOFT", "201", "CONTINUITY", "F", "4"),
        ("SOFT", "202", "LEAKAGE", "F", "2"),
        ("SOFT", "203", "IDDQ", "F", "2"),
        ("SOFT", "204", "VTH", "F", "2"),
        ("SOFT", "205", "FREQUENCY", "F", "2"),
        ("SOFT", "206", "FUNCTIONAL_SCAN", "F", "3"),
        ("SOFT", "207", "OTHER_PARAMETRIC", "F", "2"),
    ]


def test_test_data_block_has_one_row_per_die_with_spec_columns(tmp_path: Path) -> None:
    path, result = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)
    wafer = result.lots[0].wafers[0]

    test_data = blocks["[TEST_DATA]"]
    assert test_data[0] == [
        "die_x_mm",
        "die_y_mm",
        "grid_x",
        "grid_y",
        "test_site",
        "hard_bin",
        "soft_bin",
        "pass",
        *(item.id for item in result.items),
    ]
    assert len(test_data) - 1 == 2700
    assert "lot_id" not in test_data[0]
    assert "wafer_id" not in test_data[0]

    for index, row in enumerate(test_data[1:]):
        assert float(row[0]) == pytest.approx(float(wafer.x_mm[index]))
        assert float(row[1]) == pytest.approx(float(wafer.y_mm[index]))
        assert int(row[2]) == int(wafer.grid_x[index])
        assert int(row[3]) == int(wafer.grid_y[index])
        assert int(row[4]) == int(wafer.test_site[index])
        assert int(row[5]) == int(wafer.hard_bin[index])
        assert int(row[6]) == int(wafer.soft_bin[index])
        assert row[7] == ("1" if row[5] == "1" else "0")
        assert math.isfinite(float(row[0]))
        assert math.isfinite(float(row[1]))
        for column, item in enumerate(result.items, start=8):
            assert float(row[column]) == pytest.approx(
                float(wafer.values[item.id][index]), rel=1e-9
            )


def test_test_data_coordinates_follow_plus_x_right_and_plus_y_up(tmp_path: Path) -> None:
    path, _ = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)
    rows = blocks["[TEST_DATA]"][1:]

    die_width_mm, die_height_mm = 5.0, 5.0
    columns = math.floor(300 / die_width_mm)
    rows_count = math.floor(300 / die_height_mm)
    xs = [float(row[0]) for row in rows]
    ys = [float(row[1]) for row in rows]
    grid_x = [int(row[2]) for row in rows]
    grid_y = [int(row[3]) for row in rows]

    assert all(
        math.isclose(x, (column - (columns - 1) / 2) * die_width_mm)
        for x, column in zip(xs, grid_x, strict=True)
    )
    assert all(
        math.isclose(y, (row - (rows_count - 1) / 2) * die_height_mm)
        for y, row in zip(ys, grid_y, strict=True)
    )
    assert ys == sorted(ys)
    assert min(ys) < 0 < max(ys)


def test_same_scenario_and_seed_produce_identical_data_except_timestamps(
    tmp_path: Path,
) -> None:
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

    first_path = export(first, tmp_path / "first")[0]
    second_path = export(second, tmp_path / "second")[0]
    assert re.sub(_TIMESTAMP_PATTERN, "<timestamp>", first_path.name) == re.sub(
        _TIMESTAMP_PATTERN, "<timestamp>", second_path.name
    )

    _, first_blocks = _read_blocks(first_path)
    _, second_blocks = _read_blocks(second_path)
    first_metadata = dict(first_blocks["[METADATA]"][1:])
    second_metadata = dict(second_blocks["[METADATA]"][1:])
    datetime.fromisoformat(first_metadata.pop("generated_at"))
    datetime.fromisoformat(second_metadata.pop("generated_at"))
    assert first_metadata == second_metadata
    for block in ("[TEST_ITEMS]", "[BIN_DEFINITIONS]", "[TEST_DATA]"):
        assert first_blocks[block] == second_blocks[block]


def test_different_seed_changes_cp_data(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    other = scenario.model_copy(update={"seed": scenario.seed + 1})

    first = generate(scenario)
    second = generate(other)

    first_values = first.lots[0].wafers[0].values["CP_VTHN"]
    second_values = second.lots[0].wafers[0].values["CP_VTHN"]
    assert not np.array_equal(first_values, second_values)


class _CsvFormatLayout(TypedDict):
    metadata_keys: list[str]
    test_items_header: list[str]
    bin_definitions_header: list[str]
    test_data_prefix: list[str]


# The emitted csv_format_version selects the contract. Any change to these
# block layouts must bump the version and add a new entry here; keeping the
# literals independent of the implementation constants is the point.
_CSV_FORMAT_LAYOUTS: dict[str, _CsvFormatLayout] = {
    "2": {
        "metadata_keys": [
            "csv_format_version",
            "scenario_schema_version",
            "phase",
            "lot_id",
            "product",
            "device_family",
            "process_node",
            "fab",
            "test_program",
            "tester_type",
            "exec_type",
            "exec_version",
            "generated_at",
            "seed",
            "scenario_sha256",
            "wafer_id",
            "lot_die_count",
            "lot_pass_count",
            "lot_yield",
            "diameter_mm",
            "die_size_x_mm",
            "die_size_y_mm",
            "edge_exclusion_mm",
            "notch",
            "cp_sites",
            "die_count",
            "pass_count",
            "yield",
        ],
        "test_items_header": [
            "test_num",
            "item_id",
            "unit",
            "typical",
            "lsl",
            "usl",
            "description",
        ],
        "bin_definitions_header": [
            "bin_type",
            "bin_number",
            "bin_name",
            "pass_fail",
            "hard_bin",
            "description",
        ],
        "test_data_prefix": [
            "die_x_mm",
            "die_y_mm",
            "grid_x",
            "grid_y",
            "test_site",
            "hard_bin",
            "soft_bin",
            "pass",
        ],
    },
}


def test_csv_format_version_matches_the_block_layouts(tmp_path: Path) -> None:
    path, _ = _single_csv(tmp_path)
    _, blocks = _read_blocks(path)

    version = dict(blocks["[METADATA]"][1:])["csv_format_version"]
    layout = _CSV_FORMAT_LAYOUTS[version]

    assert [key for key, _ in blocks["[METADATA]"][1:]] == layout["metadata_keys"]
    assert blocks["[TEST_ITEMS]"][0] == layout["test_items_header"]
    assert blocks["[BIN_DEFINITIONS]"][0] == layout["bin_definitions_header"]
    prefix = layout["test_data_prefix"]
    assert blocks["[TEST_DATA]"][0][: len(prefix)] == prefix


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
