"""variance_spike — any slice with variance >= ratio × doc slice-mean."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, is_nan


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    var_series = ctx.traj.get("sentence_length_variance", [])
    mean = ctx.slice_mean.get("sentence_length_variance")
    if mean is None or mean == 0:
        return None
    ratio = float(params.get("min_ratio", 2.0))
    min_abs = float(params.get("min_absolute", 300.0))
    hits: list[int] = []
    for i, v in enumerate(var_series):
        if v is None or is_nan(v):
            continue
        if v >= ratio * mean and v >= min_abs:
            hits.append(i)
    if not hits:
        return None
    return {"slices": hits, "doc_slice_mean": mean}
