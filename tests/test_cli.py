import csv
import json
import logging
import re
from pathlib import Path

import pytest

from silicondraft import __version__
from silicondraft.cli import main
from silicondraft.errors import ExportError
from silicondraft.scenario.models import MAX_SEED


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
    seed: int = 20260105,
    start_date: str | None = None,
) -> Path:
    lines = [
        "schema_version: 1",
        "product:",
        "  name: GEN55LOGIC",
        "lots:",
        "  wafers_per_lot: 1",
    ]
    if start_date is not None:
        lines.append(f'  start_date: "{start_date}"')
    lines.extend(
        [
            "export:",
            "  wat_csv: false",
            f"  cp_stdf: {'true' if cp_stdf else 'false'}",
            f"  cp_csv: {'true' if cp_csv else 'false'}",
        ]
    )
    if cp_csv_layout is not None:
        lines.append(f"  cp_csv_layout: {cp_csv_layout}")
    lines.append(f"seed: {seed}")
    path = tmp_path / "tiny.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_generate_dry_run_validates_without_writing_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert "scenario: OK" in captured.out
    assert "dry-run: seed=20260105" in captured.out
    assert "dry-run: formats=stdf, csv" in captured.out
    assert "dry-run: per-die truth=on" in captured.out
    assert "dry-run: overwrite=off" in captured.out
    assert "dry-run: no files written" in captured.out
    assert not output_dir.exists()


