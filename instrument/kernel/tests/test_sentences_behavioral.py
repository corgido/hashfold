from __future__ import annotations

from instrument.kernel.sentences import split_sentences, ABBREVIATIONS


def test_no_is_not_an_abbreviation():
    assert "no" not in ABBREVIATIONS


def test_no_period_splits_into_two_sentences():
    result = split_sentences("No. The answer is clear.")
    assert len(result) == 2


def test_dr_abbreviation_keeps_one_sentence():
    result = split_sentences("Dr. Smith arrived early.")
    assert len(result) == 1


def test_lowercase_no_splits_correctly():
    result = split_sentences("I said no. Then I left.")
    assert len(result) == 2


def test_p_abbreviation_keeps_one_sentence():
    result = split_sentences("See p. 42 for details.")
    assert len(result) == 1


def test_three_short_sentences():
    result = split_sentences("Yes. No. Maybe.")
    assert len(result) == 3
