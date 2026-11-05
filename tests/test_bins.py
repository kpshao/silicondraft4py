"""Configurable hard/soft bin tables through the public API."""

import csv
from pathlib import Path
from typing import Any

import pytest
import yaml
from pytestqt.qtbot import QtBot

from silicondraft import GenerationResult, ScenarioError, export, generate, load_scenario


def _write_scenario(
    tmp_path: Path,
    *,
    bins: dict[str, Any] | None = None,
    item_overrides: list[dict[str, Any]] | None = None,
    cp_csv_layout: str = "long",
    cp_stdf: bool = False,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "TEST55"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": 1, "wafers_per_lot": 1},
        "defects": {"enabled": False},
        "export": {
            "cp_stdf": cp_stdf,
            "cp_csv": True,
            "cp_csv_layout": cp_csv_layout,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": 20260105,
    }
    if bins is not None:
        document["bins"] = bins
    if item_overrides is not None:
        document["items"] = {"overrides": item_overrides}
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(tmp_path: Path, **kwargs: Any) -> tuple[GenerationResult, tuple[Path, ...]]:
    scenario = load_scenario(_write_scenario(tmp_path, **kwargs))
    result = generate(scenario)
    return result, export(result, tmp_path / "out", formats=("csv",))


def _long_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _read_blocks(path: Path) -> dict[str, list[list[str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    blocks: dict[str, list[list[str]]] = {}
    current: str | None = None
    for row in rows:
        if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]"):
            current = row[0]
            blocks[current] = []
        else:
            assert current is not None
            blocks[current].append(row)
    return blocks


def _parse_stdf(path: Path) -> list[tuple[str, dict[str, Any]]]:
    from pystdf.IO import Parser

    records: list[tuple[str, dict[str, Any]]] = []

    class _Sink:
        def after_send(self, data_source: object, data: tuple[Any, list[Any]]) -> None:
            record, values = data
            record_type = record.__class__
            records.append(
                (
                    record_type.__name__.upper(),
                    dict(zip(record_type.fieldNames, values, strict=True)),
                )
            )

    with path.open("rb") as stream:
        parser = Parser(inp=stream)
        parser.addSink(_Sink())
        parser.parse()
    return records


def test_custom_pass_bin_codes_flow_through_the_dataset_and_long_csv(tmp_path: Path) -> None:
    result, paths = _generate(
        tmp_path,
        bins={
            "hard": {"pass": {"code": 10, "name": "GOOD"}},
            "soft": {"pass": {"code": 1000, "name": "GOOD_SOFT"}},
        },
    )
    wafer = result.lots[0].wafers[0]

    assert set(wafer.hard_bin.tolist()) == {10}
    assert set(wafer.soft_bin.tolist()) == {1000}
    assert bool(wafer.passed.all())
    assert wafer.hard_bin_pareto[0].definition.number == 10
    assert wafer.soft_bin_pareto[0].definition.number == 1000

    rows = _long_rows(paths[0])
    assert rows
    for row in rows:
        assert row["hard_bin"] == "10"
        assert row["hard_bin_name"] == "GOOD"
        assert row["soft_bin"] == "1000"
        assert row["soft_bin_name"] == "GOOD_SOFT"
        assert row["die_pass"] == "1"


@pytest.mark.parametrize(
    ("bins", "path"),
    [
        ({"hard": {"functional": {"code": 2}}}, "bins.hard.functional.code"),
        ({"soft": {"iddq": {"code": 202}}}, "bins.soft.iddq.code"),
    ],
)
def test_duplicate_bin_codes_are_rejected(tmp_path: Path, bins: dict[str, Any], path: str) -> None:
    with pytest.raises(ScenarioError) as exc_info:
        load_scenario(_write_scenario(tmp_path, bins=bins))

    assert any(
        issue.code == "DUPLICATE_BIN_CODE" and issue.path == path for issue in exc_info.value.issues
    )


def test_unknown_bin_role_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError) as exc_info:
        load_scenario(_write_scenario(tmp_path, bins={"hard": {"nope": {"code": 9}}}))

    assert any(
        issue.code == "INVALID_VALUE" and issue.path.startswith("bins.hard")
        for issue in exc_info.value.issues
    )


@pytest.mark.parametrize("code", [0, 65_535, 65_536])
def test_bin_codes_outside_the_stdf_range_are_rejected(tmp_path: Path, code: int) -> None:
    with pytest.raises(ScenarioError) as exc_info:
        load_scenario(_write_scenario(tmp_path, bins={"hard": {"pass": {"code": code}}}))

    assert any(
        issue.code == "OUT_OF_RANGE" and issue.path == "bins.hard.pass.code"
        for issue in exc_info.value.issues
    )


def test_the_highest_non_missing_stdf_bin_code_is_allowed(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, bins={"hard": {"pass": {"code": 65_534}}})

    assert set(result.lots[0].wafers[0].hard_bin.tolist()) == {65_534}


def test_custom_cp_item_can_choose_its_soft_bin_role(tmp_path: Path) -> None:
    result, _ = _generate(
        tmp_path,
        item_overrides=[
            {
                "id": "CP_CUSTOM",
                "phase": "CP",
                "test_num": 2100,
                "unit": "V",
                "typical": 5.0,
                "lsl": 10.0,
                "usl": 20.0,
                "distribution": "normal",
                "soft_bin_role": "vth",
            }
        ],
    )
    wafer = result.lots[0].wafers[0]

    assert not wafer.passed.any()
    assert set(wafer.hard_bin.tolist()) == {2}
    assert set(wafer.soft_bin.tolist()) == {204}


def test_builtin_item_can_override_its_soft_bin_role(tmp_path: Path) -> None:
    result, _ = _generate(
        tmp_path,
        item_overrides=[{"id": "CP_FRO", "lsl": 1000.0, "usl": 1001.0, "soft_bin_role": "leakage"}],
    )
    wafer = result.lots[0].wafers[0]

    assert not wafer.passed.any()
    assert set(wafer.hard_bin.tolist()) == {2}
    assert set(wafer.soft_bin.tolist()) == {202}


def test_soft_bin_role_is_rejected_for_wat_items(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError) as exc_info:
        load_scenario(
            _write_scenario(
                tmp_path,
                item_overrides=[
                    {
                        "id": "WAT_CUSTOM",
                        "phase": "WAT",
                        "test_num": 1100,
                        "unit": "V",
                        "typical": 1.0,
                        "distribution": "normal",
                        "soft_bin_role": "vth",
                    }
                ],
            )
        )

    assert any(
        issue.code == "SOFT_BIN_ROLE_REQUIRES_CP"
        and issue.path == "items.overrides[0].soft_bin_role"
        for issue in exc_info.value.issues
    )


def test_bin_precedence_stays_semantic_when_codes_are_reordered(tmp_path: Path) -> None:
    result, paths = _generate(
        tmp_path,
        bins={
            "hard": {
                "parametric": {"code": 40},
                "continuity": {"code": 2},
            },
            "soft": {
                "continuity": {"code": 900},
                "other_parametric": {"code": 901},
            },
        },
        item_overrides=[
            {"id": "CP_CONT", "lsl": 10.0, "usl": 20.0},
            {"id": "CP_IONN", "lsl": 1e6, "usl": 2e6},
        ],
    )
    wafer = result.lots[0].wafers[0]

    assert set(wafer.hard_bin.tolist()) == {2}
    assert set(wafer.soft_bin.tolist()) == {900}
    assert not wafer.passed.any()

    rows = _long_rows(paths[0])
    assert {row["hard_bin_name"] for row in rows} == {"CONTINUITY_FAIL"}
    assert {row["soft_bin_name"] for row in rows} == {"CONTINUITY"}


def test_blocks_csv_lists_the_configured_bin_definitions(tmp_path: Path) -> None:
    _, paths = _generate(
        tmp_path,
        cp_csv_layout="blocks",
        bins={
            "hard": {
                "continuity": {
                    "code": 40,
                    "name": "CT_FAIL",
                    "description": "Contact failure",
                }
            },
            "soft": {
                "continuity": {
                    "code": 1201,
                    "name": "CONTACT",
                    "description": "Contact issue",
                }
            },
        },
        item_overrides=[{"id": "CP_CONT", "lsl": 10.0, "usl": 20.0}],
    )

    rows = [tuple(row) for row in _read_blocks(paths[0])["[BIN_DEFINITIONS]"][1:]]
    assert ("HARD", "40", "CT_FAIL", "F", "40", "Contact failure") in rows
    assert ("SOFT", "1201", "CONTACT", "F", "40", "Contact issue") in rows


def test_stdf_uses_the_configured_bin_codes_and_names(tmp_path: Path) -> None:
    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            cp_stdf=True,
            bins={
                "hard": {"continuity": {"code": 40, "name": "CT_FAIL"}},
                "soft": {"continuity": {"code": 1201, "name": "CONTACT"}},
            },
            item_overrides=[{"id": "CP_CONT", "lsl": 10.0, "usl": 20.0}],
        )
    )
    paths = export(generate(scenario), tmp_path / "out", formats=("stdf",))

    records = _parse_stdf(paths[0])
    hard = [fields for name, fields in records if name == "HBR"]
    soft = [fields for name, fields in records if name == "SBR"]
    assert [(int(fields["HBIN_NUM"]), fields["HBIN_NAM"]) for fields in hard] == [(40, "CT_FAIL")]
    assert [(int(fields["SBIN_NUM"]), fields["SBIN_NAM"]) for fields in soft] == [(1201, "CONTACT")]


def test_wafer_map_uses_the_configured_bin_names(qtbot: QtBot, tmp_path: Path) -> None:
    from silicondraft.gui.wafer_map import WaferMapView

    scenario = load_scenario(
        _write_scenario(
            tmp_path,
            bins={
                "hard": {"continuity": {"code": 40, "name": "CT_FAIL"}},
                "soft": {"continuity": {"code": 1201, "name": "CONTACT"}},
            },
            item_overrides=[{"id": "CP_CONT", "lsl": 10.0, "usl": 20.0}],
        )
    )
    view = WaferMapView()
    qtbot.addWidget(view)
    view.set_result(generate(scenario))

    hard_tooltip = view.die_tooltip(0)
    assert "hard_bin=40" in hard_tooltip
    assert "CT_FAIL" in hard_tooltip
    assert view.die_color(0).name() != "#9e9e9e"

    assert view.set_color_mode("soft_bin")
    soft_tooltip = view.die_tooltip(0)
    assert "soft_bin=1201" in soft_tooltip
    assert "CONTACT" in soft_tooltip
    assert view.die_color(0).name() != "#9e9e9e"
