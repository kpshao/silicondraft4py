"""Saving scenarios back to fully expanded YAML."""

from pathlib import Path

import pytest
import yaml

from silicondraft import ScenarioError, load_scenario, save_scenario
from silicondraft.scenario.loader import parse_scenario
from silicondraft.scenario.models import Product, Scenario, Wafer


def test_saved_example_scenario_round_trips(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "examples" / "tiny.yaml"
    scenario = load_scenario(source)
    target = tmp_path / "saved.yaml"

    save_scenario(scenario, target)

    assert load_scenario(target) == scenario


def test_saved_preset_scenario_round_trips_as_expanded_yaml(tmp_path: Path) -> None:
    scenario = parse_scenario({"schema_version": 1, "preset": "quick", "seed": 7})
    target = tmp_path / "quick.yaml"

    save_scenario(scenario, target)

    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["preset"] == "quick"
    assert document["seed"] == 7
    assert document["product"]["name"] == "GEN55LOGIC"
    assert document["lots"]["count"] == 1
    assert document["lots"]["wafers_per_lot"] == 25
    assert load_scenario(target) == scenario


def test_explicit_nulls_still_override_preset_defaults_after_round_trip(
    tmp_path: Path,
) -> None:
    scenario = parse_scenario(
        {
            "schema_version": 1,
            "preset": "trend",
            "seed": 3,
            "lots": {"start_date": None},
        }
    )
    assert scenario.lots.start_date is None
    target = tmp_path / "trend.yaml"

    save_scenario(scenario, target)

    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    assert document["lots"]["start_date"] is None
    assert load_scenario(target) == scenario


def test_save_rejects_an_invalid_scenario(tmp_path: Path) -> None:
    scenario = Scenario(
        schema_version=1,
        product=Product(name="GEN55LOGIC"),
        wafer=Wafer(diameter_mm=150, edge_exclusion_mm=100.0),
        seed=1,
    )

    with pytest.raises(ScenarioError) as excinfo:
        save_scenario(scenario, tmp_path / "invalid.yaml")

    assert any(issue.code == "EDGE_EXCLUSION_TOO_LARGE" for issue in excinfo.value.issues)
    assert not (tmp_path / "invalid.yaml").exists()
