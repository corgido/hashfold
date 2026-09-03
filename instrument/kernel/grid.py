"""grid — linspace + linear interpolation without numpy.

Used by the trajectory embedder to resample per-slice readings
onto a fixed grid so documents with different slice counts produce
comparable vectors.
"""

from __future__ import annotations


def linspace(lo: float, hi: float, n: int) -> list[float]:
    """Inclusive n-point linspace. Matches `numpy.linspace` defaults."""
    if n == 1:
        return [float(lo)]
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def interp_linear(target_xs, source_xs, source_ys) -> list[float]:
    """Linear interpolation. `source_xs` must be sorted ascending.

    Values outside `[source_xs[0], source_xs[-1]]` clamp to the
    nearest endpoint (matches `numpy.interp` defaults).
    """
    out: list[float] = []
    n = len(source_xs)
    for x in target_xs:
        if x <= source_xs[0]:
            out.append(source_ys[0])
            continue
        if x >= source_xs[-1]:
            out.append(source_ys[-1])
            continue
        for i in range(n - 1):
            x0, x1 = source_xs[i], source_xs[i + 1]
            if x0 <= x <= x1:
                if x1 == x0:
                    out.append(source_ys[i])
                else:
                    t = (x - x0) / (x1 - x0)
                    out.append(source_ys[i] + t * (source_ys[i + 1] - source_ys[i]))
                break
    return out
