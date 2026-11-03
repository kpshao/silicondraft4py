"""Public generation and export API."""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
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
    PatternReport,
    WatLot,
    WatWafer,
)
from .defects import apply_random_defects
from .errors import ExportError, ScenarioError
from .exporters import export_cp_csv, export_wat_csv
from .exporters.groundtruth import export_ground_truth
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
from .patterns import apply_pattern, pattern_id, select_yield_failure_item
from .scenario.models import Lots, Scenario
from .scenario.validation import validate_scenario_model

_TAG_LOT_FACTOR = 0x10
_TAG_WAFER_FACTOR = 0x11
_TAG_DIE_FACTOR = 0x12
_TAG_CP_NOISE = 0x20
_TAG_WAT_NOISE = 0x21
_TAG_PATTERN = 0x30
_TAG_PATTERN_SCOPE = 0x31
_TAG_DEFECT = 0x40


@dataclass
class _PatternAccumulator:
    """Mutable per-pattern totals collected across lots and wafers."""

    affected_die_count: int = 0
    realized_failures: int = 0
    item_shift_sum: float = 0.0
    item_shift_die_count: int = 0
    recovery_probability_sum: float = 0.0
    affected_wafers: list[tuple[str, str]] = field(default_factory=list)


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
    items_by_id = {item.id: item for item in items}
    yield_failure_item = select_yield_failure_item(enabled_items)
    defect_targets = tuple(
        items_by_id[item_id] for item_id in scenario.defects.target_items if item_id in items_by_id
    )

    generated_at = datetime.now(UTC)
    timeline_start = _timeline_start(scenario, generated_at)
    layout = layout_dies(scenario.wafer)
    wat_layout = layout_wat_sites(scenario.wafer)
    nearest_dies = nearest_die_indices(wat_layout, layout)
    factor_count = len(FACTORS)
    pattern_stats = [_PatternAccumulator() for _ in scenario.patterns]
    lots: list[CPLot] = []
    wat_lots: list[WatLot] = []
    for lot_number in range(1, scenario.lots.count + 1):
        lot_id = scenario.lots.lot_id_template.format(product=scenario.product.name, lot=lot_number)
        lot_factors = _rng(scenario.seed, _TAG_LOT_FACTOR, lot_number).standard_normal(factor_count)
        wafer_scoped_targets = _wafer_scoped_targets(scenario, lot_number)
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
            recovery = np.zeros(layout.count, dtype=np.float64)
            pattern_hits = {}
            for index, pattern in enumerate(scenario.patterns):
                if index in wafer_scoped_targets and wafer_scoped_targets[index] != wafer_number:
                    continue
                application = apply_pattern(
                    pattern,
                    index,
                    items_by_id,
                    values,
                    layout,
                    scenario.wafer,
                    yield_failure_item,
                    _rng(scenario.seed, _TAG_PATTERN, lot_number, wafer_number, index),
                )
                pattern_hits[application.pattern_id] = application.hit
                recovery = 1.0 - (1.0 - recovery) * (1.0 - application.recovery)
                stats = pattern_stats[index]
                stats.affected_die_count += int(application.hit.sum())
                stats.realized_failures += int(application.failure.sum())
                stats.item_shift_sum += application.item_shift_sum
                stats.item_shift_die_count += application.item_shift_die_count
                stats.recovery_probability_sum += float(application.recovery.sum())
                if pattern.scope == "wafer":
                    stats.affected_wafers.append((lot_id, wafer_id))
            defects = apply_random_defects(
                scenario.defects,
                defect_targets,
                values,
                layout,
                recovery,
                _rng(scenario.seed, _TAG_DEFECT, lot_number, wafer_number),
            )
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
                    factors=factors,
                    pattern_hits=pattern_hits,
                    defect_failure=defects.failure,
                    defect_clusters=defects.clusters,
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
        pattern_reports=tuple(
            PatternReport(
                pattern_id=pattern_id(index),
                affected_die_count=stats.affected_die_count,
                realized_failures=stats.realized_failures,
                item_shift_sum=stats.item_shift_sum,
                item_shift_die_count=stats.item_shift_die_count,
                recovery_probability_sum=stats.recovery_probability_sum,
                affected_wafers=tuple(stats.affected_wafers),
            )
            for index, stats in enumerate(pattern_stats)
        ),
        generated_at=generated_at,
    )


def export(
    result: GenerationResult,
    out_dir: str | PathLike[str],
    formats: Sequence[str] = ("csv",),
    *,
    include_die_truth: bool | None = None,
) -> tuple[Path, ...]:
    """Export a generation result and return the paths written.

    ``include_die_truth`` overrides ``export.include_die_truth`` for this run;
    the CLI's ``--no-die-truth`` passes ``False``. The manifest itself is still
    written when ``export.ground_truth`` is enabled.
    """
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
        if result.scenario.export.ground_truth:
            write_die_truth = (
                result.scenario.export.include_die_truth
                if include_die_truth is None
                else include_die_truth
            )
            paths.extend(export_ground_truth(result, out, include_die_truth=write_die_truth))
    except OSError as exc:
        raise ExportError(f"cannot export to {out_dir}: {exc}") from exc
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


def _wafer_scoped_targets(scenario: Scenario, lot_number: int) -> dict[int, int]:
    """Pick the one-based wafer each wafer-scoped pattern applies to in a lot."""
    targets: dict[int, int] = {}
    for index, pattern in enumerate(scenario.patterns):
        if pattern.scope != "wafer":
            continue
        rng = _rng(scenario.seed, _TAG_PATTERN_SCOPE, lot_number, index)
        targets[index] = int(rng.integers(1, scenario.lots.wafers_per_lot + 1))
    return targets


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
