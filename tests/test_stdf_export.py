"""CP STDF V4 export through the public API, parsed by the independent pystdf."""

import csv
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml
from pystdf.IO import Parser

from silicondraft import (
    GenerationResult,
    export,
    generate,
    generate_to_directory,
    load_scenario,
)
from silicondraft.catalog import CatalogItem
from silicondraft.dataset import CPLot, CPWafer
from silicondraft.errors import ExportError
from silicondraft.scenario.models import ExportOptions, Product, Scenario

_TIMESTAMP_PATTERN = r"\d{8}T\d{12}Z"


class _RecordSink:
    """Collect pystdf records as (record name, field mapping) pairs."""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def after_send(self, data_source: object, data: tuple[Any, list[Any]]) -> None:
        record, values = data
        record_type = record.__class__
        self.records.append(
            (
                record_type.__name__.upper(),
                dict(zip(record_type.fieldNames, values, strict=True)),
            )
        )


def _parse_stdf(path: Path) -> list[tuple[str, dict[str, Any]]]:
    sink = _RecordSink()
    with path.open("rb") as stream:
        parser = Parser(inp=stream)
        parser.addSink(sink)
        parser.parse()
    return sink.records


def _records(records: list[tuple[str, dict[str, Any]]], name: str) -> list[dict[str, Any]]:
    return [fields for record_name, fields in records if record_name == name]


def _write_scenario(
    tmp_path: Path,
    *,
    lots: int = 1,
    wafers_per_lot: int = 2,
    cp_stdf: bool = True,
    cp_csv: bool = True,
    item_overrides: list[dict[str, Any]] | None = None,
) -> Path:
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
        "defects": {"enabled": False},
        "export": {
            "cp_stdf": cp_stdf,
            "cp_csv": cp_csv,
            "cp_csv_layout": "long",
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": 20260105,
    }
    if item_overrides is not None:
        document["items"] = {"overrides": item_overrides}
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate_and_export(
    tmp_path: Path, **kwargs: Any
) -> tuple[GenerationResult, tuple[Path, ...]]:
    scenario = load_scenario(_write_scenario(tmp_path, **kwargs))
    result = generate(scenario)
    return result, export(result, tmp_path / "out", formats=("stdf",))


def test_export_writes_one_parseable_stdf_per_lot(tmp_path: Path) -> None:
    _, paths = _generate_and_export(tmp_path, lots=2, wafers_per_lot=2)

    assert len(paths) == 2
    assert all(path.suffix == ".stdf" for path in paths)
    pattern = re.compile(rf"^GEN55LOGIC_GEN55LOGIC-L00[12]_CP_{_TIMESTAMP_PATTERN}\.stdf$")
    assert all(pattern.fullmatch(path.name) for path in paths)
    for path in paths:
        records = _parse_stdf(path)
        assert records[0][0] == "FAR"
        assert [name for name, _ in records].count("FAR") == 1
        assert len(_records(records, "MIR")) == 1
        assert records[-1][0] == "MRR"


def test_stdf_contains_the_full_cp_record_set(tmp_path: Path) -> None:
    result, paths = _generate_and_export(tmp_path, lots=1, wafers_per_lot=2)

    (path,) = paths
    records = _parse_stdf(path)
    names = [name for name, _ in records]
    assert set(names) == {
        "FAR",
        "MIR",
        "MRR",
        "PCR",
        "HBR",
        "SBR",
        "WIR",
        "WRR",
        "WCR",
        "PIR",
        "PRR",
        "PTR",
        "TSR",
    }

    items = result.items
    lot = result.lots[0]
    die_count = lot.die_count
    assert len(_records(records, "WIR")) == len(lot.wafers)
    assert len(_records(records, "WRR")) == len(lot.wafers)
    assert len(_records(records, "WCR")) == len(lot.wafers)
    assert len(_records(records, "PIR")) == die_count
    assert len(_records(records, "PRR")) == die_count
    assert len(_records(records, "PTR")) == die_count * len(items)
    assert len(_records(records, "TSR")) == len(items)

    hard_bins = Counter(
        int(wafer.hard_bin[index]) for wafer in lot.wafers for index in range(wafer.die_count)
    )
    soft_bins = Counter(
        int(wafer.soft_bin[index]) for wafer in lot.wafers for index in range(wafer.die_count)
    )
    assert {
        int(fields["HBIN_NUM"]): int(fields["HBIN_CNT"]) for fields in _records(records, "HBR")
    } == dict(hard_bins)
    assert {
        int(fields["SBIN_NUM"]): int(fields["SBIN_CNT"]) for fields in _records(records, "SBR")
    } == dict(soft_bins)
    assert sum(int(fields["HBIN_CNT"]) for fields in _records(records, "HBR")) == die_count
    assert sum(int(fields["SBIN_CNT"]) for fields in _records(records, "SBR")) == die_count


