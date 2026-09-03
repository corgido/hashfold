"""cross_view_diverge — fires when the convergence overall verdict is "diverge".

Threshold semantics live in `instrument.reading.convergence.OVERALL_MAJORITY`;
this flag derives from the verdict so it can never disagree with the coherence
scalar (both consume the same axis directions and the same majority threshold).
"""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    if not ctx.convergence:
        return None
    if ctx.convergence.get("overall") != "diverge":
        return None
    diverging = [
        name for name, spec in ctx.convergence.get("axes", {}).items()
        if spec.get("direction") == "diverge"
    ]
    return {"diverging_axes": diverging}
