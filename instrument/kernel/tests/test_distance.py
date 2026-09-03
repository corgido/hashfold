"""CONTRACT: distance helpers are NaN-safe and produce expected values."""

from __future__ import annotations

import math

from instrument.kernel.distance import cosine_similarity, euclidean_distance
from instrument.kernel.nanmath import is_nan

NAN = float("nan")


def test_cosine_identity_is_one():
    v = [1.0, 2.0, 3.0]
    assert math.isclose(cosine_similarity(v, v), 1.0)


def test_cosine_orthogonal_is_zero():
    assert math.isclose(cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)


def test_cosine_nan_positions_skipped():
    # [1,NaN,1] vs [1,x,1] → effectively cosine([1,1],[1,1]) = 1
    assert math.isclose(cosine_similarity([1.0, NAN, 1.0], [1.0, 999.0, 1.0]), 1.0)


def test_cosine_all_nan_is_nan():
    assert is_nan(cosine_similarity([NAN, NAN], [1.0, 2.0]))


def test_cosine_zero_vector_is_nan():
    assert is_nan(cosine_similarity([0.0, 0.0], [1.0, 2.0]))


def test_euclidean_zero_for_equal_vectors():
    assert euclidean_distance([1.0, 2.0], [1.0, 2.0]) == 0.0


def test_euclidean_pythagorean():
    assert math.isclose(euclidean_distance([0.0, 0.0], [3.0, 4.0]), 5.0)


def test_euclidean_nan_positions_skipped():
    assert euclidean_distance([1.0, NAN, 1.0], [1.0, 999.0, 1.0]) == 0.0


def test_euclidean_all_nan_is_nan():
    assert is_nan(euclidean_distance([NAN, NAN], [1.0, 2.0]))
