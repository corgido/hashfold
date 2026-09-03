"""CONTRACTS for the catalog loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instrument.emissions.catalog import (
    CatalogError,
    classify_by_max,
    classify_by_min,
    load_catalog,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_load_catalog_v2_returns_dict():
    cat = load_catalog("v2")
    assert isinstance(cat, dict)
    assert cat["version"] == "v2"


def test_load_catalog_has_expected_top_keys():
    cat = load_catalog("v2")
    expected = {
        "_comment", "version", "status",
        "instrument_version", "schema_version", "calibration_state",
        "register", "arc", "flags", "coherence",
        "deviation_overlay", "pair_overlay",
    }
    assert set(cat.keys()) == expected


def test_load_catalog_flags_has_twelve():
    cat = load_catalog("v2")
    assert len(cat["flags"]) == 12


def test_load_catalog_arc_slice_labels_has_nine():
    cat = load_catalog("v2")
    assert len(cat["arc"]["slice_labels"]) == 9


def test_unknown_version_raises():
    with pytest.raises(CatalogError):
        load_catalog("v99")


def test_classify_by_max_bands():
    bands = [
        {"label": "match", "max": 2.3},
        {"label": "drift", "max": 2.8},
        {"label": "break", "max": None},
    ]
    assert classify_by_max(1.5, bands) == "match"
    assert classify_by_max(2.5, bands) == "drift"
    assert classify_by_max(5.0, bands) == "break"


def test_classify_by_min_bands():
    bands = [
        {"label": "high", "min": 0.8},
        {"label": "moderate", "min": 0.5},
        {"label": "low", "min": None},
    ]
    assert classify_by_min(0.9, bands) == "high"
    assert classify_by_min(0.6, bands) == "moderate"
    assert classify_by_min(0.1, bands) == "low"


def test_catalog_matches_source_json():
    """The compiled catalog must match the source JSON semantics."""
    src = json.loads(
        (REPO_ROOT / "_data" / "emissions_catalog" / "v2.json")
        .read_text(encoding="utf-8")
    )
    cat = load_catalog("v2")
    # Same thresholds.
    assert cat["register"]["bands"] == src["register"]["bands"]
    assert cat["coherence"]["bands"] == src["coherence"]["bands"]
    # Same detector lists by id.
    assert (
        [f["id"] for f in cat["flags"]]
        == [f["id"] for f in src["flags"]]
    )


def test_classify_by_max_boundary_is_inclusive():
    """Pin the <= semantics: a value exactly at a band's max belongs to
    that band. (Mutation `<=` -> `<` previously survived the suite —
    no fixture lands exactly on an edge.)"""
    from instrument.emissions.catalog import classify_by_max
    bands = [{"label": "tight", "max": 1.5},
             {"label": "loose", "max": None}]
    assert classify_by_max(1.5, bands) == "tight"
    assert classify_by_max(1.5000001, bands) == "loose"


def test_classify_by_min_boundary_is_inclusive():
    from instrument.emissions.catalog import classify_by_min
    bands = [{"label": "high", "min": 0.8},
             {"label": "rest", "min": None}]
    assert classify_by_min(0.8, bands) == "high"
    assert classify_by_min(0.7999999, bands) == "rest"


def test_coherence_label_requires_measurability_floor():
    """Validity gate: < MIN_MEASURABLE_AXES measurable axes -> the
    scalar is still emitted but the advisory label is 'unmeasurable'
    (one vacuously-agreeing axis must not band as 'high')."""
    from instrument.emissions.coherence import MIN_MEASURABLE_AXES, compute_coherence
    bands = [{"label": "high", "min": 0.8},
             {"label": "moderate", "min": 0.4},
             {"label": "low", "min": None}]
    conv = {"overall": "mixed", "axes": {
        "a": {"direction": "agree_low"},
        "b": {"direction": "incomparable"},
        "c": {"direction": "incomparable"},
        "d": {"direction": "incomparable"},
        "e": {"direction": "incomparable"},
    }}
    em = compute_coherence(conv, bands)
    assert em.value == 1.0
    assert em.n_axes_measurable == 1 < MIN_MEASURABLE_AXES
    assert em.label == "unmeasurable"

    conv_ok = {"overall": "agree", "axes": {
        "a": {"direction": "agree_low"},
        "b": {"direction": "agree_mid"},
        "c": {"direction": "agree_low"},
        "d": {"direction": "incomparable"},
        "e": {"direction": "incomparable"},
    }}
    em2 = compute_coherence(conv_ok, bands)
    assert em2.n_axes_measurable == 3
    assert em2.label == "high"
