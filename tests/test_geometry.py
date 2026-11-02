import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from silicondraft.geometry import layout_dies, layout_wat_sites
from silicondraft.scenario.models import Wafer, WaferDiameterMm, WatSiteCount

_DIAMETERS = (150, 200, 300)


def _reference_layout(
    diameter_mm: int, die_size_mm: tuple[float, float], edge_exclusion_mm: float
) -> list[tuple[int, int, float, float]]:
    """Independent geometric definition of the expected die layout."""
    width_mm, height_mm = die_size_mm
    wafer_radius_mm = diameter_mm / 2
    usable_radius_mm = wafer_radius_mm - edge_exclusion_mm
    columns = math.floor(diameter_mm / width_mm)
    rows = math.floor(diameter_mm / height_mm)
    if usable_radius_mm <= 0 or columns < 1 or rows < 1:
        return []

    positions: list[tuple[int, int, float, float]] = []
    for row in range(rows):
        y_mm = (row - (rows - 1) / 2) * height_mm
        for column in range(columns):
            x_mm = (column - (columns - 1) / 2) * width_mm
            if x_mm * x_mm + y_mm * y_mm > usable_radius_mm * usable_radius_mm:
                continue
            corners = (
                (x_mm - width_mm / 2, y_mm - height_mm / 2),
                (x_mm + width_mm / 2, y_mm - height_mm / 2),
                (x_mm - width_mm / 2, y_mm + height_mm / 2),
                (x_mm + width_mm / 2, y_mm + height_mm / 2),
            )
            if any(cx * cx + cy * cy > wafer_radius_mm * wafer_radius_mm for cx, cy in corners):
                continue
            positions.append((column, row, x_mm, y_mm))
    return positions


# 5.0 x 5.0 mm dies with 3 mm edge exclusion, verified against an independent
# brute-force enumeration of the wafer grid.
@pytest.mark.parametrize(
    ("diameter_mm", "expected_dies"),
    [(150, 648), (200, 1176), (300, 2700)],
)
def test_default_geometry_die_counts_match_analytical_values(
    diameter_mm: WaferDiameterMm, expected_dies: int
) -> None:
    layout = layout_dies(Wafer(diameter_mm=diameter_mm))

    assert layout.count == expected_dies


@settings(max_examples=30, deadline=None)
@given(
    diameter_mm=st.sampled_from(_DIAMETERS),
    die_width_mm=st.floats(min_value=2.0, max_value=80.0, allow_nan=False),
    die_height_mm=st.floats(min_value=2.0, max_value=80.0, allow_nan=False),
    edge_exclusion_mm=st.floats(min_value=0.0, max_value=149.0, allow_nan=False),
)
def test_layout_matches_an_independent_geometric_definition(
    diameter_mm: WaferDiameterMm,
    die_width_mm: float,
    die_height_mm: float,
    edge_exclusion_mm: float,
) -> None:
    wafer = Wafer(
        diameter_mm=diameter_mm,
        die_size_mm=(die_width_mm, die_height_mm),
        edge_exclusion_mm=edge_exclusion_mm,
    )

    layout = layout_dies(wafer)

    expected = _reference_layout(diameter_mm, (die_width_mm, die_height_mm), edge_exclusion_mm)
    assert (
        list(
            zip(
                layout.grid_x.tolist(),
                layout.grid_y.tolist(),
                layout.x_mm,
                layout.y_mm,
                strict=True,
            )
        )
        == expected
    )


@settings(max_examples=30, deadline=None)
@given(
    diameter_mm=st.sampled_from(_DIAMETERS),
    die_width_mm=st.floats(min_value=2.0, max_value=80.0, allow_nan=False),
    die_height_mm=st.floats(min_value=2.0, max_value=80.0, allow_nan=False),
    edge_exclusion_mm=st.floats(min_value=0.0, max_value=149.0, allow_nan=False),
)
def test_dies_never_overlap(
    diameter_mm: WaferDiameterMm,
    die_width_mm: float,
    die_height_mm: float,
    edge_exclusion_mm: float,
) -> None:
    layout = layout_dies(
        Wafer(
            diameter_mm=diameter_mm,
            die_size_mm=(die_width_mm, die_height_mm),
            edge_exclusion_mm=edge_exclusion_mm,
        )
    )
    if layout.count < 2:
        return

    order = np.lexsort((layout.x_mm, layout.y_mm))
    xs = layout.x_mm[order]
    ys = layout.y_mm[order]
    delta_x = np.diff(xs)
    delta_y = np.diff(ys)
    same_row = np.isclose(delta_y, 0.0, atol=1e-9)

    assert bool((delta_x[same_row] >= die_width_mm - 1e-9).all())
    assert bool((delta_y[~same_row] >= die_height_mm - 1e-9).all())


