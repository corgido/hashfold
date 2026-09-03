"""Behavioral tests for extended SFL copula handling."""
from __future__ import annotations

from instrument.reading.extended.sfl import classify_token, analyse
from instrument.reading.document import parse


def test_classify_is_relational():
    assert classify_token('is') == 'relational'


def test_classify_are_relational():
    assert classify_token('are') == 'relational'


def test_classify_was_relational():
    assert classify_token('was') == 'relational'


def test_classify_were_relational():
    assert classify_token('were') == 'relational'


def test_classify_be_relational():
    assert classify_token('be') == 'relational'


def test_classify_there_existential():
    assert classify_token('there') == 'existential'


def test_classify_exist_existential():
    assert classify_token('exist') == 'existential'


def test_classify_think_mental():
    assert classify_token('think') == 'mental'


def test_attributive_copulas_drive_relational():
    text = (
        "The sky is blue. She was tall. They are happy. "
        "He is kind. The water was cold. "
    ) * 20
    doc = parse(text)
    result = analyse(doc)
    assert result['pct_relational'] > 0.0
    assert result['pct_existential'] < 0.05


def test_existential_triggers_drive_existential():
    text = (
        "There exist many problems. There remain several issues. "
    ) * 30
    doc = parse(text)
    result = analyse(doc)
    assert result['pct_existential'] > 0.0


def test_mixed_copula_and_existential():
    text = (
        "The sky is blue. There exist problems. She was brave. "
    ) * 30
    doc = parse(text)
    result = analyse(doc)
    assert result['pct_relational'] > 0.0
    assert result['pct_existential'] > 0.0
