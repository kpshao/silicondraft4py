"""Latent process factors, sensitivity calibration, and WAT<->CP linkage.

V1 drives related WAT and CP measurements from six shared latent process
factors (``F_VT``, ``F_MOB``, ``F_TOX``, ``F_RC``, ``F_LEAK``, ``F_SC``), as
recorded in ADR-0001. Each factor is the sum of standardized lot, wafer, and
die components; correlated items load on the same factor through a calibrated
sensitivity matrix, and all remaining variation is independent measurement
noise.

The calibration works in standardized latent space. A WAT item loads on one
primary factor with communality ``w`` (its shared variance share), while a CP
item may load on several factors with signed sensitivities ``u``. For a
WAT/CP pair the model-implied correlation is therefore ``w * u`` in latent
space; :func:`_latent_target` converts the requested raw-scale correlation to
that latent target, accounting for lognormal marginals, and the alternating
least-squares fit in :func:`_fit` finds ``w`` and ``u`` that satisfy every pair
as closely as the shared factors allow.

The achieved value reported to callers is the correlation implied by the
calibrated model. Finite generated samples vary around it; callers can compute
the observed sample correlation separately.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .catalog import Catalog, CatalogItem
from .scenario.models import Linkage

FloatArray = NDArray[np.float64]

FACTORS: tuple[str, ...] = ("F_VT", "F_MOB", "F_TOX", "F_RC", "F_LEAK", "F_SC")
_FACTOR_INDEX: dict[str, int] = {name: index for index, name in enumerate(FACTORS)}

#: Primary latent factor for every built-in WAT item.
WAT_FACTOR: dict[str, str] = {
    "WAT_VTN": "F_VT",
    "WAT_VTP": "F_VT",
    "WAT_IDSATN": "F_MOB",
    "WAT_IDSATP": "F_MOB",
    "WAT_IOFFN": "F_LEAK",
    "WAT_IOFFP": "F_LEAK",
    "WAT_SS": "F_SC",
    "WAT_DIBL": "F_SC",
    "WAT_TOX": "F_TOX",
    "WAT_RSHN": "F_RC",
    "WAT_RSHP": "F_RC",
    "WAT_RC": "F_RC",
    "WAT_RVIA": "F_RC",
    "WAT_IGATE": "F_LEAK",
    "WAT_VBD": "F_TOX",
}

#: Default WAT -> CP link-up table from the V1 test item catalog.
_DEFAULT_LINKAGE: tuple[tuple[str, str, float], ...] = (
    ("WAT_VTN", "CP_VTHN", 0.80),
    ("WAT_VTN", "CP_IDDQ", -0.50),
    ("WAT_VTN", "CP_FRO", -0.45),
    ("WAT_VTP", "CP_VTHP", 0.80),
    ("WAT_VTP", "CP_IDDQ", -0.45),
    ("WAT_VTP", "CP_FRO", -0.40),
    ("WAT_IDSATN", "CP_IONN", 0.75),
    ("WAT_IDSATN", "CP_FRO", 0.60),
    ("WAT_IDSATP", "CP_IONP", 0.75),
    ("WAT_IDSATP", "CP_FRO", 0.55),
    ("WAT_IOFFN", "CP_IOFFN", 0.70),
    ("WAT_IOFFN", "CP_IDDQ", 0.55),
    ("WAT_IOFFP", "CP_IOFFP", 0.70),
    ("WAT_IOFFP", "CP_IDDQ", 0.50),
    ("WAT_SS", "CP_IOFFN", 0.50),
    ("WAT_SS", "CP_VDDMIN", 0.45),
    ("WAT_DIBL", "CP_IOFFN", 0.55),
    ("WAT_DIBL", "CP_VDDMIN", 0.45),
    ("WAT_TOX", "CP_IGATE", -0.60),
    ("WAT_TOX", "CP_VTHN", 0.40),
    ("WAT_TOX", "CP_FRO", -0.40),
    ("WAT_RSHN", "CP_RCONT", 0.50),
    ("WAT_RSHP", "CP_RCONT", 0.50),
    ("WAT_RC", "CP_RCONT", 0.70),
    ("WAT_RC", "CP_CONT", 0.50),
    ("WAT_RVIA", "CP_CONT", 0.45),
    ("WAT_IGATE", "CP_IGATE", 0.65),
    ("WAT_VBD", "CP_IGATE", -0.45),
)

_LOT_COMPONENT_WEIGHT = 0.25
_WAFER_COMPONENT_WEIGHT = 0.25
_DIE_COMPONENT_WEIGHT = math.sqrt(1.0 - _LOT_COMPONENT_WEIGHT**2 - _WAFER_COMPONENT_WEIGHT**2)

_NORMAL_SPEC_SIGMAS = 6.0
_LOG_SPEC_SIGMAS = 6.0
_MAX_ABS_LATENT_CORRELATION = 0.999999
_FIT_ITERATIONS = 1_000
_FIT_TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class LinkagePair:
    """One active WAT/CP linkage target."""

    wat_item: str
    cp_item: str
    target_r: float
    factor: str


@dataclass(frozen=True, slots=True)
class LatentModel:
    """A calibrated latent-factor model for one resolved catalog."""

    pairs: tuple[LinkagePair, ...]
    wat_communality: Mapping[str, float]
    cp_loadings: Mapping[str, Mapping[str, float]]
    achieved_r: Mapping[tuple[str, str], float]

    def cp_noise_std(self, item_id: str) -> float:
        """Independent measurement-noise standard deviation for a CP item."""
        loadings = self.cp_loadings.get(item_id, {})
        return math.sqrt(max(0.0, 1.0 - math.fsum(value * value for value in loadings.values())))

    def wat_noise_std(self, item_id: str) -> float:
        """Independent measurement-noise standard deviation for a WAT item."""
        communality = self.wat_communality.get(item_id, 0.0)
        return math.sqrt(max(0.0, 1.0 - communality * communality))


def resolve_linkage_pairs(linkage: Linkage, catalog: Catalog) -> tuple[LinkagePair, ...]:
    """Resolve default linkage plus scenario overrides against enabled items.

    Default pairs whose WAT or CP item is disabled or removed are dropped;
    overrides replace a default target or add a new pair. Invalid references
    are rejected by semantic validation before generation.
    """
    enabled = {item.id: item for item in catalog.enabled_items}
    order: list[tuple[str, str]] = []
    resolved: dict[tuple[str, str], LinkagePair] = {}
    for wat_item, cp_item, target_r in _DEFAULT_LINKAGE:
        if wat_item not in enabled or cp_item not in enabled:
            continue
        if not _supports_linkage(enabled[wat_item], enabled[cp_item]):
            continue
        key = (wat_item, cp_item)
        resolved[key] = LinkagePair(wat_item, cp_item, target_r, WAT_FACTOR[wat_item])
        order.append(key)

    for override in linkage.overrides:
        if override.wat not in enabled or override.cp not in enabled:
            continue
        factor = WAT_FACTOR.get(override.wat)
        if factor is None or not _supports_linkage(enabled[override.wat], enabled[override.cp]):
            continue
        key = (override.wat, override.cp)
        if key not in resolved:
            order.append(key)
        resolved[key] = LinkagePair(override.wat, override.cp, override.target_r, factor)

    return tuple(resolved[key] for key in order)


def _supports_linkage(wat_item: CatalogItem, cp_item: CatalogItem) -> bool:
    return (
        wat_item.id in WAT_FACTOR
        and wat_item.distribution in {"normal", "lognormal"}
        and cp_item.distribution in {"normal", "lognormal"}
    )


def build_latent_model(catalog: Catalog, linkage: Linkage) -> LatentModel:
    """Calibrate the sensitivity matrix for the active linkage pairs."""
    pairs = resolve_linkage_pairs(linkage, catalog)
    enabled = {item.id: item for item in catalog.enabled_items}
    latent_targets = {
        (pair.wat_item, pair.cp_item): _latent_target(
            enabled[pair.wat_item], enabled[pair.cp_item], pair.target_r
        )
        for pair in pairs
    }
    communality, loadings = _fit(pairs, latent_targets)

    cp_loadings: dict[str, dict[str, float]] = {}
    for (cp_item, factor), loading in loadings.items():
        if loading != 0.0:
            cp_loadings.setdefault(cp_item, {})[factor] = loading

    achieved = {
        (pair.wat_item, pair.cp_item): _achieved_correlation(
            enabled[pair.wat_item],
            enabled[pair.cp_item],
            communality.get(pair.wat_item, 0.0) * loadings.get((pair.cp_item, pair.factor), 0.0),
        )
        for pair in pairs
    }
    return LatentModel(
        pairs=pairs,
        wat_communality={
            item.id: communality.get(item.id, 0.0)
            for item in enabled.values()
            if item.phase == "WAT"
        },
        cp_loadings=cp_loadings,
        achieved_r=achieved,
    )


def combine_factor_components(
    lot_components: FloatArray, wafer_components: FloatArray, die_components: FloatArray
) -> FloatArray:
    """Combine the standardized lot/wafer/die components into factor values.

    ``die_components`` has shape ``(factor, sample)``; the lot and wafer
    components are shared across all samples on that level.
    """
    return (
        _LOT_COMPONENT_WEIGHT * lot_components[:, np.newaxis]
        + _WAFER_COMPONENT_WEIGHT * wafer_components[:, np.newaxis]
        + _DIE_COMPONENT_WEIGHT * die_components
    )


def cp_latent(model: LatentModel, item_id: str, factors: FloatArray) -> FloatArray:
    """Return the standardized latent signal of a CP item for every die."""
    latent = np.zeros(factors.shape[1], dtype=np.float64)
    for factor, loading in model.cp_loadings.get(item_id, {}).items():
        latent += loading * factors[_FACTOR_INDEX[factor]]
    return latent


def wat_latent(model: LatentModel, item_id: str, site_factors: FloatArray) -> FloatArray:
    """Return the standardized latent signal of a WAT item for every site."""
    factor = WAT_FACTOR.get(item_id)
    communality = model.wat_communality.get(item_id, 0.0)
    if factor is None or communality == 0.0:
        return np.zeros(site_factors.shape[1], dtype=np.float64)
    latent: FloatArray = communality * site_factors[_FACTOR_INDEX[factor]]
    return latent


def sample_measurements(
    item: CatalogItem,
    latent: FloatArray,
    noise_std: float,
    rng: np.random.Generator,
) -> FloatArray:
    """Turn a standardized latent signal into item measurements."""
    if item.distribution == "bernoulli":
        probability = min(max(item.typical, 0.0), 1.0)
        return rng.binomial(1, probability, size=latent.size).astype(np.float64)

    standardized = latent + noise_std * rng.standard_normal(latent.shape)
    if item.distribution == "normal":
        return item.typical + normal_scale(item) * standardized

    tiny = np.finfo(np.float64).tiny
    with np.errstate(over="ignore", under="ignore"):
        values = np.exp(math.log(max(item.typical, tiny)) + lognormal_sigma(item) * standardized)
    # Lognormal values are positive by definition; clamp numerical
    # underflow/overflow so extreme overrides cannot yield 0 or inf.
    return np.clip(values, tiny, np.finfo(np.float64).max)


def normal_scale(item: CatalogItem) -> float:
    """Return the standard deviation used for a normal item's measurements."""
    if item.lsl is not None and item.usl is not None:
        scale = (item.usl - item.lsl) / (2 * _NORMAL_SPEC_SIGMAS)
    elif item.usl is not None:
        scale = (item.usl - item.typical) / _NORMAL_SPEC_SIGMAS
    elif item.lsl is not None:
        scale = (item.typical - item.lsl) / _NORMAL_SPEC_SIGMAS
    else:
        scale = abs(item.typical) * 0.1
    if not math.isfinite(scale) or scale <= 0:
        return max(abs(item.typical) * 0.1, 1e-12)
    return scale


