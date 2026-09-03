"""embedder — three embedding forms on the 13-feature flat reading.

Turns a document into a fixed-length deterministic vector in
station feature space:

    flat_embedding:        13-d     document as one slice
    regime_embedding:     156-d     mean/min/max/std across 3 regimes × 13 features
    trajectory_embedding: 130-d     10-step elegant-regime trajectory × 13 features

All three are deterministic. All three return plain `list[float]`
with NaN preserved as `float('nan')` (JSON serialisers re-map this
to `None` at the response boundary).
"""

from __future__ import annotations

import math

from instrument.kernel.distance import cosine_similarity, euclidean_distance
from instrument.kernel.grid import interp_linear, linspace
from instrument.kernel.nanmath import all_nan, is_nan, nanmax, nanmean, nanmin, nanstd
from instrument.kernel.regimes import measure_all_regimes
from instrument.kernel.tokens import tokenise
from instrument.reading.flat import FEATURE_ORDER, flat_reading, flat_reading_from_text

STAT_ORDER: tuple[str, ...] = ("mean", "min", "max", "std")
REGIME_ORDER: tuple[str, ...] = ("flat", "chunker", "elegant")
TRAJECTORY_GRID = 10

# Feature scales for normalisation. Upper bounds are practical maximums,
# not corpus maxima — stable as corpus grows.
# sentence_length_variance uses log1p to compress the long tail.
FEATURE_SCALES: dict[str, tuple[float, float]] = {
    "sfl.process_proxy_entropy":         (0.0, 2.2),
    "sfl.stative_active_ratio":          (0.0, 3.0),
    "sfl.projection_frequency":          (0.0, 6.0),
    "rst.marker_density":                (0.0, 1.0),
    "rst.elaboration_marker_density":          (0.0, 1.0),
    "rst.contrast_marker_density":             (0.0, 1.0),
    "cohesion.type_token_ratio":         (0.0, 1.0),
    "cohesion.pronoun_density":          (0.0, 15.0),
    "cohesion.lexical_repetition":       (0.0, 1.0),
    "register.lexical_novelty":          (0.0, 1.0),
    "register.sentence_length_variance": (0.0, 10.0),
    "register.modal_density":            (0.0, 5.0),
    "register.negation_density":         (0.0, 5.0),
}


# ---- normalisation ---------------------------------------------------------

def normalise_feature(key: str, value: float) -> float:
    """Scale a single feature to [0, 1] using FEATURE_SCALES.

    `register.sentence_length_variance` is log1p-compressed before
    scaling (log1p(51534) ≈ 10.8 fits the (0, 10) window).
    Returns NaN if value is NaN.
    """
    if is_nan(value):
        return float("nan")
    if key == "register.sentence_length_variance":
        value = math.log1p(value)
    lo, hi = FEATURE_SCALES.get(key, (0.0, 1.0))
    if hi == lo:
        return 0.0
    return max(0.0, min(1.0, (value - lo) / (hi - lo)))


def normalise_vector(vec) -> list[float]:
    """Normalise a positional 13-vector using FEATURE_SCALES."""
    return [normalise_feature(FEATURE_ORDER[i], v) for i, v in enumerate(vec)]


def _safe_value(reading: dict, feature: str) -> float:
    if reading.get("below_envelope"):
        return float("nan")
    return reading.get(feature, float("nan"))


# ---- embeddings ------------------------------------------------------------

def flat_embedding(text: str) -> list[float]:
    """13-dim normalised embedding over the whole document.

    Returns a vector of NaNs if the document is below envelope.
    """
    r = flat_reading_from_text(text)
    vec = [_safe_value(r, f) for f in FEATURE_ORDER]
    return normalise_vector(vec)


def regime_embedding(text: str) -> list[float]:
    """156-dim embedding: 3 regimes × 13 features × {mean, min, max, std}.

    Flat regime produces identical stats across its single slice
    (mean == min == max; std == 0). That is correct behaviour, not
    a bug.

    Layout: `[regime_0_feature_0_mean, ..._min, ..._max, ..._std,
    regime_0_feature_1_mean, ..., regime_1_feature_0_mean, ...]`.
    """
    # Slice the document-level cleaned text (same order as the emission
    # trajectory: clean once, then slice — no fence resurrection).
    cleaned = tokenise(text).cleaned
    regimes = measure_all_regimes(cleaned)
    vec: list[float] = []
    for regime_name in REGIME_ORDER:
        regime = regimes[regime_name]
        slices_text = [cleaned[s:e] for s, e in regime["slices"]]
        readings = [flat_reading_from_text(s) for s in slices_text]
        for feature in FEATURE_ORDER:
            values = [_safe_value(r, feature) for r in readings]
            if all_nan(values):
                vec.extend([float("nan")] * 4)
            else:
                vec.extend([
                    float(nanmean(values)),
                    float(nanmin(values)),
                    float(nanmax(values)),
                    float(nanstd(values)) if len(values) > 1 else 0.0,
                ])
    return vec


def trajectory_embedding(text: str, grid: int = TRAJECTORY_GRID) -> list[float]:
    """130-dim embedding: 13 features × 10-step grid on elegant regime.

    Each feature is resampled onto `grid` equally-spaced positions
    in [0, 1] via linear interpolation, so documents with different
    slice counts produce comparable vectors.

    Layout: `[f0_pos0, f0_pos1, ..., f0_pos9, f1_pos0, ..., f12_pos9]`.
    """
    cleaned = tokenise(text).cleaned
    regimes = measure_all_regimes(cleaned)
    elegant = regimes["elegant"]
    slices_text = [cleaned[s:e] for s, e in elegant["slices"]]
    readings = [flat_reading_from_text(s) for s in slices_text]
    n_slices = len(readings)

    vec: list[float] = []
    target_x = linspace(0.0, 1.0, grid)

    for feature in FEATURE_ORDER:
        values = [_safe_value(r, feature) for r in readings]
        if all_nan(values):
            vec.extend([float("nan")] * grid)
            continue
        if n_slices == 1:
            vec.extend([float(values[0])] * grid)
            continue
        source_x_full = linspace(0.0, 1.0, n_slices)
        pairs = [(x, v) for x, v in zip(source_x_full, values) if not is_nan(v)]
        if len(pairs) < 2:
            vec.extend([float(nanmean(values))] * grid)
            continue
        src_x = [p[0] for p in pairs]
        src_y = [p[1] for p in pairs]
        vec.extend(interp_linear(target_x, src_x, src_y))

    return vec


# Re-export distance helpers so callers doing
# `from instrument.reading.embedder import cosine_similarity` keep working.
__all__ = [
    "FEATURE_SCALES", "STAT_ORDER", "REGIME_ORDER", "TRAJECTORY_GRID",
    "normalise_feature", "normalise_vector",
    "flat_embedding", "regime_embedding", "trajectory_embedding",
    "cosine_similarity", "euclidean_distance",
]
