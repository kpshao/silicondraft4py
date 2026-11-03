"""Ground truth manifest and per-die truth export.

The manifest is a machine-readable record of what the generator injected: the
full scenario and its hash, per-lot and per-wafer yields, latent-factor means,
pattern contributions, random-defect clusters, linkage targets, and outlier
wafers. The optional per-die truth CSV.GZ joins to CP data by lot, wafer, and
grid coordinates and carries the true pass/bin, six latent factors, and the
pattern IDs active on each die.

``ManifestBuilder`` accumulates one lot at a time so the streaming export path
can release each lot's measurements after writing its CSV files.
"""

import csv
import gzip
import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from ..dataset import (
    CPLot,
    CPWafer,
    GenerationResult,
    LinkageReportEntry,
    PatternAccumulator,
    PatternReport,
)
from ..latent import FACTORS
from ..patterns import pattern_id
from ..scenario.models import Pattern, Scenario
from .common import (
    CsvWriter,
    engine_version,
    format_float,
    format_timestamp,
    safe_filename_part,
    scenario_sha256,
    timestamp_token,
)

MANIFEST_VERSION = 1

_DIE_TRUTH_HEADER: tuple[str, ...] = (
    "lot_id",
    "wafer_id",
    "die_x_mm",
    "die_y_mm",
    "grid_x",
    "grid_y",
    "test_site",
    "true_pass",
    "true_hard_bin",
    "true_soft_bin",
    "F_VT",
    "F_MOB",
    "F_TOX",
    "F_RC",
    "F_LEAK",
    "F_SC",
    "pattern_ids",
)


def export_ground_truth(
    result: GenerationResult, out_dir: Path, *, include_die_truth: bool
) -> tuple[Path, ...]:
    """Write the manifest and, when enabled, one per-die truth file per lot."""
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = timestamp_token(result.generated_at)
    product = safe_filename_part(result.scenario.product.name)

    die_truth_files: dict[str, str] = {}
    paths: list[Path] = []
    if include_die_truth:
        for lot in result.lots:
            name = die_truth_filename(product, lot.lot_id, timestamp)
            path = out_dir / name
            write_die_truth_file(path, lot)
            die_truth_files[lot.lot_id] = name
            paths.append(path)

    manifest = build_manifest(result, die_truth_files)
    manifest_path = out_dir / manifest_filename(product, timestamp)
    write_manifest_file(manifest_path, manifest)
    paths.append(manifest_path)
    return tuple(paths)


def write_manifest_file(path: Path, manifest: Mapping[str, Any]) -> None:
    """Write a manifest JSON document, creating its directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def die_truth_filename(product: str, lot_id: str, timestamp: str) -> str:
    """Return the per-die truth file name for one lot."""
    return f"{product}_{safe_filename_part(lot_id)}_die_truth_{timestamp}.csv.gz"


def manifest_filename(product: str, timestamp: str) -> str:
    """Return the ground truth manifest file name for one run."""
    return f"{product}_ground_truth_{timestamp}.json"


def write_die_truth_file(path: Path, lot: CPLot) -> None:
    """Write one lot's per-die truth rows to a gzip CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
    ):
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(_DIE_TRUTH_HEADER)
        for wafer in lot.wafers:
            _write_wafer_truth(writer, lot, wafer)


