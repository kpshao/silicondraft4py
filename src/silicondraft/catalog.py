"""Built-in test item catalog presets.

V1 ships one preset, ``generic_cmos_logic_55nm``: 15 WAT items and 21 CP
items. Scenario overrides patch or extend the selected preset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from .errors import ValidationIssue
from .i18n import _

if TYPE_CHECKING:
    from .binroles import SoftBinRole
    from .scenario.models import Distribution, ItemOverride, Items, TestPhase


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """One test item definition in a catalog preset."""

    id: str
    phase: TestPhase
    test_num: int
    description: str
    unit: str
    typical: float
    lsl: float | None
    usl: float | None
    distribution: Distribution
    enabled: bool = True
    soft_bin_role: SoftBinRole | None = None


@dataclass(frozen=True, slots=True)
class Catalog:
    """A resolved catalog: a preset with scenario overrides applied."""

    items: tuple[CatalogItem, ...]

    def get(self, item_id: str) -> CatalogItem | None:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    @property
    def enabled_items(self) -> tuple[CatalogItem, ...]:
        return tuple(item for item in self.items if item.enabled)


_GENERIC_CMOS_LOGIC_55NM: tuple[CatalogItem, ...] = (
    CatalogItem(
        "WAT_VTN", "WAT", 1001, "NMOS saturation threshold voltage", "V", 0.35, 0.28, 0.42, "normal"
    ),
    CatalogItem(
        "WAT_VTP",
        "WAT",
        1002,
        "PMOS saturation threshold voltage",
        "V",
        -0.35,
        -0.42,
        -0.28,
        "normal",
    ),
    CatalogItem(
        "WAT_IDSATN",
        "WAT",
        1003,
        "NMOS saturation drive current",
        "uA/um",
        550.0,
        480.0,
        620.0,
        "normal",
    ),
    CatalogItem(
        "WAT_IDSATP",
        "WAT",
        1004,
        "PMOS saturation drive current",
        "uA/um",
        250.0,
        210.0,
        290.0,
        "normal",
    ),
    CatalogItem(
        "WAT_IOFFN",
        "WAT",
        1005,
        "NMOS off-state leakage",
        "pA/um",
        100.0,
        None,
        1000.0,
        "lognormal",
    ),
    CatalogItem(
        "WAT_IOFFP", "WAT", 1006, "PMOS off-state leakage", "pA/um", 10.0, None, 500.0, "lognormal"
    ),
    CatalogItem("WAT_SS", "WAT", 1007, "Subthreshold swing", "mV/dec", 85.0, None, 100.0, "normal"),
    CatalogItem(
        "WAT_DIBL",
        "WAT",
        1008,
        "Drain-induced barrier lowering",
        "mV/V",
        80.0,
        None,
        120.0,
        "normal",
    ),
    CatalogItem(
        "WAT_TOX",
        "WAT",
        1009,
        "Equivalent gate oxide thickness",
        "angstrom",
        22.0,
        21.0,
        23.0,
        "normal",
    ),
    CatalogItem(
        "WAT_RSHN", "WAT", 1010, "N+ diffusion sheet resistance", "ohm/sq", 8.0, 6.0, 10.0, "normal"
    ),
    CatalogItem(
        "WAT_RSHP",
        "WAT",
        1011,
        "P+ diffusion sheet resistance",
        "ohm/sq",
        12.0,
        9.0,
        15.0,
        "normal",
    ),
    CatalogItem("WAT_RC", "WAT", 1012, "Contact resistance", "ohm", 15.0, 8.0, 25.0, "normal"),
    CatalogItem("WAT_RVIA", "WAT", 1013, "Via resistance", "ohm", 3.0, 1.5, 5.0, "normal"),
    CatalogItem(
        "WAT_IGATE",
        "WAT",
        1014,
        "Gate leakage current density",
        "A/cm2",
        1e-3,
        None,
        1e-2,
        "lognormal",
    ),
    CatalogItem(
        "WAT_VBD", "WAT", 1015, "Gate oxide breakdown voltage", "V", 5.0, 4.0, None, "normal"
    ),
    CatalogItem(
        "CP_CONT",
        "CP",
        2001,
        "Continuity / open-short resistance",
        "ohm",
        5.0,
        None,
        100.0,
        "normal",
    ),
    CatalogItem(
        "CP_FUNC", "CP", 2002, "Functional test pass flag", "", 1.0, None, None, "bernoulli"
    ),
    CatalogItem(
        "CP_SCAN", "CP", 2003, "Scan chain test pass flag", "", 1.0, None, None, "bernoulli"
    ),
    CatalogItem(
        "CP_IDDQ", "CP", 2004, "Quiescent supply current", "uA", 2.0, None, 50.0, "lognormal"
    ),
    CatalogItem("CP_VTHN", "CP", 2005, "NMOS threshold voltage", "V", 0.35, 0.28, 0.42, "normal"),
    CatalogItem(
        "CP_VTHP", "CP", 2006, "PMOS threshold voltage", "V", -0.35, -0.42, -0.28, "normal"
    ),
    CatalogItem("CP_IONN", "CP", 2007, "NMOS drive current", "uA", 600.0, 500.0, None, "normal"),
    CatalogItem("CP_IONP", "CP", 2008, "PMOS drive current", "uA", 250.0, 200.0, None, "normal"),
    CatalogItem(
        "CP_IOFFN", "CP", 2009, "NMOS off-state current", "nA", 1.0, None, 50.0, "lognormal"
    ),
    CatalogItem(
        "CP_IOFFP", "CP", 2010, "PMOS off-state current", "nA", 0.5, None, 20.0, "lognormal"
    ),
    CatalogItem(
        "CP_IGATE", "CP", 2011, "Gate leakage current", "nA", 5.0, None, 100.0, "lognormal"
    ),
    CatalogItem(
        "CP_IIL", "CP", 2012, "Input low leakage current", "uA", 0.01, None, 1.0, "lognormal"
    ),
    CatalogItem(
        "CP_IIH", "CP", 2013, "Input high leakage current", "uA", 0.01, None, 1.0, "lognormal"
    ),
    CatalogItem(
        "CP_IOZ", "CP", 2014, "Output tri-state leakage current", "uA", 0.05, None, 5.0, "lognormal"
    ),
    CatalogItem("CP_VIL", "CP", 2015, "Input low voltage", "V", 0.35, None, 0.54, "normal"),
    CatalogItem("CP_VIH", "CP", 2016, "Input high voltage", "V", 1.5, 1.26, None, "normal"),
    CatalogItem("CP_VOL", "CP", 2017, "Output low voltage", "V", 0.2, None, 0.4, "normal"),
    CatalogItem("CP_VOH", "CP", 2018, "Output high voltage", "V", 1.6, 1.4, None, "normal"),
    CatalogItem(
        "CP_FRO", "CP", 2019, "Ring oscillator frequency", "MHz", 800.0, 700.0, 900.0, "normal"
    ),
    CatalogItem("CP_RCONT", "CP", 2020, "Contact resistance", "ohm", 15.0, None, 30.0, "normal"),
    CatalogItem(
        "CP_VDDMIN", "CP", 2021, "Minimum operating voltage", "V", 0.9, None, 1.0, "normal"
    ),
)


def can_fail(item: CatalogItem) -> bool:
    """Return whether a failing measurement can violate this item's pass rule."""
    return item.distribution == "bernoulli" or item.lsl is not None or item.usl is not None


