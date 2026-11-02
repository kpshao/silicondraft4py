"""Wafer geometry used by scenario validation.

This is the minimal grid needed to report a die count and reject infeasible
geometries. The full layout (coordinates, site assignment) arrives in a later
milestone.
"""

import math
from bisect import bisect_left, bisect_right

from .scenario.models import Wafer


def count_dies(wafer: Wafer) -> int:
    """Count complete dies whose centre lies inside the usable wafer radius.

    A die is kept only when its centre is inside the usable radius and its
    whole rectangle is on the wafer, so no partial die is counted.
    """
    die_width_mm, die_height_mm = wafer.die_size_mm
    usable_radius_mm = wafer.diameter_mm / 2 - wafer.edge_exclusion_mm
    wafer_radius_mm = wafer.diameter_mm / 2
    if usable_radius_mm < 0:
        return 0

    columns = math.floor(wafer.diameter_mm / die_width_mm)
    rows = math.floor(wafer.diameter_mm / die_height_mm)
    if columns < 1 or rows < 1:
        return 0

    x_offsets = [(index - (columns - 1) / 2) * die_width_mm for index in range(columns)]
    y_offsets = [(index - (rows - 1) / 2) * die_height_mm for index in range(rows)]
    usable_radius_squared = usable_radius_mm * usable_radius_mm
    wafer_radius_squared = wafer_radius_mm * wafer_radius_mm
    half_width_mm = die_width_mm / 2
    half_height_mm = die_height_mm / 2

    count = 0
    for y_mm in y_offsets:
        centre_remaining = usable_radius_squared - y_mm * y_mm
        corner_remaining = wafer_radius_squared - (abs(y_mm) + half_height_mm) ** 2
        if centre_remaining < 0 or corner_remaining < 0:
            continue
        centre_limit_mm = math.sqrt(centre_remaining)
        corner_limit_mm = math.sqrt(corner_remaining) - half_width_mm
        if corner_limit_mm < 0:
            continue
        limit_mm = min(centre_limit_mm, corner_limit_mm)
        count += bisect_right(x_offsets, limit_mm) - bisect_left(x_offsets, -limit_mm)
    return count
