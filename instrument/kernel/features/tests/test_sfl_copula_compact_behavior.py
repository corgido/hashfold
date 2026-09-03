"""Regression guard for compact SFL copula handling."""
from __future__ import annotations

from instrument.kernel.features.sfl import classify_token, sfl_compact
from instrument.kernel.tokens import tokenise


def test_classify_is_relational():
    assert classify_token('is') == 'relational'


def test_classify_was_relational():
    assert classify_token('was') == 'relational'


def test_copula_text_has_positive_stative_active_ratio():
    text = "The sky is blue. " * 40
    result = sfl_compact(tokenise(text))
    assert result['stative_active_ratio'] > 0
