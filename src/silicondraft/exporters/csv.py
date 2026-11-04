"""CP multi-block CSV export: one file per wafer."""

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..binning import HARD_BIN_DEFINITIONS, SOFT_BIN_DEFINITIONS, item_passed
from ..dataset import CPLot, CPWafer, GenerationResult, WatLot
from .common import (
    CsvWriter,
)
from .common import (
    engine_version as _exec_version,
)
from .common import (
    format_float as _format_float,
)
from .common import (
    format_optional_float as _format_optional_float,
)
from .common import (
    format_timestamp as _format_timestamp,
)
from .common import (
    safe_filename_part as _safe_filename_part,
)
from .common import (
    scenario_sha256 as _scenario_sha256,
)
from .common import (
    timestamp_token as _timestamp_token,
)

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

_CP_LONG_HEADER = (
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
)

_HARD_BIN_NAME_BY_NUMBER = {
    definition.number: definition.name for definition in HARD_BIN_DEFINITIONS
}
_SOFT_BIN_NAME_BY_NUMBER = {
    definition.number: definition.name for definition in SOFT_BIN_DEFINITIONS
}

_WAT_HEADER = (
    "lot_id",
    "wafer_id",
    "wat_site",
    "site_x_mm",
    "site_y_mm",
    "test_num",
    "item_id",
    "value",
    "unit",
    "lsl",
    "usl",
    "pass",
    "timestamp",
)


def export_cp_csv(
    result: GenerationResult, out_dir: Path, *, layout: str | None = None
) -> tuple[Path, ...]:
    """Write CP CSV files in ``layout``, defaulting to ``export.cp_csv_layout``."""
    selected = result.scenario.export.cp_csv_layout if layout is None else layout
    paths: list[Path] = []
    if selected in ("blocks", "both"):
        paths.extend(export_cp_csv_blocks(result, out_dir))
    if selected in ("long", "both"):
        paths.extend(export_cp_csv_long(result, out_dir))
    return tuple(paths)


def export_cp_csv_blocks(result: GenerationResult, out_dir: Path) -> tuple[Path, ...]:
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


def export_cp_csv_long(result: GenerationResult, out_dir: Path) -> tuple[Path, ...]:
    """Write one pure long CP CSV per lot and return the written paths.

    The file name is ``{product}_{lot}_CP_{timestamp}.csv``; each row is one
    wafer x die x item measurement.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = result.scenario.export.encoding
    timestamp = _timestamp_token(result.generated_at)
    product = _safe_filename_part(result.scenario.product.name)
    paths: list[Path] = []
    for lot in result.lots:
        lot_part = _safe_filename_part(lot.lot_id)
        path = out_dir / f"{product}_{lot_part}_CP_{timestamp}.csv"
        _write_cp_long_lot(path, lot, result, encoding)
        paths.append(path)
    return tuple(paths)


def export_wat_csv(result: GenerationResult, out_dir: Path) -> tuple[Path, ...]:
    """Write one long WAT CSV per lot and return the written paths.

    The file name is ``{product}_{lot}_WAT_{timestamp}.csv``; each row is one
    wafer x site x item measurement.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = result.scenario.export.encoding
    timestamp = _timestamp_token(result.generated_at)
    product = _safe_filename_part(result.scenario.product.name)
    paths: list[Path] = []
    for lot in result.wat_lots:
        lot_part = _safe_filename_part(lot.lot_id)
        path = out_dir / f"{product}_{lot_part}_WAT_{timestamp}.csv"
        _write_wat_lot(path, lot, result, encoding)
        paths.append(path)
    return tuple(paths)


def _write_wat_lot(
    path: Path,
    lot: WatLot,
    result: GenerationResult,
    encoding: str,
) -> None:
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(_WAT_HEADER)
        for wafer in lot.wafers:
            passed = {
                item.id: item_passed(item, wafer.values[item.id]) for item in result.wat_items
            }
            for site_index in range(wafer.site_count):
                for item in result.wat_items:
                    writer.writerow(
                        (
                            lot.lot_id,
                            wafer.wafer_id,
                            int(wafer.site_number[site_index]),
                            _format_float(float(wafer.x_mm[site_index])),
                            _format_float(float(wafer.y_mm[site_index])),
                            item.test_num,
                            item.id,
                            _format_float(float(wafer.values[item.id][site_index])),
                            item.unit,
                            _format_optional_float(item.lsl),
                            _format_optional_float(item.usl),
                            int(passed[item.id][site_index]),
                            _format_timestamp(wafer.tested_at),
                        )
                    )


def _write_cp_long_lot(
    path: Path,
    lot: CPLot,
    result: GenerationResult,
    encoding: str,
) -> None:
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(_CP_LONG_HEADER)
        items = result.items
        for wafer in lot.wafers:
            timestamp = _format_timestamp(wafer.tested_at)
            item_passes = {item.id: item_passed(item, wafer.values[item.id]) for item in items}
            for index in range(wafer.die_count):
                hard_bin = int(wafer.hard_bin[index])
                soft_bin = int(wafer.soft_bin[index])
                die_fields = (
                    lot.lot_id,
                    wafer.wafer_id,
                    _format_float(float(wafer.x_mm[index])),
                    _format_float(float(wafer.y_mm[index])),
                    int(wafer.grid_x[index]),
                    int(wafer.grid_y[index]),
                    int(wafer.test_site[index]),
                    hard_bin,
                    _HARD_BIN_NAME_BY_NUMBER[hard_bin],
                    soft_bin,
                    _SOFT_BIN_NAME_BY_NUMBER[soft_bin],
                    int(wafer.passed[index]),
                )
                for item in items:
                    writer.writerow(
                        (
                            *die_fields,
                            item.test_num,
                            item.id,
                            _format_float(float(wafer.values[item.id][index])),
                            item.unit,
                            _format_optional_float(item.lsl),
                            _format_optional_float(item.usl),
                            int(item_passes[item.id][index]),
                            timestamp,
                        )
                    )


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
    writer: CsvWriter,
    marker: str,
    header: Sequence[object],
    rows: Iterable[Sequence[object]],
) -> None:
    writer.writerow([marker])
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)


def _write_metadata(
    writer: CsvWriter,
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


def _write_test_items(writer: CsvWriter, result: GenerationResult) -> None:
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


def _write_bin_definitions(writer: CsvWriter) -> None:
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


def _write_test_data(writer: CsvWriter, wafer: CPWafer, result: GenerationResult) -> None:
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
