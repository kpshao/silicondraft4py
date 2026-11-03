"""Typed scenario model for SiliconDraft scenario v1.

The model is the structural contract for scenario YAML. Semantic rules that span
fields (wafer fit, item references, template placeholders) live in
``silicondraft.scenario.validation`` and produce stable, locatable issues.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
Correlation = Annotated[float, Field(ge=-1.0, le=1.0, allow_inf_nan=False)]

Distribution = Literal["normal", "lognormal", "bernoulli"]
TestPhase = Literal["CP", "WAT"]
PatternKind = Literal[
    "center_high",
    "center_low",
    "edge_high",
    "edge_low",
    "ring",
    "radial_gradient",
    "local_spot",
]
PatternScope = Literal["lot", "wafer"]
PatternCombine = Literal["add", "multiply"]
ExportEncoding = Literal["utf-8", "utf-8-sig"]
WaferDiameterMm = Literal[150, 200, 300]
WatSiteCount = Literal[5, 9, 13, 21]

#: Extent fields each pattern kind requires; the JSON Schema cannot express this.
PATTERN_REQUIRED_EXTENTS: dict[str, tuple[str, ...]] = {
    "center_high": ("radius_mm",),
    "center_low": ("radius_mm",),
    "edge_high": ("extent_mm",),
    "edge_low": ("extent_mm",),
    "ring": ("radius_mm", "width_mm"),
    "radial_gradient": (),
    "local_spot": ("radius_mm",),
}
#: Kinds whose amplitude may carry its own sign.
PATTERN_SIGNED_AMPLITUDE_KINDS: frozenset[str] = frozenset(
    {"ring", "radial_gradient", "local_spot"}
)
#: Kinds whose positive amplitude lowers the target instead of raising it.
PATTERN_NEGATIVE_AMPLITUDE_KINDS: frozenset[str] = frozenset({"center_low", "edge_low"})
#: CP items that random defects fail by default and yield patterns fail on demand.
YIELD_FAILURE_ITEM_IDS: tuple[str, ...] = ("CP_FUNC", "CP_SCAN")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Product(_StrictModel):
    """Product metadata carried into exported files and ground truth."""

    name: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    device_family: str = ""
    process_node: str = ""
    fab: str = ""
    test_program: str = ""


class Wafer(_StrictModel):
    """Wafer geometry and probing configuration."""

    diameter_mm: WaferDiameterMm = 300
    die_size_mm: tuple[PositiveFloat, PositiveFloat] = (5.0, 5.0)
    edge_exclusion_mm: NonNegativeFloat = 3.0
    notch: Literal["down"] = "down"
    cp_sites: int = Field(default=4, ge=1)
    wat_sites: WatSiteCount = 9


class Lots(_StrictModel):
    """Lot/wafer counts, identifiers, and the WAT-to-CP timeline."""

    count: int = Field(default=1, ge=1, le=10)
    wafers_per_lot: int = Field(default=25, ge=1, le=25)
    lot_id_template: str = "{product}-L{lot:03d}"
    wafer_id_template: str = "W{wafer:02d}"
    start_date: datetime | None = None
    wat_to_cp_gap_min: PositiveFloat = 120.0
    cp_duration_min_per_wafer: PositiveFloat = 45.0
    lot_interval_hours: NonNegativeFloat = 168.0


class ItemOverride(_StrictModel):
    """A patch to a built-in test item, or a complete custom item.

    An override whose ``id`` matches a catalog item patches that item; an
    unknown ``id`` adds a new item and must provide ``phase``, ``test_num``,
    ``unit``, ``typical``, and ``distribution``. Set ``remove: true`` to drop
    an item from the resolved catalog.
    """

    id: str = Field(min_length=1)
    enabled: bool | None = None
    remove: bool = False
    phase: TestPhase | None = None
    test_num: int | None = Field(default=None, ge=1)
    unit: str | None = None
    typical: FiniteFloat | None = None
    lsl: FiniteFloat | None = None
    usl: FiniteFloat | None = None
    distribution: Distribution | None = None
    description: str | None = None


class Items(_StrictModel):
    """Test item selection: a built-in preset plus ordered overrides."""

    preset: Literal["generic_cmos_logic_55nm"] = "generic_cmos_logic_55nm"
    overrides: list[ItemOverride] = Field(default_factory=list)


class Pattern(_StrictModel):
    """A systematic spatial pattern injected into yield or a CP item.

    Which extent fields are required depends on ``kind``; that rule is
    semantic, because the JSON Schema cannot express it cleanly.
    """

    kind: PatternKind
    scope: PatternScope = "lot"
    target: Literal["yield"] | None = None
    target_item: str | None = None
    amplitude: FiniteFloat
    radius_mm: PositiveFloat | None = None
    extent_mm: PositiveFloat | None = None
    width_mm: PositiveFloat | None = None
    center_mm: tuple[FiniteFloat, FiniteFloat] = (0.0, 0.0)
    combine: PatternCombine = "add"


class LinkageOverride(_StrictModel):
    """A target correlation override for one WAT/CP item pair."""

    wat: str = Field(min_length=1)
    cp: str = Field(min_length=1)
    target_r: Correlation


class Linkage(_StrictModel):
    """Linkage configuration; defaults come from the built-in linkage table."""

    overrides: list[LinkageOverride] = Field(default_factory=list)


class Defects(_StrictModel):
    """Random-defect model applied after systematic spatial patterns.

    ``failure_rate`` is the expected fraction of dies carrying a random
    defect, measured across all ``target_items``. ``cluster_size`` sets both
    the expected number of defect failures per spatial cluster and the
    negative-binomial dispersion, and ``cluster_radius_mm`` controls how far a
    cluster spreads.
    """

    enabled: bool = True
    model: Literal["clustered", "poisson"] = "clustered"
    failure_rate: float = Field(default=0.01, ge=0.0, le=1.0, allow_inf_nan=False)
    cluster_size: int = Field(default=8, ge=1)
    cluster_radius_mm: PositiveFloat = 10.0
    target_items: list[str] = Field(default_factory=lambda: list(YIELD_FAILURE_ITEM_IDS))


class ExportOptions(_StrictModel):
    """Export formats and file layout."""

    cp_stdf: bool = True
    cp_csv: bool = True
    wat_csv: bool = True
    ground_truth: bool = True
    include_die_truth: bool = True
    encoding: ExportEncoding = "utf-8"


class Metadata(_StrictModel):
    """Free-form descriptive metadata for the scenario."""

    author: str = ""
    note: str = ""


class Scenario(_StrictModel):
    """A complete, reproducible generation scenario (schema version 1)."""

    schema_version: Literal[1]
    product: Product
    wafer: Wafer = Field(default_factory=Wafer)
    lots: Lots = Field(default_factory=Lots)
    items: Items = Field(default_factory=Items)
    patterns: list[Pattern] = Field(default_factory=list)
    defects: Defects = Field(default_factory=Defects)
    linkage: Linkage = Field(default_factory=Linkage)
    export: ExportOptions = Field(default_factory=ExportOptions)
    seed: int = Field(ge=0, le=2**64 - 1)
    metadata: Metadata = Field(default_factory=Metadata)
