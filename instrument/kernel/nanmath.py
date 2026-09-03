"""nanmath — NaN-aware reductions over iterables of float.

`NaN` semantics mirror `numpy.nan*` with `ddof=0` but no numpy
dependency. Every reducer returns `float('nan')` when every input
is NaN (or the input is empty).
"""

from __future__ import annotations

import math


def is_nan(x: float) -> bool:
    return x != x


def nanmean(values) -> float:
    total = 0.0
    count = 0
    for v in values:
        if not is_nan(v):
            total += v
            count += 1
    if count == 0:
        return float("nan")
    return total / count


def nanmin(values) -> float:
    m: float | None = None
    for v in values:
        if is_nan(v):
            continue
        if m is None or v < m:
            m = v
    return float("nan") if m is None else m


def nanmax(values) -> float:
    m: float | None = None
    for v in values:
        if is_nan(v):
            continue
        if m is None or v > m:
            m = v
    return float("nan") if m is None else m


def nanstd(values) -> float:
    """Population standard deviation (ddof=0) over non-NaN values.

    Matches `numpy.nanstd` with default ddof.
    """
    total = 0.0
    count = 0
    for v in values:
        if not is_nan(v):
            total += v
            count += 1
    if count == 0:
        return float("nan")
    mean = total / count
    sq = 0.0
    for v in values:
        if not is_nan(v):
            d = v - mean
            sq += d * d
    return math.sqrt(sq / count)


def all_nan(values) -> bool:
    return all(is_nan(v) for v in values)
