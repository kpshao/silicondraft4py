"""Semantic validation and the scenario summary printed by the CLI."""

from dataclasses import dataclass
from os import PathLike
from string import Formatter

from ..catalog import Catalog, can_fail, resolve_catalog
from ..errors import ScenarioError, ValidationIssue
from ..geometry import count_dies
from ..latent import DEFAULT_LINKAGE_ITEM_IDS, LINKABLE_DISTRIBUTIONS, WAT_FACTOR
from .loader import parse_scenario, read_scenario_data
from .models import (
    PATTERN_REQUIRED_EXTENTS,
    PATTERN_SIGNED_AMPLITUDE_KINDS,
    YIELD_FAILURE_ITEM_IDS,
    Defects,
    ExportOptions,
    Items,
    Linkage,
    Lots,
    Pattern,
    Scenario,
    TestPhase,
    Wafer,
)


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    """Resolved counts for a valid scenario."""

    schema_version: int
    preset: str | None
    product: str
    lots: int
    wafers_per_lot: int
    wafers: int
    dies_per_wafer: int
    dies_total: int
    cp_items: int
    wat_items: int
    items_total: int


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """The outcome of validating a scenario."""

    ok: bool
    issues: tuple[ValidationIssue, ...]
    summary: ScenarioSummary | None


def validate_scenario(path: str | PathLike[str]) -> ValidationResult:
    """Validate a scenario YAML file and return locatable issues plus a summary."""
    result, _ = _load_and_validate(path)
    return result


def load_scenario(path: str | PathLike[str]) -> Scenario:
    """Load a fully validated scenario.

    Raises :class:`ScenarioError` with locatable issues.
    """
    result, scenario = _load_and_validate(path)
    if scenario is None:
        raise ScenarioError(result.issues)
    return scenario


def _load_and_validate(
    path: str | PathLike[str],
) -> tuple[ValidationResult, Scenario | None]:
    try:
        scenario = parse_scenario(read_scenario_data(path))
    except ScenarioError as exc:
        return ValidationResult(ok=False, issues=exc.issues, summary=None), None
    result = validate_scenario_model(scenario)
    return result, scenario if result.ok else None


def validate_scenario_model(scenario: Scenario) -> ValidationResult:
    """Validate a typed scenario, including rules that span fields.

    ``generate`` uses this even for hand-built ``Scenario`` objects so that an
    invalid scenario is rejected before any data is produced.
    """
    resolution = resolve_catalog(scenario.items)
    issues: list[ValidationIssue] = list(resolution.issues)
    issues.extend(_validate_geometry(scenario.wafer))
    issues.extend(_validate_lots(scenario.lots))
    issues.extend(_validate_patterns(scenario.patterns, resolution.catalog))
    issues.extend(_validate_defects(scenario.defects, resolution.catalog))
    issues.extend(_validate_linkage(scenario.linkage, resolution.catalog))
    issues.extend(_validate_item_overrides_linkage(scenario.items))
    issues.extend(_validate_export(scenario.export))

    if issues:
        return ValidationResult(ok=False, issues=tuple(issues), summary=None)

    catalog = resolution.catalog
    enabled_items = catalog.enabled_items
    dies_per_wafer = count_dies(scenario.wafer)
    wafers = scenario.lots.count * scenario.lots.wafers_per_lot
    summary = ScenarioSummary(
        schema_version=scenario.schema_version,
        preset=scenario.preset,
        product=scenario.product.name,
        lots=scenario.lots.count,
        wafers_per_lot=scenario.lots.wafers_per_lot,
        wafers=wafers,
        dies_per_wafer=dies_per_wafer,
        dies_total=dies_per_wafer * wafers,
        cp_items=sum(1 for item in enabled_items if item.phase == "CP"),
        wat_items=sum(1 for item in enabled_items if item.phase == "WAT"),
        items_total=len(enabled_items),
    )
    return ValidationResult(ok=True, issues=(), summary=summary)


def _validate_geometry(wafer: Wafer) -> list[ValidationIssue]:
    usable_radius_mm = wafer.diameter_mm / 2 - wafer.edge_exclusion_mm
    if usable_radius_mm <= 0:
        return [
            ValidationIssue(
                code="EDGE_EXCLUSION_TOO_LARGE",
                path="wafer.edge_exclusion_mm",
                message=(
                    f"edge exclusion {wafer.edge_exclusion_mm:g} mm leaves no usable "
                    f"radius on a {wafer.diameter_mm} mm wafer"
                ),
            )
        ]
    if count_dies(wafer) == 0:
        die_width_mm, die_height_mm = wafer.die_size_mm
        return [
            ValidationIssue(
                code="DIE_GRID_DOES_NOT_FIT",
                path="wafer.die_size_mm",
                message=(
                    f"a {die_width_mm:g} x {die_height_mm:g} mm die grid does not fit "
                    f"on a {wafer.diameter_mm} mm wafer with "
                    f"{wafer.edge_exclusion_mm:g} mm edge exclusion"
                ),
            )
        ]
    return []