_PRESETS: dict[str, tuple[CatalogItem, ...]] = {
    "generic_cmos_logic_55nm": _GENERIC_CMOS_LOGIC_55NM,
}

_ITEM_ID_PATTERN = re.compile(r"^(CP|WAT)_[A-Z0-9_]+$")


@dataclass(frozen=True, slots=True)
class CatalogResolution:
    """A resolved catalog plus any override problems found while applying it."""

    catalog: Catalog
    issues: tuple[ValidationIssue, ...]


def resolve_catalog(items: Items) -> CatalogResolution:
    """Apply scenario overrides to the selected preset."""
    issues: list[ValidationIssue] = []
    base_items = _PRESETS[items.preset]
    by_id: dict[str, CatalogItem] = {item.id: item for item in base_items}
    order: list[str] = [item.id for item in base_items]
    seen_overrides: set[str] = set()

    for index, override in enumerate(items.overrides):
        path = f"items.overrides[{index}]"
        if override.id in seen_overrides:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_ITEM_OVERRIDE",
                    path=f"{path}.id",
                    message=_("item '{item}' is overridden more than once").format(
                        item=override.id
                    ),
                )
            )
            continue
        seen_overrides.add(override.id)

        if not _ITEM_ID_PATTERN.fullmatch(override.id):
            issues.append(
                ValidationIssue(
                    code="INVALID_ITEM_ID",
                    path=f"{path}.id",
                    message=_(
                        "invalid item id '{item}'; expected CP_* or WAT_* "
                        "using uppercase letters, digits, and underscores"
                    ).format(item=override.id),
                )
            )
            continue

        if override.remove:
            if by_id.pop(override.id, None) is None:
                issues.append(
                    ValidationIssue(
                        code="ITEM_REFERENCE_UNKNOWN",
                        path=f"{path}.id",
                        message=_("cannot remove unknown test item '{item}'").format(
                            item=override.id
                        ),
                    )
                )
            else:
                order.remove(override.id)
            continue

        existing = by_id.get(override.id)
        if existing is None:
            item = _new_item(override, path, issues)
            if item is None:
                continue
            order.append(item.id)
        else:
            item = _patch_item(existing, override, path, issues)

        _check_ascii_unit(item, path, issues)
        by_id[item.id] = item
        _check_test_num_collision(item, by_id, path, issues)

    resolved = tuple(by_id[item_id] for item_id in order)
    return CatalogResolution(catalog=Catalog(items=resolved), issues=tuple(issues))


