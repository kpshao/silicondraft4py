"""Systematic spatial patterns through the public API."""

from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from silicondraft import GenerationResult, generate, load_scenario

_EDGE_BAND_MM = 20.0
_CENTER_RADIUS_MM = 60.0


def _write_scenario(
    tmp_path: Path,
    *,
    patterns: list[dict[str, Any]],
    wafers_per_lot: int = 1,
    defects: dict[str, Any] | None = None,
    seed: int = 20260105,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "lots": {"wafers_per_lot": wafers_per_lot},
        "patterns": patterns,
        "defects": defects if defects is not None else {"enabled": False},
        "seed": seed,
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(tmp_path: Path, **kwargs: Any) -> GenerationResult:
    return generate(load_scenario(_write_scenario(tmp_path, **kwargs)))


def _radius(wafer: Any) -> Any:
    return np.hypot(wafer.x_mm, wafer.y_mm)


def test_edge_low_pattern_significantly_lowers_edge_yield(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        patterns=[
            {
                "kind": "edge_low",
                "scope": "lot",
                "target": "yield",
                "amplitude": 0.8,
                "extent_mm": _EDGE_BAND_MM,
            }
        ],
    )

    wafer = result.lots[0].wafers[0]
    radius = _radius(wafer)
    edge = radius >= 300 / 2 - 3 - _EDGE_BAND_MM
    center = radius <= _CENTER_RADIUS_MM

    assert wafer.passed[center].mean() > 0.98
    assert wafer.passed[edge].mean() < wafer.passed[center].mean() - 0.2


def test_pattern_can_target_a_selected_item(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        patterns=[
            {
                "kind": "center_high",
                "scope": "lot",
                "target_item": "CP_FRO",
                "amplitude": 0.2,
                "radius_mm": 40.0,
            }
        ],
    )

    wafer = result.lots[0].wafers[0]
    radius = _radius(wafer)
    center = radius <= 20.0
    outer = radius >= 60.0
    center_mean = wafer.values["CP_FRO"][center].mean()
    outer_mean = wafer.values["CP_FRO"][outer].mean()

    assert center_mean > outer_mean * 1.05


@pytest.mark.parametrize(
    ("kind", "extra", "higher_region", "lower_region"),
    [
        ("center_high", {"radius_mm": 40.0}, "center", "outer"),
        ("center_low", {"radius_mm": 40.0}, "outer", "center"),
        ("edge_high", {"extent_mm": _EDGE_BAND_MM}, "edge", "center"),
        ("edge_low", {"extent_mm": _EDGE_BAND_MM}, "center", "edge"),
        ("ring", {"radius_mm": 60.0, "width_mm": 10.0}, "ring", "outer"),
        ("radial_gradient", {}, "edge", "center"),
        ("local_spot", {"radius_mm": 20.0, "center_mm": [50.0, 0.0]}, "spot", "outer"),
    ],
)
def test_every_pattern_kind_shifts_the_targeted_item_in_the_expected_region(
    tmp_path: Path,
    kind: str,
    extra: dict[str, Any],
    higher_region: str,
    lower_region: str,
) -> None:
    result = _generate(
        tmp_path,
        patterns=[
            {
                "kind": kind,
                "target_item": "CP_FRO",
                "amplitude": 0.25,
                **extra,
            }
        ],
    )

    wafer = result.lots[0].wafers[0]
    radius = _radius(wafer)
    values = wafer.values["CP_FRO"]
    spot_radius = np.hypot(wafer.x_mm - 50.0, wafer.y_mm)
    masks = {
        "center": radius <= 20.0,
        "outer": radius >= 100.0,
        "edge": radius >= 300 / 2 - 3 - _EDGE_BAND_MM,
        "ring": np.abs(radius - 60.0) <= 5.0,
        "spot": spot_radius <= 10.0,
    }
    assert values[masks[higher_region]].mean() > values[masks[lower_region]].mean() * 1.02


def test_wafer_scoped_pattern_is_a_single_wafer_excursion(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        wafers_per_lot=3,
        patterns=[
            {
                "kind": "edge_low",
                "scope": "wafer",
                "target": "yield",
                "amplitude": 0.8,
                "extent_mm": _EDGE_BAND_MM,
            }
        ],
    )

    edge_yields = []
    for wafer in result.lots[0].wafers:
        radius = _radius(wafer)
        edge = radius >= 300 / 2 - 3 - _EDGE_BAND_MM
        edge_yields.append(float(wafer.passed[edge].mean()))

    affected = [value < 0.8 for value in edge_yields]
    assert sum(affected) == 1


def test_multiply_combine_scales_the_targeted_item(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        patterns=[
            {
                "kind": "center_high",
                "target_item": "CP_FRO",
                "amplitude": 0.2,
                "radius_mm": 40.0,
                "combine": "multiply",
            }
        ],
    )
    wafer = result.lots[0].wafers[0]
    radius = _radius(wafer)
    center = wafer.values["CP_FRO"][radius <= 20.0].mean()
    outer = wafer.values["CP_FRO"][radius >= 60.0].mean()

    assert center > outer * 1.05


def test_both_targets_do_not_double_apply_the_yield_item(tmp_path: Path) -> None:
    yield_only = _generate(
        tmp_path,
        patterns=[
            {
                "kind": "center_low",
                "target": "yield",
                "amplitude": 0.5,
                "radius_mm": 300.0,
            }
        ],
    )
    both = _generate(
        tmp_path,
        patterns=[
            {
                "kind": "center_low",
                "target": "yield",
                "target_item": "CP_FUNC",
                "amplitude": 0.5,
                "radius_mm": 300.0,
            }
        ],
    )

    np.testing.assert_array_equal(
        yield_only.lots[0].wafers[0].passed, both.lots[0].wafers[0].passed
    )


def test_pattern_extent_tracks_the_pattern_centre() -> None:
    from silicondraft.patterns import pattern_extent
    from silicondraft.scenario.models import Pattern, Wafer

    wafer = Wafer(diameter_mm=150, edge_exclusion_mm=3.0)
    ring = Pattern(
        kind="ring",
        target_item="CP_VTHN",
        amplitude=0.2,
        radius_mm=30.0,
        width_mm=5.0,
        center_mm=(10.0, -5.0),
    )
    edge = Pattern(
        kind="edge_high",
        target_item="CP_VTHN",
        amplitude=0.2,
        extent_mm=10.0,
        center_mm=(5.0, 5.0),
    )

    ring_extent = pattern_extent(ring, 0, wafer)
    edge_extent = pattern_extent(edge, 1, wafer)

    assert ring_extent is not None
    assert ring_extent.pattern_id == "pattern_1"
    assert ring_extent.center_mm == (10.0, -5.0)
    assert ring_extent.inner_radius_mm == pytest.approx(25.0)
    assert ring_extent.outer_radius_mm == pytest.approx(35.0)
    assert edge_extent is not None
    assert edge_extent.pattern_id == "pattern_2"
    assert edge_extent.center_mm == (5.0, 5.0)
    assert edge_extent.inner_radius_mm == pytest.approx(62.0)
    assert edge_extent.outer_radius_mm == pytest.approx(72.0)