def _validate_lots(lots: Lots) -> list[ValidationIssue]:
    issues = _validate_id_template(
        "lots.lot_id_template", lots.lot_id_template, frozenset({"product", "lot"})
    )
    issues.extend(
        _validate_id_template(
            "lots.wafer_id_template",
            lots.wafer_id_template,
            frozenset({"product", "lot", "wafer"}),
        )
    )
    return issues


def _validate_id_template(
    path: str, template: str, allowed: frozenset[str]
) -> list[ValidationIssue]:
    if not template.strip():
        return [
            ValidationIssue(
                code="INVALID_ID_TEMPLATE",
                path=path,
                message="template must not be empty",
            )
        ]
    try:
        fields = [
            field_name
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name is not None
        ]
    except ValueError as exc:
        return [
            ValidationIssue(
                code="INVALID_ID_TEMPLATE",
                path=path,
                message=f"invalid template: {exc}",
            )
        ]

    unknown = sorted({field_name for field_name in fields if field_name not in allowed})
    if unknown:
        return [
            ValidationIssue(
                code="INVALID_ID_TEMPLATE",
                path=path,
                message=(
                    f"unknown placeholder(s) {', '.join(unknown)}; "
                    f"allowed: {', '.join(sorted(allowed))}"
                ),
            )
        ]

    try:
        template.format(product="P", lot=1, wafer=1)
    except (KeyError, IndexError, ValueError) as exc:
        return [
            ValidationIssue(
                code="INVALID_ID_TEMPLATE",
                path=path,
                message=f"cannot render template: {exc}",
            )
        ]
    return []


def _validate_patterns(patterns: list[Pattern], catalog: Catalog) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for index, pattern in enumerate(patterns):
        path = f"patterns[{index}]"
        if pattern.target is None and pattern.target_item is None:
            issues.append(
                ValidationIssue(
                    code="PATTERN_TARGET_MISSING",
                    path=path,
                    message="pattern must target 'yield', a CP item, or both",
                )
            )
        if pattern.target_item is not None:
            issues.extend(
                _validate_item_reference(pattern.target_item, f"{path}.target_item", "CP", catalog)
            )
        for field_name in PATTERN_REQUIRED_EXTENTS[pattern.kind]:
            if getattr(pattern, field_name) is None:
                issues.append(
                    ValidationIssue(
                        code="PATTERN_EXTENT_MISSING",
                        path=f"{path}.{field_name}",
                        message=(f"pattern kind '{pattern.kind}' requires '{field_name}'"),
                    )
                )
        if pattern.target == "yield" and not _has_yield_failure_item(catalog):
            issues.append(
                ValidationIssue(
                    code="PATTERN_YIELD_TARGET_UNAVAILABLE",
                    path=f"{path}.target",
                    message=(
                        "yield target requires an enabled CP_FUNC or CP_SCAN item that can fail"
                    ),
                )
            )
        issues.extend(_validate_pattern_amplitude(pattern, path))
    return issues


def _has_yield_failure_item(catalog: Catalog) -> bool:
    return any(
        can_fail(item)
        for item in catalog.enabled_items
        if item.phase == "CP" and item.id in YIELD_FAILURE_ITEM_IDS
    )


def _validate_defects(defects: Defects, catalog: Catalog) -> list[ValidationIssue]:
    if not defects.enabled:
        return []
    if not defects.target_items:
        return [
            ValidationIssue(
                code="DEFECT_TARGET_MISSING",
                path="defects.target_items",
                message="enabled random defects must target at least one CP item",
            )
        ]

    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for index, item_id in enumerate(defects.target_items):
        path = f"defects.target_items[{index}]"
        issues.extend(_validate_item_reference(item_id, path, "CP", catalog))
        item = catalog.get(item_id)
        if item is not None and item.enabled and not can_fail(item):
            issues.append(
                ValidationIssue(
                    code="DEFECT_TARGET_UNSUPPORTED",
                    path=path,
                    message=(
                        f"test item '{item_id}' has no pass rule; defect targets need "
                        "a bernoulli item or a spec limit"
                    ),
                )
            )
        if item_id in seen:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_DEFECT_TARGET",
                    path=path,
                    message=f"defect target '{item_id}' is listed more than once",
                )
            )
        else:
            seen.add(item_id)
    return issues


