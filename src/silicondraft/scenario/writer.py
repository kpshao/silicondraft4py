"""Serialising scenarios back to fully expanded YAML."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import Any

import yaml

from ..errors import ScenarioError
from .models import Scenario
from .validation import validate_scenario_model


def scenario_document(scenario: Scenario) -> dict[str, Any]:
    """Return a YAML-ready mapping with every preset-expanded field written out.

    Explicit ``null`` values are kept: dropping them would let a preset fill
    the field back in when the saved file is loaded again.
    """
    return scenario.model_dump(mode="json")


def save_scenario(scenario: Scenario, path: str | PathLike[str]) -> Path:
    """Validate ``scenario`` and write it as fully expanded YAML.

    Saving expands presets so the file remains reproducible even if a preset
    definition changes later. Invalid scenarios raise :class:`ScenarioError`
    before any file is written.
    """
    validation = validate_scenario_model(scenario)
    if not validation.ok:
        raise ScenarioError(validation.issues)
    file_path = Path(path)
    document = scenario_document(scenario)
    text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    try:
        file_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"cannot write scenario file {file_path}: {exc}") from exc
    return file_path


__all__ = ["save_scenario", "scenario_document"]
