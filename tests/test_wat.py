"""WAT generation and export through the public API."""

import csv
import math
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from silicondraft import (
    GenerationResult,
    export,
    generate,
    load_scenario,
    validate_scenario,
)

_WAT_ITEM_IDS = [
    "WAT_VTN",
    "WAT_VTP",
    "WAT_IDSATN",
    "WAT_IDSATP",
    "WAT_IOFFN",
    "WAT_IOFFP",
    "WAT_SS",
    "WAT_DIBL",
    "WAT_TOX",
    "WAT_RSHN",
    "WAT_RSHP",
    "WAT_RC",
    "WAT_RVIA",
    "WAT_IGATE",
    "WAT_VBD",
]


def _write_scenario(
    tmp_path: Path,
    *,
    lots: int = 1,
    wafers_per_lot: int = 2,
    wat_sites: int = 9,
    die_size_mm: tuple[float, float] = (20.0, 20.0),
    linkage_overrides: list[dict[str, Any]] | None = None,
    item_overrides: list[dict[str, Any]] | None = None,
    export: dict[str, Any] | None = None,
    start_date: str | None = None,
    wat_to_cp_gap_min: float | None = None,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "wafer": {"die_size_mm": list(die_size_mm), "wat_sites": wat_sites},
        "lots": {"count": lots, "wafers_per_lot": wafers_per_lot},
        "seed": 20260105,
    }
    if start_date is not None:
        document["lots"]["start_date"] = start_date
    if wat_to_cp_gap_min is not None:
        document["lots"]["wat_to_cp_gap_min"] = wat_to_cp_gap_min
    if linkage_overrides is not None:
        document["linkage"] = {"overrides": linkage_overrides}
    if item_overrides is not None:
        document["items"] = {"overrides": item_overrides}
    export_options: dict[str, Any] = {
        "ground_truth": False,
        "include_die_truth": False,
    }
    if export is not None:
        export_options.update(export)
    document["export"] = export_options
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_generate_produces_wat_at_sites_not_dies(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, wafers_per_lot=2, wat_sites=9))

    result = generate(scenario)

    assert [item.id for item in result.wat_items] == _WAT_ITEM_IDS
    assert [item.test_num for item in result.wat_items] == list(range(1001, 1016))
    assert all(item.phase == "WAT" for item in result.wat_items)

    assert len(result.wat_lots) == 1
    wat_lot = result.wat_lots[0]
    cp_lot = result.lots[0]
    assert wat_lot.lot_id == cp_lot.lot_id
    assert [wafer.wafer_id for wafer in wat_lot.wafers] == [
        wafer.wafer_id for wafer in cp_lot.wafers
    ]

    radius_mm = 150.0
    diagonal_mm = 0.9 * radius_mm / math.sqrt(2)
    for wat_wafer, cp_wafer in zip(wat_lot.wafers, cp_lot.wafers, strict=True):
        assert wat_wafer.site_number.tolist() == list(range(1, 10))
        assert wat_wafer.x_mm.tolist() == pytest.approx(
            [0.0, 75.0, 0.0, -75.0, 0.0, diagonal_mm, -diagonal_mm, -diagonal_mm, diagonal_mm]
        )
        assert wat_wafer.y_mm.tolist() == pytest.approx(
            [0.0, 0.0, 75.0, 0.0, -75.0, diagonal_mm, diagonal_mm, -diagonal_mm, -diagonal_mm]
        )
        assert cp_wafer.die_count > wat_wafer.x_mm.size
        for item in result.wat_items:
            assert len(wat_wafer.values[item.id]) == 9
        assert set(wat_wafer.values) == set(_WAT_ITEM_IDS)
        assert set(cp_wafer.values).isdisjoint(_WAT_ITEM_IDS)
        assert all(cp_wafer.values[item.id].size == cp_wafer.die_count for item in result.items)


def test_wat_timestamps_precede_cp_on_the_configured_timeline(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=2,
            wafers_per_lot=2,
            start_date="2026-01-05T08:00:00",
            export={"wat_csv": False, "cp_csv": False},
        )
    )

    result = generate(scenario)

    for wat_lot, cp_lot in zip(result.wat_lots, result.lots, strict=True):
        for wat_wafer, cp_wafer in zip(wat_lot.wafers, cp_lot.wafers, strict=True):
            assert wat_wafer.tested_at.tzinfo is not None
            assert cp_wafer.tested_at.tzinfo is not None
            assert wat_wafer.tested_at < cp_wafer.tested_at
            assert cp_wafer.tested_at - wat_wafer.tested_at == timedelta(minutes=120)

    first_lot_start = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)
    assert result.wat_lots[0].wafers[0].tested_at == first_lot_start
    assert result.lots[0].wafers[1].tested_at == first_lot_start + timedelta(minutes=45 + 120)
    assert result.wat_lots[1].wafers[0].tested_at == first_lot_start + timedelta(hours=168)


