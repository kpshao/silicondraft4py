"""SiliconDraft public API."""

from importlib.metadata import PackageNotFoundError, version

from .api import StreamingSummary, export, generate, generate_to_directory
from .binning import BinDefinition, BinParetoEntry
from .dataset import (
    CPLot,
    CPWafer,
    GenerationResult,
    LinkageReportEntry,
    PatternReport,
    WatLot,
    WatWafer,
)
from .defects import DefectCluster
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
    "DefectCluster",
    "ExportError",
    "GenerationResult",
    "LinkageReportEntry",
    "PatternReport",
    "Scenario",
    "ScenarioError",
    "ScenarioSummary",
    "StreamingSummary",
    "ValidationIssue",
    "ValidationResult",
    "WatLot",
    "WatWafer",
    "__version__",
    "export",
    "generate",
    "generate_to_directory",
    "load_scenario",
    "scenario_schema",
    "validate_scenario",
]
