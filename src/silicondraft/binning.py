"""Hard- and soft-bin derivation from CP measurements.

V1 default hard bins: 1 = pass, 2 = parametric fail, 3 = functional/structural
fail, 4 = continuity/contact fail. V1 default soft bins: 100 = pass,
201 = continuity, 202 = leakage, 203 = Iddq, 204 = Vth, 205 = frequency,
206 = functional/scan, 207 = other parametric. Bins are always derived from
measurement values and spec limits; generation never writes a bin directly.

The scenario's ``bins`` section can change each role's exported code, name, and
description, but not its failure semantics: a continuity failure still takes
precedence over a functional failure, which still takes precedence over a
parametric failure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

from .binroles import HARD_BIN_ROLES, SOFT_BIN_ROLES, HardBinRole, SoftBinRole
from .catalog import CatalogItem

if TYPE_CHECKING:
    from .scenario.models import BinOverride, Bins

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


@dataclass(frozen=True, slots=True)
class BinTable:
    """The resolved bin table for one scenario."""

    hard: tuple[BinDefinition, ...]
    soft: tuple[BinDefinition, ...]
    hard_by_role: Mapping[HardBinRole, BinDefinition]
    soft_by_role: Mapping[SoftBinRole, BinDefinition]
    hard_by_number: Mapping[int, BinDefinition]
    soft_by_number: Mapping[int, BinDefinition]

    @property
    def hard_pass(self) -> int:
        """The hard-bin code used for passing dies."""
        return self.hard_by_role["pass"].number


_DEFAULT_HARD_BINS: dict[HardBinRole, BinDefinition] = {
    "pass": BinDefinition(PASS, "PASS", True, "Pass", PASS),
    "parametric": BinDefinition(
        PARAMETRIC_FAIL, "PARAMETRIC_FAIL", False, "Parametric failure", PARAMETRIC_FAIL
    ),
    "functional": BinDefinition(
        FUNCTIONAL_FAIL,
        "FUNCTIONAL_FAIL",
        False,
        "Functional or structural failure",
        FUNCTIONAL_FAIL,
    ),
    "continuity": BinDefinition(
        CONTINUITY_FAIL,
        "CONTINUITY_FAIL",
        False,
        "Continuity or contact failure",
        CONTINUITY_FAIL,
    ),
}

#: Hard-bin role each soft-bin failure role maps to.
SOFT_BIN_HARD_ROLE: dict[SoftBinRole, HardBinRole] = {
    "pass": "pass",
    "continuity": "continuity",
    "leakage": "parametric",
    "iddq": "parametric",
    "vth": "parametric",
    "frequency": "parametric",
    "functional": "functional",
    "other_parametric": "parametric",
}

_DEFAULT_SOFT_BINS: dict[SoftBinRole, BinDefinition] = {
    "pass": BinDefinition(SOFT_PASS, "PASS", True, "Pass", PASS),
    "continuity": BinDefinition(
        SOFT_CONTINUITY, "CONTINUITY", False, "Continuity or contact failure", CONTINUITY_FAIL
    ),
    "leakage": BinDefinition(SOFT_LEAKAGE, "LEAKAGE", False, "Leakage failure", PARAMETRIC_FAIL),
    "iddq": BinDefinition(SOFT_IDDQ, "IDDQ", False, "Quiescent current failure", PARAMETRIC_FAIL),
    "vth": BinDefinition(SOFT_VTH, "VTH", False, "Threshold voltage failure", PARAMETRIC_FAIL),
    "frequency": BinDefinition(
        SOFT_FREQUENCY, "FREQUENCY", False, "Frequency failure", PARAMETRIC_FAIL
    ),
    "functional": BinDefinition(
        SOFT_FUNCTIONAL, "FUNCTIONAL_SCAN", False, "Functional or scan failure", FUNCTIONAL_FAIL
    ),
    "other_parametric": BinDefinition(
        SOFT_OTHER_PARAMETRIC,
        "OTHER_PARAMETRIC",
        False,
        "Other parametric failure",
        PARAMETRIC_FAIL,
    ),
}

#: Failure roles from highest to lowest precedence.
SOFT_BIN_PRECEDENCE: tuple[SoftBinRole, ...] = (
    "continuity",
    "functional",
    "leakage",
    "iddq",
    "vth",
    "frequency",
    "other_parametric",
)

_SOFT_BIN_ROLE_BY_ITEM_ID: dict[str, SoftBinRole] = {
    "CP_CONT": "continuity",
    "CP_RCONT": "continuity",
    "CP_FUNC": "functional",
    "CP_SCAN": "functional",
    "CP_IDDQ": "iddq",
    "CP_VTHN": "vth",
    "CP_VTHP": "vth",
    "CP_IOFFN": "leakage",
    "CP_IOFFP": "leakage",
    "CP_IGATE": "leakage",
    "CP_IIL": "leakage",
    "CP_IIH": "leakage",
    "CP_IOZ": "leakage",
    "CP_FRO": "frequency",
}


def resolve_bin_table(bins: Bins | None = None) -> BinTable:
    """Resolve the built-in table with the scenario's per-role overrides."""
    hard: dict[HardBinRole, BinDefinition] = {}
    for hard_role in HARD_BIN_ROLES:
        definition = _DEFAULT_HARD_BINS[hard_role]
        override = bins.hard.get(hard_role) if bins is not None else None
        if override is not None:
            definition = _with_override(definition, override)
        hard[hard_role] = replace(definition, hard_bin=definition.number)

    soft: dict[SoftBinRole, BinDefinition] = {}
    for soft_role in SOFT_BIN_ROLES:
        definition = _DEFAULT_SOFT_BINS[soft_role]
        override = bins.soft.get(soft_role) if bins is not None else None
        if override is not None:
            definition = _with_override(definition, override)
        hard_number = hard[SOFT_BIN_HARD_ROLE[soft_role]].number
        soft[soft_role] = replace(definition, hard_bin=hard_number)

    return BinTable(
        hard=tuple(hard[hard_role] for hard_role in HARD_BIN_ROLES),
        soft=tuple(soft[soft_role] for soft_role in SOFT_BIN_ROLES),
        hard_by_role=hard,
        soft_by_role=soft,
        hard_by_number={definition.number: definition for definition in hard.values()},
        soft_by_number={definition.number: definition for definition in soft.values()},
    )


