"""Columnar data produced by the generation engine."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from numpy.typing import NDArray

from .binning import (
    HARD_BIN_DEFINITIONS,
    SOFT_BIN_DEFINITIONS,
    BinParetoEntry,
    bin_pareto,
)
from .catalog import CatalogItem
from .scenario.models import Scenario

FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True, slots=True)
class CPWafer:
    """CP measurements for one wafer: one row per die."""

    wafer_id: str
    x_mm: FloatArray
    y_mm: FloatArray
    grid_x: IntArray
    grid_y: IntArray
    test_site: IntArray
    hard_bin: IntArray
    soft_bin: IntArray
    passed: BoolArray
    values: Mapping[str, FloatArray]

    @property
    def die_count(self) -> int:
        """Number of dies measured on this wafer."""
        return int(self.x_mm.size)

    @property
    def pass_count(self) -> int:
        """Number of dies that passed on this wafer."""
        return int(self.passed.sum())

    @property
    def yield_fraction(self) -> float:
        """Fraction of passing dies on this wafer, between 0 and 1."""
        return self.pass_count / self.die_count

    @property
    def hard_bin_pareto(self) -> tuple[BinParetoEntry, ...]:
        """Hard-bin counts on this wafer, most frequent first."""
        return bin_pareto(self.hard_bin, HARD_BIN_DEFINITIONS)

    @property
    def soft_bin_pareto(self) -> tuple[BinParetoEntry, ...]:
        """Soft-bin counts on this wafer, most frequent first."""
        return bin_pareto(self.soft_bin, SOFT_BIN_DEFINITIONS)


@dataclass(frozen=True, slots=True)
class CPLot:
    """CP measurements for one lot."""

    lot_id: str
    wafers: tuple[CPWafer, ...]

    @property
    def die_count(self) -> int:
        """Number of dies measured in this lot."""
        return sum(wafer.die_count for wafer in self.wafers)

    @property
    def pass_count(self) -> int:
        """Number of dies that passed in this lot."""
        return sum(wafer.pass_count for wafer in self.wafers)

    @property
    def yield_fraction(self) -> float:
        """Fraction of passing dies in this lot, between 0 and 1."""
        return self.pass_count / self.die_count


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """The output of one generation run.

    ``items`` holds the enabled CP items in catalog order; ``CPWafer.values``
    maps each item ID to its per-die measurement column.
    """

    scenario: Scenario
    items: tuple[CatalogItem, ...]
    lots: tuple[CPLot, ...]
    generated_at: datetime