def test_stdf_key_fields_match_the_csv_export(tmp_path: Path) -> None:
    result, stdf_paths = _generate_and_export(tmp_path, lots=1, wafers_per_lot=2)
    csv_paths = export(result, tmp_path / "csv", formats=("csv",))
    (stdf_path,) = stdf_paths
    (csv_path,) = csv_paths
    records = _parse_stdf(stdf_path)

    with csv_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    items = result.items
    lot = result.lots[0]
    assert len(rows) == lot.die_count * len(items)

    ptrs = _records(records, "PTR")
    prrs = _records(records, "PRR")
    assert len(prrs) == len(rows) // len(items)
    assert len(ptrs) == len(rows)

    first_die_rows = rows[: len(items)]
    first_die_ptrs = ptrs[: len(items)]
    assert [int(fields["TEST_NUM"]) for fields in first_die_ptrs] == [
        item.test_num for item in items
    ]
    for row, ptr in zip(first_die_rows, first_die_ptrs, strict=True):
        assert int(ptr["HEAD_NUM"]) == 1
        assert int(ptr["SITE_NUM"]) == int(row["test_site"])
        assert float(ptr["RESULT"]) == pytest.approx(float(row["value"]), rel=1e-6)

    first_prr = prrs[0]
    first_row = first_die_rows[0]
    assert int(first_prr["HARD_BIN"]) == int(first_row["hard_bin"])
    assert int(first_prr["SOFT_BIN"]) == int(first_row["soft_bin"])
    assert int(first_prr["X_COORD"]) == int(first_row["grid_x"])
    assert int(first_prr["Y_COORD"]) == int(first_row["grid_y"])
    assert int(first_prr["NUM_TEST"]) == len(items)
    assert int(first_prr["SITE_NUM"]) == int(first_row["test_site"])

    last_wafer = lot.wafers[-1]
    last_prr = prrs[-1]
    assert int(last_prr["X_COORD"]) == int(last_wafer.grid_x[-1])
    assert int(last_prr["Y_COORD"]) == int(last_wafer.grid_y[-1])
    assert int(last_prr["HARD_BIN"]) == int(last_wafer.hard_bin[-1])
    assert int(last_prr["SOFT_BIN"]) == int(last_wafer.soft_bin[-1])

    mir = _records(records, "MIR")[0]
    assert mir["LOT_ID"] == lot.lot_id
    assert mir["PART_TYP"] == "GEN55LOGIC"
    wafers = _records(records, "WIR")
    assert [fields["WAFER_ID"] for fields in wafers] == [wafer.wafer_id for wafer in lot.wafers]

    pcr = _records(records, "PCR")[0]
    assert int(pcr["PART_CNT"]) == lot.die_count
    assert int(pcr["GOOD_CNT"]) == lot.pass_count

    tsrs = {int(fields["TEST_NUM"]): fields for fields in _records(records, "TSR")}
    for item in items:
        tsr = tsrs[item.test_num]
        assert int(tsr["EXEC_CNT"]) == lot.die_count
        expected_failures = sum(
            1 for row in rows if int(row["test_num"]) == item.test_num and int(row["pass"]) == 0
        )
        assert int(tsr["FAIL_CNT"]) == expected_failures


def test_stdf_uses_standard_missing_codes(tmp_path: Path) -> None:
    _, paths = _generate_and_export(tmp_path)
    records = _parse_stdf(paths[0])

    mir = _records(records, "MIR")[0]
    assert int(mir["BURN_TIM"]) == 65535
    assert mir["JOB_REV"] == ""
    assert mir["OPER_NAM"] == ""

    wir = _records(records, "WIR")[0]
    assert int(wir["SITE_GRP"]) == 255

    # CP_FUNC is a Bernoulli item with no unit and no spec limits.
    ptr = next(fields for fields in _records(records, "PTR") if int(fields["TEST_NUM"]) == 2002)
    assert ptr["UNITS"] == ""
    assert ptr["TEST_TXT"] == "Functional test pass flag"
    assert int(ptr["OPT_FLAG"]) & 0b0000_0010  # reserved bit is 1
    assert int(ptr["OPT_FLAG"]) & 0b0101_0100  # bits 2, 4, 6: no low limit/spec
    assert int(ptr["OPT_FLAG"]) & 0b1010_1000  # bits 3, 5, 7: no high limit/spec

    prr = _records(records, "PRR")[0]
    assert int(prr["TEST_T"]) == 0
    assert prr["PART_ID"] == ""
    assert prr["PART_TXT"] == ""
    assert prr["PART_FIX"] == []

    tsrs = {int(fields["TEST_NUM"]): fields for fields in _records(records, "TSR")}
    functional = tsrs[2002]
    assert functional["TEST_TYP"] == "F"
    assert int(functional["OPT_FLAG"]) == 0xCC  # TEST_TIM invalid plus reserved bits
    assert int(functional["TEST_TIM"]) == 0
    assert tsrs[2001]["TEST_TYP"] == "P"


