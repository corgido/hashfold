"""CONTRACTS for the reference loader."""

from __future__ import annotations

import pytest

from instrument.routing.reference import (
    ReferenceNotFoundError,
    list_cohorts,
    list_references,
    load_reference,
    references_for_cohort,
)


def test_list_references_returns_five_bundled():
    refs = list_references()
    assert len(refs) >= 5
    assert ("llm_technical_prose", "v2") in refs
    assert ("academic_prose", "v2") in refs
    assert ("dialogue_prose", "v2") in refs
    assert ("journalism_prose", "v2") in refs
    assert ("literary_prose", "v2") in refs


def test_load_reference_returns_typed_dataclass():
    ref = load_reference("llm_technical_prose", "v2")
    assert ref.name == "llm_technical_prose"
    assert ref.register_cohort
    assert ref.pc_loadings
    assert ref.pc_centroid
    assert ref.scope_statement.strip() != ""


def test_load_reference_unknown_raises():
    with pytest.raises(ReferenceNotFoundError):
        load_reference("does_not_exist", "v99")


def test_list_cohorts_covers_five_registers():
    cohorts = set(list_cohorts())
    assert len(cohorts) >= 5


def test_references_for_cohort_returns_matching():
    matches = references_for_cohort("llm_technical_prose")
    assert matches
    assert all(r.register_cohort == "llm_technical_prose" for r in matches)


@pytest.mark.parametrize("name", [
    "llm_technical_prose", "academic_prose", "dialogue_prose",
    "journalism_prose", "literary_prose",
])
def test_reference_has_required_fields(name):
    ref = load_reference(name, "v2")
    # Structural invariants that survived the M5 cut.
    assert ref.name == name
    assert ref.version == "v2"
    assert ref.per_feature
    assert ref.pc_loadings
    assert ref.pc_centroid
    assert ref.pc_zscore_mean
    assert ref.pc_zscore_std
