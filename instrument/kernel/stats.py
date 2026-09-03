"""stats — deterministic calibration statistics, numpy-free.

The calibration path (reference builds, percentile grids, empirical
p-values, multiplicity control, coverage CIs) must be a pure function
of its inputs: no numpy (dependency surface, cross-version drift), no
scipy, no tolerance-driven iteration whose step count could vary by
host. Every function here is pure and unquantised — callers quantise
at the emission boundary (see ``instrument.kernel.quantize``), so the
last-ULP libm variance documented there stays out of the record.

``percentile_linear`` implements the exact linear-interpolation
percentile (numpy's default method) used by
``tools/build_reference.py``; that tool is slated to import this
module so the two can never diverge.
"""

from __future__ import annotations

import bisect
import math


def mean(xs: list[float]) -> float:
    """Arithmetic mean. Matches ``_mean`` in tools/build_reference.py."""
    if not xs:
        raise ValueError("mean of empty input")
    return sum(xs) / len(xs)


def pstdev(xs: list[float]) -> float:
    """Population standard deviation (ddof=0).

    Matches ``_std`` in tools/build_reference.py (and the v1 refs):
    same expression, same summation order, so results are
    bit-identical with the tool's.
    """
    if not xs:
        raise ValueError("pstdev of empty input")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))


def percentile_linear(sorted_xs: list[float], q: float) -> float:
    """Linear-interpolation percentile (numpy's default method).

    CONTRACT: ``sorted_xs`` must already be sorted ascending. Sortedness
    is not verified (that would be O(n) on every call in the reference
    build's hot loop); passing unsorted input silently returns garbage.

    Same convention as ``_percentile`` in tools/build_reference.py: the
    q-th percentile sits at fractional position ``(n - 1) * q / 100``
    among the order statistics, interpolated linearly between the two
    neighbours.
    """
    if not sorted_xs:
        raise ValueError("percentile of empty input")
    if not 0.0 <= q <= 100.0:
        raise ValueError(f"percentile q must be in [0, 100], got {q}")
    n = len(sorted_xs)
    if n == 1:
        return sorted_xs[0]
    pos = (n - 1) * (q / 100.0)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_xs[lo]
    frac = pos - lo
    return sorted_xs[lo] * (1.0 - frac) + sorted_xs[hi] * frac


def midrank_percentile(sorted_xs: list[float], x: float) -> float:
    """Mid-rank percentile of ``x`` within a sorted sample.

    ``100 * (n_less + 0.5 * n_equal) / n``: ties contribute half their
    mass, so ``x`` equal to a tie block lands in the middle of the
    block's rank range rather than at either edge. This makes the
    result symmetric under sign flips and independent of how a sort
    happened to order equal values. ``x`` below the minimum gives 0.0;
    above the maximum gives 100.0.

    CONTRACT: ``sorted_xs`` must already be sorted ascending (required
    for the O(log n) bisect; not verified — see percentile_linear).
    """
    n = len(sorted_xs)
    if n == 0:
        raise ValueError("midrank_percentile of empty input")
    n_less = bisect.bisect_left(sorted_xs, x)
    n_equal = bisect.bisect_right(sorted_xs, x) - n_less
    return 100.0 * (n_less + 0.5 * n_equal) / n


def grid_cdf(grid: list[float], x: float) -> float:
    """Empirical CDF value F(x) in [0.0, 1.0] from a percentile grid.

    ``grid`` is an ascending percentile grid (typically 101 values =
    p0..p100 of a calibration distribution): ``grid[i]`` is the value
    at cumulative fraction ``i / (len(grid) - 1)``. F(x) is recovered
    by inverse linear interpolation: find where ``x`` sits between
    grid values and interpolate the cumulative fraction.

    Clamping: ``x`` below ``grid[0]`` maps to 0.0, above ``grid[-1]``
    to 1.0.

    Flat runs: a repeated grid value means the calibration
    distribution has an atom there, so the true CDF jumps across the
    run's cumulative range. ``x`` exactly equal to a flat run's value
    maps to the *midpoint* of that range — deterministic, and the
    mid-rank convention consistent with ``midrank_percentile``. The
    result is monotone non-decreasing in ``x`` by construction (strict
    interpolation below the run approaches the range's lower edge,
    above the run its upper edge, and the midpoint sits between).

    CONTRACT: ``grid`` must already be sorted ascending (not verified —
    see percentile_linear).
    """
    m = len(grid)
    if m == 0:
        raise ValueError("grid_cdf of empty grid")
    lo = bisect.bisect_left(grid, x)
    hi = bisect.bisect_right(grid, x)
    if lo < hi:
        # x equals grid[lo:hi] — a flat run spanning cumulative
        # fractions lo/(m-1) .. (hi-1)/(m-1); return the midpoint.
        if m == 1:
            return 0.5  # single-point grid: the whole [0, 1] is one run
        return (lo + (hi - 1)) / (2.0 * (m - 1))
    if lo == 0:
        return 0.0  # x < grid[0]
    if lo == m:
        return 1.0  # x > grid[-1]
    # Strictly between grid[lo-1] and grid[lo] (both differ from x, so
    # the segment has nonzero width and the division is safe).
    frac = (x - grid[lo - 1]) / (grid[lo] - grid[lo - 1])
    return ((lo - 1) + frac) / (m - 1)


