from pathlib import Path

import pytest

from silicondraft import load_scenario
from silicondraft.errors import ScenarioError


def test_minimal_scenario_loads_with_defaults(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(
        "schema_version: 1\nproduct:\n  name: GEN55LOGIC\nseed: 20260105\n",
        encoding="utf-8",
    )

    scenario = load_scenario(path)

    assert scenario.schema_version == 1
    assert scenario.product.name == "GEN55LOGIC"
    assert scenario.product.test_program == ""
    assert scenario.wafer.diameter_mm == 300
    assert scenario.wafer.die_size_mm == (5.0, 5.0)
    assert scenario.wafer.edge_exclusion_mm == 3.0
    assert scenario.wafer.notch == "down"
    assert scenario.wafer.cp_sites == 4
    assert scenario.wafer.wat_sites == 9
    assert scenario.lots.count == 1
    assert scenario.lots.wafers_per_lot == 25
    assert scenario.items.preset == "generic_cmos_logic_55nm"
    assert scenario.items.overrides == []
    assert scenario.patterns == []
    assert scenario.defects.enabled is True
    assert scenario.defects.model == "clustered"
    assert scenario.defects.failure_rate == 0.01
    assert scenario.defects.cluster_size == 8
    assert scenario.defects.cluster_radius_mm == 10.0
    assert scenario.defects.target_items == ["CP_FUNC", "CP_SCAN"]
    assert scenario.linkage.overrides == []
    assert scenario.export.cp_stdf is True
    assert scenario.export.cp_csv is True
    assert scenario.export.wat_csv is True
    assert scenario.export.ground_truth is True
    assert scenario.export.include_die_truth is True
    assert scenario.export.encoding == "utf-8"
    assert scenario.seed == 20260105
    assert scenario.metadata.author == ""
    assert scenario.metadata.note == ""


def test_load_scenario_rejects_semantic_errors(tmp_path: Path) -> None:
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
        "seed: 1\n",
        encoding="utf-8",
    )

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario(path)

    assert [(issue.code, issue.path) for issue in exc_info.value.issues] == [
        ("ITEM_REFERENCE_UNKNOWN", "patterns[0].target_item")
    ]