def lognormal_sigma(item: CatalogItem) -> float:
    """Return the log-space standard deviation used for a lognormal item."""
    typical = max(item.typical, np.finfo(np.float64).tiny)
    if item.lsl is not None and item.usl is not None and item.lsl > 0:
        sigma = math.log(item.usl / item.lsl) / (2 * _LOG_SPEC_SIGMAS)
    elif item.usl is not None and item.usl > 0:
        sigma = math.log(item.usl / typical) / _LOG_SPEC_SIGMAS
    elif item.lsl is not None and item.lsl > 0:
        sigma = math.log(typical / item.lsl) / _LOG_SPEC_SIGMAS
    else:
        sigma = 0.25
    if not math.isfinite(sigma) or sigma <= 0:
        return 0.25
    return sigma


def _fit(
    pairs: tuple[LinkagePair, ...],
    latent_targets: Mapping[tuple[str, str], float],
) -> tuple[dict[str, float], dict[tuple[str, str], float]]:
    """Fit WAT communalities and CP factor loadings by alternating least squares."""
    groups: dict[tuple[str, str], list[tuple[str, float]]] = {}
    wat_pairs: dict[str, list[tuple[str, str, float]]] = {}
    for pair in pairs:
        target = latent_targets[(pair.wat_item, pair.cp_item)]
        groups.setdefault((pair.cp_item, pair.factor), []).append((pair.wat_item, target))
        wat_pairs.setdefault(pair.wat_item, []).append((pair.cp_item, pair.factor, target))

    communality = {wat_item: 1.0 for wat_item in wat_pairs}
    loadings: dict[tuple[str, str], float] = {}
    cp_items = {pair.cp_item for pair in pairs}

    for _ in range(_FIT_ITERATIONS):
        max_change = 0.0
        for key, group_members in groups.items():
            numerator = math.fsum(target * communality[wat] for wat, target in group_members)
            denominator = math.fsum(communality[wat] ** 2 for wat, _ in group_members)
            updated = numerator / denominator if denominator > 0.0 else 0.0
            max_change = max(max_change, abs(updated - loadings.get(key, 0.0)))
            loadings[key] = updated

        for cp_item in cp_items:
            norm_squared = math.fsum(
                loadings[(cp_item, factor)] ** 2
                for factor in FACTORS
                if (cp_item, factor) in loadings
            )
            if norm_squared > 1.0:
                scale = 1.0 / math.sqrt(norm_squared)
                for factor in FACTORS:
                    key = (cp_item, factor)
                    if key in loadings:
                        loadings[key] *= scale

        for wat_item, wat_members in wat_pairs.items():
            numerator = math.fsum(
                target * loadings.get((cp_item, factor), 0.0)
                for cp_item, factor, target in wat_members
            )
            denominator = math.fsum(
                loadings.get((cp_item, factor), 0.0) ** 2 for cp_item, factor, _ in wat_members
            )
            updated = min(max(numerator / denominator, 0.0), 1.0) if denominator > 0.0 else 1.0
            max_change = max(max_change, abs(updated - communality[wat_item]))
            communality[wat_item] = updated

        if max_change < _FIT_TOLERANCE:
            break

    return communality, loadings


