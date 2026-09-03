"""novelty_reopen — novelty rises after a prior decline."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, is_nan


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    nov = ctx.traj.get("lexical_novelty", [])
    clean = [
        (i, v) for i, v in enumerate(nov)
        if v is not None and not is_nan(v)
    ]
    if len(clean) < 3:
        return None
    min_delta = float(params.get("min_delta", 0.15))
    for k in range(1, len(clean)):
        i, v = clean[k]
        j, pv = clean[k - 1]
        if v - pv < min_delta:
            continue
        before = [x for _, x in clean[:k]]
        if len(before) < 2:
            continue
        if any(before[m] > before[m + 1] for m in range(len(before) - 1)):
            return {
                "slice": i,
                "previous_slice": j,
                "rise": v - pv,
                "to_value": v,
            }
    return None
