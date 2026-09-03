"""Per-slice label detectors.

Nine detectors, each taking a `SliceLabelContext` + params from
the catalog and returning True/False. The registry maps catalog
`id` strings to detector functions.

Every detector's logic is pure, deterministic, document-internal.
Thresholds come from the catalog JSON; the code contains the
detection shape only.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Optional


def _is_nan(v) -> bool:
    try:
        return math.isnan(v)
    except TypeError:
        return False


def _finite(xs: list) -> list[float]:
    return [float(x) for x in xs if x is not None and not _is_nan(x)]


@dataclass(frozen=True)
class SliceLabelContext:
    """All inputs a slice-label detector might need."""
    traj: dict[str, list[Optional[float]]]
    index: int
    n_slices: int
    slice_mean: dict[str, Optional[float]]


# ---------- Detectors ------------------------------------------------------

def detect_opening(ctx: SliceLabelContext, params: dict) -> bool:
    return ctx.index == 0


def detect_closing(ctx: SliceLabelContext, params: dict) -> bool:
    return ctx.index == ctx.n_slices - 1


def detect_introduction(ctx: SliceLabelContext, params: dict) -> bool:
    """Novelty >= threshold at this slice (after slice 0, which is NaN)."""
    if ctx.index == 0:
        return False
    nov = ctx.traj.get("lexical_novelty", [])
    if ctx.index >= len(nov):
        return False
    v = nov[ctx.index]
    if v is None or _is_nan(v):
        return False
    return v >= float(params.get("min_novelty", 0.5))


def detect_elaboration(ctx: SliceLabelContext, params: dict) -> bool:
    """Novelty in [low, high) AND local descent from previous measurable slice."""
    nov = ctx.traj.get("lexical_novelty", [])
    if ctx.index == 0 or ctx.index >= len(nov):
        return False
    v = nov[ctx.index]
    if v is None or _is_nan(v):
        return False
    low = float(params.get("min_novelty", 0.2))
    high = float(params.get("max_novelty", 0.5))
    if not (low <= v < high):
        return False
    prev = None
    for i in range(ctx.index - 1, -1, -1):
        pv = nov[i]
        if pv is not None and not _is_nan(pv):
            prev = pv
            break
    return prev is None or prev > v


def detect_plateau(ctx: SliceLabelContext, params: dict) -> bool:
    """Novelty below a low threshold."""
    nov = ctx.traj.get("lexical_novelty", [])
    if ctx.index == 0 or ctx.index >= len(nov):
        return False
    v = nov[ctx.index]
    if v is None or _is_nan(v):
        return False
    return v < float(params.get("max_novelty", 0.2))


def detect_reopen(ctx: SliceLabelContext, params: dict) -> bool:
    """Novelty rises by >= min_delta from previous measurable slice,
    AND there was a prior decline earlier in the document."""
    nov = ctx.traj.get("lexical_novelty", [])
    if ctx.index < 2 or ctx.index >= len(nov):
        return False
    v = nov[ctx.index]
    if v is None or _is_nan(v):
        return False
    prev_idx = None
    for i in range(ctx.index - 1, -1, -1):
        pv = nov[i]
        if pv is not None and not _is_nan(pv):
            prev_idx = i
            break
    if prev_idx is None:
        return False
    prev_v = nov[prev_idx]
    if v - prev_v < float(params.get("min_delta", 0.15)):
        return False
    values_before = _finite(nov[: prev_idx + 1])
    if len(values_before) < 2:
        return False
    return any(
        values_before[i] > values_before[i + 1]
        for i in range(len(values_before) - 1)
    )


def detect_variance_burst(ctx: SliceLabelContext, params: dict) -> bool:
    """Variance at this slice >= ratio * doc mean AND above absolute floor."""
    var_series = ctx.traj.get("sentence_length_variance", [])
    if ctx.index >= len(var_series):
        return False
    v = var_series[ctx.index]
    if v is None or _is_nan(v):
        return False
    mean = ctx.slice_mean.get("sentence_length_variance")
    if mean is None or mean == 0:
        return False
    return (
        v >= float(params.get("min_ratio", 2.0)) * mean
        and v >= float(params.get("min_absolute", 300.0))
    )


def detect_negation_cluster(ctx: SliceLabelContext, params: dict) -> bool:
    """Negation density at this slice >= ratio * doc mean AND above floor."""
    neg_series = ctx.traj.get("negation_density", [])
    if ctx.index >= len(neg_series):
        return False
    v = neg_series[ctx.index]
    if v is None or _is_nan(v):
        return False
    mean = ctx.slice_mean.get("negation_density")
    if mean is None or mean == 0:
        return False
    return (
        v >= float(params.get("min_ratio", 2.0)) * mean
        and v >= float(params.get("min_absolute", 0.1))
    )


def detect_hedging_peak(ctx: SliceLabelContext, params: dict) -> bool:
    """Modal density is a local maximum (higher than adjacent measurable
    slices) AND above an absolute floor."""
    modal_series = ctx.traj.get("modal_density", [])
    if ctx.index >= len(modal_series):
        return False
    v = modal_series[ctx.index]
    if v is None or _is_nan(v):
        return False
    left = None
    for i in range(ctx.index - 1, -1, -1):
        pv = modal_series[i]
        if pv is not None and not _is_nan(pv):
            left = pv
            break
    right = None
    for i in range(ctx.index + 1, len(modal_series)):
        pv = modal_series[i]
        if pv is not None and not _is_nan(pv):
            right = pv
            break
    if left is None and right is None:
        return False
    if v < float(params.get("min_absolute", 0.5)):
        return False
    if left is not None and v <= left:
        return False
    if right is not None and v <= right:
        return False
    return True


# ---------- Registry -------------------------------------------------------

SliceLabelDetector = Callable[[SliceLabelContext, dict], bool]

SLICE_LABEL_DETECTORS: dict[str, SliceLabelDetector] = {
    "opening":          detect_opening,
    "closing":          detect_closing,
    "introduction":     detect_introduction,
    "elaboration":      detect_elaboration,
    "plateau":          detect_plateau,
    "reopen":           detect_reopen,
    "variance_burst":   detect_variance_burst,
    "negation_cluster": detect_negation_cluster,
    "hedging_peak":     detect_hedging_peak,
}


def get_slice_label_detector(detector_id: str) -> SliceLabelDetector:
    fn = SLICE_LABEL_DETECTORS.get(detector_id)
    if fn is None:
        raise KeyError(
            f"unknown slice-label detector {detector_id!r}; "
            f"available: {sorted(SLICE_LABEL_DETECTORS)}"
        )
    return fn
