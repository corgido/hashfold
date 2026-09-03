"""feature_unmeasurable_cluster — many features are None or NaN."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext, is_nan


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    unmeasurable = [
        name for name, v in ctx.features.items()
        if v is None or (isinstance(v, float) and is_nan(v))
    ]
    min_count = int(params.get("min_count", 5))
    if len(unmeasurable) >= min_count:
        return {"unmeasurable_features": unmeasurable}
    return None
