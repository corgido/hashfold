"""CONTRACTS for the router."""

from __future__ import annotations

from pathlib import Path

import pytest

from instrument.reading.joint import joint_reading
from instrument.routing.router import (
    DEFAULT_DISTANCE_THRESHOLD,
    NoComparableReferenceError,
    route,
)
from instrument.routing.types import classify_length_cohort


REPO_ROOT = Path(__file__).resolve().parents[3]


def _features_from_joint(text: str) -> dict:
    jr = joint_reading(text)
    out: dict = {}
    out.update(jr["shaper"]["features"])
    out.update(jr["other_shaper"]["features"])
    out.update(jr.get("stylometry", {}).get("features", {}))
    return out


def test_classify_length_cohort_bands():
    assert classify_length_cohort(500) == "short"
    assert classify_length_cohort(5000) == "medium"
    assert classify_length_cohort(20000) == "long"


def test_default_distance_threshold():
    assert DEFAULT_DISTANCE_THRESHOLD == 3.0


def test_route_auto_selects_for_projectable_doc():
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text()
    features = _features_from_joint(text)
    n_words = len(text.split())
    ref, rm = route(features, reading_n_words=n_words)
    assert ref.register_cohort
    assert rm.distance is not None
    assert rm.match in ("match", "distance_exceeds_threshold")


def test_route_hint_unknown_cohort_raises():
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text()
    features = _features_from_joint(text)
    with pytest.raises(NoComparableReferenceError):
        route(features, register_hint="cohort_that_does_not_exist")


@pytest.mark.parametrize("rel_path", [
    "fixtures/source/academic_short.md",
    "fixtures/source/dialogue.md",
    "fixtures/source/journalism.md",
    "fixtures/source/literary.md",
    "fixtures/source/llm_technical.md",
])
def test_route_returns_valid_match(rel_path):
    text = (REPO_ROOT / rel_path).read_text()
    features = _features_from_joint(text)
    n_words = len(text.split())
    try:
        ref, rm = route(features, reading_n_words=n_words)
    except NoComparableReferenceError:
        return
    assert ref.name
    assert ref.version
    assert rm.detected_cohort in (
        "llm_technical_prose", "academic", "dialogue",
        "journalism", "literary",
    )
    assert rm.reference_cohort == ref.register_cohort
    assert rm.match in ("match", "distance_exceeds_threshold", "unmeasurable")
