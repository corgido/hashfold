"""CONTRACT: calibration statistics are exact against hand-computed
values and match the conventions of tools/build_reference.py.
"""

from __future__ import annotations

import math

import pytest

from instrument.kernel.stats import (
    bh_adjust,
    binomial_ci_clopper_pearson,
    grid_cdf,
    mean,
    midrank_percentile,
    percentile_linear,
    pstdev,
    two_sided_p,
)


# ---- mean / pstdev ---------------------------------------------------------

def test_mean():
    assert mean([1.0, 2.0, 3.0]) == 2.0


def test_mean_empty_raises():
    with pytest.raises(ValueError):
        mean([])


def test_pstdev_ddof_zero():
    # population std of [1, 2, 3] = sqrt(2/3)
    assert math.isclose(pstdev([1.0, 2.0, 3.0]), math.sqrt(2.0 / 3.0))


def test_pstdev_empty_raises():
    with pytest.raises(ValueError):
        pstdev([])


# ---- percentile_linear -----------------------------------------------------

def test_percentile_single_element():
    assert percentile_linear([42.0], 0.0) == 42.0
    assert percentile_linear([42.0], 50.0) == 42.0
    assert percentile_linear([42.0], 100.0) == 42.0


def test_percentile_two_elements_median():
    # pos = (2-1) * 0.5 = 0.5 -> halfway between 1 and 3
    assert percentile_linear([1.0, 3.0], 50.0) == 2.0


def test_percentile_interpolated_q25():
    # pos = (4-1) * 0.25 = 0.75 -> 1 * 0.25 + 2 * 0.75 = 1.75
    assert percentile_linear([1.0, 2.0, 3.0, 4.0], 25.0) == 1.75


def test_percentile_endpoints():
    xs = [5.0, 7.0, 9.0, 11.0]
    assert percentile_linear(xs, 0.0) == 5.0
    assert percentile_linear(xs, 100.0) == 11.0


def test_percentile_guards():
    with pytest.raises(ValueError):
        percentile_linear([], 50.0)
    with pytest.raises(ValueError):
        percentile_linear([1.0], -0.1)
    with pytest.raises(ValueError):
        percentile_linear([1.0], 100.1)


def test_percentile_matches_build_reference():
    # tools/build_reference.py is slated to import stats.percentile_linear;
    # until then, prove bit-identity against its private _percentile.
    try:
        from tools.build_reference import _percentile
    except ImportError:
        pytest.skip("tools not importable as a package from this rootdir")
    xs = sorted([3.1, 0.2, 7.7, 5.5, 1.9, 4.4, 6.0, 2.2])
    for q in (0.0, 5.0, 25.0, 33.3, 50.0, 66.6, 75.0, 95.0, 100.0):
        assert percentile_linear(xs, q) == _percentile(xs, q)


# ---- midrank_percentile ----------------------------------------------------

def test_midrank_no_ties():
    # x=2 in [1,2,3,4]: n_less=1, n_equal=1 -> 100 * 1.5 / 4 = 37.5
    assert midrank_percentile([1.0, 2.0, 3.0, 4.0], 2.0) == 37.5


def test_midrank_all_equal():
    # all four equal x: n_less=0, n_equal=4 -> 100 * 2 / 4 = 50
    assert midrank_percentile([5.0, 5.0, 5.0, 5.0], 5.0) == 50.0


def test_midrank_below_min():
    # n_less=0, n_equal=0 -> formula gives exactly 0
    assert midrank_percentile([1.0, 2.0, 3.0], 0.0) == 0.0


def test_midrank_above_max():
    # n_less=n, n_equal=0 -> 100
    assert midrank_percentile([1.0, 2.0, 3.0], 10.0) == 100.0


def test_midrank_tie_block():
    # [1,2,2,2,3], x=2: n_less=1, n_equal=3 -> 100 * 2.5 / 5 = 50
    assert midrank_percentile([1.0, 2.0, 2.0, 2.0, 3.0], 2.0) == 50.0


