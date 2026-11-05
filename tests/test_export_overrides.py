"""Tests for the per-run export overrides used by the GUI dialog."""

from pathlib import Path
from typing import cast

import pytest
import yaml

from silicondraft import ExportError, export, generate, load_scenario
from silicondraft.scenario.models import CsvLayout


def _write_scenario(tmp_path: Path) -> Path:
    document: dict[str, object] = {
        "schema_version": 1,
        "product": {"name": "TEST55"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": 1, "wafers_per_lot": 2},
        "export": {
            "cp_csv": True,
            "cp_csv_layout": "long",
            "wat_csv": False,
            "ground_truth": True,
            "include_die_truth": True,
        },
        "seed": 20260105,
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_export_overrides_layout_and_truth_output(tmp_path: Path) -> None:
    result = generate(load_scenario(_write_scenario(tmp_path)))
    out_dir = tmp_path / "out"

    paths = export(
        result,
        out_dir,
        cp_csv_layout="blocks",
        include_ground_truth=True,
        include_die_truth=False,
    )

    names = sorted(path.name for path in paths)
    assert sum("_CP_" in name for name in names) == 2
    assert all("_W01_CP_" in name or "_W02_CP_" in name for name in names if "_CP_" in name)
    assert not any(name.endswith(".csv.gz") for name in names)
    assert any(name.endswith(".json") for name in names)


def test_export_refuses_to_replace_existing_files_without_overwrite(tmp_path: Path) -> None:
    result = generate(load_scenario(_write_scenario(tmp_path)))
    out_dir = tmp_path / "out"

    first = export(result, out_dir)
    assert first
    with pytest.raises(ExportError, match="already exists"):
        export(result, out_dir)

    replaced = export(result, out_dir, overwrite=True)
    assert len(replaced) == len(first)


def test_stdf_export_also_honours_the_overwrite_option(tmp_path: Path) -> None:
    result = generate(load_scenario(_write_scenario(tmp_path)))
    out_dir = tmp_path / "out"

    first = export(result, out_dir, formats=("stdf",))
    assert first
    with pytest.raises(ExportError, match="already exists"):
        export(result, out_dir, formats=("stdf",))
    assert export(result, out_dir, formats=("stdf",), overwrite=True)


def test_export_rejects_an_unknown_cp_csv_layout(tmp_path: Path) -> None:
    result = generate(load_scenario(_write_scenario(tmp_path)))
    out_dir = tmp_path / "out"

    with pytest.raises(ExportError, match="unsupported CP CSV layout"):
        export(result, out_dir, cp_csv_layout=cast(CsvLayout, "spreadsheet"))

    assert not out_dir.exists()
