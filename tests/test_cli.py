import csv
import json
import re
from pathlib import Path

import pytest

from silicondraft import __version__
from silicondraft.cli import main
from silicondraft.errors import ExportError


def _write_valid_scenario(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\n",
        encoding="utf-8",
    )
    return path


def test_validate_prints_summary_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_valid_scenario(tmp_path)

    exit_code = main(["validate", "-c", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "scenario: OK" in captured.out
    assert "dies_per_wafer: 2700" in captured.out
    assert "cp_items: 21" in captured.out
    assert "wat_items: 15" in captured.out
    assert "items_total: 36" in captured.out


def test_validate_prints_locatable_errors_and_exits_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\n"
        "product:\n"
        "  name: GEN55LOGIC\n"
        "patterns:\n"
        "  - kind: center_high\n"
        "    target_item: CP_NOPE\n"
        "    amplitude: 0.05\n"
        "    radius_mm: 40.0\n"
        "seed: 20260105\n",
        encoding="utf-8",
    )

    exit_code = main(["validate", "-c", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.out == ""
    assert "scenario: INVALID" in captured.err
    assert "patterns[0].target_item" in captured.err
    assert "ITEM_REFERENCE_UNKNOWN" in captured.err


def test_schema_prints_a_usable_json_schema(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["schema"])

    captured = capsys.readouterr()
    assert exit_code == 0
    schema = json.loads(captured.out)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert "schema_version" in schema["properties"]
    assert captured.err == ""


def test_version_prints_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["version"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out == f"silicondraft {__version__}\n"
    assert captured.err == ""


def test_missing_command_prints_help_and_exits_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main([])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "usage:" in captured.out


def test_invalid_arguments_exit_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["validate"])

    assert exc_info.value.code == 1
    assert "usage:" in capsys.readouterr().err


def _write_tiny_scenario(
    tmp_path: Path,
    *,
    cp_csv_layout: str | None = None,
    cp_stdf: bool = True,
    cp_csv: bool = True,
) -> Path:
    lines = [
        "schema_version: 1",
        "product:",
        "  name: GEN55LOGIC",
        "lots:",
        "  wafers_per_lot: 1",
        "export:",
        "  wat_csv: false",
        f"  cp_stdf: {'true' if cp_stdf else 'false'}",
        f"  cp_csv: {'true' if cp_csv else 'false'}",
    ]
    if cp_csv_layout is not None:
        lines.append(f"  cp_csv_layout: {cp_csv_layout}")
    lines.append("seed: 20260105")
    path = tmp_path / "tiny.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_generate_writes_multiblock_cp_csv_and_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path, cp_csv_layout="blocks")
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    paths = list(output_dir.glob("*.csv"))
    assert len(paths) == 1
    assert re.fullmatch(r"GEN55LOGIC_GEN55LOGIC-L001_W01_CP_\d{8}T\d{12}Z\.csv", paths[0].name)

    with paths[0].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    markers = [
        row[0] for row in rows if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]")
    ]
    assert markers == ["[METADATA]", "[TEST_ITEMS]", "[BIN_DEFINITIONS]", "[TEST_DATA]"]

    data_start = rows.index(["[TEST_DATA]"])
    assert rows[data_start + 1][:8] == [
        "die_x_mm",
        "die_y_mm",
        "grid_x",
        "grid_y",
        "test_site",
        "hard_bin",
        "soft_bin",
        "pass",
    ]
    assert "lot_id" not in rows[data_start + 1]
    assert "wafer_id" not in rows[data_start + 1]
    assert len(rows) - (data_start + 2) == 2700


def test_generate_writes_long_cp_csv_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    paths = list(output_dir.glob("*.csv"))
    assert len(paths) == 1
    assert re.fullmatch(r"GEN55LOGIC_GEN55LOGIC-L001_CP_\d{8}T\d{12}Z\.csv", paths[0].name)

    with paths[0].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == [
        "lot_id",
        "wafer_id",
        "die_x_mm",
        "die_y_mm",
        "grid_x",
        "grid_y",
        "test_site",
        "hard_bin",
        "hard_bin_name",
        "soft_bin",
        "soft_bin_name",
        "die_pass",
        "test_num",
        "item_id",
        "value",
        "unit",
        "lsl",
        "usl",
        "pass",
        "timestamp",
    ]
    assert len(rows) - 1 == 2700 * 21


def test_generate_writes_a_parseable_stdf_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from pystdf.Importer import ImportSTDF

    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    stdf_paths = list(output_dir.glob("*.stdf"))
    assert len(stdf_paths) == 1
    assert re.fullmatch(r"GEN55LOGIC_GEN55LOGIC-L001_CP_\d{8}T\d{12}Z\.stdf", stdf_paths[0].name)
    assert f"exported: {stdf_paths[0]}" in captured.out
    records = ImportSTDF(str(stdf_paths[0]))
    names = [record.__class__.__name__.upper() for record, _ in records]
    assert names[0] == "FAR"
    assert "MIR" in names
    assert names[-1] == "MRR"


def test_generate_honours_cp_stdf_false(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    scenario_path = _write_tiny_scenario(tmp_path, cp_stdf=False)
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert not list(output_dir.glob("*.stdf"))
    assert list(output_dir.glob("*.csv"))


def test_generate_maps_stdf_export_failures_to_exit_three(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path, cp_csv=False)

    def _fail_stdf(*args: object, **kwargs: object) -> tuple[Path, ...]:
        raise ExportError("STDF disk is full")

    monkeypatch.setattr("silicondraft.api.export_cp_stdf", _fail_stdf)

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(tmp_path / "out")])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "export failed: STDF disk is full" in captured.err


def test_generate_formats_selects_the_requested_artifacts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    stdf_dir = tmp_path / "stdf"
    assert (
        main(
            [
                "generate",
                "-c",
                str(scenario_path),
                "-o",
                str(stdf_dir),
                "--formats",
                "stdf",
            ]
        )
        == 0
    )
    assert list(stdf_dir.glob("*.stdf"))
    assert not list(stdf_dir.glob("*.csv"))

    csv_dir = tmp_path / "csv"
    assert main(["generate", "-c", str(scenario_path), "-o", str(csv_dir), "--formats", "csv"]) == 0
    assert list(csv_dir.glob("*.csv"))
    assert not list(csv_dir.glob("*.stdf"))
    assert capsys.readouterr().err == ""


def test_generate_formats_can_override_a_scenario_switch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path, cp_stdf=False)
    output_dir = tmp_path / "out"

    exit_code = main(
        ["generate", "-c", str(scenario_path), "-o", str(output_dir), "--formats", "stdf"]
    )

    assert exit_code == 0
    assert capsys.readouterr().err == ""
    assert list(output_dir.glob("*.stdf"))
    assert not list(output_dir.glob("*.csv"))


