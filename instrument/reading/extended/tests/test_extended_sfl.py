"""CONTRACTS for extended SFL: 11 features with legacy parity."""
from __future__ import annotations
import math
from instrument.reading.document import parse
from instrument.reading.extended.sfl import PROCESS_LEXICONS, analyse, classify_token

def test_process_lexicons_has_six_types():
    assert set(PROCESS_LEXICONS.keys()) == {'material', 'mental', 'relational', 'verbal', 'behavioral', 'existential'}
    for name, lex in PROCESS_LEXICONS.items():
        assert isinstance(lex, frozenset), name

def test_classify_token_probes():
    assert classify_token('think') == 'mental'
    assert classify_token('said') == 'verbal'
    assert classify_token('became') == 'relational'
    assert classify_token('unknownword') is None

def test_analyse_returns_eleven_features():
    doc = parse('The committee argued. They believed. ' * 30)
    result = analyse(doc)
    assert len(result) == 11
    expected = {'pct_material', 'pct_mental', 'pct_relational', 'pct_verbal', 'pct_behavioral', 'pct_existential', 'process_density', 'modal_density', 'hedge_density', 'booster_density', 'modality_balance'}
    assert set(result.keys()) == expected