@dataclass
class ManifestBuilder:
    """Accumulate manifest data one lot at a time."""

    scenario: Scenario
    generated_at: datetime
    _lots: list[dict[str, Any]] = field(default_factory=list)
    _pattern_totals: list[PatternAccumulator] = field(init=False)
    _die_truth_files: dict[str, str] = field(default_factory=dict)
    _linkage: list[dict[str, Any]] = field(default_factory=list)
    _wafer_yields: dict[tuple[str, str], float] = field(default_factory=dict)
    _total_dies: int = 0
    _total_pass: int = 0
    _defect_failure_count: int = 0
    _cluster_count: int = 0

    def __post_init__(self) -> None:
        self._pattern_totals = [PatternAccumulator() for _ in self.scenario.patterns]

    def add_pattern_reports(self, reports: Iterable[PatternReport]) -> None:
        """Merge one report per scenario pattern into the running totals."""
        report_tuple = tuple(reports)
        if not report_tuple:
            return
        for total, report in zip(self._pattern_totals, report_tuple, strict=True):
            total.add(report)

    def add_lot(
        self,
        lot: CPLot,
        *,
        pattern_reports: Iterable[PatternReport] = (),
        die_truth_file: str | None = None,
    ) -> None:
        """Add one lot's summaries, wafers, defects, and pattern contributions."""
        self.add_pattern_reports(pattern_reports)
        factor_totals = np.zeros(len(FACTORS), dtype=np.float64)
        wafers: list[dict[str, Any]] = []
        for wafer in lot.wafers:
            factor_totals += wafer.factors.sum(axis=1)
            wafers.append(_wafer_entry(wafer))
            self._wafer_yields[(lot.lot_id, wafer.wafer_id)] = wafer.yield_fraction
            self._defect_failure_count += int(wafer.defect_failure.sum())
            self._cluster_count += len(wafer.defect_clusters)
        latent_means = {
            factor: (float(factor_totals[index] / lot.die_count) if lot.die_count else 0.0)
            for index, factor in enumerate(FACTORS)
        }
        self._total_dies += lot.die_count
        self._total_pass += lot.pass_count
        if die_truth_file is not None:
            self._die_truth_files[lot.lot_id] = die_truth_file
        self._lots.append(
            {
                "lot_id": lot.lot_id,
                "die_count": lot.die_count,
                "pass_count": lot.pass_count,
                "yield": _rounded_fraction(lot.yield_fraction),
                "latent_factor_means": latent_means,
                "die_truth_file": die_truth_file,
                "wafers": wafers,
            }
        )

    def add_linkage(self, entries: Iterable[LinkageReportEntry]) -> None:
        """Record the generation report's WAT/CP linkage rows."""
        self._linkage = [
            {
                "wat_item": entry.wat_item,
                "cp_item": entry.cp_item,
                "factor": entry.factor,
                "target_r": entry.target_r,
                "achieved_r": entry.achieved_r,
                "observed_r": entry.observed_r,
                "sample_count": entry.sample_count,
            }
            for entry in entries
        ]

    def build(self) -> dict[str, Any]:
        """Render the complete manifest."""
        outlier_patterns = self._outlier_patterns()
        for lot in self._lots:
            for wafer in lot["wafers"]:
                key = (lot["lot_id"], wafer["wafer_id"])
                wafer["outlier"] = key in outlier_patterns

        scenario = self.scenario
        return {
            "manifest_version": MANIFEST_VERSION,
            "engine_version": engine_version(),
            "scenario_schema_version": scenario.schema_version,
            "generated_at": format_timestamp(self.generated_at),
            "seed": scenario.seed,
            "scenario_sha256": scenario_sha256(scenario),
            "scenario": scenario.model_dump(mode="json"),
            "product": scenario.product.model_dump(mode="json"),
            "summary": {
                "lot_count": len(self._lots),
                "wafer_count": sum(len(lot["wafers"]) for lot in self._lots),
                "die_count": self._total_dies,
                "pass_count": self._total_pass,
                "yield": (
                    _rounded_fraction(self._total_pass / self._total_dies)
                    if self._total_dies
                    else 0.0
                ),
            },
            "lots": self._lots,
            "patterns": [
                _pattern_entry(index, pattern, total)
                for index, (pattern, total) in enumerate(
                    zip(scenario.patterns, self._pattern_totals, strict=True)
                )
            ],
            "random_defects": _random_defects_entry(
                scenario,
                failure_count=self._defect_failure_count,
                die_count=self._total_dies,
                cluster_count=self._cluster_count,
            ),
            "linkage": self._linkage,
            "outlier_wafers": self._outlier_wafers(outlier_patterns),
            "die_truth_files": [
                self._die_truth_files[lot["lot_id"]]
                for lot in self._lots
                if lot["lot_id"] in self._die_truth_files
            ],
        }

    def _outlier_patterns(self) -> dict[tuple[str, str], list[str]]:
        outliers: dict[tuple[str, str], list[str]] = {}
        for index, pattern in enumerate(self.scenario.patterns):
            if pattern.scope != "wafer":
                continue
            for lot_id, wafer_id in self._pattern_totals[index].affected_wafers:
                outliers.setdefault((lot_id, wafer_id), []).append(pattern_id(index))
        return outliers

    def _outlier_wafers(
        self, outlier_patterns: Mapping[tuple[str, str], list[str]]
    ) -> list[dict[str, Any]]:
        return [
            {
                "lot_id": lot_id,
                "wafer_id": wafer_id,
                "patterns": outlier_patterns[(lot_id, wafer_id)],
                "yield": _rounded_fraction(self._wafer_yields[(lot_id, wafer_id)]),
            }
            for lot_id, wafer_id in sorted(outlier_patterns)
        ]


