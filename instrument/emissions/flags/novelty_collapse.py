"""novelty_collapse — run of slices with novelty below a threshold."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, is_nan


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    nov = ctx.traj.get("lexical_novelty", [])
    threshold = float(params.get("max_novelty", 0.1))
    min_consec = int(params.get("min_consecutive", 2))
    run_start: Optional[int] = None
    run_len = 0
    for i, v in enumerate(nov):
        if v is None or is_nan(v):
            run_start = None
            run_len = 0
            continue
        if v < threshold:
            if run_start is None:
                run_start = i
            run_len += 1
            if run_len >= min_consec:
                return {"start_slice": run_start, "length": run_len}
        else:
            run_start = None
            run_len = 0
    return None
