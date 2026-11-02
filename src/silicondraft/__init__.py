"""SiliconDraft public API."""

from importlib.metadata import PackageNotFoundError, version

from .api import export, generate
from .binning import BinDefinition, BinParetoEntry
from .dataset import CPLot, CPWafer, GenerationResult
from .errors import ExportError, ScenarioError, ValidationIssue
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
    "BinDefinition",
    "BinParetoEntry",
    "CPLot",
    "CPWafer",
    "ExportError",
    "GenerationResult",
    "Scenario",
    "ScenarioError",
    "ScenarioSummary",
    "ValidationIssue",
    "ValidationResult",
    "__version__",
    "export",
    "generate",
    "load_scenario",
    "scenario_schema",
    "validate_scenario",
]