def test_generate_dry_run_reports_the_effective_run_options(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    exit_code = main(
        [
            "generate",
            "-c",
            str(scenario_path),
            "-o",
            str(tmp_path / "out"),
            "--dry-run",
            "--seed",
            "42",
            "--formats",
            "stdf",
            "--no-die-truth",
            "--overwrite",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "dry-run: seed=42" in captured.out
    assert "dry-run: formats=stdf" in captured.out
    assert "dry-run: per-die truth=off" in captured.out
    assert "dry-run: overwrite=on" in captured.out
    assert not (tmp_path / "out").exists()


def test_generate_dry_run_does_not_create_a_requested_output_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(output_dir), "--dry-run"])

    assert exit_code == 0
    assert "dry-run" in capsys.readouterr().out
    assert not output_dir.exists()


def test_generate_dry_run_rejects_an_invalid_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = tmp_path / "invalid.yaml"
    scenario_path.write_text(
        "schema_version: 1\n"
        "product:\n"
        "  name: GEN55LOGIC\n"
        "wafer:\n"
        "  edge_exclusion_mm: 200\n"
        "seed: 20260105\n",
        encoding="utf-8",
    )

    exit_code = main(["generate", "-c", str(scenario_path), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "EDGE_EXCLUSION_TOO_LARGE" in captured.err


def test_generate_requires_output_without_dry_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["generate", "-c", str(scenario_path)])

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "--output" in captured.err
    assert "--dry-run" in captured.err


def test_generate_log_level_emits_english_logs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    with caplog.at_level(logging.INFO, logger="silicondraft.cli"):
        exit_code = main(
            [
                "generate",
                "-c",
                str(scenario_path),
                "-o",
                str(tmp_path / "out"),
                "--log-level",
                "INFO",
                "--lang",
                "zh",
            ]
        )

    assert exit_code == 0
    assert capsys.readouterr().err == ""
    messages = [record.getMessage() for record in caplog.records]
    assert any("generated" in message and "lot" in message for message in messages)
    assert all(
        "生成" not in message  # Chinese "generated" must not leak into logs
        for message in messages
    )


def test_generate_default_log_level_does_not_emit_info_logs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    with caplog.at_level(logging.INFO, logger="silicondraft.cli"):
        exit_code = main(["generate", "-c", str(scenario_path), "-o", str(tmp_path / "out")])

    assert exit_code == 0
    assert capsys.readouterr().err == ""
    assert not [record for record in caplog.records if record.levelno == logging.INFO]


def test_generate_rejects_an_unknown_log_level(
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
                "--log-level",
                "LOUD",
            ]
        )

    captured = capsys.readouterr()
    assert exc_info.value.code == 1
    assert "invalid choice" in captured.err


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


def test_generate_subprocess_smoke(tmp_path: Path) -> None:
    import subprocess
    import sys

    from pystdf.Importer import ImportSTDF

    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "subprocess-out"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "silicondraft",
            "generate",
            "-c",
            str(scenario_path),
            "-o",
            str(output_dir),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "generated: 1 lot(s), 1 wafer(s), 2700 die(s)" in completed.stdout
    assert "exported:" in completed.stdout
    stdf_path = next(output_dir.glob("*.stdf"))
    names = [record.__class__.__name__.upper() for record, _ in ImportSTDF(str(stdf_path))]
    assert names[0] == "FAR"
    assert names[-1] == "MRR"
    assert "PRR" in names


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


def test_generate_maps_generation_failures_to_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario_path = _write_tiny_scenario(tmp_path)

    def _fail_generation(*args: object, **kwargs: object) -> tuple[object, tuple[Path, ...]]:
        raise RuntimeError("unexpected engine failure")

    monkeypatch.setattr("silicondraft.cli.generate_to_directory", _fail_generation)

    exit_code = main(["generate", "-c", str(scenario_path), "-o", str(tmp_path / "out")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "generation failed: unexpected engine failure" in captured.err


def _cp_csv_bytes(directory: Path) -> bytes:
    return next(directory.glob("*_CP_*.csv")).read_bytes()


def test_generate_seed_option_overrides_the_scenario_seed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    scenario = _write_tiny_scenario(scenario_dir, seed=11, start_date="2026-01-05T08:00:00")
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit = _write_tiny_scenario(explicit_dir, seed=42, start_date="2026-01-05T08:00:00")

    default_out = tmp_path / "default"
    override_out = tmp_path / "override"
    explicit_out = tmp_path / "explicit-out"
    for scenario_path, output_dir, extra in (
        (scenario, default_out, []),
        (scenario, override_out, ["--seed", "42"]),
        (explicit, explicit_out, []),
    ):
        arguments = ["generate", "-c", str(scenario_path), "-o", str(output_dir), *extra]
        assert main(arguments) == 0
        capsys.readouterr()

    assert _cp_csv_bytes(override_out) == _cp_csv_bytes(explicit_out)
    assert _cp_csv_bytes(default_out) != _cp_csv_bytes(override_out)

    override_manifest = json.loads(
        next(override_out.glob("*ground_truth*.json")).read_text(encoding="utf-8")
    )
    default_manifest = json.loads(
        next(default_out.glob("*ground_truth*.json")).read_text(encoding="utf-8")
    )
    assert override_manifest["seed"] == 42
    assert override_manifest["scenario"]["seed"] == 42
    assert default_manifest["seed"] == 11


def test_generate_rejects_an_invalid_seed_override(
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
                "--seed=-1",
            ]
        )

    assert exc_info.value.code == 1
    assert f"seed must be between 0 and {MAX_SEED}" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


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


def test_generate_overwrite_flag_replaces_existing_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    scenario_path = _write_tiny_scenario(tmp_path)
    output_dir = tmp_path / "out"
    fixed = datetime(2026, 1, 5, 8, 0, tzinfo=UTC)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:  # type: ignore[override]
            return fixed if tz is None else fixed.astimezone(tz)  # type: ignore[arg-type]

    monkeypatch.setattr("silicondraft.api.datetime", _FixedDatetime)
    base = ["generate", "-c", str(scenario_path), "-o", str(output_dir)]

    assert main(base) == 0
    capsys.readouterr()

    assert main(base) == 3
    captured = capsys.readouterr()
    assert "already exists" in captured.err
    assert "--overwrite" in captured.err

    assert main([*base, "--overwrite"]) == 0
    capsys.readouterr()


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