def two_sided_p(F: float, n: int) -> float:
    """Two-sided empirical p-value from a CDF position.

    ``min(1.0, max(2.0 * min(F, 1.0 - F), 1.0 / (n + 1)))``. The floor
    ``1 / (n + 1)`` is the resolution of an empirical p-value with n
    calibration points: no observation can be rarer than "beyond
    everything we calibrated on", so quoting a smaller p would claim
    precision the calibration set cannot support.
    """
    if not 0.0 <= F <= 1.0:
        raise ValueError(f"two_sided_p requires F in [0, 1], got {F}")
    if n < 1:
        raise ValueError(f"two_sided_p requires n >= 1, got {n}")
    return min(1.0, max(2.0 * min(F, 1.0 - F), 1.0 / (n + 1)))


def bh_adjust(ps: list[float]) -> list[float]:
    """Benjamini-Hochberg step-up adjusted q-values, in input order.

    For sorted p-values ``p_(1) <= ... <= p_(m)``, the adjusted value
    is ``q_(i) = min_{j >= i} (m * p_(j) / j)``, clamped at 1.0 — the
    standard step-up construction with monotone enforcement, computed
    by a single reverse pass over the sorted order. Ties in ``ps``
    receive identical q-values regardless of position (the sort is
    stable and the suffix-min washes out rank differences), so the
    result is deterministic. Empty input returns an empty list.
    """
    m = len(ps)
    if m == 0:
        return []
    for p in ps:
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"bh_adjust requires p-values in [0, 1], got {p}")
    order = sorted(range(m), key=lambda i: ps[i])
    qs = [0.0] * m
    running = 1.0  # doubles as the clamp at 1.0
    for rank in range(m, 0, -1):
        idx = order[rank - 1]
        candidate = m * ps[idx] / rank
        if candidate < running:
            running = candidate
        qs[idx] = running
    return qs


def _binom_cdf(x: int, n: int, p: float) -> float:
    """P(X <= x) for X ~ Binomial(n, p), built from math.comb."""
    q = 1.0 - p
    total = 0.0
    for i in range(x + 1):
        total += math.comb(n, i) * p**i * q ** (n - i)
    return total


def binomial_ci_clopper_pearson(
    k: int, n: int, conf: float = 0.95
) -> tuple[float, float]:
    """Exact (Clopper-Pearson) two-sided binomial confidence interval.

    Inverts the binomial CDF by bisection: the lower bound is the ``p``
    with ``P(X >= k | p) = alpha/2``, the upper bound the ``p`` with
    ``P(X <= k | p) = alpha/2``. Endpoints are exact by definition:
    ``k = 0`` gives lo = 0.0 and ``k = n`` gives hi = 1.0.

    A fixed 60 bisection steps (interval width 2**-60, far below float
    resolution of the answer) rather than a tolerance-based loop: the
    iteration count — and therefore the exact sequence of operations —
    is the same on every host, so the result is deterministic by
    construction. The CDF evaluation delegates ``**`` to libm pow,
    whose last-ULP variance can in principle perturb the root by
    ~1e-15 relative; that is orders of magnitude below the emission
    quantisation (12 sig figs) that callers apply.
    """
    if n < 1:
        raise ValueError(f"binomial CI requires n >= 1, got {n}")
    if not 0 <= k <= n:
        raise ValueError(f"binomial CI requires 0 <= k <= n, got k={k}, n={n}")
    if not 0.0 < conf < 1.0:
        raise ValueError(f"binomial CI requires conf in (0, 1), got {conf}")
    alpha = 1.0 - conf

    def _invert(x: int, target: float) -> float:
        # Find p with P(X <= x | n, p) = target. The CDF is strictly
        # decreasing in p, so bisection on [0, 1] converges.
        lo, hi = 0.0, 1.0
        for _ in range(60):  # fixed count: deterministic by construction
            mid = 0.5 * (lo + hi)
            if _binom_cdf(x, n, mid) > target:
                lo = mid  # CDF too high -> p is further right
            else:
                hi = mid
        return 0.5 * (lo + hi)

    # Lower: P(X >= k | p) = alpha/2  <=>  P(X <= k-1 | p) = 1 - alpha/2.
    ci_lo = 0.0 if k == 0 else _invert(k - 1, 1.0 - alpha / 2.0)
    # Upper: P(X <= k | p) = alpha/2.
    ci_hi = 1.0 if k == n else _invert(k, alpha / 2.0)
    return (ci_lo, ci_hi)
