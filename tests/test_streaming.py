"""Streaming generation and export: bounded memory with identical artifacts."""

import gc
import json
import tracemalloc
from pathlib import Path
from typing import Any

import pytest
import yaml

from silicondraft import export, generate, generate_to_directory, load_scenario


def _write_scenario(
    tmp_path: Path,
    *,
    lots: int = 2,
    wafers_per_lot: int = 2,
    export_options: dict[str, Any] | None = None,
) -> Path:
    document: dict[str, Any] = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "lots": {
            "count": lots,
            "wafers_per_lot": wafers_per_lot,
            "start_date": "2026-01-05T08:00:00",
        },
        "patterns": [
            {
                "kind": "edge_low",
                "scope": "lot",
                "target": "yield",
                "amplitude": 0.3,
                "extent_mm": 25.0,
            },
            {
                "kind": "local_spot",
                "scope": "wafer",
                "target": "yield",
                "amplitude": -0.8,
                "radius_mm": 15.0,
            },
        ],
        "seed": 20260105,
    }
    if export_options is not None:
        document["export"] = export_options
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _manifest(directory: Path) -> dict[str, Any]:
    path = next(directory.glob("*_ground_truth_*.json"))
    with path.open(encoding="utf-8") as stream:
        manifest: dict[str, Any] = json.load(stream)
    return manifest


def _normalized_manifest(directory: Path) -> dict[str, Any]:
    manifest = _manifest(directory)
    manifest.pop("generated_at")
    manifest.pop("die_truth_files")
    for lot in manifest["lots"]:
        lot["die_truth_file"] = None
    for entry in manifest["linkage"]:
        entry["observed_r"] = round(entry["observed_r"], 9)
    return manifest


def test_streaming_export_matches_the_in_memory_export(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    generated = generate(scenario)
    full_paths = export(generated, tmp_path / "full")

    summary, stream_paths = generate_to_directory(scenario, tmp_path / "stream")

    assert summary.lot_count == len(generated.lots)
    assert summary.wafer_count == sum(len(lot.wafers) for lot in generated.lots)
    assert summary.die_count == generated.lots[0].die_count * len(generated.lots)
    assert summary.pass_count == sum(lot.pass_count for lot in generated.lots)
    assert [entry.wat_item for entry in summary.linkage_report] == [
        entry.wat_item for entry in generated.linkage_report
    ]
    for streamed, in_memory in zip(summary.linkage_report, generated.linkage_report, strict=True):
        assert streamed.target_r == in_memory.target_r
        assert streamed.achieved_r == in_memory.achieved_r
        assert streamed.sample_count == in_memory.sample_count
        assert streamed.observed_r == pytest.approx(in_memory.observed_r, abs=1e-10)

    assert _normalized_manifest(tmp_path / "stream") == _normalized_manifest(tmp_path / "full")
    assert len(stream_paths) == len(full_paths)
    assert {path.name.split("_die_truth_")[0] for path in stream_paths if path.suffix == ".gz"} == {
        path.name.split("_die_truth_")[0] for path in full_paths if path.suffix == ".gz"
    }

    full_truth = {
        path.name.split("_die_truth_")[0]: path.read_bytes()
        for path in full_paths
        if path.suffix == ".gz"
    }
    stream_truth = {
        path.name.split("_die_truth_")[0]: path.read_bytes()
        for path in stream_paths
        if path.suffix == ".gz"
    }
    assert stream_truth == full_truth


def _peak_memory(tmp_path: Path, lot_count: int) -> int:
    path = _write_scenario(
        tmp_path,
        lots=lot_count,
        wafers_per_lot=1,
        export_options={
            "cp_csv": False,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
    )
    scenario = load_scenario(path)
    gc.collect()
    tracemalloc.start()
    try:
        generate_to_directory(scenario, tmp_path / f"out-{lot_count}")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak


def test_streaming_memory_does_not_grow_linearly_with_lot_count(
    tmp_path: Path,
) -> None:
    one_lot = _peak_memory(tmp_path, 1)
    ten_lots = _peak_memory(tmp_path, 10)

    assert ten_lots < one_lot * 3
