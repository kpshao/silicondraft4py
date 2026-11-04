"""SiliconDraft public API."""

from importlib.metadata import PackageNotFoundError, version

from .api import (
    GenerationProgress,
    StreamingSummary,
    export,
    generate,
    generate_to_directory,
)
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
from .errors import ExportError, GenerationCancelled, ScenarioError, ValidationIssue
from .scenario import (
    PRESET_NAMES,
    Scenario,
    ScenarioSummary,
    ValidationResult,
    load_scenario,
    save_scenario,
    scenario_from_preset,
    scenario_schema,
    validate_scenario,
    validate_scenario_text,
)

try:
    __version__ = version("silicondraft")
except PackageNotFoundError:  # pragma: no cover - running from an unpacked tree
    __version__ = "0.0.0"

__all__ = [
    "PRESET_NAMES",
    "BinDefinition",
    "BinParetoEntry",
    "CPLot",
    "CPWafer",
    "DefectCluster",
    "ExportError",
    "GenerationCancelled",
    "GenerationProgress",
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
    "save_scenario",
    "scenario_from_preset",
    "scenario_schema",
    "validate_scenario",
    "validate_scenario_text",
]
