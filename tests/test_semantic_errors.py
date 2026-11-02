import textwrap
from pathlib import Path

import pytest

from silicondraft import validate_scenario


def _write_scenario(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "scenario.yaml"
    path.write_text(textwrap.dedent(content), encoding="utf-8")
    return path


@pytest.mark.parametrize("diameter_mm", [150, 200, 300])
def test_die_larger_than_the_wafer_is_rejected_for_every_diameter(
    tmp_path: Path, diameter_mm: int
) -> None:
    oversize_mm = diameter_mm + 10.0
    path = _write_scenario(
        tmp_path,
        f"""
        schema_version: 1
        product:
          name: GEN55LOGIC
        wafer:
          diameter_mm: {diameter_mm}
          die_size_mm: [{oversize_mm}, {oversize_mm}]
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("DIE_GRID_DOES_NOT_FIT", "wafer.die_size_mm")
    ]


@pytest.mark.parametrize("diameter_mm", [150, 200, 300])
def test_edge_exclusion_at_the_radius_is_rejected_for_every_diameter(
    tmp_path: Path, diameter_mm: int
) -> None:
    path = _write_scenario(
        tmp_path,
        f"""
        schema_version: 1
        product:
          name: GEN55LOGIC
        wafer:
          diameter_mm: {diameter_mm}
          edge_exclusion_mm: {diameter_mm / 2}
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("EDGE_EXCLUSION_TOO_LARGE", "wafer.edge_exclusion_mm")
    ]


def test_unknown_pattern_item_reference_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: center_high
            target_item: CP_NOPE
            amplitude: 0.05
            radius_mm: 40.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_REFERENCE_UNKNOWN", "patterns[0].target_item")
    ]


def test_pattern_must_target_yield_or_an_item(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: radial_gradient
            amplitude: 0.1
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("PATTERN_TARGET_MISSING", "patterns[0]")
    ]


def test_pattern_targets_must_be_cp_items(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: center_high
            target_item: WAT_VTN
            amplitude: 0.05
            radius_mm: 40.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_PHASE_MISMATCH", "patterns[0].target_item")
    ]


def test_disabled_item_cannot_be_targeted(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_FRO
              enabled: false
        patterns:
          - kind: center_high
            target_item: CP_FRO
            amplitude: 0.05
            radius_mm: 40.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_DISABLED", "patterns[0].target_item")
    ]


def test_center_pattern_requires_a_radius(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: center_high
            target: yield
            amplitude: 0.05
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("PATTERN_EXTENT_MISSING", "patterns[0].radius_mm")
    ]


def test_directional_pattern_requires_positive_amplitude(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: edge_low
            target: yield
            amplitude: -0.08
            extent_mm: 25.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_PATTERN_AMPLITUDE", "patterns[0].amplitude")
    ]


def test_disabling_an_item_updates_summary_counts(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_FRO
              enabled: false
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert result.ok is True
    assert result.summary is not None
    assert result.summary.cp_items == 20
    assert result.summary.wat_items == 15
    assert result.summary.items_total == 35


def test_custom_item_can_be_added_and_referenced(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_CUSTOM
              phase: CP
              test_num: 2100
              unit: V
              typical: 1.0
              lsl: 0.5
              usl: 1.5
              distribution: normal
        patterns:
          - kind: center_high
            target_item: CP_CUSTOM
            amplitude: 0.05
            radius_mm: 40.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert result.ok is True
    assert result.summary is not None
    assert result.summary.cp_items == 22


def test_incomplete_custom_item_reports_each_missing_field(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_CUSTOM
              phase: CP
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert {(issue.code, issue.path) for issue in result.issues} == {
        ("ITEM_OVERRIDE_INCOMPLETE", "items.overrides[0].test_num"),
        ("ITEM_OVERRIDE_INCOMPLETE", "items.overrides[0].unit"),
        ("ITEM_OVERRIDE_INCOMPLETE", "items.overrides[0].typical"),
        ("ITEM_OVERRIDE_INCOMPLETE", "items.overrides[0].distribution"),
    }


def test_duplicate_test_num_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_CUSTOM
              phase: CP
              test_num: 2019
              unit: V
              typical: 1.0
              distribution: normal
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("DUPLICATE_TEST_NUM", "items.overrides[0].test_num")
    ]


def test_invalid_item_id_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: bad_id
              enabled: false
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_ITEM_ID", "items.overrides[0].id")
    ]


def test_custom_item_id_must_match_its_phase(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: WAT_CUSTOM
              phase: CP
              test_num: 2100
              unit: V
              typical: 1.0
              distribution: normal
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_PHASE_MISMATCH", "items.overrides[0].id")
    ]


def test_phase_of_an_existing_item_cannot_change(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_VTHN
              phase: WAT
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_PHASE_CHANGE", "items.overrides[0].phase")
    ]


def test_inverted_spec_limits_are_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_VTHN
              lsl: 0.50
              usl: 0.40
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_SPEC_LIMITS", "items.overrides[0]")
    ]


