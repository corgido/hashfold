from __future__ import annotations

import pytest

from instrument.kernel.features.stylometry import _subordination_density
from instrument.kernel.tokens import word_tokens


def test_even_though_counts_once():
    sent = "Even though it rained, we went out."
    n_words = len(word_tokens(sent))
    expected = 1 / n_words * 1000
    result = _subordination_density([sent], n_words)
    assert result == pytest.approx(expected)


def test_although_counts_once():
    sent = "Although she was tired, she continued."
    n_words = len(word_tokens(sent))
    expected = 1 / n_words * 1000
    result = _subordination_density([sent], n_words)
    assert result == pytest.approx(expected)


def test_two_subordinations_in_one_sentence():
    sent = "Even though he tried, and although she helped, it failed."
    n_words = len(word_tokens(sent))
    expected = 2 / n_words * 1000
    result = _subordination_density([sent], n_words)
    assert result == pytest.approx(expected)


def test_standalone_though_counts_once():
    sent = "He went, though she warned him."
    n_words = len(word_tokens(sent))
    expected = 1 / n_words * 1000
    result = _subordination_density([sent], n_words)
    assert result == pytest.approx(expected)