def test_generate_rejects_unknown_formats(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                "generate",
                "-c",
                str(scenario_path),
                "-o",
                str(tmp_path / "out"),
                "--formats",
                "stdf,xml",
            ]
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "unsupported export format(s): xml; supported: stdf, csv" in captured.err
    assert not (tmp_path / "out").exists()


def test_generate_writes_both_cp_csv_layouts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path, cp_csv_layout="both")
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    names = sorted(path.name for path in output_dir.glob("*.csv"))
    assert len(names) == 2
    assert any(
        re.fullmatch(r"GEN55LOGIC_GEN55LOGIC-L001_CP_\d{8}T\d{12}Z\.csv", name) for name in names
    )
    assert any(
        re.fullmatch(r"GEN55LOGIC_GEN55LOGIC-L001_W01_CP_\d{8}T\d{12}Z\.csv", name)
        for name in names
    )


def test_generate_prints_the_linkage_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(tmp_path / "out")])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    lines = [line for line in captured.out.splitlines() if line.startswith("linkage: ")]
    assert len(lines) == 28
    vtn_pair = next(line for line in lines if "WAT_VTN -> CP_VTHN" in line)
    assert "target_r=0.800" in vtn_pair
    assert "achieved_r=" in vtn_pair
    assert "observed_r=" in vtn_pair


def test_generate_maps_export_failures_to_exit_three(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    def _fail_export(*args: object, **kwargs: object) -> tuple[Path, ...]:
        raise ExportError("disk is full")

    monkeypatch.setattr("silicondraft.cli.generate_to_directory", _fail_export)

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(tmp_path / "out")])

    captured = capsys.readouterr()
    assert exit_code == 3
    assert "export failed: disk is full" in captured.err


def test_generate_rejects_invalid_config_before_writing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = tmp_path / "invalid.yaml"
    scenario_path.write_text(
        "schema_version: 1\n"
        "product:\n"
        "  name: GEN55LOGIC\n"
        "wafer:\n"
        "  edge_exclusion_mm: 200\n"
        "lots:\n"
        "  wafers_per_lot: 1\n"
        "seed: 20260105\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "scenario: INVALID" in captured.err
    assert "EDGE_EXCLUSION_TOO_LARGE" in captured.err
    assert not output_dir.exists()


def test_generate_no_die_truth_flag_skips_per_die_truth(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(
        ["generate", "-c", str(scenario_path), "-o", str(output_dir), "--no-die-truth"]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert not list(output_dir.glob("*.csv.gz"))
    manifests = list(output_dir.glob("*_ground_truth_*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["die_truth_files"] == []
