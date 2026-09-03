"""CONTRACTS for coherence emission + legacy parity."""
from __future__ import annotations
from instrument.emissions.catalog import load_catalog
from instrument.emissions.coherence import compute_coherence
from instrument.emissions.types import CoherenceEmission

def test_none_convergence_returns_null_emission():
    r = compute_coherence(None)
    assert r.value is None
    assert r.label is None
    assert r.n_axes_measurable == 0
    assert r.n_axes_agree == 0
    assert r.diverging_axes == ()

def test_all_agree_returns_high():
    conv = {'axes': {'a': {'direction': 'agree_high'}, 'b': {'direction': 'agree_mid'}, 'c': {'direction': 'agree_low'}}, 'overall': 'converge'}
    bands = load_catalog('v2')['coherence']['bands']
    r = compute_coherence(conv, bands)
    assert r.value == 1.0
    assert r.n_axes_agree == 3
    assert r.n_axes_measurable == 3

def test_half_agree_half_diverge():
    conv = {'axes': {'a': {'direction': 'agree_high'}, 'b': {'direction': 'diverge'}}, 'overall': 'mixed'}
    r = compute_coherence(conv, [])
    assert r.value == 0.5
    assert r.diverging_axes == ('b',)


def _five_axis_conv(cohesion_direction='agree_high'):
    return {
        'axes': {
            'sfl_process_complexity': {'direction': 'agree_mid'},
            'rst_contrast': {'direction': 'diverge'},
            'rst_elaboration': {'direction': 'agree_mid'},
            'cohesion_repetition': {'direction': cohesion_direction},
            'register_modality': {'direction': 'agree_mid'},
        },
        'overall': 'converge',
    }


def test_duplicate_axis_excluded_from_scalar():
    """0.9.1: cohesion_repetition is one measurement counted twice
    (identical stopword lists; r=0.99, 100% within-tolerance agreement
    on real corpora) — structural agreement must not inflate the
    coherence scalar. The axis stays in the reading; it leaves the
    numerator AND denominator here."""
    r = compute_coherence(_five_axis_conv(), [])
    # 4 measurable non-excluded axes (3 agree, 1 diverge) -> 3/4.
    assert r.n_axes_measurable == 4
    assert r.n_axes_agree == 3
    assert abs(r.value - 3.0 / 4.0) < 1e-12
    assert r.evidence['excluded_axes'] == ['cohesion_repetition']
    # The excluded axis's direction is still visible in the evidence.
    assert r.evidence['axis_directions']['cohesion_repetition'] == 'agree_high'


def test_excluded_axis_direction_does_not_matter():
    a = compute_coherence(_five_axis_conv('agree_high'), [])
    b = compute_coherence(_five_axis_conv('diverge'), [])
    assert a.value == b.value
    assert a.n_axes_measurable == b.n_axes_measurable
