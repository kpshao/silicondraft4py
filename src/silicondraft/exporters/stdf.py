"""STDF V4 export for CP data: one file per lot.

The writer follows the STDF V4 record layouts and missing/invalid-data rules.
Records are written little-endian with CPU type 2 so independent parsers can
decode the file; ``pystdf`` is used as a test-only oracle.

A file contains FAR, MIR, one WIR/WCR/…/WRR group per wafer, one PCR, the HBR
and SBR summaries, one TSR per CP item, and MRR.
"""

from __future__ import annotations

import math
import struct
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Final

from ..binning import HARD_BIN_DEFINITIONS, SOFT_BIN_DEFINITIONS, BinDefinition, item_passed
from ..catalog import CatalogItem
from ..dataset import BoolArray, CPLot, CPWafer, GenerationResult
from ..errors import ExportError
from ..i18n import _
from .common import engine_version, safe_filename_part, timestamp_token

PHASE: Final = "CP"
STDF_VERSION: Final = 4
LITTLE_ENDIAN_CPU_TYPE: Final = 2

FAR: Final = (0, 10)
MIR: Final = (1, 10)
MRR: Final = (1, 20)
PCR: Final = (1, 30)
HBR: Final = (1, 40)
SBR: Final = (1, 50)
WIR: Final = (2, 10)
WRR: Final = (2, 20)
WCR: Final = (2, 30)
PIR: Final = (5, 10)
PRR: Final = (5, 20)
PTR: Final = (15, 10)
TSR: Final = (10, 30)

# Standard STDF V4 missing/invalid values.
MISSING_U1: Final = 255
MISSING_U2: Final = 65_535
MISSING_U4: Final = 4_294_967_295
_CN_LENGTH_MAX: Final = 255

_HEADER = struct.Struct("<HBB")
_SUMMARY_HEAD: Final = 255
_HEAD_NUM: Final = 1
_SITE_GROUP: Final = 255
_WAFER_UNITS_MM: Final = 3

_OPT_FLAG_RESERVED: Final = 0x02
_OPT_FLAG_NO_LOW_SPEC: Final = 0x04
_OPT_FLAG_NO_HIGH_SPEC: Final = 0x08
_OPT_FLAG_LOW_LIMIT_INVALID: Final = 0x10
_OPT_FLAG_HIGH_LIMIT_INVALID: Final = 0x20
_OPT_FLAG_NO_LOW_LIMIT: Final = 0x40
_OPT_FLAG_NO_HIGH_LIMIT: Final = 0x80

_TEST_FLAG_FAILED: Final = 0x80
_PARM_FLAG_HIGH_FAIL: Final = 0x08
_PARM_FLAG_LOW_FAIL: Final = 0x10
_PARM_FLAG_EQUALITY_PASSES: Final = 0xC0
_PART_FLAG_FAILED: Final = 0x08

_TSR_OPT_FLAG: Final = 0xCC  # TEST_TIM invalid; reserved bits 3, 6, and 7 set
_TSR_OPT_FLAG_ALL_INVALID: Final = 0xFF

_HARD_BINS: dict[int, BinDefinition] = {
    definition.number: definition for definition in HARD_BIN_DEFINITIONS
}
_SOFT_BINS: dict[int, BinDefinition] = {
    definition.number: definition for definition in SOFT_BIN_DEFINITIONS
}


@dataclass(frozen=True, slots=True)
class _PtrTemplate:
    """The per-item bytes shared by every PTR of that item."""

    prefix: bytes
    suffix: bytes
    lsl: float | None
    usl: float | None


@dataclass(slots=True)
class _ItemStats:
    """Lot-wide execution/result totals for one CP item."""

    executions: int = 0
    failures: int = 0
    minimum: float = math.inf
    maximum: float = -math.inf
    total: float = 0.0
    total_squares: float = 0.0

    def add_wafer(self, item: CatalogItem, wafer: CPWafer, passed: BoolArray) -> None:
        column = wafer.values[item.id]
        self.executions += int(column.size)
        self.failures += int((~passed).sum())
        if column.size:
            self.minimum = min(self.minimum, float(column.min()))
            self.maximum = max(self.maximum, float(column.max()))
            self.total += float(column.sum())
            self.total_squares += float((column * column).sum())


