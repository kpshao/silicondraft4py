"""Hard- and soft-bin derivation from CP measurements.

V1 default hard bins: 1 = pass, 2 = parametric fail, 3 = functional/structural
fail, 4 = continuity/contact fail. V1 default soft bins: 100 = pass,
201 = continuity, 202 = leakage, 203 = Iddq, 204 = Vth, 205 = frequency,
206 = functional/scan, 207 = other parametric. Bins are always derived from
measurement values and spec limits; generation never writes a bin directly.
"""

from collections.abc import Mapping
from dataclasses import dataclass

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

SOFT_PASS = 100
SOFT_CONTINUITY = 201
SOFT_LEAKAGE = 202
SOFT_IDDQ = 203
SOFT_VTH = 204
SOFT_FREQUENCY = 205
SOFT_FUNCTIONAL = 206
SOFT_OTHER_PARAMETRIC = 207


@dataclass(frozen=True, slots=True)
class BinDefinition:
    """One hard- or soft-bin definition carried into exported files."""

    number: int
    name: str
    passed: bool
    description: str
    hard_bin: int


HARD_BIN_DEFINITIONS: tuple[BinDefinition, ...] = (
    BinDefinition(PASS, "PASS", True, "Pass", PASS),
    BinDefinition(PARAMETRIC_FAIL, "PARAMETRIC_FAIL", False, "Parametric failure", PARAMETRIC_FAIL),
    BinDefinition(
        FUNCTIONAL_FAIL,
        "FUNCTIONAL_FAIL",
        False,
        "Functional or structural failure",
        FUNCTIONAL_FAIL,
    ),
    BinDefinition(
        CONTINUITY_FAIL, "CONTINUITY_FAIL", False, "Continuity or contact failure", CONTINUITY_FAIL
    ),
)

SOFT_BIN_DEFINITIONS: tuple[BinDefinition, ...] = (
    BinDefinition(SOFT_PASS, "PASS", True, "Pass", PASS),
    BinDefinition(
        SOFT_CONTINUITY, "CONTINUITY", False, "Continuity or contact failure", CONTINUITY_FAIL
    ),
    BinDefinition(SOFT_LEAKAGE, "LEAKAGE", False, "Leakage failure", PARAMETRIC_FAIL),
    BinDefinition(SOFT_IDDQ, "IDDQ", False, "Quiescent current failure", PARAMETRIC_FAIL),
    BinDefinition(SOFT_VTH, "VTH", False, "Threshold voltage failure", PARAMETRIC_FAIL),
    BinDefinition(SOFT_FREQUENCY, "FREQUENCY", False, "Frequency failure", PARAMETRIC_FAIL),
    BinDefinition(
        SOFT_FUNCTIONAL, "FUNCTIONAL", False, "Functional or scan failure", FUNCTIONAL_FAIL
    ),
    BinDefinition(
        SOFT_OTHER_PARAMETRIC,
        "OTHER_PARAMETRIC",
        False,
        "Other parametric failure",
        PARAMETRIC_FAIL,
    ),
)

_SOFT_BIN_BY_ITEM_ID: dict[str, int] = {
    "CP_CONT": SOFT_CONTINUITY,
    "CP_RCONT": SOFT_CONTINUITY,
    "CP_FUNC": SOFT_FUNCTIONAL,
    "CP_SCAN": SOFT_FUNCTIONAL,
    "CP_IDDQ": SOFT_IDDQ,
    "CP_VTHN": SOFT_VTH,
    "CP_VTHP": SOFT_VTH,
    "CP_IOFFN": SOFT_LEAKAGE,
    "CP_IOFFP": SOFT_LEAKAGE,
    "CP_IGATE": SOFT_LEAKAGE,
    "CP_IIL": SOFT_LEAKAGE,
    "CP_IIH": SOFT_LEAKAGE,
    "CP_IOZ": SOFT_LEAKAGE,
    "CP_FRO": SOFT_FREQUENCY,
}

# Highest severity first: continuity, then functional, then the parametric
# categories. Within parametric failures the lower soft-bin number wins.
_SOFT_BIN_PRECEDENCE: tuple[int, ...] = (
    SOFT_CONTINUITY,
    SOFT_FUNCTIONAL,
    SOFT_LEAKAGE,
    SOFT_IDDQ,
    SOFT_VTH,
    SOFT_FREQUENCY,
    SOFT_OTHER_PARAMETRIC,
)

_HARD_BIN_BY_SOFT: dict[int, int] = {
    definition.number: definition.hard_bin for definition in SOFT_BIN_DEFINITIONS
}


@dataclass(frozen=True, slots=True)
class BinArrays:
    """Derived hard and soft bin codes for every die."""

    hard: IntArray
    soft: IntArray


@dataclass(frozen=True, slots=True)
class BinCount:
    """One observed bin in a Pareto summary."""

    definition: BinDefinition
    count: int
    fraction: float


def bin_pareto(bins: IntArray, definitions: tuple[BinDefinition, ...]) -> tuple[BinCount, ...]:
    """Count the observed bins, most frequent first, ties by bin number."""
    total = int(bins.size)
    if total == 0:
        return ()

    entries = [
        BinCount(definition=definition, count=count, fraction=count / total)
        for definition in definitions
        if (count := int(np.count_nonzero(bins == definition.number))) > 0
    ]
    entries.sort(key=lambda entry: (-entry.count, entry.definition.number))
    return tuple(entries)


def classify_bins(
    items: tuple[CatalogItem, ...],
    values: Mapping[str, FloatArray],
    die_count: int,
) -> BinArrays:
    """Derive the hard and soft bin of every die from its CP measurements.

    Continuity failures take precedence over functional failures, which take
    precedence over parametric failures. Within parametric failures the
    precedence follows the soft-bin order: leakage, Iddq, Vth, frequency, other.
    """
    failures: dict[int, BoolArray] = {
        soft_bin: np.zeros(die_count, dtype=np.bool_) for soft_bin in _SOFT_BIN_PRECEDENCE
    }

    for item in items:
        failed = _item_failed(item, values[item.id])
        failures[soft_bin_for_item(item)] |= failed

    soft = np.full(die_count, SOFT_PASS, dtype=np.int64)
    for soft_bin in reversed(_SOFT_BIN_PRECEDENCE):
        soft[failures[soft_bin]] = soft_bin

    hard = np.array([_HARD_BIN_BY_SOFT[int(bin_number)] for bin_number in soft], dtype=np.int64)
    return BinArrays(hard=hard, soft=soft)


def soft_bin_for_item(item: CatalogItem) -> int:
    """Return the soft-bin category a failing item contributes to."""
    if item.id in _SOFT_BIN_BY_ITEM_ID:
        return _SOFT_BIN_BY_ITEM_ID[item.id]
    if item.distribution == "bernoulli":
        return SOFT_FUNCTIONAL
    return SOFT_OTHER_PARAMETRIC


def _item_failed(item: CatalogItem, column: FloatArray) -> BoolArray:
    failed = out_of_spec(column, item)
    if item.distribution == "bernoulli":
        failed |= column == 0
    return failed


def out_of_spec(column: FloatArray, item: CatalogItem) -> BoolArray:
    """Return a mask of values outside the item's spec limits."""
    failed = np.zeros(column.shape, dtype=np.bool_)
    if item.lsl is not None:
        failed |= column < item.lsl
    if item.usl is not None:
        failed |= column > item.usl
    return failed
