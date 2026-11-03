"""Random defect injection with optional spatial clustering.

A defect event marks one die as randomly failed and makes one configured target
item fail its pass rule. The default model draws a small number of cluster
centres and raises each die's failure probability with a Gaussian kernel around
them, so failures arrive in spatially concentrated blobs. The Poisson model
gives every die the same independent failure probability.

The expected number of failures per cluster is ``cluster_size``: the model
places ``failure_rate * die_count / cluster_size`` centres. All probabilities
are clipped, so the realised failure rate stays close to, but not exactly at,
the configured rate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .catalog import CatalogItem
from .geometry import DieLayout
from .patterns import force_failure
from .scenario.models import Defects

FloatArray = NDArray[np.float64]
BoolArray = NDArray[np.bool_]
IntArray = NDArray[np.int64]


@dataclass(frozen=True, slots=True)
class DefectCluster:
    """One spatial cluster of random-defect failures on a wafer."""

    cluster_id: str
    center_x_mm: float
    center_y_mm: float
    die_indices: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class DefectApplication:
    """The random-defect outcome for one wafer."""

    failure: BoolArray
    cluster_index: IntArray
    clusters: tuple[DefectCluster, ...]

    @property
    def failure_count(self) -> int:
        """Number of dies with a random defect."""
        return int(self.failure.sum())


def apply_random_defects(
    config: Defects,
    target_items: tuple[CatalogItem, ...],
    values: dict[str, FloatArray],
    layout: DieLayout,
    recovery: FloatArray,
    rng: np.random.Generator,
) -> DefectApplication:
    """Draw random defects and mutate the targeted measurements in place."""
    count = layout.count
    cluster_index = np.full(count, -1, dtype=np.int64)
    if not config.enabled or config.failure_rate == 0.0 or count == 0 or not target_items:
        return DefectApplication(
            failure=np.zeros(count, dtype=np.bool_),
            cluster_index=cluster_index,
            clusters=(),
        )

    cluster_centers: list[int] = []
    if config.model == "clustered":
        probability, cluster_centers = _clustered_probability(config, layout, rng)
    else:
        probability = np.full(count, config.failure_rate, dtype=np.float64)

    probability = np.clip(probability * (1.0 - np.clip(recovery, 0.0, 1.0)), 0.0, 1.0)
    failure = rng.random(count) < probability
    failing_dies = np.flatnonzero(failure)

    for position, die_index in enumerate(failing_dies):
        item = target_items[position % len(target_items)]
        mask = np.zeros(count, dtype=np.bool_)
        mask[die_index] = True
        force_failure(item, values, mask)

    clusters = _assign_clusters(cluster_centers, failing_dies, cluster_index, layout)
    return DefectApplication(failure=failure, cluster_index=cluster_index, clusters=clusters)


def _clustered_probability(
    config: Defects, layout: DieLayout, rng: np.random.Generator
) -> tuple[FloatArray, list[int]]:
    count = layout.count
    expected_failures = config.failure_rate * count
    cluster_count = min(count, max(1, round(expected_failures / config.cluster_size)))
    centers = np.sort(rng.choice(count, size=cluster_count, replace=False))
    sigma_mm = config.cluster_radius_mm / 2.0
    intensity = np.zeros(count, dtype=np.float64)
    for center in centers:
        distance_squared = (layout.x_mm - layout.x_mm[center]) ** 2 + (
            layout.y_mm - layout.y_mm[center]
        ) ** 2
        intensity += np.exp(-distance_squared / (2.0 * sigma_mm * sigma_mm))
    mean_intensity = float(intensity.mean())
    if mean_intensity <= 0.0:  # pragma: no cover - positive kernels always sum above zero
        return np.zeros(count, dtype=np.float64), []
    probability = config.failure_rate * intensity / mean_intensity
    return probability, [int(center) for center in centers]


def _assign_clusters(
    centers: list[int],
    failing_dies: IntArray,
    cluster_index: IntArray,
    layout: DieLayout,
) -> tuple[DefectCluster, ...]:
    if not centers or failing_dies.size == 0:
        return ()
    center_indices = np.asarray(centers, dtype=np.int64)
    dx = layout.x_mm[failing_dies, np.newaxis] - layout.x_mm[center_indices][np.newaxis, :]
    dy = layout.y_mm[failing_dies, np.newaxis] - layout.y_mm[center_indices][np.newaxis, :]
    assignments = np.argmin(dx * dx + dy * dy, axis=1)
    cluster_index[failing_dies] = assignments
    clusters: list[DefectCluster] = []
    for offset, center in enumerate(centers):
        members = tuple(
            int(die)
            for die, assignment in zip(failing_dies, assignments, strict=True)
            if assignment == offset
        )
        clusters.append(
            DefectCluster(
                cluster_id=f"D{offset + 1}",
                center_x_mm=float(layout.x_mm[center]),
                center_y_mm=float(layout.y_mm[center]),
                die_indices=members,
            )
        )
    return tuple(clusters)
