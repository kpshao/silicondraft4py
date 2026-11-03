"""Public generation and export API."""

from __future__ import annotations

import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from os import PathLike
from pathlib import Path

import numpy as np

from .binning import PASS, classify_bins
from .catalog import CatalogItem, resolve_catalog
from .dataset import (
    CPLot,
    CPWafer,
    FloatArray,
    GenerationResult,
    IntArray,
    LinkageReportEntry,
    PatternAccumulator,
    PatternReport,
    WatLot,
    WatWafer,
)
from .defects import apply_random_defects
from .errors import ExportError, ScenarioError
from .exporters import export_cp_csv, export_wat_csv
from .exporters.common import safe_filename_part, timestamp_token
from .exporters.groundtruth import (
    ManifestBuilder,
    die_truth_filename,
    export_ground_truth,
    manifest_filename,
    write_die_truth_file,
    write_manifest_file,
)
from .geometry import (
    DieLayout,
    WatSiteLayout,
    layout_dies,
    layout_wat_sites,
    nearest_die_indices,
)
from .latent import (
    FACTORS,
    LatentModel,
    build_latent_model,
    combine_factor_components,
    cp_latent,
    sample_measurements,
    wat_latent,
)
from .patterns import apply_pattern, select_yield_failure_item
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


@dataclass(frozen=True, slots=True)
class _Prepared:
    """Scenario-level data shared by every generated lot."""

    scenario: Scenario
    items: tuple[CatalogItem, ...]
    wat_items: tuple[CatalogItem, ...]
    items_by_id: dict[str, CatalogItem]
    latent_model: LatentModel
    layout: DieLayout
    wat_layout: WatSiteLayout
    nearest_dies: IntArray
    yield_failure_item: CatalogItem | None
    defect_targets: tuple[CatalogItem, ...]
    generated_at: datetime
    timeline_start: datetime


@dataclass(frozen=True, slots=True)
class _LotData:
    """One generated lot plus its own pattern contributions."""

    cp_lot: CPLot
    wat_lot: WatLot
    pattern_reports: tuple[PatternReport, ...]


@dataclass(frozen=True, slots=True)
class StreamingSummary:
    """Outcome of a streaming generation and export run."""

    lot_count: int
    wafer_count: int
    die_count: int
    pass_count: int
    linkage_report: tuple[LinkageReportEntry, ...]
    pattern_reports: tuple[PatternReport, ...]


