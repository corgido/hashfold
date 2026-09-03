"""Five-axis convergence/divergence between the flat and extended views.

Each axis maps one shaper (flat-view) feature to one or more
extended-view features, reduces, and compares normalised values.
Agreement means the two views produce similar normalised readings
on that axis; it does not mean the text is "good" or "coherent".

Convergence is INTERNAL CONSISTENCY across two structurally parallel
but substantially shared computations — not independent corroboration.
The two views share the pinned lexicon tree on four of five axes
(measured: identical process lexicons and stopword lists, shared RST
marker inventory, 71%-shared modals), so agreement there is partly
structural: a bias in a shared lexicon corrupts both views identically
and they still "agree". Each axis therefore carries an `independence`
annotation (see AXIS_INDEPENDENCE); only `rst_contrast` is
substantially independent in practice (r=0.41 between views on real
corpora), and `cohesion_repetition` is one measurement counted twice
(r=0.99, 100% within-tolerance agreement) — it is excluded from the
coherence scalar (COHERENCE_EXCLUDED_AXES) while remaining visible
here.

All thresholds are named constants — no learned parameters.

The axis name `register_modality` is historical. The shaper view's
`register` bucket contains trajectory and stylistic measures rather
than Halliday-register features; see
`instrument.kernel.features.register`.
"""

from __future__ import annotations

import math

# Normalisation ranges calibrated on the repo self-audit corpus
# (81 docs) at p05/p95 with a 15% symmetric buffer. Recalibration
# history lives in commit messages; the buffered ranges give each
# axis headroom so small absolute differences between views do not
# read as large relative differences under AGREE_TOLERANCE=0.20.
AXES: dict[str, dict] = {
    "sfl_process_complexity": {
        "shaper_key": "sfl.process_proxy_entropy",
        # Shaper is now 6-bucket (mental/verbal/relational/behavioral/
        # material/existential), matching the other-shaper alphabet.
        # Range matched to other_range so both sides normalise on the
        # same scale; the historical 5-bucket shaper range (1.22, 2.03)
        # is retired.
        "shaper_range": (1.13, 2.46),
        "other_keys": [
            "sfl.pct_material", "sfl.pct_mental", "sfl.pct_relational",
            "sfl.pct_verbal", "sfl.pct_behavioral", "sfl.pct_existential",
        ],
        "other_reducer": "entropy_of_proportions",
        "other_range": (1.13, 2.46),
    },
    "rst_contrast": {
        "shaper_key": "rst.contrast_marker_density",
        "shaper_range": (0.0, 0.13),
        "other_keys": ["rst.contrast_density", "rst.concession_density"],
        "other_reducer": "sum",
        "other_range": (0.0, 0.15),
    },
    "rst_elaboration": {
        "shaper_key": "rst.elaboration_marker_density",
        "shaper_range": (0.0, 0.42),
        "other_keys": ["rst.elaboration_density"],
        "other_reducer": "sum",
        "other_range": (0.0, 0.28),
    },
    "cohesion_repetition": {
        "shaper_key": "cohesion.lexical_repetition",
        "shaper_range": (0.07, 0.49),
        "other_keys": ["coh.lexical_repetition_rate"],
        "other_reducer": "sum",
        "other_range": (0.08, 0.52),
    },
    "register_modality": {
        "shaper_key": "register.modal_density",
        "shaper_range": (0.0, 2.45),
        "other_keys": ["sfl.modal_density", "sfl.hedge_density"],
        "other_reducer": "sum",
        "other_range": (0.0, 4.9),
    },
}

# How independent the two views actually are, per axis — surfaced in
# every reading so the record itself is honest about which agreements
# corroborate and which are structural (0.9.1; measured in the 0.9.0
# deep investigation).
AXIS_INDEPENDENCE: dict[str, str] = {
    "sfl_process_complexity": "shared_lexicons",      # identical process lexicons
    "rst_contrast": "independent",                     # r=0.41; discriminates
    "rst_elaboration": "shared_marker_inventory",      # shared RST cue lists
    "cohesion_repetition": "duplicate_computation",    # identical stopwords; r=0.99
    "register_modality": "shared_lexicons",            # 71%-shared modals
}

# Axes excluded from the coherence scalar (emissions/coherence.py):
# structurally-guaranteed agreement must not inflate an agreement
# fraction. The axis pair-values remain in the reading.
COHERENCE_EXCLUDED_AXES: frozenset[str] = frozenset({"cohesion_repetition"})

