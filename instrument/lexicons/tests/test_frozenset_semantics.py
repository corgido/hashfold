"""CONTRACT: every lexicon value is an immutable frozenset of lowercase strings."""

from __future__ import annotations

from instrument.lexicons import LEXICONS


def test_every_value_is_frozenset():
    for key, value in LEXICONS.items():
        assert isinstance(value, frozenset), f"{key}: {type(value).__name__}"


def test_every_entry_is_lowercase_string():
    for key, words in LEXICONS.items():
        for word in words:
            assert isinstance(word, str), f"{key}: non-str entry {word!r}"
            assert word == word.lower(), f"{key}: non-lowercase {word!r}"
            assert word.strip() == word, f"{key}: whitespace in {word!r}"


def test_known_canonical_entries_present():
    assert "think" in LEXICONS["processes_mental"]
    assert "however" in LEXICONS["cohesion_adversative"]
    assert "and" in LEXICONS["cohesion_additive"]
    assert "because" in LEXICONS["cohesion_causal"]
