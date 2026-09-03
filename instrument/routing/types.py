"""Routing types — ReferenceDistribution and associated stats.

Dataclasses are frozen and JSON-serialisable via `dataclasses.asdict`.
Numpy-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_SHORT_MAX = 2000
_LONG_MIN = 8000


def classify_length_cohort(n_words: int) -> str:
    """Return the length cohort label for a single document.

    Labels: "short" (<2000 words), "medium" ([2000, 8000) words),
    "long" (>=8000 words). The reference-level "mixed" label is
    NOT returned from this function; it applies only to a
    reference whose calibration corpus spans multiple
    document-level labels.
    """
    if n_words < _SHORT_MAX:
        return "short"
    if n_words >= _LONG_MIN:
        return "long"
    return "medium"


@dataclass(frozen=True)
class FeatureStats:
    mean: float
    std: float
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass(frozen=True)
class CompositeStats:
    mean: float
    std: float
    p05: float
    p25: float
    p50: float
    p75: float
    p95: float


@dataclass(frozen=True)
class SelfDistanceStats:
    """The calibration corpus's own distance distribution against the
    reference built from it (0.9.1). Persisted by tools.build_reference;
    absent (None) on the bundled migrated seeds — a seed cannot vouch
    for any distance, and the emission says so explicitly.

    0.10.0 additions (both None on 0.9.1-era references):
    `values` is the full sorted null distribution (quantized), so the
    runtime can report a percentile rather than only within/beyond p95;
    `basis` records how it was obtained ("cross_validated_10fold" for
    the honest held-out null, "resubstitution" for the small-corpus
    fallback that understates spread).
    """
    n: int
    median: float
    p95: float
    values: Optional[tuple[float, ...]] = None
    basis: Optional[str] = None


@dataclass(frozen=True)
class LengthCohort:
    label: str
    n_words_min: int
    n_words_max: int
    n_words_p25: int
    n_words_median: int
    n_words_p75: int


@dataclass(frozen=True)
class ReferenceDistribution:
    """A named baseline distribution."""
    name: str
    version: str
    status: str
    register_cohort: str
    length_cohort: LengthCohort
    scope_statement: str
    calibration_date: str
    corpus_description: str
    n: int
    instrument_version: str
    schema_version: str
    commit_hash: str
    reliability: str
    per_feature: dict[str, FeatureStats]
    pc_centroid: dict[str, float]
    pc_composites: dict[str, CompositeStats]
    pc_loadings: dict[str, dict[str, float]]
    pc_zscore_mean: dict[str, float]
    pc_zscore_std: dict[str, float]
    self_distance: Optional[SelfDistanceStats] = None
    # 0.10.0 provenance/stability blocks. All optional so 0.9.x
    # references (bundled seeds, user refs) load unchanged; the
    # runtime degrades explicitly when they are absent
    # (routing/calibration.py).
    collection_window: Optional[str] = None
    provenance: Optional[dict] = None
    recalibration_policy: Optional[dict] = None
    stability: Optional[dict] = None
    per_feature_quantiles: Optional[dict[str, tuple[float, ...]]] = None


@dataclass(frozen=True)
class RegisterMatch:
    """How a reading's cohort relates to the reference's.

    `distance` is standardised L2 in PC space; `match` is the
    derived verdict (cohort-terms only, not normative).
    """
    declared_hint: Optional[str]
    detected_cohort: Optional[str]
    reference_cohort: str
    distance: Optional[float]
    match: str
    flags: tuple[str, ...] = ()


# ---------- (de)serialisation ----------------------------------------------

def _asdict_stats(s) -> dict:
    return {
        "mean": s.mean, "std": s.std,
        "p05": s.p05, "p25": s.p25, "p50": s.p50, "p75": s.p75, "p95": s.p95,
    }


def reference_to_dict(ref: ReferenceDistribution) -> dict:
    """Serialise a ReferenceDistribution to a plain dict.

    Inverse of `reference_from_dict`.
    """
    return {
        "name": ref.name,
        "version": ref.version,
        "status": ref.status,
        "register_cohort": ref.register_cohort,
        "length_cohort": {
            "label": ref.length_cohort.label,
            "n_words_min": ref.length_cohort.n_words_min,
            "n_words_max": ref.length_cohort.n_words_max,
            "n_words_p25": ref.length_cohort.n_words_p25,
            "n_words_median": ref.length_cohort.n_words_median,
            "n_words_p75": ref.length_cohort.n_words_p75,
        },
        "scope_statement": ref.scope_statement,
        "calibration_date": ref.calibration_date,
        "corpus_description": ref.corpus_description,
        "n": ref.n,
        "instrument_version": ref.instrument_version,
        "schema_version": ref.schema_version,
        "commit_hash": ref.commit_hash,
        "reliability": ref.reliability,
        "per_feature": {k: _asdict_stats(v) for k, v in ref.per_feature.items()},
        "pc_centroid": dict(ref.pc_centroid),
        "pc_composites": {k: _asdict_stats(v) for k, v in ref.pc_composites.items()},
        "pc_loadings": {k: dict(v) for k, v in ref.pc_loadings.items()},
        "pc_zscore_mean": dict(ref.pc_zscore_mean),
        "pc_zscore_std": dict(ref.pc_zscore_std),
        **(
            {"self_distance": _self_distance_to_dict(ref.self_distance)}
            if ref.self_distance is not None else {}
        ),
        **(
            {"collection_window": ref.collection_window}
            if ref.collection_window is not None else {}
        ),
        **(
            {"provenance": dict(ref.provenance)}
            if ref.provenance is not None else {}
        ),
        **(
            {"recalibration_policy": dict(ref.recalibration_policy)}
            if ref.recalibration_policy is not None else {}
        ),
        **(
            {"stability": dict(ref.stability)}
            if ref.stability is not None else {}
        ),
        **(
            {"per_feature_quantiles": {
                k: list(v) for k, v in ref.per_feature_quantiles.items()
            }}
            if ref.per_feature_quantiles is not None else {}
        ),
    }


def _self_distance_to_dict(sd: SelfDistanceStats) -> dict:
    out: dict = {"n": sd.n, "median": sd.median, "p95": sd.p95}
    if sd.values is not None:
        out["values"] = list(sd.values)
    if sd.basis is not None:
        out["basis"] = sd.basis
    return out


def reference_from_dict(d: dict) -> ReferenceDistribution:
    """Deserialise a ReferenceDistribution from a plain dict.

    `scope_statement` is mandatory and must be non-empty.
    `length_cohort` is optional; missing falls back to a
    synthesised "mixed" cohort with zero word counts (legacy
    pre-schema-0.6.0 references).
    """
    scope = d.get("scope_statement", "")
    if not scope or not scope.strip():
        raise ValueError(
            "ReferenceDistribution.scope_statement is mandatory and must be non-empty"
        )
    lc_raw = d.get("length_cohort")
    if lc_raw:
        length_cohort = LengthCohort(
            label=lc_raw["label"],
            n_words_min=lc_raw["n_words_min"],
            n_words_max=lc_raw["n_words_max"],
            n_words_p25=lc_raw["n_words_p25"],
            n_words_median=lc_raw["n_words_median"],
            n_words_p75=lc_raw["n_words_p75"],
        )
    else:
        length_cohort = LengthCohort(
            label="mixed",
            n_words_min=0,
            n_words_max=0,
            n_words_p25=0,
            n_words_median=0,
            n_words_p75=0,
        )
    return ReferenceDistribution(
        name=d["name"],
        version=d["version"],
        status=d["status"],
        register_cohort=d["register_cohort"],
        length_cohort=length_cohort,
        scope_statement=scope,
        calibration_date=d["calibration_date"],
        corpus_description=d["corpus_description"],
        n=d["n"],
        instrument_version=d["instrument_version"],
        schema_version=d["schema_version"],
        commit_hash=d["commit_hash"],
        reliability=d["reliability"],
        per_feature={k: FeatureStats(**v) for k, v in d["per_feature"].items()},
        pc_centroid=dict(d["pc_centroid"]),
        pc_composites={
            k: CompositeStats(**v) for k, v in d["pc_composites"].items()
        },
        pc_loadings={k: dict(v) for k, v in d["pc_loadings"].items()},
        pc_zscore_mean=dict(d["pc_zscore_mean"]),
        pc_zscore_std=dict(d["pc_zscore_std"]),
        self_distance=(
            SelfDistanceStats(
                n=d["self_distance"]["n"],
                median=d["self_distance"]["median"],
                p95=d["self_distance"]["p95"],
                values=(
                    tuple(d["self_distance"]["values"])
                    if d["self_distance"].get("values") is not None else None
                ),
                basis=d["self_distance"].get("basis"),
            )
            if d.get("self_distance") else None
        ),
        collection_window=d.get("collection_window"),
        provenance=(
            dict(d["provenance"]) if d.get("provenance") is not None else None
        ),
        recalibration_policy=(
            dict(d["recalibration_policy"])
            if d.get("recalibration_policy") is not None else None
        ),
        stability=(
            dict(d["stability"]) if d.get("stability") is not None else None
        ),
        per_feature_quantiles=(
            {k: tuple(v) for k, v in d["per_feature_quantiles"].items()}
            if d.get("per_feature_quantiles") is not None else None
        ),
    )
