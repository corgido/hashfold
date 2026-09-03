"""CONTRACTS for the three embedding forms + legacy parity."""

from __future__ import annotations

import math

from instrument.kernel.nanmath import is_nan
from instrument.reading.embedder import (
    FEATURE_SCALES,
    REGIME_ORDER,
    STAT_ORDER,
    TRAJECTORY_GRID,
    flat_embedding,
    normalise_feature,
    normalise_vector,
    regime_embedding,
    trajectory_embedding,
)
from instrument.reading.flat import FEATURE_ORDER


def test_feature_scales_covers_all_features():
    assert set(FEATURE_SCALES.keys()) == set(FEATURE_ORDER)


def test_regime_order_has_three():
    assert REGIME_ORDER == ("flat", "chunker", "elegant")


def test_stat_order_has_four():
    assert STAT_ORDER == ("mean", "min", "max", "std")


def test_trajectory_grid_is_ten():
    assert TRAJECTORY_GRID == 10


def test_normalise_feature_clamps_low_and_high():
    assert normalise_feature("cohesion.type_token_ratio", -0.5) == 0.0
    assert normalise_feature("cohesion.type_token_ratio", 1.5) == 1.0


def test_normalise_feature_nan_propagates():
    assert is_nan(normalise_feature("cohesion.type_token_ratio", float("nan")))


def test_normalise_feature_log1p_on_variance():
    """sentence_length_variance should be log1p-compressed before scaling."""
    raw_scaled = (math.log1p(100.0) - 0.0) / (10.0 - 0.0)
    got = normalise_feature("register.sentence_length_variance", 100.0)
    assert math.isclose(got, raw_scaled, rel_tol=1e-12)


def test_normalise_vector_returns_thirteen():
    vec = [0.5] * 13
    out = normalise_vector(vec)
    assert len(out) == 13


def test_flat_embedding_below_envelope_all_nan():
    result = flat_embedding("short")
    assert len(result) == 13
    assert all(is_nan(v) for v in result)


def test_flat_embedding_returns_thirteen_floats():
    text = "The committee argued. They deliberated. " * 40
    result = flat_embedding(text)
    assert len(result) == 13


def test_regime_embedding_returns_one_fifty_six():
    text = "The committee argued. They deliberated. " * 100
    result = regime_embedding(text)
    assert len(result) == 156  # 3 regimes * 13 features * 4 stats


def test_trajectory_embedding_returns_one_thirty():
    text = "The committee argued. They deliberated. " * 100
    result = trajectory_embedding(text)
    assert len(result) == 130  # 13 features * 10 grid positions


def test_embeddings_are_deterministic_and_fixed_length():
    """Smoke: all three embeddings run end-to-end on a realistic doc and
    return fixed-length vectors with valid floats."""
    paragraph = (
        "The committee argued the proposal was flawed. "
        "They believed the costs were too high. "
        "However, the chair deferred the decision. "
        "As a result, further evidence was needed. "
    ) * 5
    text = (paragraph + "\n\n") * 4

    for fn, expected_len, label in (
        (flat_embedding, 13, "flat"),
        (regime_embedding, 156, "regime"),
        (trajectory_embedding, 130, "trajectory"),
    ):
        vec_a = fn(text)
        vec_b = fn(text)
        assert len(vec_a) == expected_len, label
        assert vec_a == vec_b, f"{label}: non-deterministic"
        for i, v in enumerate(vec_a):
            # Either a float or NaN; no strings / None.
            if is_nan(v):
                continue
            assert math.isclose(v, v, rel_tol=1e-12, abs_tol=1e-12), (
                f"{label}[{i}]: not a real float: {v!r}"
            )
