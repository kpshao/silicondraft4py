"""Serialising scenarios back to fully expanded YAML."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
from typing import Any

import yaml

from ..errors import ScenarioError
from ..i18n import _
from .models import Scenario
from .validation import validate_scenario_model


def scenario_document(scenario: Scenario) -> dict[str, Any]:
    """Return a YAML-ready mapping with every preset-expanded field written out.

    Explicit ``null`` values are kept: dropping them would let a preset fill
    the field back in when the saved file is loaded again.
    """
    return scenario.model_dump(mode="json")


def scenario_yaml(scenario: Scenario, *, include_preset: bool = True) -> str:
    """Return the fully expanded scenario as YAML text.

    ``include_preset=False`` writes ``preset: null`` so a later load does not
    re-merge preset defaults over the expanded fields. The YAML editor uses
    this mode so an edit that deletes a preset-derived section is authoritative.
    """
    document = scenario_document(scenario)
    if not include_preset:
        document["preset"] = None
    return yaml.safe_dump(document, sort_keys=False, allow_unicode=True)


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
    text = scenario_yaml(scenario)
    try:
        file_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OSError(
            _("cannot write scenario file {path}: {error}").format(path=file_path, error=exc)
        ) from exc
    return file_path


__all__ = ["save_scenario", "scenario_document", "scenario_yaml"]
