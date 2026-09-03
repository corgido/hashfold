"""CONTRACTS for extended cohesion: 13 features with legacy parity."""
from __future__ import annotations
import math
from instrument.reading.document import parse
from instrument.reading.extended.cohesion import analyse

def test_analyse_returns_thirteen_features():
    doc = parse('The committee met. They argued. ' * 50)
    result = analyse(doc)
    assert len(result) == 13
    expected = {'pronoun_density', 'demonstrative_density', 'definite_article_density', 'reference_density', 'additive_density', 'adversative_density', 'causal_density', 'temporal_density', 'conjunction_balance', 'type_token_ratio', 'lexical_repetition_rate', 'lexical_chain_count', 'lexical_chain_span'}
    assert set(result.keys()) == expected

def test_empty_doc_zero_features():
    doc = parse('')
    result = analyse(doc)
    assert all((v == 0.0 for v in result.values()))
