"""Progress reporting and cancellation for the generation engine."""

import threading
from pathlib import Path

import pytest
import yaml

from silicondraft import (
    GenerationCancelled,
    GenerationProgress,
    generate,
    load_scenario,
)


def _write_scenario(tmp_path: Path) -> Path:
    document = {
        "schema_version": 1,
        "product": {"name": "GEN55LOGIC"},
        "wafer": {
            "diameter_mm": 150,
            "die_size_mm": [20.0, 20.0],
            "edge_exclusion_mm": 3.0,
        },
        "lots": {"count": 2, "wafers_per_lot": 2},
        "export": {
            "cp_csv": False,
            "wat_csv": False,
            "ground_truth": False,
            "include_die_truth": False,
        },
        "seed": 20260105,
    }
    path = tmp_path / "scenario.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_generate_reports_cumulative_wafer_progress(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    events: list[GenerationProgress] = []

    result = generate(scenario, progress=events.append)

    assert [event.completed_wafers for event in events] == [1, 2, 3, 4]
    assert [event.total_wafers for event in events] == [4, 4, 4, 4]
    assert [(event.lot_number, event.wafer_number) for event in events] == [
        (1, 1),
        (1, 2),
        (2, 1),
        (2, 2),
    ]
    assert events[0].lot_id == "GEN55LOGIC-L001"
    assert events[0].wafer_id == "W01"
    assert len(result.lots) == 2


def test_generate_cancels_between_wafers(tmp_path: Path) -> None:
    scenario = load_scenario(_write_scenario(tmp_path))
    cancel = threading.Event()
    events: list[GenerationProgress] = []

    def progress(event: GenerationProgress) -> None:
        events.append(event)
        cancel.set()

    with pytest.raises(GenerationCancelled):
        generate(scenario, progress=progress, should_cancel=cancel.is_set)

    assert len(events) == 1
