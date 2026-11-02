"""Wafer die layout.

The layout follows the V1 coordinate convention: the origin is the wafer
centre, +X points right, and +Y points up. Only complete dies whose centre is
inside the usable radius are kept, so no partial die is ever generated.

This is the minimal layout needed by the CP CSV path; the remaining geometry
(WAT sites, optional site offsets, larger geometry test matrix) arrives in a
later milestone.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from .scenario.models import Wafer

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]


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


def _empty_layout() -> DieLayout:
    return DieLayout(
        x_mm=np.empty(0, dtype=np.float64),
        y_mm=np.empty(0, dtype=np.float64),
        grid_x=np.empty(0, dtype=np.int64),
        grid_y=np.empty(0, dtype=np.int64),
        test_site=np.empty(0, dtype=np.int64),
    )
