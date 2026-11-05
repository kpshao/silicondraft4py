"""Tests for the hidden ``--smoke-test`` entry point used by packaging."""

from pathlib import Path

import pytest

from silicondraft.gui.app import SmokeTestOptions, parse_smoke_test_options


def test_parse_smoke_options_ignores_a_normal_launch() -> None:
    arguments = ["SiliconDraft", "--lang", "zh"]

    options, remaining = parse_smoke_test_options(arguments)

    assert options is None
    assert remaining == arguments


def test_parse_smoke_options_extracts_paths_and_keeps_qt_arguments() -> None:
    arguments = [
        "SiliconDraft",
        "--smoke-test",
        "--scenario",
        "scenario.yaml",
        "--output",
        "out",
        "-platform",
        "offscreen",
    ]

    options, remaining = parse_smoke_test_options(arguments)

    assert options == SmokeTestOptions(
        scenario=Path("scenario.yaml"),
        output=Path("out"),
    )
    assert remaining == ["SiliconDraft", "-platform", "offscreen"]


def test_parse_smoke_options_requires_a_scenario_and_output() -> None:
    with pytest.raises(SystemExit):
        parse_smoke_test_options(["SiliconDraft", "--smoke-test", "--scenario", "s.yaml"])