def _log_sigma(item: CatalogItem) -> float | None:
    if item.distribution == "lognormal":
        return lognormal_sigma(item)
    if item.distribution == "bernoulli":
        raise ValueError(f"bernoulli item '{item.id}' cannot participate in latent linkage")
    return None


def _lognormal_moment(sigma: float) -> float:
    """Return ``sqrt(exp(sigma^2) - 1)``; infinite when it overflows."""
    try:
        return math.sqrt(math.expm1(sigma * sigma))
    except OverflowError:
        return math.inf


def _latent_target(wat_item: CatalogItem, cp_item: CatalogItem, target_r: float) -> float:
    """Convert a target raw-scale correlation to its latent-space counterpart."""
    wat_sigma = _log_sigma(wat_item)
    cp_sigma = _log_sigma(cp_item)

    if wat_sigma is None and cp_sigma is None:
        latent_r = target_r
    elif wat_sigma is None:
        assert cp_sigma is not None
        moment = _lognormal_moment(cp_sigma)
        latent_r = 0.0 if not math.isfinite(moment) else target_r * moment / cp_sigma
    elif cp_sigma is None:
        moment = _lognormal_moment(wat_sigma)
        latent_r = 0.0 if not math.isfinite(moment) else target_r * moment / wat_sigma
    else:
        denominator = _lognormal_moment(wat_sigma) * _lognormal_moment(cp_sigma)
        if not math.isfinite(denominator):
            latent_r = 0.0
        else:
            argument = target_r * denominator
            latent_r = -1.0 if argument <= -1.0 else math.log1p(argument) / (wat_sigma * cp_sigma)

    return min(max(latent_r, -_MAX_ABS_LATENT_CORRELATION), _MAX_ABS_LATENT_CORRELATION)


def _achieved_correlation(wat_item: CatalogItem, cp_item: CatalogItem, latent_r: float) -> float:
    """Return the raw-scale correlation implied by a latent correlation."""
    wat_sigma = _log_sigma(wat_item)
    cp_sigma = _log_sigma(cp_item)

    if wat_sigma is None and cp_sigma is None:
        correlation = latent_r
    elif wat_sigma is None:
        assert cp_sigma is not None
        moment = _lognormal_moment(cp_sigma)
        correlation = 0.0 if not math.isfinite(moment) else latent_r * cp_sigma / moment
    elif cp_sigma is None:
        moment = _lognormal_moment(wat_sigma)
        correlation = 0.0 if not math.isfinite(moment) else latent_r * wat_sigma / moment
    else:
        denominator = _lognormal_moment(wat_sigma) * _lognormal_moment(cp_sigma)
        if not math.isfinite(denominator):
            correlation = 0.0
        else:
            try:
                correlation = math.expm1(latent_r * wat_sigma * cp_sigma) / denominator
            except OverflowError:
                correlation = math.inf if latent_r > 0 else -math.inf

    return min(max(correlation, -1.0), 1.0)
