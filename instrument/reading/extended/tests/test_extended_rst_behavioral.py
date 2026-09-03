"""Behavioral tests for RST discourse-marker classification.

Verifies that _SINGLE_WORD_MARKERS maps ambiguous markers to the correct
relation category.  The original bug: dict construction used last-write-wins,
so "but" ended up as "condition" instead of "contrast", etc.
"""

from __future__ import annotations

from instrument.reading.document import parse
from instrument.reading.extended.rst import (
    _MARKER_PRIORITY,
    _SINGLE_WORD_MARKERS,
    analyse,
)


# ---- 1. Direct lookup for highest-frequency markers ----

def test_but_maps_to_contrast():
    assert _SINGLE_WORD_MARKERS["but"] == "contrast"


def test_however_maps_to_contrast():
    assert _SINGLE_WORD_MARKERS["however"] == "contrast"


def test_while_maps_to_contrast():
    assert _SINGLE_WORD_MARKERS["while"] == "contrast"


def test_since_maps_to_cause():
    assert _SINGLE_WORD_MARKERS["since"] == "cause"


def test_so_maps_to_result():
    assert _SINGLE_WORD_MARKERS["so"] == "result"


def test_for_maps_to_cause():
    assert _SINGLE_WORD_MARKERS["for"] == "cause"


def test_yet_maps_to_contrast():
    assert _SINGLE_WORD_MARKERS["yet"] == "contrast"


def test_though_maps_to_concession():
    assert _SINGLE_WORD_MARKERS["though"] == "concession"


def test_therefore_maps_to_result():
    assert _SINGLE_WORD_MARKERS["therefore"] == "result"


def test_thus_maps_to_result():
    assert _SINGLE_WORD_MARKERS["thus"] == "result"


# ---- 2. Full priority map smoke test ----

def test_all_priority_entries_honoured():
    for marker, expected_relation in _MARKER_PRIORITY.items():
        actual = _SINGLE_WORD_MARKERS[marker]
        assert actual == expected_relation, (
            f"_SINGLE_WORD_MARKERS[{marker!r}] == {actual!r}, "
            f"expected {expected_relation!r}"
        )


# ---- 3. Behavioral: "but" triggers contrast, not condition ----

def test_but_produces_contrast_density():
    sentences = []
    for _ in range(8):
        sentences.append("The evidence was strong.")
        sentences.append("But the conclusion was wrong.")
    text = " ".join(sentences)
    doc = parse(text)
    features = analyse(doc)
    assert features["contrast_density"] > 0, (
        "Expected contrast_density > 0 when 'But' is the primary marker"
    )
    # "but" must not inflate condition_density
    assert features["condition_density"] < features["contrast_density"], (
        "condition_density should not reflect 'but' markers"
    )


# ---- 4. Behavioral: "however" triggers contrast ----

def test_however_produces_contrast_density():
    sentences = []
    for _ in range(8):
        sentences.append("The results were promising.")
        sentences.append("However the method was flawed.")
    text = " ".join(sentences)
    doc = parse(text)
    features = analyse(doc)
    assert features["contrast_density"] > 0, (
        "Expected contrast_density > 0 when 'However' is the primary marker"
    )


# ---- 5. Behavioral: "since" triggers cause, not sequence ----

def test_since_produces_cause_density():
    sentences = []
    for _ in range(8):
        sentences.append("The experiment failed.")
        sentences.append("Since the sample was contaminated we stopped.")
    text = " ".join(sentences)
    doc = parse(text)
    features = analyse(doc)
    assert features["cause_density"] > 0, (
        "Expected cause_density > 0 when 'Since' is the primary marker"
    )
    assert features["sequence_density"] < features["cause_density"], (
        "sequence_density should not reflect 'since' markers"
    )
