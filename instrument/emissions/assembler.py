"""assemble a DocumentEmission from reading + trajectory + catalog.

Pure, deterministic, numpy-free. The assembler composes what the
reading/routing layers already produced; it does not compute
features.

Flow: trajectory → arc + per-slice labels; convergence → coherence;
features + trajectory + soft_flags → flags; routing → register;
all → DocumentEmission + EmissionMetadata.
"""

from __future__ import annotations

import dataclasses
import hashlib
import math
from datetime import datetime, timezone
from typing import Optional

from instrument.emissions.catalog import classify_by_max
from instrument.emissions.catalog_v2 import SOURCE_SHA256 as _CATALOG_V2_SHA256
from instrument.emissions.coherence import compute_coherence
from instrument.emissions.flags import FLAG_DETECTORS, FlagContext
from instrument.emissions.slice_labels import (
    SLICE_LABEL_DETECTORS,
    SliceLabelContext,
)
from instrument.emissions.types import (
    ArcEmission,
    DimensionSummary,
    DocumentEmission,
    EmissionMetadata,
    Flag,
    RegisterEmission,
    SliceEmission,
)
from instrument.kernel.quantize import q, quantize
from instrument.lexicons import LEXICON_VERSION

# Router uses _standardised_distance: feature-z-scored L2 distance in
# PC space. Surfaced in metadata so future migrations (e.g. true
# Mahalanobis) become explicit and version-traceable.
DISTANCE_METHOD = "feature_zscore_l2"

_CATALOG_SHA_BY_VERSION = {
    "v2": _CATALOG_V2_SHA256,
}


def _catalog_sha256_for(version: str) -> str:
    return _CATALOG_SHA_BY_VERSION.get(version, "unknown")


def _reproducibility_hash(*parts: str) -> str:
    """SHA256 of the pipe-joined stable components.

    User recomputes from the ten stable metadata fields (in order:
    instrument_version, schema_version, emission_version,
    lexicon_version, catalog_sha256, distance_method, input_sha256,
    content_sha256, reading_sha256, core_code_sha256) and compares
    against the stored hash to verify the emission is reproducible
    under the same instrument/lexicon/catalog pin.
    """
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()

TRAJECTORY_KEYS = (
    "lexical_novelty",
    "sentence_length_variance",
    "modal_density",
    "negation_density",
)


def _is_nan(v) -> bool:
    try:
        return math.isnan(v)
    except TypeError:
        return False


def _finite(xs) -> list[float]:
    return [float(x) for x in xs if x is not None and not _is_nan(x)]


def _slice_mean(trajectory: dict) -> dict[str, Optional[float]]:
    """Per-feature mean across measurable slices — the document's
    own baseline for self-referential flag thresholds."""
    out: dict[str, Optional[float]] = {}
    for k in TRAJECTORY_KEYS:
        xs = _finite(trajectory.get(k, []))
        out[k] = (sum(xs) / len(xs)) if xs else None
    return out


def _dimension_summary(xs: list) -> DimensionSummary:
    clean = _finite(xs)
    if not clean:
        return DimensionSummary(
            start=None, end=None, slope=None, range=None, monotone=None,
        )
    start = clean[0]
    end = clean[-1]
    rng = max(clean) - min(clean)
    monotone: Optional[bool] = True
    if len(clean) >= 2:
        signs = [
            1 if clean[i + 1] > clean[i]
            else (-1 if clean[i + 1] < clean[i] else 0)
            for i in range(len(clean) - 1)
        ]
        positive = any(s > 0 for s in signs)
        negative = any(s < 0 for s in signs)
        monotone = not (positive and negative)
    if len(clean) < 2:
        slope: Optional[float] = None
    else:
        mx = (len(clean) - 1) / 2.0
        my = sum(clean) / len(clean)
        num = sum((i - mx) * (y - my) for i, y in enumerate(clean))
        den = sum((i - mx) * (i - mx) for i in range(len(clean)))
        slope = num / den if den > 0 else None
    return DimensionSummary(
        start=q(start), end=q(end), slope=q(slope),
        range=q(rng), monotone=monotone,
    )


def _assemble_arc(trajectory: dict, catalog: dict) -> ArcEmission:
    """Per-slice × per-dimension, plus per-slice catalog labels."""
    slice_label_defs = catalog.get("arc", {}).get("slice_labels", [])
    n_slices = 0
    for k in TRAJECTORY_KEYS:
        n_slices = max(n_slices, len(trajectory.get(k, [])))

    slice_mean = _slice_mean(trajectory)

    per_slice: list[SliceEmission] = []
    prev_values: dict[str, Optional[float]] = {k: None for k in TRAJECTORY_KEYS}
    for i in range(n_slices):
        values: dict[str, Optional[float]] = {}
        for k in TRAJECTORY_KEYS:
            series = trajectory.get(k, [])
            v = series[i] if i < len(series) else None
            if v is None or (isinstance(v, float) and _is_nan(v)):
                values[k] = None
            else:
                values[k] = float(v)
        deltas: dict[str, Optional[float]] = {}
        for k in TRAJECTORY_KEYS:
            cur = values[k]
            prv = prev_values[k]
            if i == 0 or cur is None or prv is None:
                deltas[k] = None
            else:
                deltas[k] = q(cur - prv)
        ctx = SliceLabelContext(
            traj=trajectory, index=i, n_slices=n_slices, slice_mean=slice_mean,
        )
        labels: list[str] = []
        for lbl_def in slice_label_defs:
            detector = SLICE_LABEL_DETECTORS[lbl_def["detector"]]
            if detector(ctx, lbl_def.get("params", {})):
                labels.append(lbl_def["id"])
        per_slice.append(SliceEmission(
            index=i, values=values, deltas=deltas, labels=tuple(labels),
        ))
        prev_values = values

    per_dimension = {
        k: _dimension_summary(trajectory.get(k, [])) for k in TRAJECTORY_KEYS
    }

    return ArcEmission(
        per_slice=tuple(per_slice),
        per_dimension=per_dimension,
        n_slices=n_slices,
    )


