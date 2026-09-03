"""below_envelope_shaper — text too short for reliable measurement."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    if "below_envelope_shaper" in ctx.soft_flags:
        return {"n_words": ctx.n_words}
    if ctx.n_words < int(params.get("min_words", 150)):
        return {"n_words": ctx.n_words}
    return None