def test_linkage_references_must_exist(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        linkage:
          overrides:
            - wat: WAT_NOPE
              cp: CP_VTHN
              target_r: 0.8
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_REFERENCE_UNKNOWN", "linkage.overrides[0].wat")
    ]


def test_linkage_wat_side_must_reference_a_wat_item(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        linkage:
          overrides:
            - wat: CP_VTHN
              cp: CP_VTHN
              target_r: 0.8
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_PHASE_MISMATCH", "linkage.overrides[0].wat")
    ]


def test_linkage_cp_side_must_reference_a_cp_item(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        linkage:
          overrides:
            - wat: WAT_VTN
              cp: WAT_VTN
              target_r: 0.8
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_PHASE_MISMATCH", "linkage.overrides[0].cp")
    ]


def test_duplicate_linkage_pair_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        linkage:
          overrides:
            - wat: WAT_VTN
              cp: CP_VTHN
              target_r: 0.8
            - wat: WAT_VTN
              cp: CP_VTHN
              target_r: 0.7
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("DUPLICATE_LINKAGE_PAIR", "linkage.overrides[1]")
    ]


def test_lot_id_template_rejects_unknown_placeholders(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        lots:
          lot_id_template: "{product}-L{line}"
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_ID_TEMPLATE", "lots.lot_id_template")
    ]


def test_wafer_id_template_rejects_bad_format_specs(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        lots:
          wafer_id_template: "W{wafer:notaspec}"
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_ID_TEMPLATE", "lots.wafer_id_template")
    ]


def test_ring_pattern_requires_a_width(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: ring
            target: yield
            amplitude: 0.10
            radius_mm: 60.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("PATTERN_EXTENT_MISSING", "patterns[0].width_mm")
    ]


def test_edge_pattern_requires_an_extent(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: edge_low
            target: yield
            amplitude: 0.08
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("PATTERN_EXTENT_MISSING", "patterns[0].extent_mm")
    ]


def test_local_spot_allows_a_signed_amplitude(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: local_spot
            target: yield
            amplitude: -0.10
            radius_mm: 10.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert result.ok is True


def test_radial_gradient_rejects_zero_amplitude(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: radial_gradient
            target: yield
            amplitude: 0.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_PATTERN_AMPLITUDE", "patterns[0].amplitude")
    ]


def test_die_truth_requires_ground_truth_output(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        export:
          ground_truth: false
          include_die_truth: true
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("EXPORT_OPTION_CONFLICT", "export.include_die_truth")
    ]


def test_ring_allows_a_signed_amplitude(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: ring
            target: yield
            amplitude: -0.10
            radius_mm: 60.0
            width_mm: 10.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert result.ok is True


def test_custom_item_with_inverted_limits_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_CUSTOM
              phase: CP
              test_num: 2100
              unit: V
              typical: 1.0
              lsl: 1.5
              usl: 0.5
              distribution: normal
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_SPEC_LIMITS", "items.overrides[0]")
    ]


def test_non_finite_amplitude_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        patterns:
          - kind: radial_gradient
            target: yield
            amplitude: .nan
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_VALUE", "patterns[0].amplitude")
    ]


def test_non_finite_die_size_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        wafer:
          die_size_mm: [.inf, 5.0]
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("INVALID_VALUE", "wafer.die_size_mm[0]")
    ]


def test_die_must_fit_entirely_on_the_wafer(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        wafer:
          diameter_mm: 300
          die_size_mm: [290.0, 290.0]
          edge_exclusion_mm: 3.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("DIE_GRID_DOES_NOT_FIT", "wafer.die_size_mm")
    ]


def test_removing_an_item_updates_summary_counts(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_FRO
              remove: true
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert result.ok is True
    assert result.summary is not None
    assert result.summary.cp_items == 20
    assert result.summary.items_total == 35


def test_removed_item_cannot_be_targeted(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_FRO
              remove: true
        patterns:
          - kind: center_high
            target_item: CP_FRO
            amplitude: 0.05
            radius_mm: 40.0
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_REFERENCE_UNKNOWN", "patterns[0].target_item")
    ]


def test_removing_an_unknown_item_is_rejected(tmp_path: Path) -> None:
    path = _write_scenario(
        tmp_path,
        """
        schema_version: 1
        product:
          name: GEN55LOGIC
        items:
          overrides:
            - id: CP_NOPE
              remove: true
        seed: 1
        """,
    )

    result = validate_scenario(path)

    assert [(issue.code, issue.path) for issue in result.issues] == [
        ("ITEM_REFERENCE_UNKNOWN", "items.overrides[0].id")
    ]
