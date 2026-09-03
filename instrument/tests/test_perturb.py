"""CONTRACTS for tools.perturb + the validation study's cell math.

The perturbations feed `tools/validation_study.py`, whose committed
artifacts are byte-compared in CI — so the contracts here are the
determinism guarantees the study rests on: same seed same bytes,
intensity 0.0 is the identity, realized edits are monotone in
intensity at a fixed seed, and every perturbation actually perturbs a
real fixture at intensity 1.0. The study's per-cell statistics
(detection rate + exact CI, realized effect size, batch power) are
exercised on synthetic distance lists — no emissions, so the suite
stays fast.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from instrument.kernel.detrandom import DetRandom
from instrument.kernel.stats import binomial_ci_clopper_pearson
from instrument.lexicons import LEXICONS
from instrument.spc import in_control_params
from tools.perturb import (
    _HEDGE_INSERTIONS,
    PERTURBATIONS,
    donor_fixture_for,
    donor_sentences,
)
from tools.validation_study import (
    batch_power_cell,
    detection_summary,
    realized_effect_size,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

# One real fixture on which every perturbation has at least one site
# (verified by test_changes_a_real_fixture_at_full_intensity).
FIXTURE_TEXT = (
    REPO_ROOT / "fixtures" / "source" / "academic_short.md"
).read_text(encoding="utf-8")

ALL_IDS = sorted(PERTURBATIONS)


# ---- registry ---------------------------------------------------------------


def test_registry_has_the_eight_stable_ids():
    assert ALL_IDS == [
        "contraction_swap",
        "hedge_modal_insert",
        "paragraph_merge",
        "punctuation_shift",
        "register_mix",
        "sentence_duplicate",
        "sentence_reorder",
        "truncate",
    ]
    for perturbation_id, perturbation in PERTURBATIONS.items():
        assert perturbation.id == perturbation_id
        assert perturbation.description


# ---- per-perturbation contracts --------------------------------------------


@pytest.mark.parametrize("perturbation_id", ALL_IDS)
def test_same_seed_same_output(perturbation_id):
    perturbation = PERTURBATIONS[perturbation_id]
    first = perturbation.apply(FIXTURE_TEXT, 0.5, DetRandom("seed:a"))
    second = perturbation.apply(FIXTURE_TEXT, 0.5, DetRandom("seed:a"))
    assert first == second
    different = perturbation.apply(FIXTURE_TEXT, 0.5, DetRandom("seed:b"))
    # Not a hard contract (a tiny site count can coincide), but on this
    # fixture every perturbation has enough sites that distinct seeds
    # select distinct sites.
    assert different != first or perturbation_id == "truncate"


@pytest.mark.parametrize("perturbation_id", ALL_IDS)
def test_intensity_zero_is_identity(perturbation_id):
    out, counts = PERTURBATIONS[perturbation_id].apply(
        FIXTURE_TEXT, 0.0, DetRandom("seed:zero")
    )
    assert out == FIXTURE_TEXT
    assert counts["edited"] == 0
    assert counts["sites"] >= 0


@pytest.mark.parametrize("perturbation_id", ALL_IDS)
def test_realized_edits_monotone_in_intensity(perturbation_id):
    perturbation = PERTURBATIONS[perturbation_id]
    previous = -1
    sites = None
    for eps in (0.0, 0.25, 1.0):
        _, counts = perturbation.apply(
            FIXTURE_TEXT, eps, DetRandom("seed:mono")
        )
        assert counts["edited"] >= previous, (perturbation_id, eps)
        assert counts["edited"] <= counts["sites"]
        assert isinstance(counts["sites"], int)
        assert isinstance(counts["edited"], int)
        if sites is not None:
            assert counts["sites"] == sites  # sites are eps-independent
        sites = counts["sites"]
        previous = counts["edited"]


@pytest.mark.parametrize("perturbation_id", ALL_IDS)
def test_changes_a_real_fixture_at_full_intensity(perturbation_id):
    out, counts = PERTURBATIONS[perturbation_id].apply(
        FIXTURE_TEXT, 1.0, DetRandom("seed:full")
    )
    assert counts["sites"] > 0
    if perturbation_id == "truncate":
        # intensity 1.0 drops the trailing 40% of sentences.
        assert counts["edited"] == counts["sites"] - max(
            1, int(0.6 * counts["sites"])
        )
    else:
        assert counts["edited"] == counts["sites"]
    assert out != FIXTURE_TEXT


@pytest.mark.parametrize("perturbation_id", ALL_IDS)
@pytest.mark.parametrize("bad", (-0.1, 1.5))
def test_rejects_out_of_range_intensity(perturbation_id, bad):
    with pytest.raises(ValueError):
        PERTURBATIONS[perturbation_id].apply(
            FIXTURE_TEXT, bad, DetRandom("seed:bad")
        )


# ---- perturbation-specific behaviour ----------------------------------------


def test_hedge_insertions_come_from_the_stance_lexicons():
    """The insertable openers are built from the instrument's own
    lexicons: head hedge adverbs from stance_hedges, modals in the
    templates from stance_modal."""
    for prefix, _ in _HEDGE_INSERTIONS:
        words = prefix.lower().split()
        assert (
            words[0] in LEXICONS["stance_hedges"]
            or any(w in LEXICONS["stance_modal"] for w in words)
        ), prefix


def test_truncate_keeps_sixty_percent_at_full_intensity():
    _, counts = PERTURBATIONS["truncate"].apply(
        FIXTURE_TEXT, 1.0, DetRandom("seed:trunc")
    )
    kept = counts["sites"] - counts["edited"]
    assert kept == max(1, int(0.6 * counts["sites"]))


def test_register_mix_donor_selection_is_cross_register():
    assert donor_fixture_for("academic_long_001") == "literary"
    assert donor_fixture_for("academic_short_003") == "literary"
    assert donor_fixture_for("discourse_heavy_001") == "literary"
    assert donor_fixture_for("journalism_001") == "academic_long"
    assert donor_fixture_for("literary_005") == "academic_long"


def test_register_mix_uses_the_donor_pool():
    donor = ("This donor sentence is entirely synthetic and unique.",)
    out, counts = PERTURBATIONS["register_mix"].apply(
        FIXTURE_TEXT, 1.0, DetRandom("seed:donor"), donor=donor
    )
    assert counts["edited"] == counts["sites"]
    assert donor[0] in out
    # Every sentence replaced by the single donor sentence.
    assert out.replace(donor[0], "").strip("\n ") == ""


def test_donor_sentences_are_deterministic_and_prose():
    pool = donor_sentences("academic_long")
    assert pool == donor_sentences("academic_long")
    assert len(pool) > 10
    assert all(len(s.split()) >= 4 for s in pool)


# ---- study cell mathematics (no emissions) ----------------------------------


def test_detection_summary_counts_and_exact_ci():
    # 3 of 5 strictly above 95; None is excluded, never scored;
    # exactly 95.0 is NOT detected (strict >).
    result = detection_summary([99.0, 96.7, 95.0, 10.0, None, 100.0])
    assert result["n_scored"] == 5
    assert result["n_unmeasurable"] == 1
    assert result["n_detected"] == 3
    assert result["detection_rate"] == pytest.approx(0.6)
    lo, hi = binomial_ci_clopper_pearson(3, 5)
    assert result["ci95"] == [lo, hi]


def test_detection_summary_empty_stream():
    result = detection_summary([None, None])
    assert result["n_scored"] == 0
    assert result["n_unmeasurable"] == 2
    assert result["detection_rate"] is None
    assert result["ci95"] is None


def test_realized_effect_size_is_median_shift_in_sigma_units():
    # median([2.0, 3.0, 4.0]) = 3.0; (3.0 - 1.5) / 0.5 = 3.0
    assert realized_effect_size([4.0, 2.0, 3.0], 1.5, 0.5) == pytest.approx(3.0)
    assert realized_effect_size([], 1.5, 0.5) is None


def test_batch_power_extremes_on_synthetic_distances():
    null = [1.0, 1.1, 0.9, 1.2, 0.8, 1.05, 0.95, 1.15, 0.85, 1.0]
    params = in_control_params(null, "synthetic")
    # A shift far beyond the null signals every batch...
    huge = batch_power_cell([10.0, 11.0], null, params, 5, "power:huge")
    assert huge["power"] == 1.0
    assert huge["n_signalled"] == huge["n_batches"] == 100
    # ...and resampling the null itself almost never does.
    none = batch_power_cell(list(null), null, params, 5, "power:null")
    assert none["power"] <= 0.1
    # Exact CP interval over 100 batches.
    lo, hi = binomial_ci_clopper_pearson(none["n_signalled"], 100)
    assert none["ci95"] == [lo, hi]
    # Deterministic under the seed.
    again = batch_power_cell(list(null), null, params, 5, "power:null")
    assert again == none


# ---- the committed smoke artifact -------------------------------------------


def test_smoke_study_matches_committed_artifact():
    """Regenerate the smoke profile in memory and byte-compare against
    the committed fixtures/validation/study_smoke.json — the same gate
    as `python -m tools.validation_study --profile smoke --check`."""
    from instrument.routing.reference import list_references, set_reference_dir
    from tools.validation_study import SMOKE_JSON, render_json, run_study

    before = list_references()
    try:
        study = run_study("smoke")
    finally:
        set_reference_dir(None)
    # run_study must restore the loader state it found (here: none).
    assert list_references() == before
    assert study["negative_control"]["consistent_with_nominal"] is True
    committed = SMOKE_JSON.read_text(encoding="utf-8")
    assert render_json(study) == committed
