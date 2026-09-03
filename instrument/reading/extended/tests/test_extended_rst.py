"""CONTRACTS for extended RST: 13 features with legacy parity."""
from __future__ import annotations
import math
from instrument.reading.document import parse
from instrument.reading.extended.rst import analyse

def test_analyse_returns_thirteen_features():
    doc = parse('One sentence. Two sentences. Three sentences. ' * 15)
    result = analyse(doc)
    assert len(result) == 13
    expected = {'contrast_density', 'concession_density', 'cause_density', 'result_density', 'elaboration_density', 'sequence_density', 'condition_density', 'purpose_density', 'summary_density', 'total_marker_density', 'relation_diversity', 'branching_score', 'max_depth_score'}
    assert set(result.keys()) == expected

def test_empty_doc_zero_features():
    doc = parse('')
    result = analyse(doc)
    assert all((v == 0.0 for v in result.values()))
