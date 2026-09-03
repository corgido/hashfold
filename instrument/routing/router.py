"""Register router — cohort-aware reference selection.

Given a reading's flat feature dict, either:

    1. honours a caller-declared `register_hint` and verifies the
       reading is within distance of the declared cohort's centroid, or
    2. auto-selects the nearest cohort by standardised
       PC-centroid L2 distance.

Emits a `RegisterMatch` describing the decision and flagging any
issue (hint/detection mismatch, unmeasurable projection, distance
beyond the threshold).

Distances are in standardised PC units (each axis divided by the
reference's per-composite std before squaring), so the threshold
has a consistent interpretation across references. Default
threshold = 3.0 ≈ "3σ in each PC".

ADVISORY: the per-reference distances (raw measurements) are
canonical and exposed via `distances_to_all_references`. The
single-cohort pick (nearest reference) and the match/drift/break
verdict are inference — convenience for monitoring, not the
compliance record. Compliance pipelines should record the full
distances vector and apply their own cohort logic.
"""

from __future__ import annotations

import math
from typing import Optional

from instrument.routing.calibration import distance_percentile
from instrument.routing.pc import project_pc_composites
from instrument.routing.reference import list_references, load_reference
from instrument.routing.types import (
    ReferenceDistribution,
    RegisterMatch,
    classify_length_cohort,
)

DEFAULT_DISTANCE_THRESHOLD = 3.0


class NoComparableReferenceError(LookupError):
    """Raised when no reference is bundled at all, or the reading
    cannot be projected onto any reference's PC space."""


class UnknownRegisterHintError(NoComparableReferenceError, ValueError):
    """Raised when a caller-declared `register_hint` names a cohort
    with no bundled reference.

    Subclasses ValueError so the serve layer maps it to HTTP 400 (a
    client error — the hint is wrong), and NoComparableReferenceError
    for backwards compatibility with callers that catch the broad
    class. `instrument.emit` re-raises it instead of degrading to an
    "unprojectable" emission: a typo'd hint should be an error the
    caller sees, not a silently degraded measurement.
    """


def _standardised_distance(
    pc_values: dict[str, Optional[float]],
    reference: ReferenceDistribution,
) -> Optional[float]:
    """L2 distance in standardised PC units."""
    total = 0.0
    for pc_name, centroid in reference.pc_centroid.items():
        v = pc_values.get(pc_name)
        if v is None:
            return None
        s = reference.pc_composites[pc_name].std
        if s == 0 or math.isnan(s):
            return None
        d = (v - centroid) / s
        total += d * d
    return math.sqrt(total)


def distances_to_all_references(
    features: dict[str, Optional[float]],
) -> dict[tuple[str, str], Optional[float]]:
    """Distance from a reading to every bundled reference, keyed by
    `(name, version)`. `None` = unmeasurable for that reference.

    Public so callers (e.g. the audit shape) can record position
    against every reference rather than relying on the router's
    single-winner pick.
    """
    out: dict[tuple[str, str], Optional[float]] = {}
    for name, version in list_references():
        ref = load_reference(name, version)
        pcs = project_pc_composites(features, ref)
        out[(name, version)] = _standardised_distance(pcs, ref)
    return out


def distances_as_records(
    distances: dict[tuple[str, str], Optional[float]],
) -> list[dict]:
    """JSON-friendly list-of-records form of distances_to_all_references.

    Each record is `{"name": str, "version": str, "distance": float|None,
    "percentile": float|None}`. `percentile` (0.10.0) is the mid-rank
    position of the record's distance within THAT reference's persisted
    self-distance null distribution — None when the reference carries no
    full null (seeds, 0.9.1-era references) or the distance is
    unmeasurable. Sorted by (name, version) for byte-stable output.
    """
    return [
        {
            "name": name,
            "version": version,
            "distance": d,
            "percentile": distance_percentile(
                load_reference(name, version).self_distance, d,
            ),
        }
        for (name, version), d in sorted(distances.items())
    ]


def _canonical_reference_for_cohort(
    cohort: str,
    reading_length_cohort: Optional[str] = None,
) -> Optional[ReferenceDistribution]:
    """Preferred reference for a register cohort.

    Ranking:
        1. production before exploratory
        2. length_cohort matching the reading's length before mismatches
        3. ascending version
    """
    matches: list[ReferenceDistribution] = []
    for name, version in list_references():
        ref = load_reference(name, version)
        if ref.register_cohort == cohort:
            matches.append(ref)
    if not matches:
        return None

    def _rank(r: ReferenceDistribution) -> tuple:
        if reading_length_cohort is None:
            length_bucket: tuple[int, ...] = (0,)
        elif r.length_cohort.label == reading_length_cohort:
            length_bucket = (0,)
        elif r.length_cohort.label == "mixed":
            length_bucket = (1,)
        else:
            length_bucket = (2,)
        return (r.reliability != "production",) + length_bucket + (r.version,)

    matches.sort(key=_rank)
    return matches[0]