def _assemble_flags(
    *,
    catalog: dict,
    trajectory: dict,
    slice_mean: dict,
    features: dict,
    soft_flags: tuple[str, ...],
    convergence: Optional[dict],
    n_slices: int,
    n_words: int,
    text: str,
) -> tuple[Flag, ...]:
    """Run every catalog flag detector; collect those that fire."""
    ctx = FlagContext(
        traj=trajectory,
        slice_mean=slice_mean,
        features=features,
        soft_flags=soft_flags,
        convergence=convergence,
        n_slices=n_slices,
        n_words=n_words,
        text=text,
    )
    out: list[Flag] = []
    for flag_def in catalog.get("flags", []):
        detector = FLAG_DETECTORS[flag_def["detector"]]
        evidence = detector(ctx, flag_def.get("params", {}))
        if evidence is None:
            continue
        out.append(Flag(
            type=flag_def["id"],
            severity=flag_def.get("severity", "notable"),
            evidence=quantize(evidence),
        ))
    return tuple(out)


def assemble(
    catalog: dict,
    register_label: str,
    register_cohort: str,
    register_distance: Optional[float],
    register_evidence: dict,
    trajectory: dict,
    features: dict,
    soft_flags: tuple[str, ...],
    convergence: Optional[dict],
    n_words: int,
    n_sentences: int,
    instrument_version: str,
    schema_version: str,
    input_sha256: str = "",
    content_sha256: str = "",
    reading_sha256: str = "",
    core_code_sha256: str = "",
    reading_below_envelope: bool = False,
) -> DocumentEmission:
    """Compose the four-part emission from pre-computed inputs.

    `input_sha256` is computed by the caller at the transport boundary
    over the RAW input bytes (emit.py) — the assembler never re-derives
    it from decoded text, so provenance is transport-independent.

    `content_sha256` is a hash over the quantised canonical measurement
    record (reading + distances), computed by the caller where both are
    available. It is folded into `reproducibility_hash` so the hash fails
    when the measured numbers drift, not only when a version pin changes.
    """
    # P0-1: quantise numeric inputs so the emitted arc / distances are
    # byte-identical across hosts. Computation upstream is full-precision.
    trajectory = quantize(trajectory)
    register_distance = q(register_distance)
    if "distances_to_all_references" in register_evidence:
        register_evidence = {
            **register_evidence,
            "distances_to_all_references": quantize(
                register_evidence["distances_to_all_references"]
            ),
        }
    arc = _assemble_arc(trajectory, catalog)
    slice_mean = _slice_mean(trajectory)
    flags = _assemble_flags(
        catalog=catalog,
        trajectory=trajectory,
        slice_mean=slice_mean,
        features=features,
        soft_flags=soft_flags,
        convergence=convergence,
        n_slices=arc.n_slices,
        n_words=n_words,
        text=register_evidence.get("_text", ""),
    )
    coherence = compute_coherence(
        convergence,
        bands=catalog.get("coherence", {}).get("bands"),
    )
    # D2 guard (0.9.1): the advisory coherence band must not contradict
    # the register layer. On degenerate/unprojectable input the few
    # measurable axes can trivially agree; banding that as "high" next
    # to register:unprojectable misleads. The scalar (a true agreement
    # measurement) is preserved; only the band degrades.
    if coherence.label in ("high", "moderate", "low"):
        degraded_reason = None
        if register_label == "unprojectable":
            degraded_reason = "register_unprojectable"
        elif register_label == "structural":
            degraded_reason = "register_structural"
        elif reading_below_envelope:
            degraded_reason = "below_envelope"
        if degraded_reason is not None:
            coherence = dataclasses.replace(
                coherence,
                label="unmeasurable",
                evidence={**coherence.evidence, "degraded_reason": degraded_reason},
            )

    register = RegisterEmission(
        label=register_label,
        cohort=register_cohort,
        distance=register_distance,
        evidence={
            k: v for k, v in register_evidence.items() if not k.startswith("_")
        },
    )

    emission_version = catalog["version"]
    catalog_sha256 = _catalog_sha256_for(emission_version)
    repro = _reproducibility_hash(
        instrument_version,
        schema_version,
        emission_version,
        LEXICON_VERSION,
        catalog_sha256,
        DISTANCE_METHOD,
        input_sha256,
        content_sha256,
        reading_sha256,
        core_code_sha256,
    )

    return DocumentEmission(
        register=register,
        arc=arc,
        flags=flags,
        coherence=coherence,
        metadata=EmissionMetadata(
            emission_version=emission_version,
            instrument_version=instrument_version,
            schema_version=schema_version,
            n_words=n_words,
            n_sentences=n_sentences,
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            lexicon_version=LEXICON_VERSION,
            catalog_sha256=catalog_sha256,
            distance_method=DISTANCE_METHOD,
            input_sha256=input_sha256,
            content_sha256=content_sha256,
            reading_sha256=reading_sha256,
            core_code_sha256=core_code_sha256,
            reproducibility_hash=repro,
        ),
    )


def register_band_label(
    distance: Optional[float], catalog: dict,
) -> Optional[str]:
    """Classify a register distance into its catalog band label."""
    return classify_by_max(distance, catalog.get("register", {}).get("bands", []))
