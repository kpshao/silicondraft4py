"""Hard-bin derivation from CP measurements.

V1 default hard bins: 1 = pass, 2 = parametric fail, 3 = functional/structural
fail, 4 = continuity/contact fail. Bins are always derived from measurement
values and spec limits; generation never writes a bin directly.
"""

from collections.abc import Mapping

import numpy as np
from numpy.typing import NDArray

from .catalog import CatalogItem

IntArray = NDArray[np.int64]
FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]

PASS = 1
PARAMETRIC_FAIL = 2
FUNCTIONAL_FAIL = 3
CONTINUITY_FAIL = 4

_CONTINUITY_ITEM_ID = "CP_CONT"
_FUNCTIONAL_ITEM_IDS = frozenset({"CP_FUNC", "CP_SCAN"})


def classify_hard_bins(
    items: tuple[CatalogItem, ...],
    values: Mapping[str, FloatArray],
    die_count: int,
) -> IntArray:
    """Derive the hard bin of every die from its CP measurements.

    Continuity failures take precedence over functional failures, which take
    precedence over parametric failures.
    """
    continuity_failed = np.zeros(die_count, dtype=np.bool_)
    functional_failed = np.zeros(die_count, dtype=np.bool_)
    parametric_failed = np.zeros(die_count, dtype=np.bool_)

    for item in items:
        column = values[item.id]
        if item.id == _CONTINUITY_ITEM_ID:
            continuity_failed |= out_of_spec(column, item)
        elif item.id in _FUNCTIONAL_ITEM_IDS:
            functional_failed |= column == 0
        else:
            parametric_failed |= out_of_spec(column, item)

    bins = np.ones(die_count, dtype=np.int64)
    bins[parametric_failed] = PARAMETRIC_FAIL
    bins[functional_failed] = FUNCTIONAL_FAIL
    bins[continuity_failed] = CONTINUITY_FAIL
    return bins


def out_of_spec(column: FloatArray, item: CatalogItem) -> BoolArray:
    """Return a mask of values outside the item's spec limits."""
    failed = np.zeros(column.shape, dtype=np.bool_)
    if item.lsl is not None:
        failed |= column < item.lsl
    if item.usl is not None:
        failed |= column > item.usl
    return failed