def export_cp_stdf(result: GenerationResult, out_dir: Path) -> tuple[Path, ...]:
    """Write one STDF V4 file per CP lot and return the written paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp_token(result.generated_at)
    product = safe_filename_part(result.scenario.product.name)
    paths: list[Path] = []
    for lot in result.lots:
        lot_part = safe_filename_part(lot.lot_id)
        path = out_dir / f"{product}_{lot_part}_{PHASE}_{timestamp}.stdf"
        write_cp_stdf_lot(path, lot, result)
        paths.append(path)
    return tuple(paths)


def write_cp_stdf_lot(path: Path, lot: CPLot, result: GenerationResult) -> None:
    """Write the STDF V4 file for ``lot`` to ``path``."""
    try:
        with path.open("wb") as stream:
            _write_lot(stream, lot, result)
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise ExportError(
            _("cannot write STDF file {path}: {error}").format(path=path, error=exc)
        ) from exc
    except (struct.error, OverflowError) as exc:
        path.unlink(missing_ok=True)
        raise ExportError(_("cannot encode STDF record: {error}").format(error=exc)) from exc
    except ExportError:
        path.unlink(missing_ok=True)
        raise


def _write_lot(stream: BinaryIO, lot: CPLot, result: GenerationResult) -> None:
    items = result.items
    templates = tuple(_ptr_template(item) for item in items)
    stats = [_ItemStats() for _ in items]
    hard_counts: Counter[int] = Counter()
    soft_counts: Counter[int] = Counter()
    first_time = lot.wafers[0].tested_at if lot.wafers else result.generated_at
    last_time = lot.wafers[-1].tested_at if lot.wafers else result.generated_at

    _write_record(stream, *FAR, _far_body())
    _write_record(stream, *MIR, _mir_body(result, lot, first_time))
    for wafer in lot.wafers:
        _write_record(stream, *WIR, _wir_body(wafer))
        _write_record(stream, *WCR, _wcr_body(result, wafer))
        passes = {item.id: item_passed(item, wafer.values[item.id]) for item in items}
        for index in range(wafer.die_count):
            test_site = int(wafer.test_site[index])
            _write_record(stream, *PIR, struct.pack("<BB", _HEAD_NUM, _check_site_num(test_site)))
            for item, template in zip(items, templates, strict=True):
                value = float(wafer.values[item.id][index])
                _write_record(
                    stream,
                    *PTR,
                    _ptr_body(template, test_site, value, bool(passes[item.id][index])),
                )
            hard_bin = int(wafer.hard_bin[index])
            soft_bin = int(wafer.soft_bin[index])
            hard_counts[hard_bin] += 1
            soft_counts[soft_bin] += 1
            _write_record(
                stream,
                *PRR,
                _prr_body(
                    site_num=test_site,
                    passed=bool(wafer.passed[index]),
                    num_test=len(items),
                    hard_bin=hard_bin,
                    soft_bin=soft_bin,
                    x_coord=int(wafer.grid_x[index]),
                    y_coord=int(wafer.grid_y[index]),
                ),
            )
        _write_record(stream, *WRR, _wrr_body(wafer))
        for item, item_stats in zip(items, stats, strict=True):
            item_stats.add_wafer(item, wafer, passes[item.id])

    _write_record(stream, *PCR, _pcr_body(lot))
    _write_bin_summaries(stream, hard_counts, _HARD_BINS, HBR, "HBIN_NAM", "hard")
    _write_bin_summaries(stream, soft_counts, _SOFT_BINS, SBR, "SBIN_NAM", "soft")
    for item, item_stats in zip(items, stats, strict=True):
        _write_record(stream, *TSR, _tsr_body(item, item_stats))
    _write_record(stream, *MRR, _mrr_body(last_time))


def _write_record(stream: BinaryIO, typ: int, sub: int, body: bytes) -> None:
    if len(body) > MISSING_U2:
        raise ExportError(_("STDF record is too long ({size} bytes)").format(size=len(body)))
    stream.write(_HEADER.pack(len(body), typ, sub) + body)


def _far_body() -> bytes:
    return struct.pack("<BB", LITTLE_ENDIAN_CPU_TYPE, STDF_VERSION)


def _mir_body(result: GenerationResult, lot: CPLot, start: datetime) -> bytes:
    scenario = result.scenario
    product = scenario.product
    job_name = product.test_program or scenario.items.preset
    return b"".join(
        (
            struct.pack("<II", _stdf_time(result.generated_at), _stdf_time(start)),
            bytes((0,)) + _c1("P") + _c1("N") + _c1(" ") + struct.pack("<H", MISSING_U2),
            _c1(" "),
            _cn(lot.lot_id, "LOT_ID"),
            _cn(product.name, "PART_TYP"),
            _cn("SIM", "NODE_NAM"),
            _cn("SIM", "TSTR_TYP"),
            _cn(job_name, "JOB_NAM"),
            _cn("", "JOB_REV"),
            _cn(lot.lot_id, "SBLOT_ID"),
            _cn("", "OPER_NAM"),
            _cn("SiliconDraft", "EXEC_TYP"),
            _cn(engine_version(), "EXEC_VER"),
            _cn(PHASE, "TEST_COD"),
            _cn("", "TST_TEMP"),
            _cn("", "USER_TXT"),
            _cn("", "AUX_FILE"),
            _cn("", "PKG_TYP"),
            _cn(product.device_family, "FAMLY_ID"),
            _cn("", "DATE_COD"),
            _cn(product.fab, "FACIL_ID"),
            _cn("", "FLOOR_ID"),
            _cn(product.process_node, "PROC_ID"),
            _cn("", "OPER_FRQ"),
            _cn("", "SPEC_NAM"),
            _cn("", "SPEC_VER"),
            _cn("", "FLOW_ID"),
            _cn("", "SETUP_ID"),
            _cn("", "DSGN_REV"),
            _cn("", "ENG_ID"),
            _cn("", "ROM_COD"),
            _cn("", "SERL_NUM"),
            _cn("", "SUPR_NAM"),
        )
    )


def _mrr_body(finish: datetime) -> bytes:
    return b"".join(
        (
            struct.pack("<I", _stdf_time(finish)),
            _c1(" "),
            _cn("", "USR_DESC"),
            _cn("", "EXC_DESC"),
        )
    )


def _wir_body(wafer: CPWafer) -> bytes:
    return b"".join(
        (
            struct.pack("<BBI", _HEAD_NUM, _SITE_GROUP, _stdf_time(wafer.tested_at)),
            _cn(wafer.wafer_id, "WAFER_ID"),
        )
    )


def _wrr_body(wafer: CPWafer) -> bytes:
    return b"".join(
        (
            struct.pack(
                "<BBIIIIII",
                _HEAD_NUM,
                _SITE_GROUP,
                _stdf_time(wafer.tested_at),
                wafer.die_count,
                0,
                0,
                wafer.pass_count,
                wafer.die_count,
            ),
            _cn(wafer.wafer_id, "WAFER_ID"),
            _cn("", "FABWF_ID"),
            _cn("", "FRAME_ID"),
            _cn("", "MASK_ID"),
            _cn("", "USR_DESC"),
            _cn("", "EXC_DESC"),
        )
    )


def _wcr_body(result: GenerationResult, wafer: CPWafer) -> bytes:
    scenario = result.scenario
    width_mm, height_mm = scenario.wafer.die_size_mm
    center_x = int(wafer.grid_x.max()) // 2 if wafer.die_count else 0
    center_y = int(wafer.grid_y.max()) // 2 if wafer.die_count else 0
    return b"".join(
        (
            struct.pack(
                "<fffB",
                float(scenario.wafer.diameter_mm),
                float(height_mm),
                float(width_mm),
                _WAFER_UNITS_MM,
            ),
            _c1("D"),
            struct.pack("<hh", _check_i2(center_x, "CENTER_X"), _check_i2(center_y, "CENTER_Y")),
            _c1("R"),
            _c1("U"),
        )
    )


def _pcr_body(lot: CPLot) -> bytes:
    return struct.pack(
        "<BBIIIII",
        _SUMMARY_HEAD,
        _SUMMARY_HEAD,
        lot.die_count,
        0,
        0,
        lot.pass_count,
        lot.die_count,
    )


def _write_bin_summaries(
    stream: BinaryIO,
    counts: Counter[int],
    definitions: dict[int, BinDefinition],
    record_type: tuple[int, int],
    field: str,
    kind: str,
) -> None:
    for number in sorted(counts):
        definition = definitions.get(number)
        if definition is None:
            raise ExportError(_("unknown {kind} bin {bin}").format(kind=kind, bin=number))
        _write_record(stream, *record_type, _bin_body(definition, counts[number], field))


def _bin_body(definition: BinDefinition, count: int, field: str) -> bytes:
    body = struct.pack("<BBHI", _SUMMARY_HEAD, _SUMMARY_HEAD, definition.number, count)
    return body + _c1("P" if definition.passed else "F") + _cn(definition.name, field)


def _ptr_template(item: CatalogItem) -> _PtrTemplate:
    opt_flag = _OPT_FLAG_RESERVED
    if item.lsl is None:
        opt_flag |= _OPT_FLAG_NO_LOW_SPEC | _OPT_FLAG_LOW_LIMIT_INVALID | _OPT_FLAG_NO_LOW_LIMIT
    if item.usl is None:
        opt_flag |= _OPT_FLAG_NO_HIGH_SPEC | _OPT_FLAG_HIGH_LIMIT_INVALID | _OPT_FLAG_NO_HIGH_LIMIT
    low = float(item.lsl) if item.lsl is not None else 0.0
    high = float(item.usl) if item.usl is not None else 0.0
    suffix = b"".join(
        (
            _cn(item.description, "TEST_TXT"),
            _cn("", "ALARM_ID"),
            bytes((opt_flag, 0, 0, 0)),
            struct.pack("<ff", low, high),
            _cn(item.unit, "UNITS"),
            _cn("", "C_RESFMT"),
            _cn("", "C_LLMFMT"),
            _cn("", "C_HLMFMT"),
            struct.pack("<ff", low, high),
        )
    )
    return _PtrTemplate(
        prefix=struct.pack("<I", item.test_num) + bytes((_HEAD_NUM,)),
        suffix=suffix,
        lsl=item.lsl,
        usl=item.usl,
    )


def _ptr_body(template: _PtrTemplate, site_num: int, value: float, passed: bool) -> bytes:
    test_flag = 0 if passed else _TEST_FLAG_FAILED
    param_flag = _PARM_FLAG_EQUALITY_PASSES
    if template.lsl is not None and value < template.lsl:
        param_flag |= _PARM_FLAG_LOW_FAIL
    if template.usl is not None and value > template.usl:
        param_flag |= _PARM_FLAG_HIGH_FAIL
    return b"".join(
        (
            template.prefix,
            struct.pack("<BBB", _check_site_num(site_num), test_flag, param_flag),
            struct.pack("<f", value),
            template.suffix,
        )
    )


def _prr_body(
    *,
    site_num: int,
    passed: bool,
    num_test: int,
    hard_bin: int,
    soft_bin: int,
    x_coord: int,
    y_coord: int,
) -> bytes:
    return b"".join(
        (
            struct.pack(
                "<BBBHHHhhI",
                _HEAD_NUM,
                _check_site_num(site_num),
                0 if passed else _PART_FLAG_FAILED,
                num_test,
                hard_bin,
                soft_bin,
                _check_i2(x_coord, "X_COORD"),
                _check_i2(y_coord, "Y_COORD"),
                0,
            ),
            _cn("", "PART_ID"),
            _cn("", "PART_TXT"),
            bytes((0,)),
        )
    )


def _tsr_body(item: CatalogItem, stats: _ItemStats) -> bytes:
    if stats.executions == 0:
        counts = struct.pack("<III", MISSING_U4, MISSING_U4, MISSING_U4)
        opt_flag = _TSR_OPT_FLAG_ALL_INVALID
        minimum = maximum = total = total_squares = 0.0
    else:
        counts = struct.pack("<III", stats.executions, stats.failures, 0)
        opt_flag = _TSR_OPT_FLAG
        minimum = stats.minimum
        maximum = stats.maximum
        total = stats.total
        total_squares = stats.total_squares
    return b"".join(
        (
            bytes((_SUMMARY_HEAD, _SUMMARY_HEAD)),
            _c1("F" if item.distribution == "bernoulli" else "P"),
            struct.pack("<I", item.test_num),
            counts,
            _cn(item.id, "TEST_NAM"),
            _cn("", "SEQ_NAME"),
            _cn("", "TEST_LBL"),
            bytes((opt_flag,)),
            struct.pack("<fffff", 0.0, minimum, maximum, total, total_squares),
        )
    )


def _stdf_time(value: datetime) -> int:
    """Convert a timestamp to STDF's U*4 epoch seconds."""
    seconds = int(value.astimezone(UTC).timestamp())
    if not 0 <= seconds < MISSING_U4:
        raise ExportError(
            _("timestamp {value} does not fit an STDF U*4 field").format(value=value.isoformat())
        )
    return seconds