@settings(max_examples=30, deadline=None)
@given(
    diameter_mm=st.sampled_from(_DIAMETERS),
    die_width_mm=st.floats(min_value=2.0, max_value=80.0, allow_nan=False),
    die_height_mm=st.floats(min_value=2.0, max_value=80.0, allow_nan=False),
    edge_exclusion_mm=st.floats(min_value=0.0, max_value=149.0, allow_nan=False),
)
def test_die_centres_respect_edge_exclusion_and_dies_are_complete(
    diameter_mm: WaferDiameterMm,
    die_width_mm: float,
    die_height_mm: float,
    edge_exclusion_mm: float,
) -> None:
    layout = layout_dies(
        Wafer(
            diameter_mm=diameter_mm,
            die_size_mm=(die_width_mm, die_height_mm),
            edge_exclusion_mm=edge_exclusion_mm,
        )
    )
    wafer_radius_mm = diameter_mm / 2
    usable_radius_mm = wafer_radius_mm - edge_exclusion_mm
    if layout.count == 0:
        return

    centre_radii = np.hypot(layout.x_mm, layout.y_mm)
    assert float(centre_radii.max()) <= max(usable_radius_mm, 0.0) + 1e-9

    half_width_mm = die_width_mm / 2
    half_height_mm = die_height_mm / 2
    corner_radii = np.hypot(
        np.abs(layout.x_mm) + half_width_mm,
        np.abs(layout.y_mm) + half_height_mm,
    )
    assert float(corner_radii.max()) <= wafer_radius_mm + 1e-9


def test_layout_uses_plus_x_right_plus_y_up_and_orders_rows_bottom_to_top() -> None:
    die_width_mm, die_height_mm = 5.0, 5.0
    layout = layout_dies(Wafer(diameter_mm=300, die_size_mm=(die_width_mm, die_height_mm)))
    columns = math.floor(300 / die_width_mm)
    rows = math.floor(300 / die_height_mm)

    np.testing.assert_allclose(layout.x_mm, (layout.grid_x - (columns - 1) / 2) * die_width_mm)
    np.testing.assert_allclose(layout.y_mm, (layout.grid_y - (rows - 1) / 2) * die_height_mm)
    assert float(layout.y_mm.min()) == pytest.approx(-142.5)
    assert float(layout.y_mm.max()) == pytest.approx(142.5)
    assert bool((np.diff(layout.y_mm) >= 0).all())

    assert float(layout.x_mm.min()) == pytest.approx(-float(layout.x_mm.max()))
    assert float(layout.y_mm.min()) == pytest.approx(-float(layout.y_mm.max()))


def test_cp_test_sites_are_assigned_in_test_order_and_are_reproducible() -> None:
    wafer = Wafer(cp_sites=4)
    layout = layout_dies(wafer)
    repeated = layout_dies(wafer)

    np.testing.assert_array_equal(layout.test_site, np.arange(layout.count) % 4 + 1)
    np.testing.assert_array_equal(layout.test_site, repeated.test_site)
    assert set(layout.test_site.tolist()) == {1, 2, 3, 4}

    single_site = layout_dies(Wafer(cp_sites=1))
    assert set(single_site.test_site.tolist()) == {1}


def test_default_wat_layout_is_centre_plus_inner_orthogonal_plus_outer_diagonal() -> None:
    layout = layout_wat_sites(Wafer(diameter_mm=300, wat_sites=9))
    radius_mm = 150.0
    diagonal_mm = 0.9 * radius_mm / math.sqrt(2)

    assert layout.count == 9
    assert layout.site_number.tolist() == list(range(1, 10))
    assert [
        (round(float(x), 9), round(float(y), 9))
        for x, y in zip(layout.x_mm, layout.y_mm, strict=True)
    ] == [
        (0.0, 0.0),
        (75.0, 0.0),
        (0.0, 75.0),
        (-75.0, 0.0),
        (0.0, -75.0),
        (round(diagonal_mm, 9), round(diagonal_mm, 9)),
        (round(-diagonal_mm, 9), round(diagonal_mm, 9)),
        (round(-diagonal_mm, 9), round(-diagonal_mm, 9)),
        (round(diagonal_mm, 9), round(-diagonal_mm, 9)),
    ]


def test_wat_site_count_is_configurable() -> None:
    for site_count in (5, 9, 13, 21):
        layout = layout_wat_sites(Wafer(diameter_mm=300, wat_sites=site_count))
        assert layout.count == site_count


