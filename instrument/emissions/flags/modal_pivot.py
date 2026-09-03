"""modal_pivot — modal-density slope reverses between halves."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, finite


def _slope(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mx = (len(xs) - 1) / 2.0
    my = sum(xs) / len(xs)
    num = sum((i - mx) * (y - my) for i, y in enumerate(xs))
    den = sum((i - mx) * (i - mx) for i in range(len(xs)))
    return num / den if den > 0 else 0.0


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    modal = ctx.traj.get("modal_density", [])
    clean = finite(modal)
    if len(clean) < 4:
        return None
    mid = len(clean) // 2
    first, second = clean[:mid], clean[mid:]
    min_swing = float(params.get("min_swing", 0.3))
    s1 = _slope(first)
    s2 = _slope(second)
    if s1 == 0 or s2 == 0:
        return None
    if s1 * s2 >= 0:
        return None
    if abs(s1 - s2) < min_swing:
        return None
    return {
        "first_half_slope": s1,
        "second_half_slope": s2,
        "pivot_at_slice": mid,
    }
