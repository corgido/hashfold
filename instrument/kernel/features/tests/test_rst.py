"""CONTRACTS for RST compact view."""
from __future__ import annotations
import math
from instrument.kernel.features.rst import ALL_MARKERS, ELABORATION_BROAD_MARKERS, ELABORATION_MARKERS, count_sentence_initial_markers, has_sentence_terminators, rst_compact
from instrument.kernel.nanmath import is_nan
from instrument.kernel.tokens import tokenise

def test_marker_frozensets_nonempty():
    for name, markers in ALL_MARKERS.items():
        assert isinstance(markers, frozenset), name
        assert markers, name

def test_elaboration_broad_is_subset_of_elaboration():
    assert ELABORATION_BROAD_MARKERS <= ELABORATION_MARKERS

def test_has_sentence_terminators():
    assert has_sentence_terminators('hello. world')
    assert has_sentence_terminators('why!')
    assert has_sentence_terminators('what?')
    assert not has_sentence_terminators('no terminators here')

def test_rst_below_envelope_returns_nan():
    r = rst_compact(tokenise('short text without enough content. ' * 3))
    assert r['below_envelope'] is True
    assert is_nan(r['marker_density'])
    assert is_nan(r['elaboration_marker_density'])
    assert is_nan(r['contrast_marker_density'])
