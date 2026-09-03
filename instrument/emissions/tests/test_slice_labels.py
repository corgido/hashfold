"""CONTRACTS for the 9 slice-label detectors."""

from __future__ import annotations

import pytest

from instrument.emissions.catalog import load_catalog
from instrument.emissions.slice_labels import (
    SLICE_LABEL_DETECTORS,
    SliceLabelContext,
    get_slice_label_detector,
)

EXPECTED_IDS = {
    "opening", "closing", "introduction", "elaboration", "plateau",
    "reopen", "variance_burst", "negation_cluster", "hedging_peak",
}


def test_registry_has_nine_detectors():
    assert set(SLICE_LABEL_DETECTORS.keys()) == EXPECTED_IDS


def test_registry_matches_catalog_ids():
    cat = load_catalog("v2")
    catalog_ids = {d["id"] for d in cat["arc"]["slice_labels"]}
    assert catalog_ids == EXPECTED_IDS


def test_get_unknown_detector_raises():
    with pytest.raises(KeyError):
        get_slice_label_detector("not_a_real_label")


# Shared fixture used by every detector-specific test below.
TRAJ = {
    "lexical_novelty":          [None, 0.8, 0.6, 0.3, 0.15, 0.45, 0.4, 0.5],
    "sentence_length_variance": [100.0, 120.0, 900.0, 110.0, 105.0, 108.0, 115.0, 112.0],
    "modal_density":            [1.0, 1.2, 1.5, 3.0, 1.4, 1.2, 1.0, 1.0],
    "negation_density":         [0.1, 0.15, 0.2, 0.1, 0.8, 0.15, 0.1, 0.1],
}
SLICE_MEAN = {
    "sentence_length_variance": 208.75,
    "negation_density": 0.21,
    "modal_density": 1.42,
    "lexical_novelty": 0.45,
}
N_SLICES = 8


def _ctx(index: int) -> SliceLabelContext:
    return SliceLabelContext(
        traj=TRAJ, index=index, n_slices=N_SLICES, slice_mean=SLICE_MEAN,
    )


def test_opening_fires_at_index_zero_only():
    assert SLICE_LABEL_DETECTORS["opening"](_ctx(0), {}) is True
    assert SLICE_LABEL_DETECTORS["opening"](_ctx(1), {}) is False


def test_closing_fires_at_last_index_only():
    assert SLICE_LABEL_DETECTORS["closing"](_ctx(N_SLICES - 1), {}) is True
    assert SLICE_LABEL_DETECTORS["closing"](_ctx(0), {}) is False


def test_variance_burst_fires_on_spike():
    # Slice 2 has variance 900, doc mean 208.75 → ratio 4.3 > 2.0, abs > 300.
    assert SLICE_LABEL_DETECTORS["variance_burst"](_ctx(2), {}) is True
    assert SLICE_LABEL_DETECTORS["variance_burst"](_ctx(0), {}) is False


def test_negation_cluster_fires_on_slice_with_high_density():
    # Slice 4 has negation 0.8, mean 0.21 → ratio 3.8 > 2.0, abs > 0.1.
    assert SLICE_LABEL_DETECTORS["negation_cluster"](_ctx(4), {}) is True


def test_plateau_fires_when_novelty_below_threshold():
    # Slice 4 has novelty 0.15 < 0.2 default.
    assert SLICE_LABEL_DETECTORS["plateau"](_ctx(4), {}) is True
    # Slice 1 has novelty 0.8 > 0.2.
    assert SLICE_LABEL_DETECTORS["plateau"](_ctx(1), {}) is False
