"""Ground truth manifest and per-die truth export through the public API."""

import csv
import gzip
import json
import math
from pathlib import Path
from typing import Any

import yaml

from silicondraft import GenerationResult, export, generate, load_scenario

_DIE_TRUTH_HEADER = [
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
]
_TIMESTAMP_PATTERN = r"\d{8}T\d{12}Z"


def _write_scenario(
    tmp_path: Path,
    *,
    patterns: list[dict[str, Any]] | None = None,
    wafers_per_lot: int = 2,
    export_options: dict[str, Any] | None = None,
    seed: int = 20260105,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "lots": {"wafers_per_lot": wafers_per_lot},
        "patterns": patterns or [],
        "seed": seed,
    }
    if export_options is not None:
        document["export"] = export_options
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _generate(tmp_path: Path, **kwargs: Any) -> GenerationResult:
    return generate(load_scenario(_write_scenario(tmp_path, **kwargs)))


def _export(tmp_path: Path, result: GenerationResult, **kwargs: Any) -> tuple[Path, ...]:
    return export(result, tmp_path / "out", **kwargs)


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


def _read_die_truth(path: Path) -> list[list[str]]:
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        return list(csv.reader(stream))


def _manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        manifest: dict[str, Any] = json.load(stream)
    return manifest


def _one_of(paths: tuple[Path, ...], suffix: str) -> Path:
    matches = [path for path in paths if path.name.endswith(suffix)]
    assert len(matches) == 1
    return matches[0]


def test_manifest_contains_the_run_summary(tmp_path: Path) -> None:
    patterns = [
        {
            "kind": "edge_low",
            "scope": "lot",
            "target": "yield",
            "amplitude": 0.5,
            "extent_mm": 25.0,
        },
        {
            "kind": "center_high",
            "scope": "lot",
            "target_item": "CP_FRO",
            "amplitude": 0.2,
            "radius_mm": 40.0,
        },
        {
            "kind": "edge_low",
            "scope": "wafer",
            "target": "yield",
            "amplitude": 0.8,
            "extent_mm": 20.0,
        },
    ]
    result = _generate(tmp_path, patterns=patterns, wafers_per_lot=2)
    paths = _export(tmp_path, result)

    manifest_path = _one_of(paths, ".json")
    manifest = _manifest(manifest_path)
    cp_blocks = [_read_blocks(path) for path in sorted(Path(tmp_path / "out").glob("*_CP_*.csv"))]

    assert manifest["manifest_version"] == 1
    assert manifest["engine_version"]
    assert manifest["scenario_schema_version"] == 1
    assert manifest["seed"] == result.scenario.seed
    assert manifest["scenario"]["product"]["name"] == "GEN55LOGIC"
    assert len(manifest["scenario"]["patterns"]) == 3
    assert manifest["scenario_sha256"] == dict(cp_blocks[0]["[METADATA]"][1:])["scenario_sha256"]

    assert manifest["summary"]["lot_count"] == 1
    assert manifest["summary"]["wafer_count"] == 2
    assert manifest["summary"]["die_count"] == sum(
        wafer.die_count for lot in result.lots for wafer in lot.wafers
    )
    assert manifest["summary"]["pass_count"] == sum(
        wafer.pass_count for lot in result.lots for wafer in lot.wafers
    )

    lot_entry = manifest["lots"][0]
    assert lot_entry["lot_id"] == result.lots[0].lot_id
    assert set(lot_entry["latent_factor_means"]) == {
        "F_VT",
        "F_MOB",
        "F_TOX",
        "F_RC",
        "F_LEAK",
        "F_SC",
    }
    assert all(math.isfinite(value) for value in lot_entry["latent_factor_means"].values())
    assert len(lot_entry["wafers"]) == 2
    for entry, wafer, blocks in zip(
        lot_entry["wafers"], result.lots[0].wafers, cp_blocks, strict=True
    ):
        metadata = dict(blocks["[METADATA]"][1:])
        assert entry["wafer_id"] == wafer.wafer_id
        assert entry["die_count"] == wafer.die_count
        assert entry["pass_count"] == wafer.pass_count
        assert entry["yield"] == float(metadata["yield"])
        assert entry["defects"]["failure_count"] == int(wafer.defect_failure.sum())

    assert [pattern["id"] for pattern in manifest["patterns"]] == [
        "pattern_1",
        "pattern_2",
        "pattern_3",
    ]
    for pattern in manifest["patterns"]:
        assert set(pattern["contribution"]) == {
            "realized_failures",
            "item_shift_die_count",
            "mean_relative_item_shift",
            "recovery_probability_sum",
        }
    assert manifest["patterns"][0]["contribution"]["realized_failures"] > 0
    assert manifest["patterns"][0]["contribution"]["item_shift_die_count"] == 0
    assert manifest["patterns"][1]["contribution"]["mean_relative_item_shift"] > 0
    assert manifest["patterns"][1]["contribution"]["item_shift_die_count"] > 0
    assert len(manifest["patterns"][2]["affected_wafers"]) == 1

    assert len(manifest["outlier_wafers"]) == 1
    outlier = manifest["outlier_wafers"][0]
    assert outlier["patterns"] == ["pattern_3"]
    assert outlier["wafer_id"] in {"W01", "W02"}
    outlier_flags = [entry["outlier"] for entry in lot_entry["wafers"]]
    assert sum(outlier_flags) == 1

    assert manifest["random_defects"]["enabled"] is True
    assert manifest["random_defects"]["model"] == "clustered"
    assert manifest["random_defects"]["failure_rate"] == 0.01
    assert manifest["random_defects"]["target_items"] == ["CP_FUNC", "CP_SCAN"]
    assert manifest["random_defects"]["failure_count"] > 0
    assert manifest["random_defects"]["observed_failure_rate"] == (
        manifest["random_defects"]["failure_count"] / manifest["summary"]["die_count"]
    )

    assert len(manifest["linkage"]) == len(result.linkage_report)
    first_linkage = manifest["linkage"][0]
    assert first_linkage["target_r"] == result.linkage_report[0].target_r
    assert first_linkage["achieved_r"] == result.linkage_report[0].achieved_r

    assert len(manifest["die_truth_files"]) == 1
    assert (tmp_path / "out" / manifest["die_truth_files"][0]).is_file()