def _check_site_num(value: int) -> int:
    """Validate an individual STDF SITE_NUM (255 is reserved for summaries)."""
    if not 1 <= value <= 254:
        raise ExportError(
            _("STDF SITE_NUM {value} is outside the U*1 range 1-254").format(value=value)
        )
    return value


def _check_i2(value: int, field: str) -> int:
    """Validate a signed two-byte STDF integer field."""
    if not -32767 <= value <= 32767:
        raise ExportError(
            _("STDF field {field} value {value} is outside the I*2 range").format(
                field=field, value=value
            )
        )
    return value


def _c1(value: str) -> bytes:
    """Encode one fixed STDF C*1 byte."""
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ExportError(
            _("STDF fixed string {value!r} is not ASCII").format(value=value)
        ) from exc
    if len(encoded) != 1:
        raise ExportError(_("STDF fixed string {value!r} must be one byte").format(value=value))
    return encoded


def _cn(value: str, field: str) -> bytes:
    """Encode an STDF C*n string as a length byte followed by ASCII bytes."""
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ExportError(
            _("STDF field {field} is not ASCII: {value!r}").format(field=field, value=value)
        ) from exc
    if len(encoded) > _CN_LENGTH_MAX:
        raise ExportError(_("STDF field {field} is longer than 255 bytes").format(field=field))
    return bytes((len(encoded),)) + encoded