BAND_LOW = 0.33
BAND_HIGH = 0.66
# AGREE_TOLERANCE is deliberately FROZEN, not recalibrated. It was
# derived from an 81-doc self-audit corpus; any recalibration corpus
# of LLM output bakes in the prompt style that produced it, so a
# "better-tuned" tolerance would just be tuned to one prompt
# distribution. The instrument's position: thresholds here are
# advisory inference (see emissions/catalog.py ADVISORY note);
# consumers needing calibrated agreement should record the raw
# per-axis values from the audit shape and band them against their
# own baselines. Changing this constant is a measurement-surface
# change (bump the instrument version).
AGREE_TOLERANCE = 0.20
OVERALL_MAJORITY = 4  # out of 5 axes


def _clamp01(x: float) -> float:
    if x != x:  # NaN
        return 0.0
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _normalise(value: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return _clamp01((value - lo) / (hi - lo))


def _reduce_other(features: dict, keys: list[str], reducer: str) -> float | None:
    """Combine one or more extended features into a single scalar."""
    if reducer == "missing" or not keys:
        return None
    vals = [features.get(k, 0.0) for k in keys]
    if reducer == "sum":
        return sum(vals)
    if reducer == "entropy_of_proportions":
        h = 0.0
        for p in vals:
            if p > 0.0:
                h -= p * math.log2(p)
        return h
    raise ValueError(f"unknown reducer: {reducer!r}")


def _classify(shaper_norm: float, other_norm: float) -> tuple[str, float]:
    """Return (direction, confidence) for a normalised pair."""
    confidence = 1.0 - abs(shaper_norm - other_norm)
    if confidence >= (1.0 - AGREE_TOLERANCE):
        mean = (shaper_norm + other_norm) / 2.0
        if mean >= BAND_HIGH:
            return ("agree_high", confidence)
        if mean <= BAND_LOW:
            return ("agree_low", confidence)
        return ("agree_mid", confidence)
    return ("diverge", confidence)


def compute(shaper_features: dict, other_features: dict) -> dict:
    """Compute the per-axis convergence signal.

    Returns a dict with `axes`, `overall`, `n_axes_agree`,
    `n_axes_diverge`, `n_axes_incomparable`.
    """
    axes_out: dict[str, dict] = {}
    n_agree = n_diverge = n_incomparable = 0

    for name, spec in AXES.items():
        s_key = spec["shaper_key"]
        s_val = shaper_features.get(s_key, 0.0)

        if isinstance(s_val, float) and math.isnan(s_val):
            axes_out[name] = {
                "shaper_key": s_key,
                "shaper_value": s_val,
                "shaper_normalised": None,
                "other_keys": spec["other_keys"],
                "other_value": None,
                "other_normalised": None,
                "direction": "incomparable",
                "confidence": None,
                "independence": AXIS_INDEPENDENCE[name],
            }
            n_incomparable += 1
            continue

        s_norm = _normalise(s_val, *spec["shaper_range"])
        o_raw = _reduce_other(other_features, spec["other_keys"], spec["other_reducer"])

        if o_raw is None:
            axes_out[name] = {
                "shaper_key": s_key,
                "shaper_value": s_val,
                "shaper_normalised": s_norm,
                "other_keys": spec["other_keys"],
                "other_value": None,
                "other_normalised": None,
                "direction": "incomparable",
                "confidence": None,
                "independence": AXIS_INDEPENDENCE[name],
            }
            n_incomparable += 1
            continue

        o_norm = _normalise(o_raw, *spec["other_range"])
        direction, confidence = _classify(s_norm, o_norm)

        axes_out[name] = {
            "shaper_key": s_key,
            "shaper_value": s_val,
            "shaper_normalised": s_norm,
            "other_keys": spec["other_keys"],
            "other_reducer": spec["other_reducer"],
            "other_value": o_raw,
            "other_normalised": o_norm,
            "direction": direction,
            "confidence": confidence,
            "independence": AXIS_INDEPENDENCE[name],
        }

        if direction == "diverge":
            n_diverge += 1
        else:
            n_agree += 1

    if n_agree >= OVERALL_MAJORITY:
        overall = "converge"
    elif n_diverge >= OVERALL_MAJORITY:
        overall = "diverge"
    else:
        overall = "mixed"

    return {
        "axes": axes_out,
        "overall": overall,
        "n_axes_agree": n_agree,
        "n_axes_diverge": n_diverge,
        "n_axes_incomparable": n_incomparable,
    }
