"""register_shift — adjacent-slice Euclidean distance above median × ratio."""

from __future__ import annotations

import math
from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, finite, is_nan

_TRAJ_KEYS = (
    "lexical_novelty",
    "sentence_length_variance",
    "modal_density",
    "negation_density",
)


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    series = {k: ctx.traj.get(k, []) for k in _TRAJ_KEYS}
    n = ctx.n_slices
    if n < 3:
        return None

    norms: dict[str, float] = {}
    for k in _TRAJ_KEYS:
        vals = finite(series[k])
        norms[k] = max((abs(v) for v in vals), default=0.0) or 1.0

    dists: list[tuple[int, float]] = []
    for i in range(1, n):
        total = 0.0
        missing = False
        for k in _TRAJ_KEYS:
            a = series[k][i] if i < len(series[k]) else None
            b = series[k][i - 1] if (i - 1) < len(series[k]) else None
            if a is None or b is None or is_nan(a) or is_nan(b):
                missing = True
                break
            d = (a - b) / norms[k]
            total += d * d
        if missing:
            continue
        dists.append((i, math.sqrt(total)))

    if len(dists) < 2:
        return None
    sorted_d = sorted(d for _, d in dists)
    median = sorted_d[len(sorted_d) // 2]
    ratio = float(params.get("min_ratio", 2.0))
    hits = [i for i, d in dists if median > 0 and d >= ratio * median]
    if not hits:
        return None
    return {
        "slices_after_shift": hits,
        "median_adjacent_distance": median,
    }