def test_wat_site_plans_are_nested_in_site_order() -> None:
    plans = {
        site_count: layout_wat_sites(Wafer(diameter_mm=300, wat_sites=site_count))
        for site_count in (5, 9, 13, 21)
    }

    for smaller, larger in ((5, 9), (9, 13), (13, 21)):
        np.testing.assert_array_equal(
            plans[smaller].x_mm, plans[larger].x_mm[: plans[smaller].count]
        )
        np.testing.assert_array_equal(
            plans[smaller].y_mm, plans[larger].y_mm[: plans[smaller].count]
        )


def _expected_wat_site_polar_plan(site_count: WatSiteCount) -> list[tuple[float, float | None]]:
    centre: list[tuple[float, float | None]] = [(0.0, None)]
    inner_orthogonal: list[tuple[float, float | None]] = [
        (0.5, float(angle)) for angle in (0, 90, 180, 270)
    ]
    outer_diagonal: list[tuple[float, float | None]] = [
        (0.9, float(angle)) for angle in (45, 135, 225, 315)
    ]
    outer_orthogonal: list[tuple[float, float | None]] = [
        (0.9, float(angle)) for angle in (0, 90, 180, 270)
    ]
    mid_ring: list[tuple[float, float | None]] = [
        (0.7, float(angle)) for angle in (0, 90, 180, 270, 45, 135, 225, 315)
    ]
    plans: dict[int, list[tuple[float, float | None]]] = {
        5: centre + inner_orthogonal,
        9: centre + inner_orthogonal + outer_diagonal,
        13: centre + inner_orthogonal + outer_diagonal + outer_orthogonal,
        21: centre + inner_orthogonal + outer_diagonal + outer_orthogonal + mid_ring,
    }
    return plans[site_count]


@pytest.mark.parametrize("site_count", [5, 9, 13, 21])
def test_wat_site_numbering_follows_the_ring_plan(site_count: WatSiteCount) -> None:
    layout = layout_wat_sites(Wafer(diameter_mm=300, wat_sites=site_count))
    wafer_radius_mm = 150.0

    assert layout.count == len(_expected_wat_site_polar_plan(site_count))
    for (radius_fraction, expected_angle), x, y in zip(
        _expected_wat_site_polar_plan(site_count), layout.x_mm, layout.y_mm, strict=True
    ):
        radius_mm = math.hypot(x, y)
        assert radius_mm == pytest.approx(radius_fraction * wafer_radius_mm)
        if expected_angle is None:
            assert x == 0.0
            assert y == 0.0
        else:
            angle = math.degrees(math.atan2(y, x)) % 360
            assert angle == pytest.approx(expected_angle)


def test_wat_site_positions_are_reproducible_and_scale_with_the_diameter() -> None:
    first = layout_wat_sites(Wafer(diameter_mm=300))
    second = layout_wat_sites(Wafer(diameter_mm=300))
    np.testing.assert_array_equal(first.x_mm, second.x_mm)
    np.testing.assert_array_equal(first.y_mm, second.y_mm)
    np.testing.assert_array_equal(first.site_number, second.site_number)

    half_size = layout_wat_sites(Wafer(diameter_mm=150))
    np.testing.assert_allclose(first.x_mm / 2, half_size.x_mm)
    np.testing.assert_allclose(first.y_mm / 2, half_size.y_mm)


@pytest.mark.parametrize("diameter_mm", [150, 200, 300])
@pytest.mark.parametrize("site_count", [5, 9, 13, 21])
def test_wat_sites_stay_inside_the_wafer(
    diameter_mm: WaferDiameterMm, site_count: WatSiteCount
) -> None:
    layout = layout_wat_sites(Wafer(diameter_mm=diameter_mm, wat_sites=site_count))
    wafer_radius_mm = diameter_mm / 2
    radii = np.hypot(layout.x_mm, layout.y_mm)
    outer_fraction = 0.5 if site_count == 5 else 0.9

    assert layout.x_mm[0] == 0.0
    assert layout.y_mm[0] == 0.0
    assert float(radii.max()) == pytest.approx(outer_fraction * wafer_radius_mm)
    assert bool((radii <= wafer_radius_mm).all())
    positions = {(float(x), float(y)) for x, y in zip(layout.x_mm, layout.y_mm, strict=True)}
    assert len(positions) == site_count


def test_wat_site_positions_ignore_edge_exclusion() -> None:
    narrow = layout_wat_sites(Wafer(diameter_mm=300, edge_exclusion_mm=3.0))
    wide = layout_wat_sites(Wafer(diameter_mm=300, edge_exclusion_mm=50.0))

    np.testing.assert_array_equal(narrow.x_mm, wide.x_mm)
    np.testing.assert_array_equal(narrow.y_mm, wide.y_mm)
