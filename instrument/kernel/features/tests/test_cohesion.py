"""CONTRACTS for cohesion compact view."""
from __future__ import annotations
import math
from instrument.kernel.features.cohesion import PRONOUNS, STOPWORDS, cohesion_compact
from instrument.kernel.nanmath import is_nan
from instrument.kernel.tokens import tokenise

def test_stopwords_is_frozenset_superset_of_pronouns():
    assert isinstance(STOPWORDS, frozenset)
    assert isinstance(PRONOUNS, frozenset)
    assert PRONOUNS <= STOPWORDS

def test_cohesion_below_envelope_returns_nan():
    reading = cohesion_compact(tokenise('short text ' * 5))
    assert reading['below_envelope'] is True
    assert is_nan(reading['type_token_ratio'])
    assert is_nan(reading['pronoun_density'])
    assert is_nan(reading['lexical_repetition'])

def test_cohesion_above_envelope_returns_bounded_values():
    text = 'The researcher thought about the problem carefully. She believed the solution existed. She said the method would work. The argument was clear and strong. ' * 10
    reading = cohesion_compact(tokenise(text))
    assert reading['below_envelope'] is False
    assert 0.0 <= reading['type_token_ratio'] <= 1.0
    assert reading['pronoun_density'] >= 0.0
    assert 0.0 <= reading['lexical_repetition'] <= 1.0
