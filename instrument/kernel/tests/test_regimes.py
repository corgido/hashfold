"""CONTRACTS for the three slicing regimes and legacy parity."""
from __future__ import annotations
from instrument.kernel.regimes import REGIMES, measure_all_regimes, regime_chunker, regime_elegant, regime_flat

def test_flat_regime_covers_document():
    text = 'any text here'
    r = regime_flat(text)
    assert r['n_slices'] == 1
    assert r['slices'] == [(0, len(text))]

def test_chunker_regime_short_doc_collapses():
    r = regime_chunker('short')
    assert r['n_slices'] == 1

def test_chunker_regime_long_doc_splits():
    text = 'word ' * 1000
    r = regime_chunker(text, n_slices=3)
    assert r['n_slices'] == 3
    assert r['slices'][0][0] == 0
    assert r['slices'][-1][1] == len(text)
    for i in range(len(r['slices']) - 1):
        assert r['slices'][i][1] == r['slices'][i + 1][0]

def test_elegant_regime_returns_contract_ok_slicing():
    para = 'The committee argued that the proposal was flawed. They believed the costs were too high. The chair said the decision would be deferred. ' * 5
    text = para + '\n\n' + para + '\n\n' + para
    r = regime_elegant(text)
    assert r['n_slices'] >= 1
    assert r['boundary_level']

def test_measure_all_regimes_returns_three_regimes():
    text = 'some text ' * 200
    all_r = measure_all_regimes(text)
    assert set(all_r.keys()) == {'flat', 'chunker', 'elegant'}
    for r in all_r.values():
        assert 'contract_ok' in r
        assert 'contract_failures' in r
