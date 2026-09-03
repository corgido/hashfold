"""CONTRACT: NaN-aware reductions propagate NaN correctly (matching numpy.nan*)."""

from __future__ import annotations

import math

from instrument.kernel.nanmath import (
    all_nan,
    is_nan,
    nanmax,
    nanmean,
    nanmin,
    nanstd,
)

NAN = float("nan")


def test_is_nan():
    assert is_nan(NAN)
    assert not is_nan(0.0)
    assert not is_nan(-1.5)


def test_nanmean_skips_nan():
    assert nanmean([1.0, NAN, 3.0]) == 2.0


def test_nanmean_empty_is_nan():
    assert is_nan(nanmean([]))


def test_nanmean_all_nan_is_nan():
    assert is_nan(nanmean([NAN, NAN]))


def test_nanmin_nanmax():
    assert nanmin([3.0, 1.0, NAN, 2.0]) == 1.0
    assert nanmax([3.0, 1.0, NAN, 2.0]) == 3.0


def test_nanmin_all_nan_is_nan():
    assert is_nan(nanmin([NAN, NAN]))
    assert is_nan(nanmax([NAN, NAN]))


def test_nanstd_ddof_zero():
    # population std of [1, 2, 3] = sqrt(2/3)
    result = nanstd([1.0, 2.0, 3.0])
    assert math.isclose(result, math.sqrt(2.0 / 3.0))


def test_nanstd_skips_nan():
    # std of [1, 2, 3] with a NaN interleaved matches std of [1, 2, 3]
    expected = nanstd([1.0, 2.0, 3.0])
    assert math.isclose(nanstd([1.0, NAN, 2.0, NAN, 3.0]), expected)


def test_all_nan_true_and_false():
    assert all_nan([NAN, NAN])
    assert not all_nan([NAN, 1.0])
    assert all_nan([])
