"""CONTRACTS for subordination-density matching.

Multi-word subordinators are matched on word-token sequences, not
substrings, and both phrase classes count per occurrence. Before
the fix, `"so that" in sentence.lower()` counted "also that", and
each multi-word phrase counted at most once per sentence while
single-word subordinators counted per occurrence.
"""

from __future__ import annotations

from instrument.kernel.features.stylometry import _subordination_density


def _density(sentence: str, n_words: int = 1000) -> float:
    """Hits per 1000 words with a fixed denominator → hits count."""
    return _subordination_density([sentence], n_words)


def test_also_that_is_not_so_that():
    assert _density("It's also that the team was tired.") == 0.0


def test_so_that_on_token_boundary_counts():
    assert _density("We refactored so that the tests pass.") == 1.0


def test_multi_word_counts_per_occurrence():
    s = ("Even though it rained, and even though the forecast was "
         "clear, they went.")
    # two "even though" phrases; "though" tokens are consumed so they
    # do not double-count via the single-word set.
    assert _density(s) == 2.0


def test_single_word_still_counts_per_occurrence():
    s = "Because it rained, and because the wind rose, they stayed."
    assert _density(s) == 2.0


def test_longest_phrase_wins():
    # "as soon as" must match as one 3-token phrase, not leak parts.
    assert _density("Leave as soon as the gate opens.") == 1.0
