"""CONTRACTS for emission types — frozen dataclasses, JSON-serialisable."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from instrument.emissions.types import (
    ArcEmission,
    CoherenceEmission,
    DimensionSummary,
    DocumentEmission,
    EmissionMetadata,
    Flag,
    RegisterEmission,
    SliceEmission,
)


def test_flag_is_frozen():
    f = Flag(type="variance_spike", severity="notable", evidence={"ratio": 2.1})
    with pytest.raises(FrozenInstanceError):
        f.type = "other"  # type: ignore[misc]


def test_register_emission_round_trips():
    r = RegisterEmission(
        label="match", cohort="llm_technical_prose",
        distance=1.7, evidence={"reference_name": "llm_technical_prose"},
    )
    assert asdict(r)["label"] == "match"
    assert asdict(r)["evidence"]["reference_name"] == "llm_technical_prose"


def test_slice_emission_tuple_labels():
    s = SliceEmission(
        index=0,
        values={"lexical_novelty": None},
        deltas={"lexical_novelty": None},
        labels=("opening",),
    )
    assert isinstance(s.labels, tuple)
    assert s.deltas == {"lexical_novelty": None}


def test_full_emission_composes():
    metadata = EmissionMetadata(
        emission_version="v2", instrument_version="0.6.0",
        schema_version="0.6.0", n_words=180, n_sentences=12,
        timestamp="2026-04-20T12:00:00Z",
        lexicon_version="v1",
        catalog_sha256="0" * 64,
        distance_method="feature_zscore_l2",
        input_sha256="0" * 64,
        content_sha256="0" * 64,
        reading_sha256="0" * 64,
        core_code_sha256="0" * 64,
        reproducibility_hash="0" * 64,
    )
    d = DocumentEmission(
        register=RegisterEmission(
            label="match", cohort="llm_technical_prose", distance=1.0,
        ),
        arc=ArcEmission(
            per_slice=(),
            per_dimension={
                k: DimensionSummary(None, None, None, None, None)
                for k in (
                    "lexical_novelty", "sentence_length_variance",
                    "modal_density", "negation_density",
                )
            },
            n_slices=0,
        ),
        flags=(),
        coherence=CoherenceEmission(
            value=1.0, label="high",
            n_axes_measurable=5, n_axes_agree=5,
            diverging_axes=(), incomparable_axes=(),
        ),
        metadata=metadata,
    )
    as_dict = asdict(d)
    assert set(as_dict.keys()) == {
        "register", "arc", "flags", "coherence", "metadata",
    }
