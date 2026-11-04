"""Systematic spatial pattern injection.

Patterns are deterministic spatial weight fields over the wafer. Each kind maps
a die centre to a weight in ``[0, 1]``: centre and local-spot patterns decay
from a point, edge patterns ramp inward from the usable wafer edge, rings peak
at a radius, and radial gradients grow from the centre. A pattern's signed
amplitude selects the direction: ``center_high`` and ``edge_high`` raise the
target, ``center_low`` and ``edge_low`` lower it, and ring, radial-gradient and
local-spot carry their sign directly.

Patterns act on measurement values, never on bin codes. A yield-targeted
pattern lowers the pass probability of a functional CP item; a positive yield
pattern instead recovers random-defect failures. An item-targeted pattern
shifts that item's measurements relative to its typical value.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .catalog import CatalogItem, can_fail
from .geometry import DieLayout
from .scenario.models import (
    PATTERN_NEGATIVE_AMPLITUDE_KINDS,
    YIELD_FAILURE_ITEM_IDS,
    Pattern,
    Wafer,
)

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class PatternApplication:
    """The effect of one pattern on one wafer.

    ``hit`` marks dies inside the pattern's spatial extent (nonzero weight);
    ``failure`` marks the dies this pattern actually forced to fail.
    """

    pattern_id: str
    hit: BoolArray
    failure: BoolArray
    recovery: FloatArray
    item_shift_sum: float
    item_shift_die_count: int


def pattern_id(index: int) -> str:
    """Return the stable ground-truth identifier for the pattern at ``index``."""
    return f"pattern_{index + 1}"


@dataclass(frozen=True, slots=True)
class PatternExtent:
    """The spatial extent of one pattern's weight field, in wafer millimetres.

    ``inner_radius_mm`` is zero for filled extents; a positive value marks an
    annulus. The centre matches the one used by :func:`spatial_weight`, so an
    overlay drawn from this type lines up with the injected pattern.
    """

    pattern_id: str
    kind: str
    center_mm: tuple[float, float]
    inner_radius_mm: float
    outer_radius_mm: float


def pattern_extent(pattern: Pattern, index: int, wafer: Wafer) -> PatternExtent | None:
    """Return where a pattern's weight field is non-zero, or ``None`` without geometry."""
    identifier = pattern_id(index)
    usable_radius_mm = wafer.diameter_mm / 2 - wafer.edge_exclusion_mm
    centre = pattern.center_mm

    if pattern.kind in {"center_high", "center_low", "local_spot"}:
        if pattern.radius_mm is None:
            return None
        return PatternExtent(identifier, pattern.kind, centre, 0.0, pattern.radius_mm)

    if pattern.kind in {"edge_high", "edge_low"}:
        if pattern.extent_mm is None:
            return None
        return PatternExtent(
            identifier,
            pattern.kind,
            centre,
            max(0.0, usable_radius_mm - pattern.extent_mm),
            usable_radius_mm,
        )

    if pattern.kind == "ring":
        if pattern.radius_mm is None or pattern.width_mm is None:
            return None
        return PatternExtent(
            identifier,
            pattern.kind,
            centre,
            max(0.0, pattern.radius_mm - pattern.width_mm),
            pattern.radius_mm + pattern.width_mm,
        )

    if pattern.kind == "radial_gradient":
        return PatternExtent(identifier, pattern.kind, centre, 0.0, usable_radius_mm)

    return None


def select_yield_failure_item(items: Iterable[CatalogItem]) -> CatalogItem | None:
    """Return the functional CP item a yield pattern should fail."""
    enabled = {item.id: item for item in items if item.enabled and item.phase == "CP"}
    for item_id in YIELD_FAILURE_ITEM_IDS:
        item = enabled.get(item_id)
        if item is not None and can_fail(item):
            return item
    return None


def signed_amplitude(pattern: Pattern) -> float:
    """Return the pattern amplitude with the direction encoded by its kind."""
    if pattern.kind in PATTERN_NEGATIVE_AMPLITUDE_KINDS:
        return -pattern.amplitude
    return pattern.amplitude


