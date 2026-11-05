"""Semantic validation and the scenario summary printed by the CLI."""

from dataclasses import dataclass
from os import PathLike
from string import Formatter

from ..binning import BinDefinition, resolve_bin_table
from ..binroles import HARD_BIN_ROLES, SOFT_BIN_ROLES
from ..catalog import Catalog, can_fail, resolve_catalog
from ..errors import ScenarioError, ValidationIssue
from ..geometry import count_dies
from ..i18n import _
from ..latent import DEFAULT_LINKAGE_ITEM_IDS, LINKABLE_DISTRIBUTIONS, WAT_FACTOR
from .loader import parse_scenario, parse_scenario_text, read_scenario_data
from .models import (
    PATTERN_REQUIRED_EXTENTS,
    PATTERN_SIGNED_AMPLITUDE_KINDS,
    YIELD_FAILURE_ITEM_IDS,
    Bins,
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
from .presets import PRESET_NAMES


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


def validate_scenario_text(text: str) -> ValidationResult:
    """Validate scenario YAML held in memory and return locatable issues."""
    try:
        scenario = parse_scenario_text(text)
    except ScenarioError as exc:
        return ValidationResult(ok=False, issues=exc.issues, summary=None)
    return validate_scenario_model(scenario)


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
    issues.extend(_validate_bins(scenario.bins))
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


def scenario_from_preset(name: str, seed: int) -> Scenario:
    """Build a fully expanded, validated scenario from a built-in preset."""
    if name not in PRESET_NAMES:
        raise ScenarioError(
            [
                ValidationIssue(
                    code="UNKNOWN_PRESET",
                    path="preset",
                    message=_("unknown preset '{name}'; available: {available}").format(
                        name=name, available=", ".join(PRESET_NAMES)
                    ),
                )
            ]
        )
    scenario = parse_scenario({"schema_version": 1, "preset": name, "seed": seed})
    result = validate_scenario_model(scenario)
    if not result.ok:
        raise ScenarioError(result.issues)
    return scenario


def _validate_geometry(wafer: Wafer) -> list[ValidationIssue]:
    usable_radius_mm = wafer.diameter_mm / 2 - wafer.edge_exclusion_mm
    if usable_radius_mm <= 0:
        return [
            ValidationIssue(
                code="EDGE_EXCLUSION_TOO_LARGE",
                path="wafer.edge_exclusion_mm",
                message=_(
                    "edge exclusion {exclusion:g} mm leaves no usable radius "
                    "on a {diameter} mm wafer"
                ).format(
                    exclusion=wafer.edge_exclusion_mm,
                    diameter=wafer.diameter_mm,
                ),
            )
        ]
    if count_dies(wafer) == 0:
        die_width_mm, die_height_mm = wafer.die_size_mm
        return [
            ValidationIssue(
                code="DIE_GRID_DOES_NOT_FIT",
                path="wafer.die_size_mm",
                message=_(
                    "a {width:g} x {height:g} mm die grid does not fit on a "
                    "{diameter} mm wafer with {exclusion:g} mm edge exclusion"
                ).format(
                    width=die_width_mm,
                    height=die_height_mm,
                    diameter=wafer.diameter_mm,
                    exclusion=wafer.edge_exclusion_mm,
                ),
            )
        ]
    return []


def _validate_bins(bins: Bins) -> list[ValidationIssue]:
    table = resolve_bin_table(bins)
    issues = _duplicate_bin_code_issues("hard", table.hard, HARD_BIN_ROLES, set(bins.hard))
    issues.extend(_duplicate_bin_code_issues("soft", table.soft, SOFT_BIN_ROLES, set(bins.soft)))
    return issues


def _duplicate_bin_code_issues(
    kind: str,
    definitions: tuple[BinDefinition, ...],
    roles: tuple[str, ...],
    overridden_roles: set[str],
) -> list[ValidationIssue]:
    roles_by_number: dict[int, list[str]] = {}
    for role, definition in zip(roles, definitions, strict=True):
        roles_by_number.setdefault(definition.number, []).append(role)

    issues: list[ValidationIssue] = []
    for number, duplicated in roles_by_number.items():
        if len(duplicated) < 2:
            continue
        reported = [role for role in duplicated if role in overridden_roles] or duplicated[1:]
        issues.extend(
            ValidationIssue(
                code="DUPLICATE_BIN_CODE",
                path=f"bins.{kind}.{role}.code",
                message=_("{kind} bin code {number} is used by more than one role").format(
                    kind=kind, number=number
                ),
            )
            for role in reported
        )
    return issues


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
                message=_("template must not be empty"),
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
                message=_("invalid template: {error}").format(error=exc),
            )
        ]

    unknown = sorted({field_name for field_name in fields if field_name not in allowed})
    if unknown:
        return [
            ValidationIssue(
                code="INVALID_ID_TEMPLATE",
                path=path,
                message=_("unknown placeholder(s) {unknown}; allowed: {allowed}").format(
                    unknown=", ".join(unknown),
                    allowed=", ".join(sorted(allowed)),
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
                message=_("cannot render template: {error}").format(error=exc),
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
                    message=_("pattern must target 'yield', a CP item, or both"),
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
                        message=_("pattern kind '{kind}' requires '{field}'").format(
                            kind=pattern.kind, field=field_name
                        ),
                    )
                )
        if pattern.target == "yield" and not _has_yield_failure_item(catalog):
            issues.append(
                ValidationIssue(
                    code="PATTERN_YIELD_TARGET_UNAVAILABLE",
                    path=f"{path}.target",
                    message=_(
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
                message=_("enabled random defects must target at least one CP item"),
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
                    message=_(
                        "test item '{item}' has no pass rule; defect targets need "
                        "a bernoulli item or a spec limit"
                    ).format(item=item_id),
                )
            )
        if item_id in seen:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_DEFECT_TARGET",
                    path=path,
                    message=_("defect target '{item}' is listed more than once").format(
                        item=item_id
                    ),
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
                message=_("unknown test item '{item}'").format(item=item_id),
            )
        ]
    if not item.enabled:
        return [
            ValidationIssue(
                code="ITEM_DISABLED",
                path=path,
                message=_("test item '{item}' is disabled").format(item=item_id),
            )
        ]
    if item.phase != expected_phase:
        return [
            ValidationIssue(
                code="ITEM_PHASE_MISMATCH",
                path=path,
                message=_("expected a {expected} item; '{item}' is a {actual} item").format(
                    expected=expected_phase, item=item_id, actual=item.phase
                ),
            )
        ]
    return []


