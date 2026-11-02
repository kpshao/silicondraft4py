"""SiliconDraft public API."""

from importlib.metadata import PackageNotFoundError, version

from .errors import ScenarioError, ValidationIssue
from .scenario import (
    Scenario,
    ScenarioSummary,
    ValidationResult,
    load_scenario,
    scenario_schema,
    validate_scenario,
)

try:
    __version__ = version("silicondraft")
except PackageNotFoundError:  # pragma: no cover - running from an unpacked tree
    __version__ = "0.0.0"

__all__ = [
    "Scenario",
    "ScenarioError",
    "ScenarioSummary",
    "ValidationIssue",
    "ValidationResult",
    "__version__",
    "load_scenario",
    "scenario_schema",
    "validate_scenario",
]