def spatial_weight(pattern: Pattern, layout: DieLayout, wafer: Wafer) -> FloatArray:
    """Return each die's weight in ``[0, 1]`` for this pattern."""
    if layout.count == 0:
        return np.empty(0, dtype=np.float64)

    offset_x = layout.x_mm - pattern.center_mm[0]
    offset_y = layout.y_mm - pattern.center_mm[1]
    radius_mm = np.hypot(offset_x, offset_y)
    usable_radius_mm = wafer.diameter_mm / 2 - wafer.edge_exclusion_mm
    kind = pattern.kind

    if kind in {"center_high", "center_low", "local_spot"}:
        extent = pattern.radius_mm
        if extent is None:
            return np.zeros(layout.count, dtype=np.float64)
        return np.clip(1.0 - radius_mm / extent, 0.0, 1.0)

    if kind in {"edge_high", "edge_low"}:
        extent = pattern.extent_mm
        if extent is None or usable_radius_mm <= 0:
            return np.zeros(layout.count, dtype=np.float64)
        return np.clip((radius_mm - (usable_radius_mm - extent)) / extent, 0.0, 1.0)

    if kind == "ring":
        ring_radius = pattern.radius_mm
        width = pattern.width_mm
        if ring_radius is None or width is None:
            return np.zeros(layout.count, dtype=np.float64)
        return np.clip(1.0 - np.abs(radius_mm - ring_radius) / width, 0.0, 1.0)

    if kind == "radial_gradient":
        if usable_radius_mm <= 0:
            return np.zeros(layout.count, dtype=np.float64)
        return np.clip(radius_mm / usable_radius_mm, 0.0, 1.0)

    return np.zeros(layout.count, dtype=np.float64)


def apply_pattern(
    pattern: Pattern,
    index: int,
    items: Mapping[str, CatalogItem],
    values: dict[str, FloatArray],
    layout: DieLayout,
    wafer: Wafer,
    yield_failure_item: CatalogItem | None,
    rng: np.random.Generator,
) -> PatternApplication:
    """Apply one pattern to a wafer's measurement values in place."""
    weight = spatial_weight(pattern, layout, wafer)
    delta = signed_amplitude(pattern) * weight
    hit = weight > 0.0
    failure = np.zeros(layout.count, dtype=np.bool_)
    recovery = np.zeros(layout.count, dtype=np.float64)
    shift_sum = 0.0
    shift_die_count = 0

    if pattern.target == "yield":
        if yield_failure_item is None:  # pragma: no cover - rejected by validation
            raise ValueError("yield pattern requires an enabled CP_FUNC or CP_SCAN item")
        draws = rng.random(layout.count) < np.clip(-delta, 0.0, 1.0)
        force_failure(yield_failure_item, values, draws)
        failure |= draws
        recovery = np.clip(delta, 0.0, 1.0)

    if pattern.target_item is not None:
        item = items[pattern.target_item]
        column = values[item.id]
        same_as_yield_item = (
            pattern.target == "yield"
            and yield_failure_item is not None
            and item.id == yield_failure_item.id
        )
        if not same_as_yield_item:
            if item.distribution == "bernoulli":
                draws = rng.random(layout.count) < np.clip(-delta, 0.0, 1.0)
                column[draws] = 0.0
                failure |= draws
            else:
                _shift_item(item, column, delta, pattern.combine)
                shift_sum = float(np.abs(delta[hit]).sum())
                shift_die_count = int(hit.sum())

    return PatternApplication(
        pattern_id=pattern_id(index),
        hit=hit,
        failure=failure,
        recovery=recovery,
        item_shift_sum=shift_sum,
        item_shift_die_count=shift_die_count,
    )


def _shift_item(item: CatalogItem, column: FloatArray, delta: FloatArray, combine: str) -> None:
    """Shift one item's measurements by a relative pattern delta."""
    if item.distribution == "lognormal":
        if combine == "multiply":
            column *= np.exp(delta)
        else:
            column += _amplitude_scale(item) * delta
        np.clip(column, np.finfo(np.float64).tiny, np.finfo(np.float64).max, out=column)
        return

    if combine == "multiply":
        column *= 1.0 + delta
    else:
        column += _amplitude_scale(item) * delta


def _amplitude_scale(item: CatalogItem) -> float:
    scale = abs(item.typical)
    if scale > 0.0:
        return scale
    # Imported lazily so pattern injection does not participate in the
    # latent/scenario import cycle at module load time.
    from .latent import normal_scale

    return normal_scale(item)


def force_failure(item: CatalogItem, values: dict[str, FloatArray], mask: BoolArray) -> None:
    """Make the selected measurements fail their item's pass rule."""
    column = values[item.id]
    if item.distribution == "bernoulli":
        column[mask] = 0.0
        return
    if item.usl is not None:
        column[mask] = item.usl + _failure_margin(item.usl)
    elif item.lsl is not None:
        column[mask] = item.lsl - _failure_margin(item.lsl)


def _failure_margin(limit: float) -> float:
    return max(abs(limit) * 0.01, 1e-9)
