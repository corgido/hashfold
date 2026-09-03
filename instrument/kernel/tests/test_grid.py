"""CONTRACT: linspace / interp_linear match numpy defaults without numpy."""

from __future__ import annotations

import math

from instrument.kernel.grid import interp_linear, linspace


def test_linspace_endpoints_included():
    assert linspace(0.0, 1.0, 2) == [0.0, 1.0]


def test_linspace_five_points():
    result = linspace(0.0, 1.0, 5)
    assert len(result) == 5
    assert math.isclose(result[0], 0.0)
    assert math.isclose(result[-1], 1.0)
    assert math.isclose(result[2], 0.5)


def test_linspace_single_point():
    assert linspace(3.0, 9.0, 1) == [3.0]


def test_interp_linear_exact_match_endpoints():
    result = interp_linear([0.0, 1.0], [0.0, 1.0], [10.0, 20.0])
    assert result == [10.0, 20.0]


def test_interp_linear_midpoint():
    result = interp_linear([0.5], [0.0, 1.0], [10.0, 20.0])
    assert result == [15.0]


def test_interp_linear_clamps_below_range():
    result = interp_linear([-0.5], [0.0, 1.0], [10.0, 20.0])
    assert result == [10.0]


def test_interp_linear_clamps_above_range():
    result = interp_linear([1.5], [0.0, 1.0], [10.0, 20.0])
    assert result == [20.0]


def test_interp_linear_multi_segment():
    # Source: (0,0), (0.5,10), (1.0,30)
    result = interp_linear([0.25, 0.75], [0.0, 0.5, 1.0], [0.0, 10.0, 30.0])
    assert math.isclose(result[0], 5.0)
    assert math.isclose(result[1], 20.0)
