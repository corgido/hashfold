"""CONTRACTS for 5-axis convergence."""
from __future__ import annotations
import math
from instrument.reading.convergence import AGREE_TOLERANCE, AXES, BAND_HIGH, BAND_LOW, OVERALL_MAJORITY, compute
NAN = float('nan')

def test_five_axes():
    assert set(AXES.keys()) == {'sfl_process_complexity', 'rst_contrast', 'rst_elaboration', 'cohesion_repetition', 'register_modality'}

def test_thresholds_are_named_constants():
    assert BAND_LOW == 0.33
    assert BAND_HIGH == 0.66
    assert AGREE_TOLERANCE == 0.2
    assert OVERALL_MAJORITY == 4

def _zero_features() -> tuple[dict, dict]:
    shaper = {'sfl.process_proxy_entropy': 0.0, 'rst.contrast_marker_density': 0.0, 'rst.elaboration_marker_density': 0.0, 'cohesion.lexical_repetition': 0.0, 'register.modal_density': 0.0}
    other = {'sfl.pct_material': 0.0, 'sfl.pct_mental': 0.0, 'sfl.pct_relational': 0.0, 'sfl.pct_verbal': 0.0, 'sfl.pct_behavioral': 0.0, 'sfl.pct_existential': 0.0, 'sfl.modal_density': 0.0, 'sfl.hedge_density': 0.0, 'rst.contrast_density': 0.0, 'rst.concession_density': 0.0, 'rst.elaboration_density': 0.0, 'coh.lexical_repetition_rate': 0.0}
    return (shaper, other)

def test_all_zero_features_agree_low():
    shaper, other = _zero_features()
    r = compute(shaper, other)
    assert r['n_axes_incomparable'] == 0
    assert r['n_axes_agree'] == 5
    assert r['overall'] == 'converge'

def test_nan_shaper_value_is_incomparable():
    shaper, other = _zero_features()
    shaper['sfl.process_proxy_entropy'] = NAN
    r = compute(shaper, other)
    assert r['axes']['sfl_process_complexity']['direction'] == 'incomparable'
    assert r['n_axes_incomparable'] >= 1


def test_every_axis_carries_independence_annotation():
    """0.9.1: the reading itself declares how independent each axis's
    two views are (deep-investigation finding: 4 of 5 axes rest on
    shared vocabulary; only rst_contrast genuinely discriminates)."""
    from instrument.reading.convergence import AXIS_INDEPENDENCE
    assert AXIS_INDEPENDENCE == {
        'sfl_process_complexity': 'shared_lexicons',
        'rst_contrast': 'independent',
        'rst_elaboration': 'shared_marker_inventory',
        'cohesion_repetition': 'duplicate_computation',
        'register_modality': 'shared_lexicons',
    }
    shaper, other = _zero_features()
    r = compute(shaper, other)
    for name, axis in r['axes'].items():
        assert axis['independence'] == AXIS_INDEPENDENCE[name]
    # NaN (incomparable) axes carry the annotation too.
    shaper['sfl.process_proxy_entropy'] = NAN
    r = compute(shaper, other)
    assert r['axes']['sfl_process_complexity']['independence'] == 'shared_lexicons'


def test_coherence_excluded_axes_constant():
    from instrument.reading.convergence import COHERENCE_EXCLUDED_AXES
    assert COHERENCE_EXCLUDED_AXES == frozenset({'cohesion_repetition'})