def _nearest_cohort(
    distances: dict[tuple[str, str], Optional[float]],
) -> Optional[str]:
    """Cohort with the smallest distance, or `None` if every distance is `None`."""
    best_key: Optional[tuple[str, str]] = None
    best_d: Optional[float] = None
    for key, d in distances.items():
        if d is None:
            continue
        if best_d is None or d < best_d:
            best_d = d
            best_key = key
    if best_key is None:
        return None
    name, version = best_key
    return load_reference(name, version).register_cohort


def _length_mismatch_flag(
    reading_length_cohort: Optional[str],
    reference: ReferenceDistribution,
) -> Optional[str]:
    """`length_mismatch:<a>_vs_<b>` when clearly outside the reference's
    cohort. `mixed` absorbs any reading cohort without flagging."""
    if reading_length_cohort is None:
        return None
    if reference.length_cohort.label in ("mixed", reading_length_cohort):
        return None
    return (
        f"length_mismatch:{reading_length_cohort}_vs_"
        f"{reference.length_cohort.label}"
    )


def route(
    features: dict[str, Optional[float]],
    register_hint: Optional[str] = None,
    distance_threshold: float = DEFAULT_DISTANCE_THRESHOLD,
    reading_n_words: Optional[int] = None,
) -> tuple[ReferenceDistribution, RegisterMatch]:
    """Select a reference for a reading and describe the register match.

    Raises `NoComparableReferenceError` when (a) `register_hint`
    is given but no reference is bundled for that cohort, or
    (b) no reference is bundled at all, or (c) the reading cannot
    be projected onto any reference's PC space.
    """
    all_refs = list_references()
    if not all_refs:
        raise NoComparableReferenceError(
            "no references bundled in the routing package"
        )

    reading_length_cohort: Optional[str] = (
        classify_length_cohort(reading_n_words)
        if reading_n_words is not None else None
    )

    distances = distances_to_all_references(features)

    if register_hint is not None:
        chosen = _canonical_reference_for_cohort(
            register_hint, reading_length_cohort,
        )
        if chosen is None:
            available = sorted(
                {load_reference(n, v).register_cohort for n, v in all_refs}
            )
            raise UnknownRegisterHintError(
                f"no reference for cohort {register_hint!r}; "
                f"available cohorts: {available}"
            )
        detected = _nearest_cohort(distances)
        d_to_hint = distances.get((chosen.name, chosen.version))

        flags: list[str] = []
        if d_to_hint is None:
            match = "unmeasurable"
            flags.append("reading_not_projectable")
        elif d_to_hint > distance_threshold:
            match = "distance_exceeds_threshold"
        else:
            match = "match"

        if detected is not None and detected != register_hint:
            flags.append("hint_mismatch")
        lm = _length_mismatch_flag(reading_length_cohort, chosen)
        if lm:
            flags.append(lm)

        return chosen, RegisterMatch(
            declared_hint=register_hint,
            detected_cohort=detected,
            reference_cohort=chosen.register_cohort,
            distance=d_to_hint,
            match=match,
            flags=tuple(flags),
        )

    # Auto-select: nearest cohort.
    detected = _nearest_cohort(distances)
    if detected is None:
        raise NoComparableReferenceError(
            "reading not projectable onto any reference's PC space "
            "(all features NaN or missing)"
        )
    chosen = _canonical_reference_for_cohort(detected, reading_length_cohort)
    assert chosen is not None, "detected cohort must have a canonical reference"
    d = distances[(chosen.name, chosen.version)]

    # 0.9.1: auto-selection is the NORMAL no-hint path; the flag is a
    # neutral statement of how the reference was chosen, not a warning
    # (the 0.9.0 name "undeclared_hint" fired on every default request
    # and read as a defect).
    flags_auto: list[str] = ["auto_routed"]
    if d is not None and d > distance_threshold:
        match = "distance_exceeds_threshold"
        flags_auto.append("auto_selected_distance_exceeds_threshold")
    else:
        match = "match"
    lm = _length_mismatch_flag(reading_length_cohort, chosen)
    if lm:
        flags_auto.append(lm)

    return chosen, RegisterMatch(
        declared_hint=None,
        detected_cohort=detected,
        reference_cohort=chosen.register_cohort,
        distance=d,
        match=match,
        flags=tuple(flags_auto),
    )
