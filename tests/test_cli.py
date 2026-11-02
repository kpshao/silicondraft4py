import csv
import json
from pathlib import Path

import pytest

from silicondraft import __version__
from silicondraft.cli import main


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


def _write_tiny_scenario(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.yaml"
    path.write_text(
        "schema_version: 1\n"
        "product:\n"
        "  name: GEN55LOGIC\n"
        "lots:\n"
        "  wafers_per_lot: 1\n"
        "seed: 20260105\n",
        encoding="utf-8",
    )
    return path


def test_generate_writes_cp_csv_and_exits_zero(
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
    with paths[0].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2700
    assert {"lot_id", "wafer_id", "hard_bin", "CP_VTHN"} <= set(rows[0])


def test_generate_maps_export_failures_to_exit_three(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    def _fail_export(*args: object, **kwargs: object) -> tuple[Path, ...]:
        raise RuntimeError("disk is full")

    monkeypatch.setattr("silicondraft.cli.export", _fail_export)

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
