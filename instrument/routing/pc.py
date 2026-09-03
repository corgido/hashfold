"""PC composite projection.

Projects a reading's flat feature dict onto the named PC axes
embedded in a `ReferenceDistribution`. Numpy-free; plain-Python
dot product. NaN-propagating: any NaN feature contaminates every
PC output (a partial projection would silently omit features,
which is worse than refusing to project).
"""

from __future__ import annotations

import math
from typing import Optional

from instrument.routing.types import ReferenceDistribution


def _is_nan(v) -> bool:
    try:
        return math.isnan(v)
    except TypeError:
        return False


def project_pc_composites(
    features: dict[str, Optional[float]],
    reference: ReferenceDistribution,
) -> dict[str, Optional[float]]:
    """Project `features` onto each of the reference's named PC axes.

    Any NaN / missing feature value → every PC in the output
    reports `None` (contamination). Returns `{pc_name: value | None}`.
    """
    z: dict[str, float] = {}
    any_nan_feature = False
    for feature_name, mu in reference.pc_zscore_mean.items():
        s = reference.pc_zscore_std.get(feature_name, 0.0)
        v = features.get(feature_name)
        if v is None or _is_nan(v) or s == 0:
            z[feature_name] = float("nan")
            any_nan_feature = True
        else:
            z[feature_name] = (v - mu) / s

    out: dict[str, Optional[float]] = {}
    for pc_name, loadings in reference.pc_loadings.items():
        if any_nan_feature:
            out[pc_name] = None
            continue
        total = 0.0
        for feat, weight in loadings.items():
            total += z.get(feat, 0.0) * weight
        out[pc_name] = total
    return out
