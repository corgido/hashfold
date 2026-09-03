"""CONTRACTS for the extended F() composer and FeatureVector."""
from __future__ import annotations
import math
from instrument.reading.document import parse
from instrument.reading.extended.feature import ALL_FEATURE_KEYS, COHESION_FEATURE_KEYS, F, F_from_doc, FeatureVector, RST_FEATURE_KEYS, SFL_FEATURE_KEYS

def test_all_feature_keys_has_thirty_seven():
    assert len(ALL_FEATURE_KEYS) == 37
    assert len(SFL_FEATURE_KEYS) == 11
    assert len(RST_FEATURE_KEYS) == 13
    assert len(COHESION_FEATURE_KEYS) == 13

def test_all_feature_keys_are_prefixed():
    for k in ALL_FEATURE_KEYS:
        assert k.startswith(('sfl.', 'rst.', 'coh.'))

def test_F_returns_featurevector():
    fv = F('The committee argued the proposal was flawed. ' * 30, text_id='t1')
    assert isinstance(fv, FeatureVector)
    assert fv.text_id == 't1'
    assert fv.n_words > 0

def test_to_dict_has_all_keys_plus_metadata():
    fv = F('The committee argued. ' * 30)
    d = fv.to_dict()
    for k in ALL_FEATURE_KEYS:
        assert k in d
    assert {'text_id', 'n_words', 'n_sentences', 'n_paragraphs'} <= set(d.keys())

def test_to_vector_length_is_thirty_seven():
    fv = F('The committee argued. ' * 30)
    assert len(fv.to_vector()) == 37