def test_midrank_empty_raises():
    with pytest.raises(ValueError):
        midrank_percentile([], 1.0)


# ---- grid_cdf --------------------------------------------------------------

def test_grid_cdf_exact_at_grid_points():
    grid = [0.0, 1.0, 2.0, 3.0, 4.0]
    # unique grid[i] maps to i / (m-1)
    assert grid_cdf(grid, 0.0) == 0.0
    assert grid_cdf(grid, 2.0) == 0.5
    assert grid_cdf(grid, 4.0) == 1.0


def test_grid_cdf_interpolates_between_points():
    grid = [0.0, 1.0, 2.0, 3.0, 4.0]
    # x=2.5 sits halfway in segment [2, 3] -> (2 + 0.5) / 4 = 0.625
    assert grid_cdf(grid, 2.5) == 0.625


def test_grid_cdf_clamps():
    grid = [0.0, 1.0, 2.0]
    assert grid_cdf(grid, -5.0) == 0.0
    assert grid_cdf(grid, 99.0) == 1.0


def test_grid_cdf_flat_run_midpoint():
    # Flat run of 1.0 at indices 1..3 of a 5-point grid spans
    # cumulative 1/4 .. 3/4; x == 1.0 maps to the midpoint 0.5.
    grid = [0.0, 1.0, 1.0, 1.0, 2.0]
    assert grid_cdf(grid, 1.0) == 0.5
    # Strictly below / above the run interpolate toward its edges.
    assert grid_cdf(grid, 0.5) == 0.125   # (0 + 0.5) / 4
    assert grid_cdf(grid, 1.5) == 0.875   # (3 + 0.5) / 4


def test_grid_cdf_single_point_grid():
    assert grid_cdf([5.0], 4.0) == 0.0
    assert grid_cdf([5.0], 5.0) == 0.5    # whole [0,1] is one flat run
    assert grid_cdf([5.0], 6.0) == 1.0


def test_grid_cdf_monotone_over_scan():
    grid = [0.0, 1.0, 1.0, 1.0, 2.0, 3.0, 3.0, 5.0]
    xs = [-1.0 + 0.05 * i for i in range(150)]  # scan -1.0 .. 6.45
    fs = [grid_cdf(grid, x) for x in xs]
    assert all(0.0 <= f <= 1.0 for f in fs)
    assert all(b >= a for a, b in zip(fs, fs[1:]))


def test_grid_cdf_empty_raises():
    with pytest.raises(ValueError):
        grid_cdf([], 1.0)


# ---- two_sided_p -----------------------------------------------------------

def test_two_sided_p_floor():
    # F=0 -> 2*min(F, 1-F) = 0, floored at 1/(n+1)
    assert two_sided_p(0.0, 99) == 1.0 / 100.0
    assert two_sided_p(1.0, 9) == 0.1
    # tail value above the floor is untouched
    assert two_sided_p(0.1, 99) == pytest.approx(0.2)


def test_two_sided_p_symmetric_center_clamps_to_one():
    # F = 0.5 -> 2 * 0.5 = 1.0, clamped at 1.0
    assert two_sided_p(0.5, 100) == 1.0


def test_two_sided_p_symmetry():
    # 0.25 / 0.75 are exact dyadic floats, so 1.0 - F is exact and the
    # symmetry holds bitwise, not just approximately.
    assert two_sided_p(0.25, 50) == two_sided_p(0.75, 50)


def test_two_sided_p_guards():
    with pytest.raises(ValueError):
        two_sided_p(-0.1, 10)
    with pytest.raises(ValueError):
        two_sided_p(1.1, 10)
    with pytest.raises(ValueError):
        two_sided_p(0.5, 0)


# ---- bh_adjust -------------------------------------------------------------