def _validate_export(export: ExportOptions) -> list[ValidationIssue]:
    if export.include_die_truth and not export.ground_truth:
        return [
            ValidationIssue(
                code="EXPORT_OPTION_CONFLICT",
                path="export.include_die_truth",
                message=_("include_die_truth requires ground_truth to be enabled"),
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
                    message=_(
                        "cannot link WAT item '{item}' with distribution "
                        "'{distribution}'; linkage supports normal and lognormal items"
                    ).format(item=override.wat, distribution=wat_item.distribution),
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
                    message=_(
                        "cannot link CP item '{item}' with distribution "
                        "'{distribution}'; linkage supports normal and lognormal items"
                    ).format(item=override.cp, distribution=cp_item.distribution),
                )
            )
        if wat_item is not None and wat_item.phase == "WAT" and override.wat not in WAT_FACTOR:
            issues.append(
                ValidationIssue(
                    code="LINKAGE_UNSUPPORTED_WAT_ITEM",
                    path=f"{path}.wat",
                    message=_(
                        "WAT item '{item}' has no primary latent factor; "
                        "custom WAT items cannot be linked"
                    ).format(item=override.wat),
                )
            )
        pair = (override.wat, override.cp)
        if pair in seen_pairs:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_LINKAGE_PAIR",
                    path=path,
                    message=_("linkage pair '{wat}' -> '{cp}' is specified more than once").format(
                        wat=override.wat, cp=override.cp
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
                message=_(
                    "changing item '{item}' to distribution '{distribution}' would "
                    "drop its default linkage pairs; remove or disable the item instead"
                ).format(item=override.id, distribution=override.distribution),
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
                    message=_("amplitude must be non-zero; the sign selects high or low"),
                )
            ]
        return []
    if pattern.amplitude <= 0:
        return [
            ValidationIssue(
                code="INVALID_PATTERN_AMPLITUDE",
                path=f"{path}.amplitude",
                message=_("amplitude must be positive; direction is encoded by the pattern kind"),
            )
        ]
    return []
