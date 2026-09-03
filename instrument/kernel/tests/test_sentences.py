"""CONTRACT: abbreviation-aware sentence splitting is deterministic."""

from __future__ import annotations

from instrument.kernel.sentences import split_sentences, ABBREVIATIONS


def test_splits_on_period_space_uppercase():
    assert split_sentences("First. Second. Third.") == [
        "First.", "Second.", "Third.",
    ]


def test_does_not_split_on_known_abbreviation():
    result = split_sentences("Dr. Smith arrived. He was late.")
    assert result == ["Dr. Smith arrived.", "He was late."]


def test_chained_abbreviations_stay_together():
    result = split_sentences("Say e.g. Dr. Jones is here. Done.")
    assert result == ["Say e.g. Dr. Jones is here.", "Done."]


def test_empty_input_is_empty():
    assert split_sentences("") == []


def test_trailing_abbreviation_kept():
    result = split_sentences("This is etc.")
    assert result == ["This is etc."]


def test_abbreviations_is_frozenset():
    assert isinstance(ABBREVIATIONS, frozenset)


def test_determinism_across_calls():
    text = "Prof. Smith wrote a book. It was long."
    assert split_sentences(text) == split_sentences(text)
