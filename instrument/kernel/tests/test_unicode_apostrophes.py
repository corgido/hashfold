"""CONTRACT: U+2019 (typographic apostrophe) measures like ASCII `'`.

LLM and word-processor output uses U+2019 in contractions. Before
this contract, the word tokeniser fragmented "don\u2019t" into
["don", "t"], so every apostrophe-form lexicon entry (NEGATIONS,
process verbs) silently stopped matching and negation_density
collapsed to ~0 on smart-quote input. The fixtures only contained
ASCII apostrophes, so the goldens blessed the broken path.
"""

from __future__ import annotations

from instrument.kernel.cleaning import clean, normalise_apostrophes
from instrument.kernel.features.register import negation_density
from instrument.kernel.tokens import tokenise, word_tokens

_STRAIGHT = (
    "I don't know whether they won't listen. It isn't that they "
    "can't engage; they haven't had the time, and we shouldn't "
    "assume malice when the explanation is simpler. "
) * 10

_CURLY = _STRAIGHT.replace("'", "\u2019")


def test_word_tokens_keep_curly_contractions_whole():
    assert word_tokens("don\u2019t stop") == ["don't", "stop"]


def test_word_tokens_parity_straight_vs_curly():
    assert word_tokens(_CURLY) == word_tokens(_STRAIGHT)


def test_clean_normalises_typographic_apostrophe():
    assert "\u2019" not in clean(_CURLY)
    assert normalise_apostrophes("don\u2019t") == "don't"


def test_negation_density_parity():
    straight = negation_density(tokenise(_STRAIGHT))
    curly = negation_density(tokenise(_CURLY))
    assert straight > 0.0
    assert curly == straight


def test_n_words_parity():
    assert tokenise(_CURLY).n_words == tokenise(_STRAIGHT).n_words


def test_full_joint_reading_parity():
    """The whole reading — both views, stylometry, convergence — must
    be identical for curly vs straight apostrophes (ts excluded)."""
    from instrument.reading.joint import joint_reading

    a = joint_reading(_STRAIGHT)
    b = joint_reading(_CURLY)
    a.pop("ts")
    b.pop("ts")
    assert a == b
