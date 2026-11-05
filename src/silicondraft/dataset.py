"""Columnar data produced by the generation engine."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from numpy.typing import NDArray

from .binning import (
    DEFAULT_BIN_TABLE,
    BinParetoEntry,
    BinTable,
    bin_pareto,
    resolve_bin_table,
)
from .catalog import CatalogItem
from .defects import DefectCluster
from .patterns import pattern_id
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
    factors: FloatArray
    pattern_hits: Mapping[str, BoolArray]
    defect_failure: BoolArray
    defect_clusters: tuple[DefectCluster, ...]
    tested_at: datetime
    bin_table: BinTable = DEFAULT_BIN_TABLE

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
        return bin_pareto(self.hard_bin, self.bin_table.hard)

    @property
    def soft_bin_pareto(self) -> tuple[BinParetoEntry, ...]:
        """Soft-bin counts on this wafer, most frequent first."""
        return bin_pareto(self.soft_bin, self.bin_table.soft)


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
class WatWafer:
    """WAT measurements for one wafer: one row per PCM site."""

    wafer_id: str
    site_number: IntArray
    x_mm: FloatArray
    y_mm: FloatArray
    values: Mapping[str, FloatArray]
    tested_at: datetime

    @property
    def site_count(self) -> int:
        """Number of WAT sites measured on this wafer."""
        return int(self.x_mm.size)


@dataclass(frozen=True, slots=True)
class WatLot:
    """WAT measurements for one lot."""

    lot_id: str
    wafers: tuple[WatWafer, ...]


@dataclass(frozen=True, slots=True)
class LinkageReportEntry:
    """Target and achieved correlation for one WAT/CP linkage pair.

    ``achieved_r`` is the correlation implied by the calibrated latent model;
    ``observed_r`` is the Pearson correlation of the generated WAT site values
    against the CP values of their nearest dies.
    """

    wat_item: str
    cp_item: str
    factor: str
    target_r: float
    achieved_r: float
    observed_r: float
    sample_count: int


@dataclass(frozen=True, slots=True)
class PatternReport:
    """Injected contribution of one systematic spatial pattern."""

    pattern_id: str
    affected_die_count: int
    realized_failures: int
    item_shift_sum: float
    item_shift_die_count: int
    recovery_probability_sum: float
    affected_wafers: tuple[tuple[str, str], ...]


@dataclass
class PatternAccumulator:
    """Mutable totals merged from one or more pattern reports."""

    affected_die_count: int = 0
    realized_failures: int = 0
    item_shift_sum: float = 0.0
    item_shift_die_count: int = 0
    recovery_probability_sum: float = 0.0
    affected_wafers: list[tuple[str, str]] = field(default_factory=list)

    def add(self, report: PatternReport) -> None:
        """Merge one report into these totals."""
        self.affected_die_count += report.affected_die_count
        self.realized_failures += report.realized_failures
        self.item_shift_sum += report.item_shift_sum
        self.item_shift_die_count += report.item_shift_die_count
        self.recovery_probability_sum += report.recovery_probability_sum
        self.affected_wafers.extend(report.affected_wafers)

    def report(self, index: int) -> PatternReport:
        """Snapshot these totals as the report for the pattern at ``index``."""
        return PatternReport(
            pattern_id=pattern_id(index),
            affected_die_count=self.affected_die_count,
            realized_failures=self.realized_failures,
            item_shift_sum=self.item_shift_sum,
            item_shift_die_count=self.item_shift_die_count,
            recovery_probability_sum=self.recovery_probability_sum,
            affected_wafers=tuple(self.affected_wafers),
        )


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """The output of one generation run.

    ``items`` holds the enabled CP items in catalog order; ``CPWafer.values``
    maps each item ID to its per-die measurement column. ``wat_items`` and
    ``wat_lots`` are the WAT counterparts, measured per PCM site.
    """

    scenario: Scenario
    items: tuple[CatalogItem, ...]
    wat_items: tuple[CatalogItem, ...]
    lots: tuple[CPLot, ...]
    wat_lots: tuple[WatLot, ...]
    linkage_report: tuple[LinkageReportEntry, ...]
    pattern_reports: tuple[PatternReport, ...]
    generated_at: datetime

    @property
    def bin_table(self) -> BinTable:
        """The resolved bin table for this result's scenario."""
        return resolve_bin_table(self.scenario.bins)
