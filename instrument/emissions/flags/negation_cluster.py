"""negation_cluster — any slice with negation density >= ratio × doc mean."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, is_nan


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    neg_series = ctx.traj.get("negation_density", [])
    mean = ctx.slice_mean.get("negation_density")
    if mean is None or mean == 0:
        return None
    ratio = float(params.get("min_ratio", 2.0))
    min_abs = float(params.get("min_absolute", 0.1))
    hits: list[int] = []
    for i, v in enumerate(neg_series):
        if v is None or is_nan(v):
            continue
        if v >= ratio * mean and v >= min_abs:
            hits.append(i)
    if not hits:
        return None
    return {"slices": hits, "doc_slice_mean": mean}
