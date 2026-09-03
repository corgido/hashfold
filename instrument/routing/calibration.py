"""Calibration evidence — envelope + provenance blocks for emissions.

Turns the static calibration blocks persisted inside a
`ReferenceDistribution` (self-distance null distribution, collection
window, recalibration policy, stability figures) into the advisory
evidence dicts the emission carries. Everything here is a pure
function of (reference bytes, measured distance): no wall clock, no
I/O, no state — age math against `max_age_days` is deliberately an
offline concern, because a timestamp read at emission time would make
the record non-reproducible.

Degradation is explicit and layered, matching the reference's vintage:

    seed (no self_distance)      -> status: seed_reference_no_confidence_envelope
    0.9.1 (n/median/p95 only)    -> within/beyond p95 + percentile_status
    0.10.0 (full null persisted) -> percentile + empirical exceedance

and per-feature calibration mirrors the same ladder: a reference
without stored percentile grids (`per_feature_quantiles` — all
bundled seeds and 0.9.1 references) degrades to
status: reference_lacks_feature_quantiles.

All floats that reach the emitted artifact go through
`instrument.kernel.quantize.q()`.
"""

from __future__ import annotations

import math
from typing import Optional

from instrument.kernel.quantize import q
from instrument.kernel.stats import bh_adjust, grid_cdf, midrank_percentile, two_sided_p
from instrument.routing.types import ReferenceDistribution, SelfDistanceStats


def distance_percentile(
    sd: Optional[SelfDistanceStats],
    distance: Optional[float],
) -> Optional[float]:
    """Mid-rank percentile of `distance` within a persisted null.

    Returns None when the reference carries no full null distribution
    (seed or 0.9.1-era `self_distance`) or the distance is
    unmeasurable. The lookup uses the quantized distance against the
    already-quantized stored values — the same q()-space the envelope's
    within/beyond comparison happens in — and the result is quantized
    for emission.
    """
    if sd is None or sd.values is None or distance is None:
        return None
    return q(midrank_percentile(list(sd.values), q(distance)))


def envelope_block(
    reference: ReferenceDistribution,
    distance: Optional[float],
) -> dict:
    """Advisory confidence envelope for the chosen reference.

    Positional, not evaluative: compares the document's distance to the
    calibration corpus's own self-distance distribution when the
    reference persists one (`tools.build_reference` under >=0.9.1).
    The bundled migrated seeds carry none — a seed cannot vouch for any
    distance, and the record says so instead of implying confidence.
    Pure quantized arithmetic; derived from attested distances plus
    pinned reference bytes (derived-advisory, like the arc).

    0.10.0: references that persist the full null distribution
    (`self_distance.values`, built as a cross-validated held-out null)
    additionally get `percentile` (mid-rank position of this distance
    within the null) and `empirical_exceedance` — the fraction of the
    baseline's own documents at least this far out, i.e. the empirical
    false-positive rate of alarming at this distance. A 0.9.1-era
    reference (summary stats only) says so via `percentile_status`.
    """
    sd = getattr(reference, "self_distance", None)
    if sd is None:
        return {"status": "seed_reference_no_confidence_envelope"}
    if distance is None:
        position = None
    else:
        position = (
            "within_p95" if q(distance) <= q(sd.p95) else "beyond_p95"
        )
    out: dict = {
        "self_distance_n": sd.n,
        "self_distance_median": sd.median,
        "self_distance_p95": sd.p95,
        "position": position,
    }
    if sd.values is None:
        out["percentile_status"] = "reference_predates_null_distribution"
        return out
    pct = distance_percentile(sd, distance)
    if pct is not None:
        out["percentile"] = pct
        out["empirical_exceedance"] = q(1.0 - pct / 100.0)
        out["basis"] = sd.basis
        out["percentile_method"] = "midrank"
    return out


