from __future__ import annotations

import pytest

from instrument.kernel.features.register import NEGATIONS, negation_density
from instrument.kernel.features.trajectory_features import read_trajectory
from instrument.kernel.regimes import regime_elegant
from instrument.kernel.tokens import tokenise


def test_contracted_negations_detected():
    text = "I don't think she can't go and he won't try. " * 20
    tokens = tokenise(text)
    assert tokens.n_words > 150
    assert negation_density(tokens) > 0.0


def test_non_contracted_negations_detected():
    text = "Not ever and never and nothing and nobody and cannot. " * 20
    tokens = tokenise(text)
    assert negation_density(tokens) > 0.0


def test_no_negations_yields_zero():
    text = "The bright sun rose over the quiet hills at dawn. " * 20
    tokens = tokenise(text)
    assert negation_density(tokens) == 0.0


def test_known_density():
    filler = "the quick brown fox jumps over a lazy dog near big red"
    filler_words = filler.split()
    neg = "don't"
    neg_count = 3
    parts = []
    for i in range(neg_count):
        parts.append(neg)
        parts.extend(filler_words)
    text = " ".join(parts)
    tokens = tokenise(text)
    n_words = tokens.n_words
    expected = neg_count / n_words * 100.0
    assert negation_density(tokens) == pytest.approx(expected)


def test_apostrophe_and_bare_forms_in_negations():
    assert "don't" in NEGATIONS
    assert "dont" in NEGATIONS
    assert "can't" in NEGATIONS
    assert "cant" in NEGATIONS
    assert "won't" in NEGATIONS
    assert "wont" in NEGATIONS


def test_trajectory_negation_with_contractions():
    text = "I don't believe it and she won't agree. " * 60
    tokens = tokenise(text)
    slicing = regime_elegant(tokens.text)
    trajectory = read_trajectory(tokens, slicing["slices"])
    assert any(v > 0 for v in trajectory["negation_density"])
