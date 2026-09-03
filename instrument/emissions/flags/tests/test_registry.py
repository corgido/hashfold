"""CONTRACTS for the flag registry."""

from __future__ import annotations

import pytest

from instrument.emissions.catalog import load_catalog
from instrument.emissions.flags import FLAG_DETECTORS, get_flag_detector


EXPECTED_IDS = {
    "novelty_reopen", "novelty_collapse", "variance_spike",
    "modal_pivot", "negation_cluster", "register_shift",
    "malformed_fence_recovered", "unbalanced_quotation",
    "below_envelope_shaper", "trajectory_unmeasurable",
    "cross_view_diverge", "feature_unmeasurable_cluster",
}


def test_registry_has_twelve_detectors():
    assert set(FLAG_DETECTORS.keys()) == EXPECTED_IDS


def test_registry_matches_catalog_flag_ids():
    cat = load_catalog("v2")
    catalog_ids = {f["id"] for f in cat["flags"]}
    assert catalog_ids == EXPECTED_IDS


def test_every_detector_has_catalog_entry():
    cat = load_catalog("v2")
    catalog_ids = {f["id"] for f in cat["flags"]}
    for detector_id in FLAG_DETECTORS:
        assert detector_id in catalog_ids, detector_id


def test_get_flag_detector_raises_on_unknown():
    with pytest.raises(KeyError):
        get_flag_detector("not_a_real_flag")