def _validate_item_reference(
    item_id: str, path: str, expected_phase: TestPhase, catalog: Catalog
) -> list[ValidationIssue]:
    item = catalog.get(item_id)
    if item is None:
        return [
            ValidationIssue(
                code="ITEM_REFERENCE_UNKNOWN",
                path=path,
                message=f"unknown test item '{item_id}'",
            )
        ]
    if not item.enabled:
        return [
            ValidationIssue(
                code="ITEM_DISABLED",
                path=path,
                message=f"test item '{item_id}' is disabled",
            )
        ]
    if item.phase != expected_phase:
        return [
            ValidationIssue(
                code="ITEM_PHASE_MISMATCH",
                path=path,
                message=(f"expected a {expected_phase} item; '{item_id}' is a {item.phase} item"),
            )
        ]
    return []


def _validate_export(export: ExportOptions) -> list[ValidationIssue]:
    if export.include_die_truth and not export.ground_truth:
        return [
            ValidationIssue(
                code="EXPORT_OPTION_CONFLICT",
                path="export.include_die_truth",
                message="include_die_truth requires ground_truth to be enabled",
            )
        ]
    return []


def _validate_linkage(linkage: Linkage, catalog: Catalog) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    seen_pairs: set[tuple[str, str]] = set()
    for index, override in enumerate(linkage.overrides):
        path = f"linkage.overrides[{index}]"
        issues.extend(_validate_item_reference(override.wat, f"{path}.wat", "WAT", catalog))
        issues.extend(_validate_item_reference(override.cp, f"{path}.cp", "CP", catalog))
        wat_item = catalog.get(override.wat)
        cp_item = catalog.get(override.cp)
        if (
            wat_item is not None
            and wat_item.phase == "WAT"
            and wat_item.distribution not in LINKABLE_DISTRIBUTIONS
        ):
            issues.append(
                ValidationIssue(
                    code="LINKAGE_UNSUPPORTED_DISTRIBUTION",
                    path=f"{path}.wat",
                    message=(
                        f"cannot link WAT item '{override.wat}' with distribution "
                        f"'{wat_item.distribution}'; linkage supports normal and lognormal items"
                    ),
                )
            )
        if (
            cp_item is not None
            and cp_item.phase == "CP"
            and cp_item.distribution not in LINKABLE_DISTRIBUTIONS
        ):
            issues.append(
                ValidationIssue(
                    code="LINKAGE_UNSUPPORTED_DISTRIBUTION",
                    path=f"{path}.cp",
                    message=(
                        f"cannot link CP item '{override.cp}' with distribution "
                        f"'{cp_item.distribution}'; linkage supports normal and lognormal items"
                    ),
                )
            )
        if wat_item is not None and wat_item.phase == "WAT" and override.wat not in WAT_FACTOR:
            issues.append(
                ValidationIssue(
                    code="LINKAGE_UNSUPPORTED_WAT_ITEM",
                    path=f"{path}.wat",
                    message=(
                        f"WAT item '{override.wat}' has no primary latent factor; "
                        "custom WAT items cannot be linked"
                    ),
                )
            )
        pair = (override.wat, override.cp)
        if pair in seen_pairs:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_LINKAGE_PAIR",
                    path=path,
                    message=(
                        f"linkage pair '{override.wat}' -> '{override.cp}' "
                        "is specified more than once"
                    ),
                )
            )
        else:
            seen_pairs.add(pair)
    return issues


def _validate_item_overrides_linkage(items: Items) -> list[ValidationIssue]:
    """Reject distribution changes that would silently drop default linkage pairs.

    Disabling or removing a linked item is an explicit way to drop its pairs;
    changing it to a distribution that cannot participate in linkage is not.
    """
    issues: list[ValidationIssue] = []
    for index, override in enumerate(items.overrides):
        if override.remove or override.enabled is False:
            continue
        if override.distribution is None or override.distribution in LINKABLE_DISTRIBUTIONS:
            continue
        if override.id not in DEFAULT_LINKAGE_ITEM_IDS:
            continue
        issues.append(
            ValidationIssue(
                code="LINKAGE_UNSUPPORTED_DISTRIBUTION",
                path=f"items.overrides[{index}].distribution",
                message=(
                    f"changing item '{override.id}' to distribution "
                    f"'{override.distribution}' would drop its default linkage pairs; "
                    "remove or disable the item instead"
                ),
            )
        )
    return issues


def _validate_pattern_amplitude(pattern: Pattern, path: str) -> list[ValidationIssue]:
    if pattern.kind in PATTERN_SIGNED_AMPLITUDE_KINDS:
        if pattern.amplitude == 0:
            return [
                ValidationIssue(
                    code="INVALID_PATTERN_AMPLITUDE",
                    path=f"{path}.amplitude",
                    message="amplitude must be non-zero; the sign selects high or low",
                )
            ]
        return []
    if pattern.amplitude <= 0:
        return [
            ValidationIssue(
                code="INVALID_PATTERN_AMPLITUDE",
                path=f"{path}.amplitude",
                message=("amplitude must be positive; direction is encoded by the pattern kind"),
            )
        ]
    return []
