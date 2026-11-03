"""Random defect injection with optional spatial clustering.

A defect event marks one die as randomly failed and makes one configured target
item fail its pass rule. The default model draws a small number of cluster
centres and builds a Gaussian intensity field around them; each die's defect
count is negative-binomial with that intensity, so failures arrive in spatial
clusters and counts are overdispersed. The Poisson model gives every die the
same independent failure probability.

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
    clusters: tuple[DefectCluster, ...]


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
    if not config.enabled or config.failure_rate == 0.0 or count == 0 or not target_items:
        return DefectApplication(failure=np.zeros(count, dtype=np.bool_), clusters=())

    if config.model == "clustered":
        failure, cluster_centers = _clustered_failures(config, layout, recovery, rng)
    else:
        retention = 1.0 - np.clip(recovery, 0.0, 1.0)
        probability = np.clip(config.failure_rate * retention, 0.0, 1.0)
        failure = rng.random(count) < probability
        cluster_centers = []
    failing_dies = np.flatnonzero(failure)

    for position, die_index in enumerate(failing_dies):
        item = target_items[position % len(target_items)]
        mask = np.zeros(count, dtype=np.bool_)
        mask[die_index] = True
        force_failure(item, values, mask)

    clusters = _assign_clusters(cluster_centers, failing_dies, layout)
    return DefectApplication(failure=failure, clusters=clusters)


def _clustered_failures(
    config: Defects,
    layout: DieLayout,
    recovery: FloatArray,
    rng: np.random.Generator,
) -> tuple[BoolArray, list[int]]:
    """Draw clustered failures with a negative-binomial count per die.

    A Gaussian kernel field supplies the spatial intensity; the count of
    defects on each die is negative-binomial with dispersion ``cluster_size``,
    so a die fails when it receives at least one defect. The intensity is
    rescaled by :func:`_calibrate_scale` so the mean failure probability
    matches ``failure_rate`` after yield-pattern recovery.
    """
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
        return np.zeros(count, dtype=np.bool_), []

    retention = 1.0 - np.clip(recovery, 0.0, 1.0)
    weights = (intensity / mean_intensity) * retention
    target_rate = config.failure_rate * float(retention.mean())
    if target_rate >= 1.0:
        return np.ones(count, dtype=np.bool_), [int(center) for center in centers]

    dispersion = config.cluster_size
    scale = _calibrate_scale(weights, dispersion, target_rate)
    if scale <= 0.0:
        return np.zeros(count, dtype=np.bool_), [int(center) for center in centers]
    mean_defects = weights * scale
    probability = np.divide(
        float(dispersion),
        dispersion + mean_defects,
        out=np.ones_like(mean_defects),
        where=mean_defects > 0.0,
    )
    probability = np.clip(probability, np.finfo(np.float64).tiny, 1.0)
    counts = rng.negative_binomial(dispersion, probability)
    return counts > 0, [int(center) for center in centers]


def _calibrate_scale(weights: FloatArray, dispersion: int, target_rate: float) -> float:
    """Find the intensity scale whose negative-binomial failure rate matches the target."""

    def mean_failure_rate(scale: float) -> float:
        mean_defects = weights * scale
        survived = (dispersion / (dispersion + mean_defects)) ** dispersion
        return float(np.mean(1.0 - survived))

    if target_rate <= 0.0:
        return 0.0
    low = 0.0
    high = 1.0
    while mean_failure_rate(high) < target_rate and high < 1e12:
        high *= 2.0
    for _ in range(60):
        middle = (low + high) / 2.0
        if mean_failure_rate(middle) < target_rate:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _assign_clusters(
    centers: list[int],
    failing_dies: IntArray,
    layout: DieLayout,
) -> tuple[DefectCluster, ...]:
    if not centers or failing_dies.size == 0:
        return ()
    center_indices = np.asarray(centers, dtype=np.int64)
    dx = layout.x_mm[failing_dies, np.newaxis] - layout.x_mm[center_indices][np.newaxis, :]
    dy = layout.y_mm[failing_dies, np.newaxis] - layout.y_mm[center_indices][np.newaxis, :]
    assignments = np.argmin(dx * dx + dy * dy, axis=1)
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
