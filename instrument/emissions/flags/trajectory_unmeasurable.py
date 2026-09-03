"""trajectory_unmeasurable — too few slices for a trajectory reading."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    min_slices = int(params.get("min_slices", 2))
    if ctx.n_slices < min_slices:
        return {"n_slices": ctx.n_slices}
    return None
