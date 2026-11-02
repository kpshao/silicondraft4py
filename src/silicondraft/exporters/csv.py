"""CP wide CSV export: one row per die, one column per CP test item."""

import csv
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ..dataset import CPLot, CPWafer, GenerationResult

_METADATA_COLUMNS = (
    "lot_id",
    "wafer_id",
    "die_x_mm",
    "die_y_mm",
    "grid_x",
    "grid_y",
    "test_site",
    "hard_bin",
    "pass",
)
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


class _CsvWriter(Protocol):
    """The subset of ``csv.writer`` used by this module."""

    def writerow(self, row: Sequence[object]) -> object: ...


def export_cp_csv(result: GenerationResult, out_dir: Path) -> tuple[Path, ...]:
    """Write one wide CP CSV per lot and return the written paths.

    The file name is ``{product}_{lot}_CP_{timestamp}.csv``; the timestamp is
    part of the file name only, so exported measurements stay reproducible.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    encoding = result.scenario.export.encoding
    timestamp = _timestamp_token(result.generated_at)
    product = _safe_filename_part(result.scenario.product.name)
    paths: list[Path] = []
    for lot in result.lots:
        path = out_dir / f"{product}_{_safe_filename_part(lot.lot_id)}_CP_{timestamp}.csv"
        _write_lot(path, lot, result, encoding)
        paths.append(path)
    return tuple(paths)


def _write_lot(path: Path, lot: CPLot, result: GenerationResult, encoding: str) -> None:
    with path.open("w", encoding=encoding, newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow([*_METADATA_COLUMNS, *(item.id for item in result.items)])
        for wafer in lot.wafers:
            _write_wafer(writer, lot.lot_id, wafer, result)


def _write_wafer(
    writer: _CsvWriter,
    lot_id: str,
    wafer: CPWafer,
    result: GenerationResult,
) -> None:
    item_columns = [wafer.values[item.id] for item in result.items]
    for index in range(wafer.die_count):
        writer.writerow(
            [
                lot_id,
                wafer.wafer_id,
                _format_float(float(wafer.x_mm[index])),
                _format_float(float(wafer.y_mm[index])),
                int(wafer.grid_x[index]),
                int(wafer.grid_y[index]),
                int(wafer.test_site[index]),
                int(wafer.hard_bin[index]),
                int(wafer.passed[index]),
                *(_format_float(float(column[index])) for column in item_columns),
            ]
        )


def _format_float(value: float) -> str:
    return format(value, ".10g")


def _timestamp_token(generated_at: datetime) -> str:
    return generated_at.astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _safe_filename_part(value: str) -> str:
    return _UNSAFE_FILENAME_CHARS.sub("_", value).strip("_") or "unnamed"
