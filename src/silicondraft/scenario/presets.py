"""Built-in scenario presets.

A preset is a scenario fragment: the loader deep-merges it under the explicit
YAML document, so scalar and mapping fields override the preset while lists
(such as ``patterns``) replace it wholesale. Presets never set ``seed`` or
product identity beyond a sensible default name, so every run stays explicit
about reproducibility.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, get_args

from .models import ScenarioPreset

#: Preset names derived from the schema literal, so the two never drift apart.
PRESET_NAMES: tuple[str, ...] = tuple(get_args(ScenarioPreset))

_PRESETS: dict[str, dict[str, Any]] = {
    "quick": {
        "product": {"name": "GEN55LOGIC"},
        "lots": {"count": 1, "wafers_per_lot": 25},
        "patterns": [],
    },
    "trend": {
        "product": {"name": "GEN55LOGIC"},
        "lots": {
            "count": 5,
            "wafers_per_lot": 25,
            "start_date": "2026-01-05T08:00:00",
            "wat_to_cp_gap_min": 120.0,
            "cp_duration_min_per_wafer": 45.0,
            "lot_interval_hours": 168.0,
        },
        "patterns": [],
    },
    "demo": {
        "product": {"name": "GEN55LOGIC"},
        "lots": {"count": 1, "wafers_per_lot": 25},
        "patterns": [
            {
                "kind": "edge_low",
                "scope": "lot",
                "target": "yield",
                "amplitude": 0.35,
                "extent_mm": 25.0,
            },
            {
                "kind": "center_high",
                "scope": "lot",
                "target_item": "CP_FRO",
                "amplitude": 0.05,
                "radius_mm": 40.0,
            },
            {
                "kind": "ring",
                "scope": "lot",
                "target": "yield",
                "amplitude": -0.25,
                "radius_mm": 60.0,
                "width_mm": 10.0,
            },
            {
                "kind": "local_spot",
                "scope": "wafer",
                "target": "yield",
                "amplitude": -0.90,
                "radius_mm": 15.0,
                "center_mm": [40.0, -20.0],
            },
        ],
        "linkage": {
            "overrides": [
                {"wat": "WAT_VTN", "cp": "CP_VTHN", "target_r": 0.85},
                {"wat": "WAT_IDSATN", "cp": "CP_IONN", "target_r": 0.82},
                {"wat": "WAT_IOFFN", "cp": "CP_IOFFN", "target_r": 0.75},
            ]
        },
    },
}


assert set(_PRESETS) == set(PRESET_NAMES), "preset definitions must match ScenarioPreset"


def expand_preset(document: object) -> object:
    """Merge a named preset under an explicit scenario document."""
    if not isinstance(document, dict):
        return document
    name = document.get("preset")
    if not isinstance(name, str) or name not in _PRESETS:
        return document
    return _deep_merge(deepcopy(_PRESETS[name]), document)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        current = base.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            base[key] = _deep_merge(current, value)
        else:
            base[key] = value
    return base
