"""Wafer die and WAT site layout.

The layout follows the V1 coordinate convention: the origin is the wafer
centre, +X points right, and +Y points up, with the notch at the bottom. Only
complete dies whose centre is inside the usable radius are kept, so no partial
die is ever generated.

WAT sites are placed on concentric rings of the wafer radius ``R``: the centre,
four orthogonal sites at ``0.5R``, four diagonal sites at ``0.9R``, and, for
the denser plans, four orthogonal sites at ``0.9R`` plus eight sites at
``0.7R``. Site positions are independent of edge exclusion because WAT
structures sit in the scribe lines rather than on the die array.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from .scenario.models import Wafer

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]

_ORTHOGONAL_DIRECTIONS: tuple[tuple[float, float], ...] = (
    (1.0, 0.0),
    (0.0, 1.0),
    (-1.0, 0.0),
    (0.0, -1.0),
)
_DIAGONAL_SCALE = math.sqrt(0.5)
_DIAGONAL_DIRECTIONS: tuple[tuple[float, float], ...] = (
    (_DIAGONAL_SCALE, _DIAGONAL_SCALE),
    (-_DIAGONAL_SCALE, _DIAGONAL_SCALE),
    (-_DIAGONAL_SCALE, -_DIAGONAL_SCALE),
    (_DIAGONAL_SCALE, -_DIAGONAL_SCALE),
)
_ALL_DIRECTIONS = _ORTHOGONAL_DIRECTIONS + _DIAGONAL_DIRECTIONS


class _SiteRing(NamedTuple):
    """One ring of WAT sites at a fraction of the wafer radius."""

    radius_fraction: float
    directions: tuple[tuple[float, float], ...]


_INNER_ORTHOGONAL = _SiteRing(0.5, _ORTHOGONAL_DIRECTIONS)
_OUTER_DIAGONAL = _SiteRing(0.9, _DIAGONAL_DIRECTIONS)
_OUTER_ORTHOGONAL = _SiteRing(0.9, _ORTHOGONAL_DIRECTIONS)
_MID_RING = _SiteRing(0.7, _ALL_DIRECTIONS)

# Plans are nested in site-count order, so the first N sites of a larger plan
# match the smaller plan's sites.
_WAT_SITE_RINGS: dict[int, tuple[_SiteRing, ...]] = {
    5: (_INNER_ORTHOGONAL,),
    9: (_INNER_ORTHOGONAL, _OUTER_DIAGONAL),
    13: (_INNER_ORTHOGONAL, _OUTER_DIAGONAL, _OUTER_ORTHOGONAL),
    21: (_INNER_ORTHOGONAL, _OUTER_DIAGONAL, _OUTER_ORTHOGONAL, _MID_RING),
}


@dataclass(frozen=True, slots=True)
class DieLayout:
    """Die positions in millimetres and integer grid indices.

    ``grid_x`` and ``grid_y`` are zero-based indices from the bottom-left
    corner of the wafer grid; ``test_site`` is one-based, cycling through the
    configured CP sites in test order.
    """

    x_mm: FloatArray
    y_mm: FloatArray
    grid_x: IntArray
    grid_y: IntArray
    test_site: IntArray

    @property
    def count(self) -> int:
        """Number of dies in the layout."""
        return int(self.x_mm.size)


def layout_dies(wafer: Wafer) -> DieLayout:
    """Lay out all complete dies on a wafer in bottom-to-top, left-to-right order."""
    die_width_mm, die_height_mm = wafer.die_size_mm
    usable_radius_mm = wafer.diameter_mm / 2 - wafer.edge_exclusion_mm
    wafer_radius_mm = wafer.diameter_mm / 2
    columns = math.floor(wafer.diameter_mm / die_width_mm)
    rows = math.floor(wafer.diameter_mm / die_height_mm)
    if usable_radius_mm <= 0 or columns < 1 or rows < 1:
        return _empty_layout()

    x_offsets = [(index - (columns - 1) / 2) * die_width_mm for index in range(columns)]
    y_offsets = [(index - (rows - 1) / 2) * die_height_mm for index in range(rows)]
    usable_radius_squared = usable_radius_mm * usable_radius_mm
    wafer_radius_squared = wafer_radius_mm * wafer_radius_mm
    half_width_mm = die_width_mm / 2
    half_height_mm = die_height_mm / 2

    xs: list[float] = []
    ys: list[float] = []
    grid_xs: list[int] = []
    grid_ys: list[int] = []
    for row, y_mm in enumerate(y_offsets):
        centre_remaining = usable_radius_squared - y_mm * y_mm
        corner_remaining = wafer_radius_squared - (abs(y_mm) + half_height_mm) ** 2
        if centre_remaining < 0 or corner_remaining < 0:
            continue
        limit_mm = min(
            math.sqrt(centre_remaining),
            math.sqrt(corner_remaining) - half_width_mm,
        )
        if limit_mm < 0:
            continue
        first = bisect_left(x_offsets, -limit_mm)
        last = bisect_right(x_offsets, limit_mm)
        for column in range(first, last):
            xs.append(x_offsets[column])
            ys.append(y_mm)
            grid_xs.append(column)
            grid_ys.append(row)

    count = len(xs)
    if count == 0:
        return _empty_layout()
    return DieLayout(
        x_mm=np.asarray(xs, dtype=np.float64),
        y_mm=np.asarray(ys, dtype=np.float64),
        grid_x=np.asarray(grid_xs, dtype=np.int64),
        grid_y=np.asarray(grid_ys, dtype=np.int64),
        test_site=(np.arange(count, dtype=np.int64) % wafer.cp_sites) + 1,
    )


def count_dies(wafer: Wafer) -> int:
    """Count complete dies whose centre lies inside the usable wafer radius."""
    return layout_dies(wafer).count


@dataclass(frozen=True, slots=True)
class WatSiteLayout:
    """WAT measurement sites in millimetres, numbered in test order."""

    site_number: IntArray
    x_mm: FloatArray
    y_mm: FloatArray

    @property
    def count(self) -> int:
        """Number of WAT sites in the layout."""
        return int(self.x_mm.size)


def layout_wat_sites(wafer: Wafer) -> WatSiteLayout:
    """Lay out the configured WAT sites on concentric rings of the wafer radius."""
    radius_mm = wafer.diameter_mm / 2
    xs = [0.0]
    ys = [0.0]
    for ring in _WAT_SITE_RINGS[wafer.wat_sites]:
        site_radius_mm = ring.radius_fraction * radius_mm
        for direction_x, direction_y in ring.directions:
            xs.append(site_radius_mm * direction_x)
            ys.append(site_radius_mm * direction_y)

    count = len(xs)
    return WatSiteLayout(
        site_number=np.arange(1, count + 1, dtype=np.int64),
        x_mm=np.asarray(xs, dtype=np.float64),
        y_mm=np.asarray(ys, dtype=np.float64),
    )


def nearest_die_indices(wat_sites: WatSiteLayout, dies: DieLayout) -> IntArray:
    """Return the index of the nearest die for every WAT site.

    A WAT site samples the latent factor vector of its nearest die, modelling
    local process conditions at the PCM structure. Ties resolve to the first
    die in layout order.
    """
    if dies.count == 0:
        return np.empty(0, dtype=np.int64)
    dx = wat_sites.x_mm[:, np.newaxis] - dies.x_mm[np.newaxis, :]
    dy = wat_sites.y_mm[:, np.newaxis] - dies.y_mm[np.newaxis, :]
    return np.argmin(dx * dx + dy * dy, axis=1).astype(np.int64)


def _empty_layout() -> DieLayout:
    return DieLayout(
        x_mm=np.empty(0, dtype=np.float64),
        y_mm=np.empty(0, dtype=np.float64),
        grid_x=np.empty(0, dtype=np.int64),
        grid_y=np.empty(0, dtype=np.int64),
        test_site=np.empty(0, dtype=np.int64),
    )
