from pathlib import Path

import pytest

from silicondraft import load_scenario, validate_scenario
from silicondraft.errors import ScenarioError


def test_unknown_field_is_reported_with_its_path(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\nunknown_section: {}\n",
        encoding="utf-8",
    )

    result = validate_scenario(path)

    assert result.ok is False
    assert result.summary is None
    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("UNKNOWN_FIELD", "unknown_section")
    ]


def test_load_scenario_raises_with_the_same_locatable_issues(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct: {}\nseed: 20260105\n",
        encoding="utf-8",
    )

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario(path)

    assert [(issue.code, issue.path) for issue in exc_info.value.issues] == [
        ("REQUIRED", "product.name")
    ]
    assert "product.name" in str(exc_info.value)
