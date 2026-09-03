"""CONTRACTS for assembler: composition + soft-flag relay."""

from __future__ import annotations

import math
from dataclasses import asdict

import pytest

from instrument.emissions.assembler import (
    _dimension_summary,
    _slice_mean,
    assemble,
    register_band_label,
)
from instrument.emissions.catalog import load_catalog
from instrument.emissions.types import DocumentEmission


def test_slice_mean_all_missing_returns_none():
    t = {k: [] for k in (
        "lexical_novelty", "sentence_length_variance",
        "modal_density", "negation_density",
    )}
    mean = _slice_mean(t)
    for v in mean.values():
        assert v is None


def test_slice_mean_ignores_nan_and_none():
    t = {"lexical_novelty": [0.5, None, float("nan"), 0.3]}
    mean = _slice_mean(t)
    assert math.isclose(mean["lexical_novelty"], 0.4)


def test_dimension_summary_single_value_no_slope():
    s = _dimension_summary([0.5])
    assert s.start == 0.5 == s.end
    assert s.slope is None
    assert s.range == 0


def test_dimension_summary_monotone_and_slope():
    s = _dimension_summary([1.0, 2.0, 3.0, 4.0])
    assert s.monotone is True
    assert s.slope is not None
    assert s.slope > 0


def test_register_band_label_match_drift_break():
    cat = load_catalog("v2")
    assert register_band_label(1.0, cat) == "match"
    assert register_band_label(2.5, cat) == "drift"
    assert register_band_label(10.0, cat) == "break"


def test_assemble_composes_four_part_emission():
    cat = load_catalog("v2")
    d = assemble(
        catalog=cat,
        register_label="match",
        register_cohort="llm_technical_prose",
        register_distance=1.2,
        register_evidence={
            "reference_name": "llm_technical_prose",
            "reference_version": "v1",
            "_text": 'Some prose with a "quote pair" and more prose.',
        },
        trajectory={
            "lexical_novelty":          [None, 0.8, 0.6, 0.3, 0.15, 0.45, 0.4, 0.5],
            "sentence_length_variance": [100.0, 120.0, 900.0, 110.0, 105.0, 108.0, 115.0, 112.0],
            "modal_density":            [1.0, 1.2, 1.5, 3.0, 1.4, 1.2, 1.0, 1.0],
            "negation_density":         [0.1, 0.15, 0.2, 0.1, 0.8, 0.15, 0.1, 0.1],
        },
        features={"sfl.process_proxy_entropy": 1.8},
        soft_flags=(),
        convergence={
            "axes": {
                "sfl_process_complexity": {"direction": "agree_mid"},
                "rst_contrast":           {"direction": "agree_high"},
                "rst_elaboration":        {"direction": "diverge"},
                "cohesion_repetition":    {"direction": "agree_mid"},
                "register_modality":      {"direction": "agree_low"},
            },
            "overall": "mixed",
        },
        n_words=320,
        n_sentences=28,
        instrument_version="0.6.0",
        schema_version="0.6.0",
    )
    assert isinstance(d, DocumentEmission)
    # Four buckets + metadata.
    keys = set(asdict(d).keys())
    assert keys == {"register", "arc", "flags", "coherence", "metadata"}
    # Private `_text` evidence scrubbed from the emitted register.
    assert "_text" not in d.register.evidence
    # Arc counts slices from the longest trajectory series.
    assert d.arc.n_slices == 8


@pytest.mark.parametrize("soft_flags,expected_flag", [
    (("malformed_fence_recovered",), "malformed_fence_recovered"),
    (("below_envelope_shaper",), "below_envelope_shaper"),
])
def test_assemble_relays_soft_flags(soft_flags, expected_flag):
    cat = load_catalog("v2")
    d = assemble(
        catalog=cat,
        register_label="unprojectable",
        register_cohort="insufficient_prose",
        register_distance=None,
        register_evidence={"_text": "short"},
        trajectory={k: [] for k in (
            "lexical_novelty", "sentence_length_variance",
            "modal_density", "negation_density",
        )},
        features={},
        soft_flags=soft_flags,
        convergence=None,
        n_words=30,
        n_sentences=0,
        instrument_version="0.6.0",
        schema_version="0.6.0",
    )
    flag_types = {f.type for f in d.flags}
    assert expected_flag in flag_types