def test_wat_to_cp_gap_must_be_positive(tmp_path: Path) -> None:
    result = validate_scenario(_write_scenario(tmp_path, wafers_per_lot=1, wat_to_cp_gap_min=0))

    assert result.ok is False
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("OUT_OF_RANGE", "lots.wat_to_cp_gap_min")
    ]


def test_timeline_defaults_anchor_to_the_generation_time(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=2,
            export={"wat_csv": False, "cp_csv": False},
        )
    )

    result = generate(scenario)

    for wat_wafer, cp_wafer in zip(result.wat_lots[0].wafers, result.lots[0].wafers, strict=True):
        assert wat_wafer.tested_at < cp_wafer.tested_at
        assert cp_wafer.tested_at - wat_wafer.tested_at == timedelta(minutes=120)


_DEFAULT_LINKAGE = {
    ("WAT_VTN", "CP_VTHN"): 0.80,
    ("WAT_VTN", "CP_IDDQ"): -0.50,
    ("WAT_VTN", "CP_FRO"): -0.45,
    ("WAT_VTP", "CP_VTHP"): 0.80,
    ("WAT_VTP", "CP_IDDQ"): -0.45,
    ("WAT_VTP", "CP_FRO"): -0.40,
    ("WAT_IDSATN", "CP_IONN"): 0.75,
    ("WAT_IDSATN", "CP_FRO"): 0.60,
    ("WAT_IDSATP", "CP_IONP"): 0.75,
    ("WAT_IDSATP", "CP_FRO"): 0.55,
    ("WAT_IOFFN", "CP_IOFFN"): 0.70,
    ("WAT_IOFFN", "CP_IDDQ"): 0.55,
    ("WAT_IOFFP", "CP_IOFFP"): 0.70,
    ("WAT_IOFFP", "CP_IDDQ"): 0.50,
    ("WAT_SS", "CP_IOFFN"): 0.50,
    ("WAT_SS", "CP_VDDMIN"): 0.45,
    ("WAT_DIBL", "CP_IOFFN"): 0.55,
    ("WAT_DIBL", "CP_VDDMIN"): 0.45,
    ("WAT_TOX", "CP_IGATE"): -0.60,
    ("WAT_TOX", "CP_VTHN"): 0.40,
    ("WAT_TOX", "CP_FRO"): -0.40,
    ("WAT_RSHN", "CP_RCONT"): 0.50,
    ("WAT_RSHP", "CP_RCONT"): 0.50,
    ("WAT_RC", "CP_RCONT"): 0.70,
    ("WAT_RC", "CP_CONT"): 0.50,
    ("WAT_RVIA", "CP_CONT"): 0.45,
    ("WAT_IGATE", "CP_IGATE"): 0.65,
    ("WAT_VBD", "CP_IGATE"): -0.45,
}


def _tolerance(target_r: float) -> float:
    return 0.05 if target_r >= 0.5 else 0.08


def test_default_linkage_report_lists_target_and_achieved_correlations(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    entries = {(entry.wat_item, entry.cp_item): entry for entry in result.linkage_report}
    assert set(entries) == set(_DEFAULT_LINKAGE)
    for pair, target_r in _DEFAULT_LINKAGE.items():
        entry = entries[pair]
        assert entry.target_r == pytest.approx(target_r)
        assert entry.factor in {
            "F_VT",
            "F_MOB",
            "F_TOX",
            "F_RC",
            "F_LEAK",
            "F_SC",
        }
        assert abs(entry.achieved_r - target_r) <= _tolerance(target_r)
        assert math.copysign(1.0, entry.achieved_r) == math.copysign(1.0, target_r)
        assert entry.sample_count == 9


_LINKAGE_DOC_ROW = re.compile(
    r"^\|\s*`(?P<wat>WAT_[A-Z0-9_]+)`\s*\|\s*`(?P<cp>CP_[A-Z0-9_]+)`\s*\|"
    r"\s*(?P<sign>[^|]+?)\s*\|\s*(?P<target>[0-9.]+)\s*\|"
)


def test_default_linkage_matches_the_catalog_documentation(tmp_path: Path) -> None:
    catalog_doc = Path(__file__).resolve().parents[1] / "docs/design/v1-test-item-catalog.md"
    documented: dict[tuple[str, str], float] = {}
    for line in catalog_doc.read_text(encoding="utf-8").splitlines():
        match = _LINKAGE_DOC_ROW.match(line)
        if match is None:
            continue
        sign_text = match["sign"].strip()
        sign = -1.0 if sign_text == "-" or ord(sign_text) == 0x2212 else 1.0
        documented[(match["wat"], match["cp"])] = sign * float(match["target"])

    assert len(documented) == 28

    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            export={"cp_csv": False, "wat_csv": False},
        )
    )
    result = generate(scenario)
    reported = {(entry.wat_item, entry.cp_item): entry.target_r for entry in result.linkage_report}

    assert reported.keys() == documented.keys()
    for pair, target_r in documented.items():
        assert reported[pair] == pytest.approx(target_r)


