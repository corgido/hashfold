"""malformed_fence_recovered — relay of the joint-reading soft flag."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    if "malformed_fence_recovered" in ctx.soft_flags:
        return {}
    return None
