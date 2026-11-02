"""CP multi-block CSV export: one file per wafer."""

import csv
import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Protocol

from ..binning import HARD_BIN_DEFINITIONS, SOFT_BIN_DEFINITIONS
from ..dataset import CPLot, CPWafer, GenerationResult
from ..scenario.models import Scenario

CSV_FORMAT_VERSION = "2"
TESTER_TYPE = "SIM"
EXEC_TYPE = "SiliconDraft"
PHASE = "CP"

_METADATA_HEADER = ("key", "value")
_TEST_ITEM_HEADER = ("test_num", "item_id", "unit", "typical", "lsl", "usl", "description")
_BIN_DEFINITION_HEADER = (
    "bin_type",
    "bin_number",
    "bin_name",
    "pass_fail",
    "hard_bin",
    "description",
)
_TEST_DATA_PREFIX = (
    "die_x_mm",
    "die_y_mm",
    "grid_x",
    "grid_y",
    "test_site",
    "hard_bin",
    "soft_bin",
    "pass",
)

_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


class _CsvWriter(Protocol):
    """The subset of ``csv.writer`` used by this module."""

    def writerow(self, row: Sequence[object]) -> object: ...


def export_cp_csv(result: GenerationResult, out_dir: Path) -> tuple[Path, ...]:
    """Write one multi-block CP CSV per wafer and return the written paths.

    The file name is ``{product}_{lot}_{wafer}_CP_{timestamp}.csv``; the
    timestamp is part of the file name only, so exported measurements stay
    reproducible.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = result.scenario.export.encoding
    timestamp = _timestamp_token(result.generated_at)
    product = _safe_filename_part(result.scenario.product.name)
    scenario_hash = _scenario_sha256(result.scenario)
    paths: list[Path] = []
    for lot in result.lots:
        lot_part = _safe_filename_part(lot.lot_id)
        for wafer in lot.wafers:
            wafer_part = _safe_filename_part(wafer.wafer_id)
            path = out_dir / f"{product}_{lot_part}_{wafer_part}_CP_{timestamp}.csv"
            _write_wafer(path, lot, wafer, result, scenario_hash, encoding)
            paths.append(path)
    return tuple(paths)


def _write_wafer(
    path: Path,
    lot: CPLot,
    wafer: CPWafer,
    result: GenerationResult,
    scenario_hash: str,
    encoding: str,
) -> None:
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        _write_metadata(writer, lot, wafer, result, scenario_hash)
        _write_test_items(writer, result)
        _write_bin_definitions(writer)
        _write_test_data(writer, wafer, result)


def _write_block(
    writer: _CsvWriter,
    marker: str,
    header: Sequence[object],
    rows: Iterable[Sequence[object]],
) -> None:
    writer.writerow([marker])
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)


def _write_metadata(
    writer: _CsvWriter,
    lot: CPLot,
    wafer: CPWafer,
    result: GenerationResult,
    scenario_hash: str,
) -> None:
    scenario = result.scenario
    product = scenario.product
    rows = [
        ("csv_format_version", CSV_FORMAT_VERSION),
        ("scenario_schema_version", str(scenario.schema_version)),
        ("phase", PHASE),
        ("lot_id", lot.lot_id),
        ("product", product.name),
        ("device_family", product.device_family),
        ("process_node", product.process_node),
        ("fab", product.fab),
        ("test_program", product.test_program or scenario.items.preset),
        ("tester_type", TESTER_TYPE),
        ("exec_type", EXEC_TYPE),
        ("exec_version", _exec_version()),
        ("generated_at", _format_timestamp(result.generated_at)),
        ("seed", str(scenario.seed)),
        ("scenario_sha256", scenario_hash),
        ("wafer_id", wafer.wafer_id),
        ("lot_die_count", str(lot.die_count)),
        ("lot_pass_count", str(lot.pass_count)),
        ("lot_yield", f"{lot.yield_fraction:.6f}"),
        ("diameter_mm", str(scenario.wafer.diameter_mm)),
        ("die_size_x_mm", _format_float(scenario.wafer.die_size_mm[0])),
        ("die_size_y_mm", _format_float(scenario.wafer.die_size_mm[1])),
        ("edge_exclusion_mm", _format_float(scenario.wafer.edge_exclusion_mm)),
        ("notch", scenario.wafer.notch),
        ("cp_sites", str(scenario.wafer.cp_sites)),
        ("die_count", str(wafer.die_count)),
        ("pass_count", str(wafer.pass_count)),
        ("yield", f"{wafer.yield_fraction:.6f}"),
    ]
    _write_block(writer, "[METADATA]", _METADATA_HEADER, rows)


def _write_test_items(writer: _CsvWriter, result: GenerationResult) -> None:
    rows = (
        (
            item.test_num,
            item.id,
            item.unit,
            _format_float(item.typical),
            _format_optional_float(item.lsl),
            _format_optional_float(item.usl),
            item.description,
        )
        for item in result.items
    )
    _write_block(writer, "[TEST_ITEMS]", _TEST_ITEM_HEADER, rows)


def _write_bin_definitions(writer: _CsvWriter) -> None:
    rows = [
        (
            bin_type,
            definition.number,
            definition.name,
            "P" if definition.passed else "F",
            definition.hard_bin,
            definition.description,
        )
        for bin_type, definitions in (
            ("HARD", HARD_BIN_DEFINITIONS),
            ("SOFT", SOFT_BIN_DEFINITIONS),
        )
        for definition in definitions
    ]
    _write_block(writer, "[BIN_DEFINITIONS]", _BIN_DEFINITION_HEADER, rows)


def _write_test_data(writer: _CsvWriter, wafer: CPWafer, result: GenerationResult) -> None:
    header = (*_TEST_DATA_PREFIX, *(item.id for item in result.items))
    item_columns = [wafer.values[item.id] for item in result.items]
    rows = (
        (
            _format_float(float(wafer.x_mm[index])),
            _format_float(float(wafer.y_mm[index])),
            int(wafer.grid_x[index]),
            int(wafer.grid_y[index]),
            int(wafer.test_site[index]),
            int(wafer.hard_bin[index]),
            int(wafer.soft_bin[index]),
            int(wafer.passed[index]),
            *(_format_float(float(column[index])) for column in item_columns),
        )
        for index in range(wafer.die_count)
    )
    _write_block(writer, "[TEST_DATA]", header, rows)


def _format_float(value: float) -> str:
    return format(value, ".10g")


def _format_optional_float(value: float | None) -> str:
    return "" if value is None else _format_float(value)


def _format_timestamp(generated_at: datetime) -> str:
    return generated_at.astimezone(UTC).isoformat()


def _timestamp_token(generated_at: datetime) -> str:
    return generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _scenario_sha256(scenario: Scenario) -> str:
    canonical = json.dumps(
        scenario.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _exec_version() -> str:
    try:
        return package_version("silicondraft")
    except PackageNotFoundError:  # pragma: no cover - running from an unpacked tree
        return "0.0.0"


def _safe_filename_part(value: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", value).strip("_") or "unnamed"
