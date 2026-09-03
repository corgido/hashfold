"""CONTRACTS for the flat 13-feature composer + tokenise-once."""
from __future__ import annotations
import math
from unittest.mock import patch
from instrument.reading.flat import FEATURE_ORDER, flat_reading, flat_reading_from_text, read
from instrument.kernel.tokens import tokenise

def test_feature_order_has_thirteen_keys():
    assert len(FEATURE_ORDER) == 13

def test_feature_order_prefixes():
    prefixes = {k.split('.')[0] for k in FEATURE_ORDER}
    assert prefixes == {'sfl', 'rst', 'cohesion', 'register'}

def test_read_returns_four_buckets():
    t = tokenise('The committee argued. ' * 30)
    r = read(t)
    assert set(r.keys()) == {'sfl', 'rst', 'cohesion', 'register'}

def test_flat_reading_has_all_feature_keys():
    text = 'The committee argued the proposal was flawed. ' * 30
    out = flat_reading(tokenise(text))
    for k in FEATURE_ORDER:
        assert k in out, k
    assert 'n_words' in out
    assert 'below_envelope' in out

def test_flat_reading_below_envelope_marks_below():
    r = flat_reading(tokenise('short text'))
    assert r['below_envelope'] is True
