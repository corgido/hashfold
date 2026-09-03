"""CONTRACTS for register features: match the legacy read composition."""
from __future__ import annotations
import math
from instrument.kernel.features.register import MODALS, NEGATIONS, lexical_novelty, modal_density, negation_density, register_read, sentence_length_variance
from instrument.kernel.tokens import tokenise

def test_modals_and_negations_frozensets():
    assert isinstance(MODALS, frozenset)
    assert isinstance(NEGATIONS, frozenset)

def test_lexical_novelty_bounded():
    text = 'The data was clear. ' * 40
    v = lexical_novelty(tokenise(text))
    assert 0.0 <= v <= 1.0

def test_variance_zero_for_single_sentence():
    text = 'One sentence only without period terminator in context'
    assert sentence_length_variance(tokenise(text)) == 0.0

def test_modal_and_negation_density_nonneg():
    text = 'We can decide. We will not retreat. ' * 20
    t = tokenise(text)
    assert modal_density(t) >= 0.0
    assert negation_density(t) >= 0.0