def build_manifest(result: GenerationResult, die_truth_files: Mapping[str, str]) -> dict[str, Any]:
    """Build the ground truth manifest for one complete generation result."""
    builder = ManifestBuilder(result.scenario, result.generated_at)
    builder.add_pattern_reports(result.pattern_reports)
    for lot in result.lots:
        builder.add_lot(lot, die_truth_file=die_truth_files.get(lot.lot_id))
    builder.add_linkage(result.linkage_report)
    return builder.build()


def _wafer_entry(wafer: CPWafer) -> dict[str, Any]:
    failure_count = int(wafer.defect_failure.sum())
    return {
        "wafer_id": wafer.wafer_id,
        "die_count": wafer.die_count,
        "pass_count": wafer.pass_count,
        "yield": _rounded_fraction(wafer.yield_fraction),
        "outlier": False,
        "defects": {
            "failure_count": failure_count,
            "observed_failure_rate": (failure_count / wafer.die_count if wafer.die_count else 0.0),
            "defect_dies": _die_coordinates(wafer, np.flatnonzero(wafer.defect_failure)),
            "clusters": [
                {
                    "cluster_id": cluster.cluster_id,
                    "center_x_mm": cluster.center_x_mm,
                    "center_y_mm": cluster.center_y_mm,
                    "die_count": len(cluster.die_indices),
                    "dies": _die_coordinates(
                        wafer, np.asarray(cluster.die_indices, dtype=np.int64)
                    ),
                }
                for cluster in wafer.defect_clusters
            ],
        },
    }


def _pattern_entry(index: int, pattern: Pattern, total: PatternAccumulator) -> dict[str, Any]:
    mean_shift = (
        total.item_shift_sum / total.item_shift_die_count if total.item_shift_die_count else 0.0
    )
    return {
        "id": pattern_id(index),
        "kind": pattern.kind,
        "scope": pattern.scope,
        "target": pattern.target,
        "target_item": pattern.target_item,
        "amplitude": pattern.amplitude,
        "radius_mm": pattern.radius_mm,
        "extent_mm": pattern.extent_mm,
        "width_mm": pattern.width_mm,
        "center_mm": list(pattern.center_mm),
        "combine": pattern.combine,
        "affected_die_count": total.affected_die_count,
        "affected_wafers": [
            {"lot_id": lot_id, "wafer_id": wafer_id} for lot_id, wafer_id in total.affected_wafers
        ],
        "contribution": {
            "realized_failures": total.realized_failures,
            "item_shift_die_count": total.item_shift_die_count,
            "mean_relative_item_shift": mean_shift,
            "recovery_probability_sum": total.recovery_probability_sum,
        },
    }


def _random_defects_entry(
    scenario: Scenario,
    *,
    failure_count: int,
    die_count: int,
    cluster_count: int,
) -> dict[str, Any]:
    config = scenario.defects
    return {
        "enabled": config.enabled,
        "model": config.model,
        "failure_rate": config.failure_rate,
        "cluster_size": config.cluster_size,
        "cluster_radius_mm": config.cluster_radius_mm,
        "target_items": list(config.target_items),
        "failure_count": failure_count,
        "die_count": die_count,
        "observed_failure_rate": failure_count / die_count if die_count else 0.0,
        "cluster_count": cluster_count,
    }


def _die_coordinates(wafer: CPWafer, indices: NDArray[np.int64]) -> list[list[int]]:
    return [[int(wafer.grid_x[index]), int(wafer.grid_y[index])] for index in indices]


def _rounded_fraction(value: float) -> float:
    """Round a yield fraction to the six decimals used by CSV metadata."""
    return float(f"{value:.6f}")


def _write_wafer_truth(writer: CsvWriter, lot: CPLot, wafer: CPWafer) -> None:
    pattern_ids = list(wafer.pattern_hits)
    masks = [wafer.pattern_hits[pattern_id] for pattern_id in pattern_ids]
    for index in range(wafer.die_count):
        active = "|".join(
            pattern_id for pattern_id, mask in zip(pattern_ids, masks, strict=True) if mask[index]
        )
        writer.writerow(
            (
                lot.lot_id,
                wafer.wafer_id,
                format_float(float(wafer.x_mm[index])),
                format_float(float(wafer.y_mm[index])),
                int(wafer.grid_x[index]),
                int(wafer.grid_y[index]),
                int(wafer.test_site[index]),
                int(wafer.passed[index]),
                int(wafer.hard_bin[index]),
                int(wafer.soft_bin[index]),
                *(
                    format_float(float(wafer.factors[factor, index]))
                    for factor in range(len(FACTORS))
                ),
                active,
            )
        )
