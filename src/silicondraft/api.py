"""Public generation and export API."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from os import PathLike
from pathlib import Path

import numpy as np

from .binning import PASS, classify_bins
from .catalog import resolve_catalog
from .dataset import (
    CPLot,
    CPWafer,
    FloatArray,
    GenerationResult,
    IntArray,
    LinkageReportEntry,
    WatLot,
    WatWafer,
)
from .errors import ExportError, ScenarioError
from .exporters import export_cp_csv, export_wat_csv
from .geometry import layout_dies, layout_wat_sites, nearest_die_indices
from .latent import (
    FACTORS,
    LatentModel,
    build_latent_model,
    combine_factor_components,
    cp_latent,
    sample_measurements,
    wat_latent,
)
from .scenario.models import Lots, Scenario
from .scenario.validation import validate_scenario_model

_TAG_LOT_FACTOR = 0x10
_TAG_WAFER_FACTOR = 0x11
_TAG_DIE_FACTOR = 0x12
_TAG_CP_NOISE = 0x20
_TAG_WAT_NOISE = 0x21


def generate(scenario: Scenario) -> GenerationResult:
    """Generate CP and WAT data for a validated scenario.

    The scenario is re-validated here so that a hand-built ``Scenario`` cannot
    produce data before its geometry and item references are checked.
    """
    validation = validate_scenario_model(scenario)
    if not validation.ok:
        raise ScenarioError(validation.issues)

    resolution = resolve_catalog(scenario.items)
    if resolution.issues:
        raise ScenarioError(resolution.issues)
    enabled_items = resolution.catalog.enabled_items
    items = tuple(item for item in enabled_items if item.phase == "CP")
    wat_items = tuple(item for item in enabled_items if item.phase == "WAT")
    latent_model = build_latent_model(resolution.catalog, scenario.linkage)

    generated_at = datetime.now(UTC)
    timeline_start = _timeline_start(scenario, generated_at)
    layout = layout_dies(scenario.wafer)
    wat_layout = layout_wat_sites(scenario.wafer)
    nearest_dies = nearest_die_indices(wat_layout, layout)
    factor_count = len(FACTORS)
    lots: list[CPLot] = []
    wat_lots: list[WatLot] = []
    for lot_number in range(1, scenario.lots.count + 1):
        lot_id = scenario.lots.lot_id_template.format(product=scenario.product.name, lot=lot_number)
        lot_factors = _rng(scenario.seed, _TAG_LOT_FACTOR, lot_number).standard_normal(factor_count)
        wafers: list[CPWafer] = []
        wat_wafers: list[WatWafer] = []
        for wafer_number in range(1, scenario.lots.wafers_per_lot + 1):
            wafer_id = scenario.lots.wafer_id_template.format(
                product=scenario.product.name, lot=lot_number, wafer=wafer_number
            )
            wat_time, cp_time = _timeline(scenario.lots, timeline_start, lot_number, wafer_number)
            wafer_factors = _rng(
                scenario.seed, _TAG_WAFER_FACTOR, lot_number, wafer_number
            ).standard_normal(factor_count)
            die_components = _rng(
                scenario.seed, _TAG_DIE_FACTOR, lot_number, wafer_number
            ).standard_normal((factor_count, layout.count))
            factors = combine_factor_components(lot_factors, wafer_factors, die_components)
            site_factors = factors[:, nearest_dies]

            values = {
                item.id: sample_measurements(
                    item,
                    cp_latent(latent_model, item.id, factors),
                    latent_model.cp_noise_std(item.id),
                    _rng(scenario.seed, _TAG_CP_NOISE, lot_number, wafer_number, item.test_num),
                )
                for item in items
            }
            bins = classify_bins(items, values, layout.count)
            wafers.append(
                CPWafer(
                    wafer_id=wafer_id,
                    x_mm=layout.x_mm,
                    y_mm=layout.y_mm,
                    grid_x=layout.grid_x,
                    grid_y=layout.grid_y,
                    test_site=layout.test_site,
                    hard_bin=bins.hard,
                    soft_bin=bins.soft,
                    passed=bins.hard == PASS,
                    values=values,
                    tested_at=cp_time,
                )
            )
            wat_wafers.append(
                WatWafer(
                    wafer_id=wafer_id,
                    site_number=wat_layout.site_number,
                    x_mm=wat_layout.x_mm,
                    y_mm=wat_layout.y_mm,
                    values={
                        item.id: sample_measurements(
                            item,
                            wat_latent(latent_model, item.id, site_factors),
                            latent_model.wat_noise_std(item.id),
                            _rng(
                                scenario.seed,
                                _TAG_WAT_NOISE,
                                lot_number,
                                wafer_number,
                                item.test_num,
                            ),
                        )
                        for item in wat_items
                    },
                    tested_at=wat_time,
                )
            )
        lots.append(CPLot(lot_id=lot_id, wafers=tuple(wafers)))
        wat_lots.append(WatLot(lot_id=lot_id, wafers=tuple(wat_wafers)))

    return GenerationResult(
        scenario=scenario,
        items=items,
        wat_items=wat_items,
        lots=tuple(lots),
        wat_lots=tuple(wat_lots),
        linkage_report=_linkage_report(latent_model, tuple(lots), tuple(wat_lots), nearest_dies),
        generated_at=generated_at,
    )


def export(
    result: GenerationResult,
    out_dir: str | PathLike[str],
    formats: Sequence[str] = ("csv",),
) -> tuple[Path, ...]:
    """Export a generation result and return the paths written."""
    requested = tuple(format_name.lower() for format_name in formats)
    if not requested:
        raise ExportError("no export format requested; supported: csv")
    unsupported = sorted({format_name for format_name in requested if format_name != "csv"})
    if unsupported:
        raise ExportError(f"unsupported export format(s): {', '.join(unsupported)}; supported: csv")

    out = Path(out_dir)
    paths: list[Path] = []
    try:
        if result.scenario.export.cp_csv:
            paths.extend(export_cp_csv(result, out))
        if result.scenario.export.wat_csv:
            paths.extend(export_wat_csv(result, out))
    except OSError as exc:
        raise ExportError(f"cannot export CSV to {out_dir}: {exc}") from exc
    return tuple(paths)


def _timeline_start(scenario: Scenario, generated_at: datetime) -> datetime:
    start = scenario.lots.start_date
    if start is None:
        return generated_at
    if start.tzinfo is None:
        return start.replace(tzinfo=UTC)
    return start.astimezone(UTC)


def _timeline(
    lots: Lots, start: datetime, lot_number: int, wafer_number: int
) -> tuple[datetime, datetime]:
    """Return the (WAT, CP) timestamps for one wafer.

    WAT for wafer ``n`` starts one CP-duration after wafer ``n-1``; CP follows
    the WAT measurement by ``wat_to_cp_gap_min``. Lot 1 starts at ``start`` and
    each subsequent lot starts ``lot_interval_hours`` later.
    """
    lot_start = start + timedelta(hours=lots.lot_interval_hours * (lot_number - 1))
    wat_time = lot_start + timedelta(minutes=lots.cp_duration_min_per_wafer * (wafer_number - 1))
    cp_time = wat_time + timedelta(minutes=lots.wat_to_cp_gap_min)
    return wat_time, cp_time


def _rng(seed: int, *keys: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([seed, *keys]))


def _linkage_report(
    model: LatentModel,
    lots: tuple[CPLot, ...],
    wat_lots: tuple[WatLot, ...],
    nearest_dies: IntArray,
) -> tuple[LinkageReportEntry, ...]:
    entries: list[LinkageReportEntry] = []
    for pair in model.pairs:
        wat_chunks: list[FloatArray] = []
        cp_chunks: list[FloatArray] = []
        for wat_lot, cp_lot in zip(wat_lots, lots, strict=True):
            for wat_wafer, cp_wafer in zip(wat_lot.wafers, cp_lot.wafers, strict=True):
                wat_chunks.append(wat_wafer.values[pair.wat_item])
                cp_chunks.append(cp_wafer.values[pair.cp_item][nearest_dies])
        if wat_chunks:
            wat_values = np.concatenate(wat_chunks)
            cp_values = np.concatenate(cp_chunks)
            observed_r = _pearson(wat_values, cp_values)
            sample_count = int(wat_values.size)
        else:
            observed_r = 0.0
            sample_count = 0
        entries.append(
            LinkageReportEntry(
                wat_item=pair.wat_item,
                cp_item=pair.cp_item,
                factor=pair.factor,
                target_r=pair.target_r,
                achieved_r=model.achieved_r[(pair.wat_item, pair.cp_item)],
                observed_r=observed_r,
                sample_count=sample_count,
            )
        )
    return tuple(entries)


def _pearson(left: FloatArray, right: FloatArray) -> float:
    if left.size < 2:
        return 0.0
    left_centered = left - left.mean()
    right_centered = right - right.mean()
    denominator = math.sqrt(
        float(np.dot(left_centered, left_centered)) * float(np.dot(right_centered, right_centered))
    )
    if denominator == 0.0 or not math.isfinite(denominator):
        return 0.0
    return float(np.clip(float(np.dot(left_centered, right_centered)) / denominator, -1.0, 1.0))
