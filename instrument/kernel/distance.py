"""distance — NaN-safe vector metrics.

Positions in any of the instrument's embedding spaces are
structural, not semantic. These helpers are the L1 primitives the
metrology layer composes for drift detection.
"""

from __future__ import annotations

import math

from instrument.kernel.nanmath import is_nan


def _check_same_length(a, b, op: str) -> tuple[list, list]:
    aa = list(a)
    bb = list(b)
    if len(aa) != len(bb):
        raise ValueError(
            f"{op}: vector lengths differ ({len(aa)} vs {len(bb)}); "
            "zip would silently truncate"
        )
    return aa, bb


def cosine_similarity(a, b) -> float:
    """Cosine similarity, NaN-safe.

    Positions where either side is NaN are skipped. Zero vectors
    return NaN (direction undefined). Raises ValueError on
    unequal-length inputs (the silent-truncation failure mode of
    bare `zip`).
    """
    a, b = _check_same_length(a, b, "cosine_similarity")
    aa: list[float] = []
    bb: list[float] = []
    for x, y in zip(a, b):
        if is_nan(x) or is_nan(y):
            continue
        aa.append(x)
        bb.append(y)
    if not aa:
        return float("nan")
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(aa, bb):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return float("nan")
    return float(dot / (math.sqrt(na) * math.sqrt(nb)))


def euclidean_distance(a, b) -> float:
    """Euclidean distance, NaN-safe.

    Raises ValueError on unequal-length inputs.
    """
    a, b = _check_same_length(a, b, "euclidean_distance")
    total = 0.0
    count = 0
    for x, y in zip(a, b):
        if is_nan(x) or is_nan(y):
            continue
        d = x - y
        total += d * d
        count += 1
    if count == 0:
        return float("nan")
    return float(math.sqrt(total))