def generate(scenario: Scenario) -> GenerationResult:
    """Generate CP and WAT data for a validated scenario.

    The scenario is re-validated here so that a hand-built ``Scenario`` cannot
    produce data before its geometry and item references are checked.
    """
    prepared = _prepare(scenario)
    pattern_totals = [PatternAccumulator() for _ in scenario.patterns]
    lots: list[CPLot] = []
    wat_lots: list[WatLot] = []
    for data in _iter_lots(prepared):
        lots.append(data.cp_lot)
        wat_lots.append(data.wat_lot)
        for index, report in enumerate(data.pattern_reports):
            pattern_totals[index].add(report)

    return GenerationResult(
        scenario=scenario,
        items=prepared.items,
        wat_items=prepared.wat_items,
        lots=tuple(lots),
        wat_lots=tuple(wat_lots),
        linkage_report=_linkage_report(
            prepared.latent_model, tuple(lots), tuple(wat_lots), prepared.nearest_dies
        ),
        pattern_reports=tuple(totals.report(index) for index, totals in enumerate(pattern_totals)),
        generated_at=prepared.generated_at,
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
    _check_formats(formats)
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


def generate_to_directory(
    scenario: Scenario,
    out_dir: str | PathLike[str],
    *,
    include_die_truth: bool | None = None,
) -> tuple[StreamingSummary, tuple[Path, ...]]:
    """Generate one lot at a time and write its artifacts before releasing it.

    Unlike :func:`generate`, this path never retains all lots' measurement
    arrays, so peak memory stays bounded by the largest single lot. It is the
    CLI's generation path; the in-memory :func:`generate` remains available for
    API callers that need the complete dataset.
    """
    prepared = _prepare(scenario)
    scenario_config = scenario.export
    out = Path(out_dir)
    timestamp = timestamp_token(prepared.generated_at)
    product = safe_filename_part(scenario.product.name)
    write_die_truth = (
        scenario_config.include_die_truth if include_die_truth is None else include_die_truth
    )
    builder = (
        ManifestBuilder(scenario, prepared.generated_at) if scenario_config.ground_truth else None
    )
    linkage = _LinkageMoments(prepared.latent_model, prepared.nearest_dies)
    pattern_totals = [PatternAccumulator() for _ in scenario.patterns]

    paths: list[Path] = []
    lot_count = 0
    wafer_count = 0
    die_count = 0
    pass_count = 0
    try:
        for data in _iter_lots(prepared):
            lot_count += 1
            wafer_count += len(data.cp_lot.wafers)
            die_count += data.cp_lot.die_count
            pass_count += data.cp_lot.pass_count
            shell = GenerationResult(
                scenario=scenario,
                items=prepared.items,
                wat_items=prepared.wat_items,
                lots=(data.cp_lot,),
                wat_lots=(data.wat_lot,),
                linkage_report=(),
                pattern_reports=(),
                generated_at=prepared.generated_at,
            )
            if scenario_config.cp_csv:
                paths.extend(export_cp_csv(shell, out))
            if scenario_config.wat_csv:
                paths.extend(export_wat_csv(shell, out))
            die_truth_file: str | None = None
            if builder is not None and write_die_truth:
                die_truth_file = die_truth_filename(product, data.cp_lot.lot_id, timestamp)
                die_truth_path = out / die_truth_file
                write_die_truth_file(die_truth_path, data.cp_lot)
                paths.append(die_truth_path)
            if builder is not None:
                builder.add_lot(
                    data.cp_lot,
                    pattern_reports=data.pattern_reports,
                    die_truth_file=die_truth_file,
                )
            linkage.add(data.cp_lot, data.wat_lot)
            for index, report in enumerate(data.pattern_reports):
                pattern_totals[index].add(report)

        linkage_report = linkage.build()
        if builder is not None:
            builder.add_linkage(linkage_report)
            manifest_path = out / manifest_filename(product, timestamp)
            write_manifest_file(manifest_path, builder.build())
            paths.append(manifest_path)
    except OSError as exc:
        raise ExportError(f"cannot export to {out_dir}: {exc}") from exc

    summary = StreamingSummary(
        lot_count=lot_count,
        wafer_count=wafer_count,
        die_count=die_count,
        pass_count=pass_count,
        linkage_report=linkage_report,
        pattern_reports=tuple(totals.report(index) for index, totals in enumerate(pattern_totals)),
    )
    return summary, tuple(paths)


def _prepare(scenario: Scenario) -> _Prepared:
    validation = validate_scenario_model(scenario)
    if not validation.ok:
        raise ScenarioError(validation.issues)
    resolution = resolve_catalog(scenario.items)
    if resolution.issues:
        raise ScenarioError(resolution.issues)

    enabled_items = resolution.catalog.enabled_items
    items = tuple(item for item in enabled_items if item.phase == "CP")
    wat_items = tuple(item for item in enabled_items if item.phase == "WAT")
    items_by_id = {item.id: item for item in items}
    latent_model = build_latent_model(resolution.catalog, scenario.linkage)
    generated_at = datetime.now(UTC)
    layout = layout_dies(scenario.wafer)
    wat_layout = layout_wat_sites(scenario.wafer)
    return _Prepared(
        scenario=scenario,
        items=items,
        wat_items=wat_items,
        items_by_id=items_by_id,
        latent_model=latent_model,
        layout=layout,
        wat_layout=wat_layout,
        nearest_dies=nearest_die_indices(wat_layout, layout),
        yield_failure_item=select_yield_failure_item(enabled_items),
        defect_targets=tuple(
            items_by_id[item_id]
            for item_id in scenario.defects.target_items
            if item_id in items_by_id
        ),
        generated_at=generated_at,
        timeline_start=_timeline_start(scenario, generated_at),
    )


def _iter_lots(prepared: _Prepared) -> Iterator[_LotData]:
    scenario = prepared.scenario
    factor_count = len(FACTORS)
    for lot_number in range(1, scenario.lots.count + 1):
        lot_id = scenario.lots.lot_id_template.format(product=scenario.product.name, lot=lot_number)
        lot_factors = _rng(scenario.seed, _TAG_LOT_FACTOR, lot_number).standard_normal(factor_count)
        wafer_scoped_targets = _wafer_scoped_targets(scenario, lot_number)
        pattern_stats = [PatternAccumulator() for _ in scenario.patterns]
        wafers: list[CPWafer] = []
        wat_wafers: list[WatWafer] = []
        for wafer_number in range(1, scenario.lots.wafers_per_lot + 1):
            wafer_id = scenario.lots.wafer_id_template.format(
                product=scenario.product.name, lot=lot_number, wafer=wafer_number
            )
            wat_time, cp_time = _timeline(
                scenario.lots, prepared.timeline_start, lot_number, wafer_number
            )
            wafer_factors = _rng(
                scenario.seed, _TAG_WAFER_FACTOR, lot_number, wafer_number
            ).standard_normal(factor_count)
            die_components = _rng(
                scenario.seed, _TAG_DIE_FACTOR, lot_number, wafer_number
            ).standard_normal((factor_count, prepared.layout.count))
            factors = combine_factor_components(lot_factors, wafer_factors, die_components)
            site_factors = factors[:, prepared.nearest_dies]

            values = {
                item.id: sample_measurements(
                    item,
                    cp_latent(prepared.latent_model, item.id, factors),
                    prepared.latent_model.cp_noise_std(item.id),
                    _rng(scenario.seed, _TAG_CP_NOISE, lot_number, wafer_number, item.test_num),
                )
                for item in prepared.items
            }
            recovery = np.zeros(prepared.layout.count, dtype=np.float64)
            pattern_hits = {}
            for index, pattern in enumerate(scenario.patterns):
                if index in wafer_scoped_targets and wafer_scoped_targets[index] != wafer_number:
                    continue
                application = apply_pattern(
                    pattern,
                    index,
                    prepared.items_by_id,
                    values,
                    prepared.layout,
                    scenario.wafer,
                    prepared.yield_failure_item,
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
                prepared.defect_targets,
                values,
                prepared.layout,
                recovery,
                _rng(scenario.seed, _TAG_DEFECT, lot_number, wafer_number),
            )
            bins = classify_bins(prepared.items, values, prepared.layout.count)
            wafers.append(
                CPWafer(
                    wafer_id=wafer_id,
                    x_mm=prepared.layout.x_mm,
                    y_mm=prepared.layout.y_mm,
                    grid_x=prepared.layout.grid_x,
                    grid_y=prepared.layout.grid_y,
                    test_site=prepared.layout.test_site,
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
                    site_number=prepared.wat_layout.site_number,
                    x_mm=prepared.wat_layout.x_mm,
                    y_mm=prepared.wat_layout.y_mm,
                    values={
                        item.id: sample_measurements(
                            item,
                            wat_latent(prepared.latent_model, item.id, site_factors),
                            prepared.latent_model.wat_noise_std(item.id),
                            _rng(
                                scenario.seed,
                                _TAG_WAT_NOISE,
                                lot_number,
                                wafer_number,
                                item.test_num,
                            ),
                        )
                        for item in prepared.wat_items
                    },
                    tested_at=wat_time,
                )
            )
        yield _LotData(
            cp_lot=CPLot(lot_id=lot_id, wafers=tuple(wafers)),
            wat_lot=WatLot(lot_id=lot_id, wafers=tuple(wat_wafers)),
            pattern_reports=tuple(stats.report(index) for index, stats in enumerate(pattern_stats)),
        )


def _check_formats(formats: Sequence[str]) -> None:
    requested = tuple(format_name.lower() for format_name in formats)
    if not requested:
        raise ExportError("no export format requested; supported: csv")
    unsupported = sorted({format_name for format_name in requested if format_name != "csv"})
    if unsupported:
        raise ExportError(f"unsupported export format(s): {', '.join(unsupported)}; supported: csv")


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


@dataclass
class _Moment:
    """Streaming Pearson moments for one WAT/CP pair."""

    count: int = 0
    mean_x: float = 0.0
    mean_y: float = 0.0
    m2_x: float = 0.0
    m2_y: float = 0.0
    co_moment: float = 0.0

    def add(self, left: FloatArray, right: FloatArray) -> None:
        if left.size == 0:
            return
        chunk = _Moment()
        chunk.count = int(left.size)
        chunk.mean_x = float(left.mean())
        chunk.mean_y = float(right.mean())
        left_centered = left - chunk.mean_x
        right_centered = right - chunk.mean_y
        chunk.m2_x = float(np.dot(left_centered, left_centered))
        chunk.m2_y = float(np.dot(right_centered, right_centered))
        chunk.co_moment = float(np.dot(left_centered, right_centered))
        self._merge(chunk)

    def _merge(self, other: _Moment) -> None:
        if other.count == 0:
            return
        if self.count == 0:
            self.count = other.count
            self.mean_x = other.mean_x
            self.mean_y = other.mean_y
            self.m2_x = other.m2_x
            self.m2_y = other.m2_y
            self.co_moment = other.co_moment
            return
        total = self.count + other.count
        delta_x = other.mean_x - self.mean_x
        delta_y = other.mean_y - self.mean_y
        weight = self.count * other.count / total
        self.m2_x += other.m2_x + delta_x * delta_x * weight
        self.m2_y += other.m2_y + delta_y * delta_y * weight
        self.co_moment += other.co_moment + delta_x * delta_y * weight
        self.mean_x += delta_x * other.count / total
        self.mean_y += delta_y * other.count / total
        self.count = total

    def correlation(self) -> float:
        if self.count < 2:
            return 0.0
        denominator = math.sqrt(self.m2_x * self.m2_y)
        if denominator == 0.0 or not math.isfinite(denominator):
            return 0.0
        return float(np.clip(self.co_moment / denominator, -1.0, 1.0))


class _LinkageMoments:
    """Accumulate observed WAT/CP correlations without retaining lots."""

    def __init__(self, model: LatentModel, nearest_dies: IntArray) -> None:
        self._model = model
        self._nearest_dies = nearest_dies
        self._moments = [_Moment() for _ in model.pairs]

    def add(self, cp_lot: CPLot, wat_lot: WatLot) -> None:
        for pair, moment in zip(self._model.pairs, self._moments, strict=True):
            for wat_wafer, cp_wafer in zip(wat_lot.wafers, cp_lot.wafers, strict=True):
                moment.add(
                    wat_wafer.values[pair.wat_item],
                    cp_wafer.values[pair.cp_item][self._nearest_dies],
                )

    def build(self) -> tuple[LinkageReportEntry, ...]:
        return tuple(
            LinkageReportEntry(
                wat_item=pair.wat_item,
                cp_item=pair.cp_item,
                factor=pair.factor,
                target_r=pair.target_r,
                achieved_r=self._model.achieved_r[(pair.wat_item, pair.cp_item)],
                observed_r=moment.correlation(),
                sample_count=moment.count,
            )
            for pair, moment in zip(self._model.pairs, self._moments, strict=True)
        )


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