def test_default_linkage_observed_direction_at_default_size(tmp_path: Path) -> None:
    """At the schema default (1 lot x 25 wafers x 9 sites) sample r is noisy.

    Only 225 site-die pairs are available, so the strict tolerance is not
    statistically reachable; this test pins direction and rejects gross errors,
    while the 10-lot test below pins the strict tolerance on a large sample.
    """
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=1,
            wafers_per_lot=25,
            wat_sites=9,
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    assert len(result.linkage_report) == 28
    for entry in result.linkage_report:
        assert entry.sample_count == 25 * 9
        assert math.copysign(1.0, entry.observed_r) == math.copysign(1.0, entry.target_r), (
            f"{entry.wat_item}->{entry.cp_item}: target {entry.target_r:+.2f}, "
            f"observed {entry.observed_r:+.3f}"
        )
        assert abs(entry.observed_r - entry.target_r) <= 0.25


def test_default_linkage_observed_correlations_meet_tolerance_and_direction(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=10,
            wafers_per_lot=25,
            wat_sites=21,
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    entries = {(entry.wat_item, entry.cp_item): entry for entry in result.linkage_report}
    assert set(entries) == set(_DEFAULT_LINKAGE)
    for pair, target_r in _DEFAULT_LINKAGE.items():
        entry = entries[pair]
        assert entry.sample_count == 10 * 25 * 21
        assert abs(entry.observed_r - target_r) <= _tolerance(target_r), (
            f"{pair}: target {target_r:+.2f}, observed {entry.observed_r:+.3f}"
        )
        assert math.copysign(1.0, entry.observed_r) == math.copysign(1.0, target_r)


def test_linkage_overrides_support_negative_and_one_to_many_links(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=10,
            wafers_per_lot=25,
            wat_sites=21,
            linkage_overrides=[
                {"wat": "WAT_IDSATN", "cp": "CP_IONN", "target_r": -0.50},
                {"wat": "WAT_VTN", "cp": "CP_VIL", "target_r": 0.35},
                {"wat": "WAT_VTN", "cp": "CP_VOH", "target_r": -0.30},
            ],
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    entries = {(entry.wat_item, entry.cp_item): entry for entry in result.linkage_report}
    flipped = entries[("WAT_IDSATN", "CP_IONN")]
    assert flipped.target_r == pytest.approx(-0.50)
    assert flipped.achieved_r < 0
    assert abs(flipped.achieved_r - flipped.target_r) <= _tolerance(flipped.target_r)
    assert flipped.observed_r < 0
    assert abs(flipped.observed_r - flipped.target_r) <= _tolerance(flipped.target_r)

    for pair, target_r in (
        (("WAT_VTN", "CP_VIL"), 0.35),
        (("WAT_VTN", "CP_VOH"), -0.30),
    ):
        entry = entries[pair]
        assert entry.target_r == pytest.approx(target_r)
        assert abs(entry.achieved_r - target_r) <= _tolerance(target_r)
        assert math.copysign(1.0, entry.achieved_r) == math.copysign(1.0, target_r)
        assert math.copysign(1.0, entry.observed_r) == math.copysign(1.0, target_r)

    vtn_cp_items = {entry.cp_item for entry in result.linkage_report if entry.wat_item == "WAT_VTN"}
    assert vtn_cp_items == {"CP_VTHN", "CP_IDDQ", "CP_FRO", "CP_VIL", "CP_VOH"}


def test_linkage_report_sample_count_and_observed_correlation_follow_generated_data(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=2,
            wafers_per_lot=3,
            wat_sites=9,
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    for entry in result.linkage_report:
        assert entry.sample_count == 2 * 3 * 9
        assert -1.0 <= entry.observed_r <= 1.0
        assert math.isfinite(entry.observed_r)


def _observed_correlation(
    result: GenerationResult, wat_item: str, cp_item: str, site_count: int
) -> float:
    wat_values: list[np.ndarray] = []
    cp_values: list[np.ndarray] = []
    die_x = result.lots[0].wafers[0].x_mm
    die_y = result.lots[0].wafers[0].y_mm
    nearest: list[int] = []
    wat_x = result.wat_lots[0].wafers[0].x_mm
    wat_y = result.wat_lots[0].wafers[0].y_mm
    for site in range(site_count):
        distances = (die_x - wat_x[site]) ** 2 + (die_y - wat_y[site]) ** 2
        nearest.append(int(np.argmin(distances)))
    for wat_lot, cp_lot in zip(result.wat_lots, result.lots, strict=True):
        for wat_wafer, cp_wafer in zip(wat_lot.wafers, cp_lot.wafers, strict=True):
            wat_values.append(wat_wafer.values[wat_item])
            cp_values.append(cp_wafer.values[cp_item][nearest])
    wat_all = np.concatenate(wat_values)
    cp_all = np.concatenate(cp_values)
    return float(np.corrcoef(wat_all, cp_all)[0, 1])


def test_observed_correlation_uses_the_nearest_die_pairing(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=3,
            wafers_per_lot=4,
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    entry = next(
        entry
        for entry in result.linkage_report
        if (entry.wat_item, entry.cp_item) == ("WAT_VTN", "CP_VTHN")
    )
    expected = _observed_correlation(result, "WAT_VTN", "CP_VTHN", 9)

    assert entry.observed_r == pytest.approx(expected, abs=1e-12)


_WAT_CSV_HEADER = [
    "lot_id",
    "wafer_id",
    "wat_site",
    "site_x_mm",
    "site_y_mm",
    "test_num",
    "item_id",
    "value",
    "unit",
    "lsl",
    "usl",
    "pass",
    "timestamp",
]


def test_export_writes_one_long_wat_csv_per_lot(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=2,
            wafers_per_lot=2,
            export={"cp_csv": False, "wat_csv": True},
        )
    )
    result = generate(scenario)

    paths = export(result, tmp_path / "out")

    assert len(paths) == 2
    names = sorted(path.name for path in paths)
    pattern = re.compile(r"^GEN55LOGIC_GEN55LOGIC-L00[12]_WAT_\d{8}T\d{12}Z\.csv$")
    assert all(pattern.fullmatch(name) for name in names)
    timestamps = {re.search(r"\d{8}T\d{12}Z", name).group() for name in names}  # type: ignore[union-attr]
    assert len(timestamps) == 1

    for path, wat_lot in zip(sorted(paths), result.wat_lots, strict=True):
        with path.open(encoding="utf-8", newline="") as stream:
            rows = list(csv.reader(stream))
        assert rows[0] == _WAT_CSV_HEADER
        body = rows[1:]
        assert len(body) == (scenario.lots.wafers_per_lot * 9 * len(result.wat_items))

        row_index = 0
        for wat_wafer in wat_lot.wafers:
            for site_index in range(wat_wafer.site_count):
                for item in result.wat_items:
                    row = body[row_index]
                    row_index += 1
                    value = float(row[7])
                    expected_pass = (item.lsl is None or value >= item.lsl) and (
                        item.usl is None or value <= item.usl
                    )
                    assert row[0] == wat_lot.lot_id
                    assert row[1] == wat_wafer.wafer_id
                    assert int(row[2]) == int(wat_wafer.site_number[site_index])
                    assert float(row[3]) == pytest.approx(
                        float(wat_wafer.x_mm[site_index]), rel=1e-9
                    )
                    assert float(row[4]) == pytest.approx(
                        float(wat_wafer.y_mm[site_index]), rel=1e-9
                    )
                    assert int(row[5]) == item.test_num
                    assert row[6] == item.id
                    assert value == pytest.approx(
                        float(wat_wafer.values[item.id][site_index]), rel=1e-9
                    )
                    assert row[8] == item.unit
                    assert row[8].isascii()
                    assert (row[9] == "") is (item.lsl is None)
                    assert (row[10] == "") is (item.usl is None)
                    if item.lsl is not None:
                        assert float(row[9]) == pytest.approx(item.lsl)
                    if item.usl is not None:
                        assert float(row[10]) == pytest.approx(item.usl)
                    assert row[11] == ("1" if expected_pass else "0")
                    assert datetime.fromisoformat(row[12]) == wat_wafer.tested_at
        assert row_index == len(body)


def test_export_skips_wat_csv_when_disabled(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    paths = export(generate(scenario), tmp_path / "out")

    assert paths == ()


def test_same_scenario_and_seed_reproduce_wat_and_the_linkage_report(
    tmp_path: Path,
) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            lots=2,
            wafers_per_lot=2,
            start_date="2026-01-05T08:00:00",
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    first = generate(scenario)
    second = generate(scenario)

    assert first.linkage_report == second.linkage_report
    for first_lot, second_lot in zip(first.wat_lots, second.wat_lots, strict=True):
        for first_wafer, second_wafer in zip(first_lot.wafers, second_lot.wafers, strict=True):
            assert first_wafer.tested_at == second_wafer.tested_at
            for item in first.wat_items:
                np.testing.assert_array_equal(
                    first_wafer.values[item.id], second_wafer.values[item.id]
                )

    other = scenario.model_copy(update={"seed": scenario.seed + 1})
    third = generate(other)
    assert not np.array_equal(
        first.wat_lots[0].wafers[0].values["WAT_VTN"],
        third.wat_lots[0].wafers[0].values["WAT_VTN"],
    )


def test_linkage_override_to_a_bernoulli_item_is_rejected(tmp_path: Path) -> None:
    result = validate_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            linkage_overrides=[{"wat": "WAT_VTN", "cp": "CP_FUNC", "target_r": 0.50}],
        )
    )

    assert result.ok is False
    assert [issue.code for issue in result.issues] == ["LINKAGE_UNSUPPORTED_DISTRIBUTION"]
    assert result.issues[0].path == "linkage.overrides[0].cp"


def test_linkage_override_to_a_custom_wat_item_without_a_factor_is_rejected(
    tmp_path: Path,
) -> None:
    result = validate_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            item_overrides=[
                {
                    "id": "WAT_CUSTOM",
                    "phase": "WAT",
                    "test_num": 1100,
                    "unit": "V",
                    "typical": 1.0,
                    "distribution": "normal",
                }
            ],
            linkage_overrides=[{"wat": "WAT_CUSTOM", "cp": "CP_VTHN", "target_r": 0.50}],
        )
    )

    assert result.ok is False
    assert [issue.code for issue in result.issues] == ["LINKAGE_UNSUPPORTED_WAT_ITEM"]
    assert result.issues[0].path == "linkage.overrides[0].wat"


