"""Public generation and export API."""

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path

import numpy as np

from .binning import PASS, classify_hard_bins
from .catalog import CatalogItem, resolve_catalog
from .dataset import CPLot, CPWafer, FloatArray, GenerationResult
from .errors import ExportError, ScenarioError
from .exporters import export_cp_csv
from .geometry import layout_dies
from .scenario.models import Scenario
from .scenario.validation import validate_scenario_model

_NORMAL_SPEC_SIGMAS = 6.0
_LOG_SPEC_SIGMAS = 6.0


def generate(scenario: Scenario) -> GenerationResult:
    """Generate CP data for a validated scenario.

    The scenario is re-validated here so that a hand-built ``Scenario`` cannot
    produce data before its geometry and item references are checked.
    """
    validation = validate_scenario_model(scenario)
    if not validation.ok:
        raise ScenarioError(validation.issues)

    resolution = resolve_catalog(scenario.items)
    if resolution.issues:
        raise ScenarioError(resolution.issues)
    items = tuple(item for item in resolution.catalog.enabled_items if item.phase == "CP")

    layout = layout_dies(scenario.wafer)
    lots: list[CPLot] = []
    for lot_number in range(1, scenario.lots.count + 1):
        lot_id = scenario.lots.lot_id_template.format(product=scenario.product.name, lot=lot_number)
        wafers: list[CPWafer] = []
        for wafer_number in range(1, scenario.lots.wafers_per_lot + 1):
            values = {
                item.id: _generate_column(
                    item, scenario.seed, lot_number, wafer_number, layout.count
                )
                for item in items
            }
            hard_bin = classify_hard_bins(items, values, layout.count)
            wafers.append(
                CPWafer(
                    wafer_id=scenario.lots.wafer_id_template.format(
                        product=scenario.product.name, lot=lot_number, wafer=wafer_number
                    ),
                    x_mm=layout.x_mm,
                    y_mm=layout.y_mm,
                    grid_x=layout.grid_x,
                    grid_y=layout.grid_y,
                    test_site=layout.test_site,
                    hard_bin=hard_bin,
                    passed=hard_bin == PASS,
                    values=values,
                )
            )
        lots.append(CPLot(lot_id=lot_id, wafers=tuple(wafers)))

    return GenerationResult(
        scenario=scenario,
        items=items,
        lots=tuple(lots),
        generated_at=datetime.now(UTC),
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

    try:
        return export_cp_csv(result, Path(out_dir))
    except OSError as exc:
        raise ExportError(f"cannot export CP CSV to {out_dir}: {exc}") from exc


def _generate_column(
    item: CatalogItem,
    seed: int,
    lot_number: int,
    wafer_number: int,
    die_count: int,
) -> FloatArray:
    rng = np.random.default_rng(
        np.random.SeedSequence([seed, lot_number, wafer_number, item.test_num])
    )
    if item.distribution == "normal":
        return rng.normal(loc=item.typical, scale=_normal_scale(item), size=die_count)
    if item.distribution == "lognormal":
        return rng.lognormal(
            mean=math.log(max(item.typical, np.finfo(np.float64).tiny)),
            sigma=_lognormal_sigma(item),
            size=die_count,
        )

    probability = min(max(item.typical, 0.0), 1.0)
    return rng.binomial(1, probability, size=die_count).astype(np.float64)


def _normal_scale(item: CatalogItem) -> float:
    if item.lsl is not None and item.usl is not None:
        scale = (item.usl - item.lsl) / (2 * _NORMAL_SPEC_SIGMAS)
    elif item.usl is not None:
        scale = (item.usl - item.typical) / _NORMAL_SPEC_SIGMAS
    elif item.lsl is not None:
        scale = (item.typical - item.lsl) / _NORMAL_SPEC_SIGMAS
    else:
        scale = abs(item.typical) * 0.1
    if not math.isfinite(scale) or scale <= 0:
        return max(abs(item.typical) * 0.1, 1e-12)
    return scale


def _lognormal_sigma(item: CatalogItem) -> float:
    typical = max(item.typical, np.finfo(np.float64).tiny)
    if item.lsl is not None and item.usl is not None:
        sigma = math.log(item.usl / item.lsl) / (2 * _LOG_SPEC_SIGMAS)
    elif item.usl is not None:
        sigma = math.log(item.usl / typical) / _LOG_SPEC_SIGMAS
    elif item.lsl is not None:
        sigma = math.log(typical / item.lsl) / _LOG_SPEC_SIGMAS
    else:
        sigma = 0.25
    if not math.isfinite(sigma) or sigma <= 0:
        return 0.25
    return sigma