def test_bh_adjust_known_vector():
    # ps = [0.01, 0.04, 0.03, 0.005], m = 4.
    # Sorted: p_(1)=0.005, p_(2)=0.01, p_(3)=0.03, p_(4)=0.04.
    # Raw m*p/j:   4*0.005/1 = 0.02
    #              4*0.01 /2 = 0.02
    #              4*0.03 /3 = 0.04
    #              4*0.04 /4 = 0.04
    # Suffix-min:  q_(4)=0.04, q_(3)=min(0.04, 0.04)=0.04,
    #              q_(2)=min(0.02, 0.04)=0.02, q_(1)=min(0.02, 0.02)=0.02.
    # Back in input order: [0.02, 0.04, 0.04, 0.02].
    qs = bh_adjust([0.01, 0.04, 0.03, 0.005])
    expected = [0.02, 0.04, 0.04, 0.02]
    assert len(qs) == 4
    for got, want in zip(qs, expected):
        assert math.isclose(got, want, rel_tol=1e-12)


def test_bh_adjust_monotone_in_sorted_order():
    ps = [0.30, 0.001, 0.20, 0.045, 0.02, 0.8, 0.11]
    qs = bh_adjust(ps)
    paired = sorted(zip(ps, qs))
    sorted_qs = [q for _, q in paired]
    assert all(b >= a for a, b in zip(sorted_qs, sorted_qs[1:]))


def test_bh_adjust_preserves_input_order():
    ps = [0.04, 0.005, 0.03, 0.01]
    qs = bh_adjust(ps)
    # Same multiset of p-values in a different order: each p must map
    # to the same q regardless of position.
    ps2 = [0.005, 0.01, 0.03, 0.04]
    qs2 = bh_adjust(ps2)
    mapping = dict(zip(ps2, qs2))
    assert qs == [mapping[p] for p in ps]


def test_bh_adjust_all_at_most_one():
    qs = bh_adjust([0.9, 0.99, 0.5, 1.0, 0.7])
    assert all(q <= 1.0 for q in qs)


def test_bh_adjust_empty():
    assert bh_adjust([]) == []


def test_bh_adjust_guards():
    with pytest.raises(ValueError):
        bh_adjust([0.5, -0.01])
    with pytest.raises(ValueError):
        bh_adjust([1.5])


# ---- binomial_ci_clopper_pearson -------------------------------------------

def test_clopper_pearson_k_zero():
    lo, hi = binomial_ci_clopper_pearson(0, 10)
    assert lo == 0.0
    # exact upper bound: 1 - 0.025**(1/10) = 0.30850...
    assert abs(hi - 0.3085) < 2e-3


def test_clopper_pearson_k_equals_n():
    lo, hi = binomial_ci_clopper_pearson(10, 10)
    assert hi == 1.0
    assert abs(lo - 0.6915) < 2e-3


def test_clopper_pearson_k2_n10():
    lo, hi = binomial_ci_clopper_pearson(2, 10)
    assert abs(lo - 0.0252) < 2e-3
    assert abs(hi - 0.5561) < 2e-3


def test_clopper_pearson_contains_point_estimate():
    for k, n in ((0, 10), (2, 10), (5, 10), (10, 10), (7, 23), (1, 100)):
        lo, hi = binomial_ci_clopper_pearson(k, n)
        assert lo <= k / n <= hi


def test_clopper_pearson_deterministic():
    assert binomial_ci_clopper_pearson(3, 17) == binomial_ci_clopper_pearson(3, 17)


def test_clopper_pearson_guards():
    with pytest.raises(ValueError):
        binomial_ci_clopper_pearson(-1, 10)
    with pytest.raises(ValueError):
        binomial_ci_clopper_pearson(11, 10)
    with pytest.raises(ValueError):
        binomial_ci_clopper_pearson(1, 0)
    with pytest.raises(ValueError):
        binomial_ci_clopper_pearson(1, 10, conf=0.0)
    with pytest.raises(ValueError):
        binomial_ci_clopper_pearson(1, 10, conf=1.0)