def _new_item(
    override: ItemOverride, path: str, issues: list[ValidationIssue]
) -> CatalogItem | None:
    required = (
        ("phase", override.phase),
        ("test_num", override.test_num),
        ("unit", override.unit),
        ("typical", override.typical),
        ("distribution", override.distribution),
    )
    missing = [name for name, value in required if value is None]
    for name in missing:
        issues.append(
            ValidationIssue(
                code="ITEM_OVERRIDE_INCOMPLETE",
                path=f"{path}.{name}",
                message=_("new item '{item}' requires '{field}'").format(
                    item=override.id, field=name
                ),
            )
        )
    if missing:
        return None

    if (
        override.phase is None
        or override.test_num is None
        or override.unit is None
        or override.typical is None
        or override.distribution is None
    ):
        return None

    if not override.id.startswith(f"{override.phase}_"):
        issues.append(
            ValidationIssue(
                code="ITEM_PHASE_MISMATCH",
                path=f"{path}.id",
                message=_(
                    "item id '{item}' does not match phase '{phase}'; expected prefix '{phase}_'"
                ).format(item=override.id, phase=override.phase),
            )
        )
    _check_soft_bin_role_phase(override.soft_bin_role, override.phase, path, issues)

    item = CatalogItem(
        id=override.id,
        phase=override.phase,
        test_num=override.test_num,
        description=override.description or "",
        unit=override.unit,
        typical=override.typical,
        lsl=override.lsl,
        usl=override.usl,
        distribution=override.distribution,
        enabled=override.enabled if override.enabled is not None else True,
        soft_bin_role=override.soft_bin_role,
    )
    _check_spec_limits(item, path, issues)
    return item


def _patch_item(
    existing: CatalogItem, override: ItemOverride, path: str, issues: list[ValidationIssue]
) -> CatalogItem:
    if override.phase is not None and override.phase != existing.phase:
        issues.append(
            ValidationIssue(
                code="ITEM_PHASE_CHANGE",
                path=f"{path}.phase",
                message=_("cannot change phase of item '{item}' from {old} to {new}").format(
                    item=existing.id, old=existing.phase, new=override.phase
                ),
            )
        )

    _check_soft_bin_role_phase(override.soft_bin_role, existing.phase, path, issues)
    updated = replace(
        existing,
        enabled=override.enabled if override.enabled is not None else existing.enabled,
        test_num=override.test_num if override.test_num is not None else existing.test_num,
        unit=override.unit if override.unit is not None else existing.unit,
        typical=override.typical if override.typical is not None else existing.typical,
        lsl=override.lsl if override.lsl is not None else existing.lsl,
        usl=override.usl if override.usl is not None else existing.usl,
        distribution=(
            override.distribution if override.distribution is not None else existing.distribution
        ),
        description=(
            override.description if override.description is not None else existing.description
        ),
        soft_bin_role=(
            override.soft_bin_role if override.soft_bin_role is not None else existing.soft_bin_role
        ),
    )

    _check_spec_limits(updated, path, issues)
    return updated


def _check_soft_bin_role_phase(
    soft_bin_role: SoftBinRole | None,
    phase: TestPhase,
    path: str,
    issues: list[ValidationIssue],
) -> None:
    if soft_bin_role is not None and phase != "CP":
        issues.append(
            ValidationIssue(
                code="SOFT_BIN_ROLE_REQUIRES_CP",
                path=f"{path}.soft_bin_role",
                message=_("soft_bin_role applies only to CP items"),
            )
        )


_ASCII_UNIT_REPLACEMENTS = {
    "µ": "u",
    "Ω": "ohm",
    "Å": "angstrom",
    "²": "2",
}


def _check_ascii_unit(item: CatalogItem, path: str, issues: list[ValidationIssue]) -> None:
    if item.unit.isascii():
        return
    hint = item.unit
    for source, replacement in _ASCII_UNIT_REPLACEMENTS.items():
        hint = hint.replace(source, replacement)
    if hint.isascii():
        message = _(
            "unit '{unit}' is not ASCII; use '{hint}' (µ→u, Ω→ohm, Å→angstrom, ²→2)"
        ).format(unit=item.unit, hint=hint)
    else:
        message = _("unit '{unit}' is not ASCII; use ASCII unit notation").format(unit=item.unit)
    issues.append(
        ValidationIssue(
            code="ITEM_UNIT_NOT_ASCII",
            path=f"{path}.unit",
            message=message,
        )
    )


def _check_spec_limits(item: CatalogItem, path: str, issues: list[ValidationIssue]) -> None:
    if item.lsl is not None and item.usl is not None and item.lsl >= item.usl:
        issues.append(
            ValidationIssue(
                code="INVALID_SPEC_LIMITS",
                path=path,
                message=_("item '{item}' has LSL {lsl:g} >= USL {usl:g}").format(
                    item=item.id, lsl=item.lsl, usl=item.usl
                ),
            )
        )


def _check_test_num_collision(
    item: CatalogItem,
    by_id: dict[str, CatalogItem],
    path: str,
    issues: list[ValidationIssue],
) -> None:
    for other in by_id.values():
        if other.id != item.id and other.test_num == item.test_num:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_TEST_NUM",
                    path=f"{path}.test_num",
                    message=_("test_num {test_num} is already used by '{other}'").format(
                        test_num=item.test_num, other=other.id
                    ),
                )
            )
            return