def test_stdf_export_fails_clearly_on_non_ascii_text(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            cp_csv=False,
            item_overrides=[{"id": "CP_FUNC", "description": "功能测试"}],
        )
    )
    result = generate(scenario)
    out_dir = tmp_path / "out"

    with pytest.raises(ExportError, match=r"TEST_TXT.*not ASCII"):
        export(result, out_dir, formats=("stdf",))

    assert not list(out_dir.glob("*.stdf"))


def _manual_result(*, grid_x: int = 0, site_num: int = 1) -> GenerationResult:
    item = CatalogItem(
        id="CP_TEST",
        phase="CP",
        test_num=2001,
        description="Test item",
        unit="V",
        typical=0.5,
        lsl=0.0,
        usl=1.0,
        distribution="normal",
    )
    scenario = Scenario(
        schema_version=1,
        product=Product(name="MANUAL"),
        export=ExportOptions(
            cp_stdf=True,
            cp_csv=False,
            wat_csv=False,
            ground_truth=False,
            include_die_truth=False,
        ),
        seed=1,
    )
    wafer = CPWafer(
        wafer_id="W01",
        x_mm=np.array([0.0]),
        y_mm=np.array([0.0]),
        grid_x=np.array([grid_x]),
        grid_y=np.array([0]),
        test_site=np.array([site_num]),
        hard_bin=np.array([1]),
        soft_bin=np.array([100]),
        passed=np.array([True]),
        values={"CP_TEST": np.array([0.5])},
        factors=np.zeros((1, 1)),
        pattern_hits={},
        defect_failure=np.array([False]),
        defect_clusters=(),
        tested_at=datetime(2026, 1, 5, tzinfo=UTC),
    )
    return GenerationResult(
        scenario=scenario,
        items=(item,),
        wat_items=(),
        lots=(CPLot(lot_id="L001", wafers=(wafer,)),),
        wat_lots=(),
        linkage_report=(),
        pattern_reports=(),
        generated_at=datetime(2026, 1, 5, tzinfo=UTC),
    )


def test_stdf_export_rejects_grid_coordinates_outside_the_i2_range(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"

    with pytest.raises(ExportError, match=r"I\*2"):
        export(_manual_result(grid_x=40_000), out_dir, formats=("stdf",))

    assert not list(out_dir.glob("*.stdf"))


def test_stdf_export_rejects_test_sites_outside_the_u1_range(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"

    with pytest.raises(ExportError, match="SITE_NUM"):
        export(_manual_result(site_num=300), out_dir, formats=("stdf",))

    assert not list(out_dir.glob("*.stdf"))


def test_same_scenario_and_seed_produce_identical_stdf_data(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    first = generate(scenario)
    second = generate(scenario)
    first_paths = export(first, tmp_path / "first", formats=("stdf",))
    second_paths = export(second, tmp_path / "second", formats=("stdf",))

    timestamps = {"SETUP_T", "START_T", "FINISH_T"}

    def normalized(path: Path) -> list[tuple[str, tuple[tuple[str, Any], ...]]]:
        return [
            (
                name,
                tuple((key, value) for key, value in fields.items() if key not in timestamps),
            )
            for name, fields in _parse_stdf(path)
        ]

    assert normalized(first_paths[0]) == normalized(second_paths[0])


def test_explicit_stdf_format_overrides_the_scenario_switch(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, cp_stdf=False, cp_csv=True))
    result = generate(scenario)

    paths = export(result, tmp_path / "in-memory", formats=("stdf",))
    assert len(paths) == 1
    assert paths[0].suffix == ".stdf"
    assert not list((tmp_path / "in-memory").glob("*.csv"))

    _, streamed = generate_to_directory(scenario, tmp_path / "streamed", formats=("stdf",))
    assert len(streamed) == 1
    assert streamed[0].suffix == ".stdf"


def test_generate_to_directory_streams_stdf_like_the_cli(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, lots=2, wafers_per_lot=1))

    summary, paths = generate_to_directory(scenario, tmp_path / "out")

    stdf_paths = [path for path in paths if path.suffix == ".stdf"]
    assert len(stdf_paths) == 2
    assert summary.lot_count == 2
    for path in stdf_paths:
        records = _parse_stdf(path)
        assert records[0][0] == "FAR"
        assert records[-1][0] == "MRR"
