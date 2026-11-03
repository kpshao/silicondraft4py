from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from silicondraft import scenario_schema, validate_scenario

SPEC_EXAMPLE = """\
schema_version: 1

product:
  name: GEN55LOGIC
  device_family: cmos_logic
  process_node: "55nm"
  fab: FAB-A
  test_program: GEN55LOGIC_CP

wafer:
  diameter_mm: 300
  die_size_mm: [5.0, 5.0]
  edge_exclusion_mm: 3.0
  notch: down
  cp_sites: 4
  wat_sites: 9

lots:
  count: 1
  wafers_per_lot: 25
  lot_id_template: "{product}-L{lot:03d}"
  wafer_id_template: "W{wafer:02d}"
  start_date: "2026-01-05T08:00:00"
  wat_to_cp_gap_min: 120
  cp_duration_min_per_wafer: 45
  lot_interval_hours: 168

items:
  preset: generic_cmos_logic_55nm
  overrides: []

patterns:
  - kind: edge_low
    scope: lot
    target: yield
    amplitude: 0.08
    extent_mm: 25.0
  - kind: center_high
    scope: wafer
    target_item: CP_FRO
    amplitude: 0.05
    radius_mm: 40.0

linkage:
  overrides:
    - wat: WAT_VTN
      cp: CP_VTHN
      target_r: 0.80

export:
  cp_stdf: true
  cp_csv: true
  cp_csv_layout: long
  wat_csv: true
  ground_truth: true
  include_die_truth: true
  encoding: utf-8

seed: 20260105

metadata:
  author: ""
  note: "quick preset"
"""


def test_spec_example_passes_validation(tmp_path: Path) -> None:
    path = tmp_path / "scenario.yaml"
    path.write_text(SPEC_EXAMPLE, encoding="utf-8")

    result = validate_scenario(path)

    assert result.ok is True
    assert result.summary is not None
    assert result.summary.dies_per_wafer == 2700
    assert result.summary.items_total == 36


def test_spec_example_passes_the_json_schema() -> None:
    document = yaml.safe_load(SPEC_EXAMPLE)

    Draft202012Validator(scenario_schema()).validate(document)