def test_changing_a_default_linked_item_to_bernoulli_is_rejected(
    tmp_path: Path,
) -> None:
    result = validate_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            item_overrides=[{"id": "CP_FRO", "distribution": "bernoulli"}],
        )
    )

    assert result.ok is False
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("LINKAGE_UNSUPPORTED_DISTRIBUTION", "items.overrides[0].distribution")
    ]


def test_removing_a_linked_cp_item_drops_its_default_pairs(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            item_overrides=[{"id": "CP_FRO", "remove": True}],
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    assert len(result.linkage_report) == 23
    assert all(entry.cp_item != "CP_FRO" for entry in result.linkage_report)
    assert "CP_FRO" not in {item.id for item in result.items}
    assert "CP_FRO" not in result.lots[0].wafers[0].values


def test_disabling_a_linked_wat_item_drops_its_default_pairs(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            wafers_per_lot=1,
            item_overrides=[{"id": "WAT_IDSATN", "enabled": False}],
            export={"cp_csv": False, "wat_csv": False},
        )
    )

    result = generate(scenario)

    assert all(entry.wat_item != "WAT_IDSATN" for entry in result.linkage_report)
    assert "WAT_IDSATN" not in {item.id for item in result.wat_items}
    assert all(
        "WAT_IDSATN" not in wat_wafer.values
        for wat_lot in result.wat_lots
        for wat_wafer in wat_lot.wafers
    )


def test_wat_site_count_follows_the_configured_plan(tmp_path: Path) -> None:
    for site_count in (5, 9, 13, 21):
        scenario = load_scenario(
            _write_scenario(
                tmp_path,
                wafers_per_lot=1,
                wat_sites=site_count,
                export={"wat_csv": False, "cp_csv": False},
            )
        )

        result = generate(scenario)

        wat_wafer = result.wat_lots[0].wafers[0]
        assert wat_wafer.site_number.size == site_count
        for item in result.wat_items:
            values = wat_wafer.values[item.id]
            assert values.size == site_count
            assert np.all(np.isfinite(values))
