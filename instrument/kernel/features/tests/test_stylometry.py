"""CONTRACTS for stylometry compact view."""
from __future__ import annotations
import math
from instrument.kernel.features.stylometry import FEATURE_ORDER, stylometry_compact
from instrument.kernel.tokens import tokenise

def test_feature_order_has_seven_keys():
    assert len(FEATURE_ORDER) == 7
    assert set(FEATURE_ORDER) == {'compression_ratio', 'semicolon_per_1k_words', 'comma_per_sentence', 'question_rate', 'exclamation_rate', 'quotation_density', 'subordination_density'}

def test_stylometry_returns_seven_keys():
    t = tokenise('Some prose goes here. ' * 50)
    r = stylometry_compact(t)
    assert set(r.keys()) == set(FEATURE_ORDER)

def test_compression_ratio_bounded_for_repetitive_text():
    text = 'the same phrase repeats ' * 200
    r = stylometry_compact(tokenise(text))
    assert 0.0 < r['compression_ratio'] < 0.2

def test_question_rate_counts_interrogatives():
    text = 'Is this a question? What about this? Declarative statement here. ' * 20
    r = stylometry_compact(tokenise(text))
    assert math.isclose(r['question_rate'], 2 / 3, abs_tol=0.02)

def test_exclamation_rate_counts_exclamations():
    text = 'Wow! Amazing! A neutral sentence. ' * 20
    r = stylometry_compact(tokenise(text))
    assert math.isclose(r['exclamation_rate'], 2 / 3, abs_tol=0.02)

def test_determinism_across_calls():
    text = 'The data revealed unusual patterns. ' * 40
    r1 = stylometry_compact(tokenise(text))
    r2 = stylometry_compact(tokenise(text))
    assert r1 == r2