def test_die_truth_matches_the_cp_csv_and_records_pattern_ids(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        wafers_per_lot=1,
        patterns=[
            {
                "kind": "edge_low",
                "scope": "lot",
                "target": "yield",
                "amplitude": 0.6,
                "extent_mm": 25.0,
            }
        ],
    )
    paths = _export(tmp_path, result)

    die_truth_path = _one_of(paths, ".csv.gz")
    rows = _read_die_truth(die_truth_path)
    assert rows[0] == _DIE_TRUTH_HEADER
    assert len(rows) - 1 == result.lots[0].wafers[0].die_count

    cp_path = next(path for path in paths if "_CP_" in path.name)
    test_data = _read_blocks(cp_path)["[TEST_DATA]"]
    cp_rows = {(int(row[2]), int(row[3])): row for row in test_data[1:]}

    pattern_found = False
    for row in rows[1:]:
        key = (int(row[4]), int(row[5]))
        cp_row = cp_rows[key]
        assert row[0] == result.lots[0].lot_id
        assert row[1] == result.lots[0].wafers[0].wafer_id
        assert row[7] == cp_row[7]
        assert row[8] == cp_row[5]
        assert row[9] == cp_row[6]
        assert all(math.isfinite(float(value)) for value in row[10:16])
        if float(row[2]) ** 2 + float(row[3]) ** 2 >= (300 / 2 - 3 - 25) ** 2:
            assert "pattern_1" in row[16].split("|")
            pattern_found = True
        else:
            assert row[16] == ""
    assert pattern_found


def test_overlapping_patterns_record_their_own_contributions(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        wafers_per_lot=1,
        patterns=[
            {
                "kind": "center_low",
                "scope": "lot",
                "target": "yield",
                "amplitude": 0.6,
                "radius_mm": 150.0,
            },
            {
                "kind": "edge_low",
                "scope": "lot",
                "target": "yield",
                "amplitude": 0.6,
                "extent_mm": 40.0,
            },
        ],
    )
    paths = _export(tmp_path, result)

    manifest = _manifest(_one_of(paths, ".json"))
    first, second = manifest["patterns"]
    assert first["id"] == "pattern_1"
    assert second["id"] == "pattern_2"
    assert first["contribution"]["realized_failures"] > 0
    assert second["contribution"]["realized_failures"] > 0
    assert first["affected_die_count"] > 0
    assert second["affected_die_count"] > 0

    rows = _read_die_truth(_one_of(paths, ".csv.gz"))
    overlap_ids = [
        row[16] for row in rows[1:] if 115.0 <= math.hypot(float(row[2]), float(row[3])) <= 140.0
    ]
    assert overlap_ids
    assert all(value == "pattern_1|pattern_2" for value in overlap_ids)


def test_no_die_truth_is_available_as_an_export_override(tmp_path: Path) -> None:
    result = _generate(tmp_path, wafers_per_lot=1)

    paths = _export(tmp_path, result, include_die_truth=False)

    assert not any(path.name.endswith(".csv.gz") for path in paths)
    manifest = _manifest(_one_of(paths, ".json"))
    assert manifest["die_truth_files"] == []
    assert manifest["lots"][0]["die_truth_file"] is None


def test_disabling_ground_truth_writes_only_csv(tmp_path: Path) -> None:
    result = _generate(
        tmp_path,
        wafers_per_lot=1,
        export_options={"ground_truth": False, "include_die_truth": False},
    )

    paths = _export(tmp_path, result)

    assert paths
    assert all(path.name.endswith(".csv") for path in paths)


def test_ground_truth_is_reproducible_except_for_generated_at(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path, wafers_per_lot=2))
    first = generate(scenario)
    second = generate(scenario)

    first_paths = export(first, tmp_path / "first")
    second_paths = export(second, tmp_path / "second")

    first_manifest = _manifest(_one_of(first_paths, ".json"))
    second_manifest = _manifest(_one_of(second_paths, ".json"))
    for manifest in (first_manifest, second_manifest):
        manifest.pop("generated_at")
        manifest.pop("die_truth_files")
        for lot in manifest["lots"]:
            lot["die_truth_file"] = None
    assert first_manifest == second_manifest

    first_truth = _one_of(first_paths, ".csv.gz").read_bytes()
    second_truth = _one_of(second_paths, ".csv.gz").read_bytes()
    assert first_truth == second_truth