def _with_override(definition: BinDefinition, override: BinOverride) -> BinDefinition:
    return replace(
        definition,
        number=override.code if override.code is not None else definition.number,
        name=override.name if override.name is not None else definition.name,
        description=(
            override.description if override.description is not None else definition.description
        ),
    )


DEFAULT_BIN_TABLE: BinTable = resolve_bin_table()


@dataclass(frozen=True, slots=True)
class BinArrays:
    """Derived hard and soft bin codes for every die."""

    hard: IntArray
    soft: IntArray


@dataclass(frozen=True, slots=True)
class BinParetoEntry:
    """One observed bin in a Pareto summary over all dies."""

    definition: BinDefinition
    count: int
    fraction_of_dies: float


def bin_pareto(
    bins: IntArray, definitions: tuple[BinDefinition, ...]
) -> tuple[BinParetoEntry, ...]:
    """Count the observed bins, most frequent first, ties by bin number."""
    total = int(bins.size)
    entries = [
        BinParetoEntry(
            definition=definition,
            count=count,
            fraction_of_dies=count / total,
        )
        for definition in definitions
        if (count := int(np.count_nonzero(bins == definition.number))) > 0
    ]
    entries.sort(key=lambda entry: (-entry.count, entry.definition.number))
    return tuple(entries)


def classify_bins(
    items: tuple[CatalogItem, ...],
    values: Mapping[str, FloatArray],
    die_count: int,
    table: BinTable | None = None,
) -> BinArrays:
    """Derive the hard and soft bin of every die from its CP measurements.

    Continuity failures take precedence over functional failures, which take
    precedence over parametric failures. Within parametric failures the
    precedence follows the soft-role order: leakage, Iddq, Vth, frequency,
    other parametric.
    """
    resolved = DEFAULT_BIN_TABLE if table is None else table
    failures: dict[SoftBinRole, BoolArray] = {
        role: np.zeros(die_count, dtype=np.bool_) for role in SOFT_BIN_PRECEDENCE
    }

    for item in items:
        failed = _item_failed(item, values[item.id])
        failures[soft_bin_role_for_item(item)] |= failed

    soft = np.full(die_count, resolved.soft_by_role["pass"].number, dtype=np.int64)
    for role in reversed(SOFT_BIN_PRECEDENCE):
        soft[failures[role]] = resolved.soft_by_role[role].number

    hard_by_soft = {definition.number: definition.hard_bin for definition in resolved.soft}
    hard = np.array([hard_by_soft[int(bin_number)] for bin_number in soft], dtype=np.int64)
    return BinArrays(hard=hard, soft=soft)


def soft_bin_role_for_item(item: CatalogItem) -> SoftBinRole:
    """Return the soft-bin role a failing item contributes to."""
    if item.soft_bin_role is not None:
        return item.soft_bin_role
    if item.id in _SOFT_BIN_ROLE_BY_ITEM_ID:
        return _SOFT_BIN_ROLE_BY_ITEM_ID[item.id]
    if item.distribution == "bernoulli":
        return "functional"
    return "other_parametric"


def _item_failed(item: CatalogItem, column: FloatArray) -> BoolArray:
    return ~item_passed(item, column)


def item_passed(item: CatalogItem, column: FloatArray) -> BoolArray:
    """Return a mask of measurements that satisfy the item's pass rule.

    Every item must satisfy its configured spec limits; Bernoulli items must
    additionally carry a non-zero pass flag.
    """
    passed = np.ones(column.shape, dtype=np.bool_)
    if item.lsl is not None:
        passed &= column >= item.lsl
    if item.usl is not None:
        passed &= column <= item.usl
    if item.distribution == "bernoulli":
        passed &= column != 0
    return passed
