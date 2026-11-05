"""CLI language selection smoke tests."""

import csv
import json
from pathlib import Path

import pytest

from silicondraft.cli import main


def _write_valid_scenario(tmp_path: Path) -> Path:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\n",
        encoding="utf-8",
    )
    return path


def test_english_is_the_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write_valid_scenario(tmp_path)

    exit_code = main(["validate", "-c", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "scenario: OK" in captured.out
    assert "场景" not in captured.out


def test_lang_zh_prints_chinese_messages(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write_valid_scenario(tmp_path)

    exit_code = main(["--lang", "zh", "validate", "-c", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "场景：通过" in captured.out  # noqa: RUF001
    assert "die 总数" in captured.out
    assert "scenario: OK" not in captured.out


def test_lang_zh_translates_engine_issues(
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

    exit_code = main(["--lang", "zh", "validate", "-c", str(path)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "场景：无效" in captured.err  # noqa: RUF001
    assert "未知测试项目" in captured.err
    assert "ITEM_REFERENCE_UNKNOWN" in captured.err


def test_lang_zh_keeps_export_identifiers_english(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario_path = tmp_path / "tiny.yaml"
    scenario_path.write_text(
        "schema_version: 1\n"
        "product:\n"
        "  name: GEN55LOGIC\n"
        "lots:\n"
        "  wafers_per_lot: 1\n"
        "export:\n"
        "  wat_csv: false\n"
        "seed: 20260105\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "out"

    exit_code = main(["--lang", "zh", "generate", "-c", str(scenario_path), "-o", str(output_dir)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "已生成" in captured.out
    paths = list(output_dir.glob("*.csv"))
    assert len(paths) == 1
    with paths[0].open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    header = rows[0]
    assert header == [
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
    first_row = dict(zip(header, rows[1], strict=True))
    assert first_row["hard_bin_name"].isascii()
    assert first_row["soft_bin_name"].isascii()
    assert first_row["item_id"].startswith("CP_")
    assert first_row["unit"].isascii()

    manifests = list(output_dir.glob("*_ground_truth_*.json"))
    assert len(manifests) == 1
    manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    assert manifest["product"]["name"] == "GEN55LOGIC"
    assert manifest["manifest_version"] == 1
