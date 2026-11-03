"""Ground truth manifest and per-die truth export.

The manifest is a machine-readable record of what the generator injected: the
full scenario and its hash, per-lot and per-wafer yields, latent-factor means,
pattern contributions, random-defect clusters, linkage targets, and outlier
wafers. The optional per-die truth CSV.GZ joins to CP data by lot, wafer, and
grid coordinates and carries the true pass/bin, six latent factors, and the
pattern IDs active on each die.
"""

import csv
import gzip
import io
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from numpy.typing import NDArray

from ..dataset import CPLot, CPWafer, GenerationResult, PatternReport
from ..latent import FACTORS
from ..scenario.models import Pattern
from .common import (
    engine_version,
    format_float,
    format_timestamp,
    safe_filename_part,
    scenario_sha256,
    timestamp_token,
)

MANIFEST_VERSION = 1


class _CsvWriter(Protocol):
    """The subset of ``csv.writer`` used by this module."""

    def writerow(self, row: Sequence[object]) -> object: ...


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
            name = f"{product}_{safe_filename_part(lot.lot_id)}_die_truth_{timestamp}.csv.gz"
            path = out_dir / name
            _write_die_truth(path, lot)
            die_truth_files[lot.lot_id] = name
            paths.append(path)

    manifest = build_manifest(result, die_truth_files)
    manifest_path = out_dir / f"{product}_ground_truth_{timestamp}.json"
    with manifest_path.open("w", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    paths.append(manifest_path)
    return tuple(paths)


def build_manifest(result: GenerationResult, die_truth_files: Mapping[str, str]) -> dict[str, Any]:
    """Build the ground truth manifest for one generation result."""
    scenario = result.scenario
    outlier_patterns = _outlier_patterns(result)
    wafer_lookup = {
        (lot.lot_id, wafer.wafer_id): wafer for lot in result.lots for wafer in lot.wafers
    }

    lots: list[dict[str, Any]] = []
    total_dies = 0
    total_pass = 0
    for lot in result.lots:
        factor_totals = np.zeros(len(FACTORS), dtype=np.float64)
        wafer_entries: list[dict[str, Any]] = []
        for wafer in lot.wafers:
            factor_totals += wafer.factors.sum(axis=1)
            wafer_entries.append(
                _wafer_entry(
                    wafer,
                    is_outlier=(lot.lot_id, wafer.wafer_id) in outlier_patterns,
                )
            )
        total_dies += lot.die_count
        total_pass += lot.pass_count
        latent_means = {
            factor: (float(factor_totals[index] / lot.die_count) if lot.die_count else 0.0)
            for index, factor in enumerate(FACTORS)
        }
        lots.append(
            {
                "lot_id": lot.lot_id,
                "die_count": lot.die_count,
                "pass_count": lot.pass_count,
                "yield": _fraction(lot.yield_fraction),
                "latent_factor_means": latent_means,
                "die_truth_file": die_truth_files.get(lot.lot_id),
                "wafers": wafer_entries,
            }
        )

    patterns = [
        _pattern_entry(pattern, result.pattern_reports[index])
        for index, pattern in enumerate(scenario.patterns)
    ]
    random_defects = _random_defects_entry(result)
    outliers = [
        {
            "lot_id": lot_id,
            "wafer_id": wafer_id,
            "patterns": outlier_patterns[(lot_id, wafer_id)],
            "yield": _fraction(wafer_lookup[(lot_id, wafer_id)].yield_fraction),
        }
        for lot_id, wafer_id in sorted(outlier_patterns)
    ]

    return {
        "manifest_version": MANIFEST_VERSION,
        "engine_version": engine_version(),
        "scenario_schema_version": scenario.schema_version,
        "generated_at": format_timestamp(result.generated_at),
        "seed": scenario.seed,
        "scenario_sha256": scenario_sha256(scenario),
        "scenario": scenario.model_dump(mode="json"),
        "product": scenario.product.model_dump(mode="json"),
        "summary": {
            "lot_count": len(result.lots),
            "wafer_count": sum(len(lot.wafers) for lot in result.lots),
            "die_count": total_dies,
            "pass_count": total_pass,
            "yield": _fraction(total_pass / total_dies) if total_dies else 0.0,
        },
        "lots": lots,
        "patterns": patterns,
        "random_defects": random_defects,
        "linkage": [
            {
                "wat_item": entry.wat_item,
                "cp_item": entry.cp_item,
                "factor": entry.factor,
                "target_r": entry.target_r,
                "achieved_r": entry.achieved_r,
                "observed_r": entry.observed_r,
                "sample_count": entry.sample_count,
            }
            for entry in result.linkage_report
        ],
        "outlier_wafers": outliers,
        "die_truth_files": [
            die_truth_files[lot.lot_id] for lot in result.lots if lot.lot_id in die_truth_files
        ],
    }


def _outlier_patterns(result: GenerationResult) -> dict[tuple[str, str], list[str]]:
    outliers: dict[tuple[str, str], list[str]] = {}
    for pattern, report in zip(result.scenario.patterns, result.pattern_reports, strict=True):
        if pattern.scope != "wafer":
            continue
        for lot_id, wafer_id in report.affected_wafers:
            outliers.setdefault((lot_id, wafer_id), []).append(report.pattern_id)
    return outliers


def _wafer_entry(wafer: CPWafer, *, is_outlier: bool) -> dict[str, Any]:
    failure_count = int(wafer.defect_failure.sum())
    return {
        "wafer_id": wafer.wafer_id,
        "die_count": wafer.die_count,
        "pass_count": wafer.pass_count,
        "yield": _fraction(wafer.yield_fraction),
        "outlier": is_outlier,
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


def _pattern_entry(pattern: Pattern, report: PatternReport) -> dict[str, Any]:
    mean_shift = (
        report.item_shift_sum / report.item_shift_die_count if report.item_shift_die_count else 0.0
    )
    return {
        "id": report.pattern_id,
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
        "affected_die_count": report.affected_die_count,
        "affected_wafers": [
            {"lot_id": lot_id, "wafer_id": wafer_id} for lot_id, wafer_id in report.affected_wafers
        ],
        "contribution": {
            "realized_failures": report.realized_failures,
            "item_shift_die_count": report.item_shift_die_count,
            "mean_relative_item_shift": mean_shift,
            "recovery_probability_sum": report.recovery_probability_sum,
        },
    }


def _random_defects_entry(result: GenerationResult) -> dict[str, Any]:
    config = result.scenario.defects
    wafers = [wafer for lot in result.lots for wafer in lot.wafers]
    failure_count = sum(int(wafer.defect_failure.sum()) for wafer in wafers)
    die_count = sum(wafer.die_count for wafer in wafers)
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
        "cluster_count": sum(len(wafer.defect_clusters) for wafer in wafers),
    }


def _die_coordinates(wafer: CPWafer, indices: NDArray[np.int64]) -> list[list[int]]:
    return [[int(wafer.grid_x[index]), int(wafer.grid_y[index])] for index in indices]


def _fraction(value: float) -> float:
    return float(f"{value:.6f}")


def _write_die_truth(path: Path, lot: CPLot) -> None:
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
        io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
    ):
        writer = csv.writer(text, lineterminator="\n")
        writer.writerow(_DIE_TRUTH_HEADER)
        for wafer in lot.wafers:
            _write_wafer_truth(writer, lot, wafer)


def _write_wafer_truth(writer: _CsvWriter, lot: CPLot, wafer: CPWafer) -> None:
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