def feature_calibration(features: dict, reference: ReferenceDistribution) -> dict:
    """Per-feature empirical calibration with BH FDR control.

    Fifty-seven features compared on every document makes false
    positives a certainty, not a risk — so the record carries the
    multiplicity correction instead of leaving it to the reader. For
    every feature that both has a stored 101-point percentile grid in
    the reference (`per_feature_quantiles`) and a finite value in this
    document, the block reports the feature's empirical CDF position
    (`percentile`), its two-sided empirical p-value (floored at
    1/(n+1), the resolution of an n-point calibration set), and its
    Benjamini-Hochberg q-value across the whole family.

    A q-value here is the smallest false discovery rate at which this
    feature would be called discordant from the reference. It is a
    descriptive coordinate, not a verdict: no alpha ships and nothing
    fires on this block, because the instrument emits reference
    points while decision rules — and their thresholds — belong to
    the user. (The worked "features with q <= 0.05" example in
    the docs is documentation, not code.)

    The family size `m` varies per document: a NaN/inf feature value
    is not evidence about the baseline, so it leaves the family
    rather than being imputed, and the record shows `m` so the
    multiplicity correction stays auditable against exactly the
    family it was computed over. Degradation is explicit: a reference
    without stored grids (all bundled seeds and 0.9.1 references)
    -> {"status": "reference_lacks_feature_quantiles"}; a document
    with no finite family member -> status
    "no_finite_features_for_calibration" with m = 0 in the policy.

    Pure function of (features, reference bytes). The lookup uses the
    quantized value against the already-quantized stored grid — the
    same q()-space as the envelope — and p-values are collected in
    sorted-feature-name order, so the BH pass and the emitted block
    are deterministic. All emitted floats go through q().
    """
    grids = getattr(reference, "per_feature_quantiles", None)
    if not grids:
        return {"status": "reference_lacks_feature_quantiles"}
    family = sorted(
        name for name, value in features.items()
        if name in grids
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )
    family_policy = {
        "method": "benjamini_hochberg",
        "family": (
            "reference features with finite reading value "
            "and stored quantile grid"
        ),
        "m": len(family),
        "sidedness": "two_sided",
        "p_resolution_floor": q(1.0 / (reference.n + 1)),
    }
    if not family:
        return {
            "status": "no_finite_features_for_calibration",
            "family_policy": family_policy,
        }
    per_feature: dict = {}
    ps: list[float] = []
    for name in family:
        value = q(features[name])
        F = grid_cdf(list(grids[name]), value)
        ps.append(two_sided_p(F, reference.n))
        per_feature[name] = {
            "value": value,
            "percentile": q(100.0 * F),
        }
    for name, p, qv in zip(family, ps, bh_adjust(ps)):
        per_feature[name]["p_two_sided"] = q(p)
        per_feature[name]["q_value"] = q(qv)
    return {
        "per_feature": per_feature,
        "family_policy": family_policy,
        "reference_n": reference.n,
    }


def provenance_block(reference: ReferenceDistribution) -> dict:
    """Static provenance echo for the chosen reference.

    Repeats bytes already pinned inside the reference file —
    calibration date, collection window, corpus size, recalibration
    policy, and a two-number summary of the stored jackknife stability
    block — so an emission is auditable without the reference file in
    hand. Nothing here is computed against a wall clock: whether the
    baseline has exceeded `max_age_days` is an offline check.

    Pre-0.10 references (no 0.10 calibration block at all) degrade to
    `{"provenance_status": "pre_0_10_reference"}`; partially populated
    references echo what exists.
    """
    has_any = any(
        getattr(reference, field, None) is not None
        for field in (
            "collection_window", "provenance",
            "recalibration_policy", "stability",
        )
    )
    if not has_any:
        return {"provenance_status": "pre_0_10_reference"}
    out: dict = {
        "calibration_date": reference.calibration_date,
        "n": reference.n,
    }
    if reference.collection_window is not None:
        out["collection_window"] = reference.collection_window
    if reference.recalibration_policy is not None:
        out["recalibration_policy"] = dict(reference.recalibration_policy)
    summary = _stability_summary(reference.stability)
    if summary is not None:
        out["stability_summary"] = summary
    return out


def _stability_summary(stability: Optional[dict]) -> Optional[dict]:
    """Worst-case pair from a stored stability block.

    `max_centroid_shift_std` — the largest centroid displacement (in
    reference std units, over all PCs and all jackknife replicates) —
    and `min_loading_alignment` — the smallest |cos| between full and
    replicate loading vectors. Large shift / low alignment means the
    baseline's geometry is driven by a small slice of the corpus.
    """
    if not stability:
        return None
    shifts = stability.get("centroid_shift_std_units") or {}
    aligns = stability.get("loading_alignment_abs_cos") or {}
    maxima = [v.get("max") for v in shifts.values() if v.get("max") is not None]
    minima = [v.get("min") for v in aligns.values() if v.get("min") is not None]
    if not maxima and not minima:
        return None
    out: dict = {}
    if maxima:
        out["max_centroid_shift_std"] = q(max(maxima))
    if minima:
        out["min_loading_alignment"] = q(min(minima))
    return out
