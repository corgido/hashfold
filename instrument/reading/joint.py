"""joint — the canonical top-level reading.

`joint_reading(text)` composes the flat 13-feature view, the
extended 37-feature view, the 7-feature stylometry view, the
12-feature distributional view, and the 5-axis convergence between
the compact and extended views into one schema-versioned dict.

Stdlib only. No file I/O. No env reads. Safe to import on any
read-only stateless runtime.
"""

from __future__ import annotations

from datetime import datetime, timezone

from instrument.kernel.features.stylometry import (
    FEATURE_ORDER as STYLOMETRY_FEATURE_ORDER,
    stylometry_compact,
)
from instrument.kernel.cleaning import canonicalise
from instrument.kernel.features.trajectory_features import read_trajectory
from instrument.kernel.quantize import quantize
from instrument.kernel.regimes import regime_elegant
from instrument.kernel.scripts import nonlatin_stats
from instrument.kernel.tokens import tokenise
from instrument.reading import convergence as _convergence
from instrument.reading.distributional import (
    FEATURE_ORDER as DISTRIBUTIONAL_FEATURE_ORDER,
    distributional_reading,
)
from instrument.reading.extended import F, ALL_FEATURE_KEYS as OTHER_FEATURE_ORDER
from instrument.reading.flat import FEATURE_ORDER as SHAPER_FEATURE_ORDER, flat_reading

SCHEMA_VERSION = "0.10.0"

# Soft-envelope thresholds from other-shaper/README.md. Used for advisory
# flags, not hard gates. Shaper has its own hard 150-word floor.
_OTHER_HARD = 60
_OTHER_JOINT = 120
_OTHER_RST = 200

# Soft-flag thresholds for non-Latin content (0.9.1, D5): the
# tokeniser is ASCII-Latin, so non-Latin text contributes nothing to
# any measurement — a document with this much of it is only partially
# measured and the record should say so.
_NONLATIN_FLAG_MIN_LETTERS = 50
_NONLATIN_FLAG_MIN_RATIO = 0.10


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _other_soft_flags(n_words: int) -> list[str]:
    flags: list[str] = []
    if n_words < _OTHER_HARD:
        flags.append("below_hard_floor")
    if n_words < _OTHER_JOINT:
        flags.append("joint_cosine_unreliable")
    if n_words < _OTHER_RST:
        flags.append("rst_unreliable")
    return flags


def joint_reading(text: str, *, _tokens=None) -> dict:
    """Compute the joint reading.

    Returns a JSON-serialisable dict matching legacy schema 0.6.0:

        schema_version   str   — reading-schema version.
        ts               str   — UTC timestamp (informational).
        n_words          dict  — {shaper, other_shaper} per-view counts.
        below_envelope   dict  — {shaper: bool, other_shaper_soft_flags: [str]}
        soft_flags       list  — advisory flags (e.g. malformed_fence_recovered).
        shaper           dict  — {feature_order, features} (13 features).
        other_shaper     dict  — {feature_order, features} (37 features).
        stylometry       dict  — {feature_order, features} (7 features).
        convergence      dict  — see reading.convergence.compute.
        trajectory       dict  — {regime, boundary_level, n_slices,
                                  slices, features}: the per-slice
                                  streams of the four register features
                                  on the elegant slicing of the cleaned
                                  text. Part of the attested reading
                                  (covered by reading/content hashes);
                                  the emissions arc derives from it.
    """
    # Canonicalise first (idempotent): the reading is a function of the
    # canonical measurement text, whatever transport the caller used.
    text = canonicalise(text)
    tokens = _tokens or tokenise(text)

    shaper_flat = flat_reading(tokens)
    other_fv = F(
        text,
        text_id="joint",
        cleaned=tokens.cleaned,
        sentences_by_paragraph=tokens.paragraph_sentences,
    )
    other_dict = other_fv.to_dict()
    stylometry_flat = stylometry_compact(tokens)
    dist_flat = distributional_reading(tokens)

    shaper_features = {
        k: shaper_flat[k] for k in SHAPER_FEATURE_ORDER if k in shaper_flat
    }
    other_features = {
        k: other_dict[k] for k in OTHER_FEATURE_ORDER if k in other_dict
    }
    stylometry_features = {
        f"stylometry.{k}": stylometry_flat[k] for k in STYLOMETRY_FEATURE_ORDER
    }
    distributional_features = {
        f"dist.{k}": dist_flat[k] for k in DISTRIBUTIONAL_FEATURE_ORDER
    }

    shaper_below = bool(shaper_flat.get("below_envelope", False))
    other_flags = _other_soft_flags(other_fv.n_words)

    soft_flags: list[str] = []
    if tokens.has_unclosed_fence:
        soft_flags.append("malformed_fence_recovered")
    n_latin, n_nonlatin = nonlatin_stats(tokens.cleaned)
    if (n_nonlatin >= _NONLATIN_FLAG_MIN_LETTERS
            and (n_latin + n_nonlatin) > 0
            and n_nonlatin / (n_latin + n_nonlatin) >= _NONLATIN_FLAG_MIN_RATIO):
        soft_flags.append("substantive_non_latin_content")

    conv = _convergence.compute(shaper_features, other_features)

    # Per-slice trajectory on the elegant slicing of the CLEANED text
    # (clean once, then slice — kernel guarantees totality on degenerate
    # inputs: worst case one document-level slice). Embedded in the
    # reading so `reading_sha256`/`content_sha256` attest every surfaced
    # trajectory number (A-prime, 0.9.1).
    elegant = regime_elegant(tokens.cleaned)
    trajectory = {
        "regime": "elegant",
        "boundary_level": elegant["boundary_level"],
        "n_slices": elegant["n_slices"],
        "slices": [[s, e] for (s, e) in elegant["slices"]],
        "features": read_trajectory(tokens, elegant["slices"]),
    }

    # P0-1: quantise every emitted float to a fixed significant-figure
    # precision so the record is byte-identical across C libraries / CPUs.
    # Computation above runs at full precision; only the emitted values are
    # canonicalised. `ts` (a string) is unaffected here and is excluded from
    # the reproducibility content hash separately.
    return quantize({
        "schema_version": SCHEMA_VERSION,
        "ts": _utc_now(),
        "n_words": {
            "shaper": shaper_flat.get("n_words", 0),
            "other_shaper": other_fv.n_words,
        },
        "below_envelope": {
            "shaper": shaper_below,
            "other_shaper_soft_flags": other_flags,
        },
        "soft_flags": soft_flags,
        "shaper": {
            "feature_order": list(SHAPER_FEATURE_ORDER),
            "features": shaper_features,
        },
        "other_shaper": {
            "feature_order": list(OTHER_FEATURE_ORDER),
            "features": other_features,
        },
        "stylometry": {
            "feature_order": [f"stylometry.{k}" for k in STYLOMETRY_FEATURE_ORDER],
            "features": stylometry_features,
        },
        "distributional": {
            "feature_order": [f"dist.{k}" for k in DISTRIBUTIONAL_FEATURE_ORDER],
            "features": distributional_features,
        },
        "convergence": conv,
        "trajectory": trajectory,
        "n_sentences": len(tokens.sentences),
    })
