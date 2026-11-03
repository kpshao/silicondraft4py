"""Random defects through the public API."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from silicondraft import GenerationResult, generate, load_scenario


def _write_scenario(
    tmp_path: Path,
    *,
    defects: dict[str, Any] | None = None,
    wafers_per_lot: int = 1,
    seed: int = 20260105,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "lots": {"wafers_per_lot": wafers_per_lot},
        "patterns": [],
        "seed": seed,
    }
    if defects is not None:
        document["defects"] = defects
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(tmp_path: Path, **kwargs: Any) -> GenerationResult:
    return generate(load_scenario(_write_scenario(tmp_path, **kwargs)))


def _defect_failed(wafer: Any) -> Any:
    return (wafer.values["CP_FUNC"] == 0) | (wafer.values["CP_SCAN"] == 0)


def _defect_rate(result: GenerationResult) -> float:
    failed = sum(int(_defect_failed(wafer).sum()) for wafer in result.lots[0].wafers)
    dies = sum(wafer.die_count for wafer in result.lots[0].wafers)
    return failed / dies


def test_default_random_defect_failure_rate_is_about_one_percent(tmp_path: Path) -> None:
    result = _generate(tmp_path, wafers_per_lot=3)

    assert _defect_rate(result) == pytest.approx(0.01, abs=0.004)


def test_default_random_defects_fail_cp_func_and_cp_scan(tmp_path: Path) -> None:
    result = _generate(tmp_path, wafers_per_lot=3)

    func_failures = sum(
        int((wafer.values["CP_FUNC"] == 0).sum()) for wafer in result.lots[0].wafers
    )
    scan_failures = sum(
        int((wafer.values["CP_SCAN"] == 0).sum()) for wafer in result.lots[0].wafers
    )

    assert func_failures > 0
    assert scan_failures > 0


def test_random_defect_failures_drive_functional_bins(tmp_path: Path) -> None:
    result = _generate(tmp_path, wafers_per_lot=1)
    wafer = result.lots[0].wafers[0]
    failed = _defect_failed(wafer)

    assert failed.any()
    assert np.all(wafer.hard_bin[failed] == 3)
    assert np.all(wafer.soft_bin[failed] == 206)


def test_clustered_defects_are_more_spatially_concentrated_than_poisson(
    tmp_path: Path,
) -> None:
    clustered = _generate(
        tmp_path,
        defects={
            "model": "clustered",
            "failure_rate": 0.01,
            "cluster_size": 20,
            "cluster_radius_mm": 6.0,
        },
    )
    poisson = _generate(
        tmp_path,
        defects={"model": "poisson", "failure_rate": 0.01},
    )

    clustered_distance = _mean_nearest_neighbour_distance(clustered.lots[0].wafers[0])
    poisson_distance = _mean_nearest_neighbour_distance(poisson.lots[0].wafers[0])

    assert clustered_distance < poisson_distance * 0.5


def test_poisson_model_failure_rate_is_configurable(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        wafers_per_lot=3,
        defects={"model": "poisson", "failure_rate": 0.02},
    )

    assert _defect_rate(result) == pytest.approx(0.02, abs=0.005)


def test_disabling_random_defects_restores_a_clean_baseline(tmp_path: Path) -> None:
    result = _generate(tmp_path, defects={"enabled": False})
    wafer = result.lots[0].wafers[0]

    assert np.all(wafer.values["CP_FUNC"] == 1)
    assert np.all(wafer.values["CP_SCAN"] == 1)
    assert wafer.passed.all()


def _mean_nearest_neighbour_distance(wafer: Any) -> float:
    failed = _defect_failed(wafer)
    points = np.column_stack((wafer.x_mm[failed], wafer.y_mm[failed]))
    dx = points[:, np.newaxis, 0] - points[np.newaxis, :, 0]
    dy = points[:, np.newaxis, 1] - points[np.newaxis, :, 1]
    distances = np.hypot(dx, dy)
    np.fill_diagonal(distances, np.inf)
    return float(distances.min(axis=1).mean())


def test_random_defects_can_target_a_continuous_item(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        defects={"failure_rate": 0.02, "target_items": ["CP_VTHN"]},
    )
    wafer = result.lots[0].wafers[0]
    failed = wafer.values["CP_VTHN"] > 0.42

    assert 0 < failed.mean() < 0.04
    assert np.all(wafer.hard_bin[failed] == 2)
    assert np.all(wafer.soft_bin[failed] == 204)
