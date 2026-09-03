"""CONTRACTS for routing.calibration — envelope + provenance evidence.

The 0.10.0 envelope ladder: what an emission may claim about a
distance depends strictly on what the reference persists —

    seed (no self_distance)       -> seed_reference_no_confidence_envelope
    0.9.1 (summary stats only)    -> within/beyond p95
                                     + percentile_status saying why no more
    0.10.0 (full CV null)         -> percentile + empirical_exceedance

and the provenance ladder mirrors it (pre_0_10_reference / partial
echo / full echo with stability summary), as does per-feature
calibration (reference_lacks_feature_quantiles for seeds and 0.9.1
references / no_finite_features_for_calibration with m=0 for a
document contributing no finite family member / full per-feature
percentile + p + BH q block). Percentile, p-value and BH arithmetic
are spot-checked against hand-computed values. The emit-level tests
exercise the whole path against the committed
`fixtures/references/fixture_prose_v1.json` with the odd (held-out)
fixture split — documents the reference build never saw.
"""

from __future__ import annotations

from dataclasses import asdict, replace

import pytest

from instrument.routing.calibration import (
    distance_percentile,
    envelope_block,
    feature_calibration,
    provenance_block,
)
from instrument.routing.reference import load_reference, set_reference_dir
from instrument.routing.router import distances_as_records
from instrument.routing.types import SelfDistanceStats

_VALUES = (1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Every test starts and ends with no user directory."""
    set_reference_dir(None)
    yield
    set_reference_dir(None)


def _seed_ref():
    return load_reference("llm_technical_prose", "v2")


def _era_091_ref():
    return replace(
        _seed_ref(), self_distance=SelfDistanceStats(n=30, median=1.5, p95=3.0),
    )


def _full_ref():
    return replace(
        _seed_ref(),
        self_distance=SelfDistanceStats(
            n=10, median=1.9, p95=2.71,
            values=_VALUES, basis="cross_validated_10fold",
        ),
    )


# ---------- envelope ladder -------------------------------------------------

def test_envelope_seed_degrades_explicitly():
    assert envelope_block(_seed_ref(), 2.0) == {
        "status": "seed_reference_no_confidence_envelope"
    }


def test_envelope_091_reference_says_why_no_percentile():
    env = envelope_block(_era_091_ref(), 2.9)
    assert env == {
        "self_distance_n": 30, "self_distance_median": 1.5,
        "self_distance_p95": 3.0, "position": "within_p95",
        "percentile_status": "reference_predates_null_distribution",
    }
    assert envelope_block(_era_091_ref(), 3.1)["position"] == "beyond_p95"


def test_envelope_full_reference_reports_percentile():
    env = envelope_block(_full_ref(), 1.5)
    assert env["position"] == "within_p95"
    assert env["percentile"] == 30.0        # 3 of 10 values below 1.5
    assert env["empirical_exceedance"] == 0.7
    assert env["basis"] == "cross_validated_10fold"
    assert env["percentile_method"] == "midrank"
    assert "percentile_status" not in env


def test_envelope_none_distance_has_no_position_or_percentile():
    env = envelope_block(_full_ref(), None)
    assert env["position"] is None
    assert "percentile" not in env
    assert "empirical_exceedance" not in env


# ---------- percentile / exceedance spot-checks ------------------------------

def test_midrank_ties_split_their_mass():
    sd = _full_ref().self_distance
    # 2.0 ties one value: 5 below + half the tie = 55.0.
    assert distance_percentile(sd, 2.0) == 55.0
    env = envelope_block(_full_ref(), 2.0)
    assert env["percentile"] == 55.0
    assert env["empirical_exceedance"] == 0.45


def test_percentile_clamps_at_the_extremes():
    sd = _full_ref().self_distance
    assert distance_percentile(sd, 0.5) == 0.0
    assert distance_percentile(sd, 5.0) == 100.0
    assert envelope_block(_full_ref(), 5.0)["empirical_exceedance"] == 0.0
    assert envelope_block(_full_ref(), 0.5)["empirical_exceedance"] == 1.0


def test_distance_percentile_degrades_to_none():
    assert distance_percentile(None, 1.0) is None
    assert distance_percentile(_era_091_ref().self_distance, 1.0) is None
    assert distance_percentile(_full_ref().self_distance, None) is None


# ---------- provenance ladder -------------------------------------------------

def test_provenance_pre_010_reference():
    assert provenance_block(_seed_ref()) == {
        "provenance_status": "pre_0_10_reference"
    }


def test_provenance_partial_echoes_what_exists():
    ref = replace(_seed_ref(), collection_window="2026-05-01..2026-06-30")
    block = provenance_block(ref)
    assert block["collection_window"] == "2026-05-01..2026-06-30"
    assert block["calibration_date"] == ref.calibration_date
    assert block["n"] == ref.n
    assert "recalibration_policy" not in block
    assert "stability_summary" not in block
    assert "provenance_status" not in block


def test_provenance_full_summarises_stability():
    policy = {"max_age_days": 180, "triggers": ["model_update"],
              "note": "", "policy_version": "1"}
    stability = {
        "method": "delete_block_jackknife",
        "d_fraction": 0.1,
        "n_replicates": 10,
        "centroid_shift_std_units": {
            "pc_1": {"mean": 0.05, "max": 0.11},
            "pc_2": {"mean": 0.20, "max": 0.42},
        },
        "loading_alignment_abs_cos": {
            "pc_1": {"min": 0.98, "mean": 0.99},
            "pc_2": {"min": 0.61, "mean": 0.85},
        },
        "self_p95_replicate_range": [1.9, 2.4],
    }
    ref = replace(
        _seed_ref(),
        collection_window="repo fixtures (static)",
        recalibration_policy=policy,
        stability=stability,
    )
    block = provenance_block(ref)
    assert block["recalibration_policy"] == policy
    # Worst case across PCs: largest shift, smallest alignment.
    assert block["stability_summary"] == {
        "max_centroid_shift_std": 0.42,
        "min_loading_alignment": 0.61,
    }


# ---------- feature calibration (BH FDR) --------------------------------------

_FEATURE_GRID = (0.0, 1.0, 2.0, 3.0, 4.0)  # fractions 0, .25, .5, .75, 1


def _grid_ref():
    """A reference with synthetic 5-point grids; n=9 -> p floor 0.1."""
    return replace(
        _seed_ref(), n=9,
        per_feature_quantiles={
            "alpha": _FEATURE_GRID, "bravo": _FEATURE_GRID,
            "charlie": _FEATURE_GRID, "delta": _FEATURE_GRID,
        },
    )


def test_feature_calibration_known_answers():
    # Grid (0,1,2,3,4) sits at fractions (0, .25, .5, .75, 1); n=9
    # floors p at 1/(9+1) = 0.1. Per feature:
    #   alpha   10.0  beyond top end   F=1.0    p=max(0.0, 0.1)=0.1 (floor)
    #   bravo    0.4  between points   F=0.4*0.25=0.1          p=0.2
    #   charlie  1.5  between points   F=(1+0.5)/4=0.375       p=0.75
    #   delta    2.0  exact grid point F=0.5                   p=1.0
    # BH over sorted names (alpha, bravo, charlie, delta), m=4,
    # q_(i) = min_{j>=i} m*p_(j)/j by the reverse suffix-min pass:
    #   rank 4: 4*1.00/4 = 1.0
    #   rank 3: 4*0.75/3 = 1.0 -> suffix min 1.0
    #   rank 2: 4*0.20/2 = 0.4
    #   rank 1: 4*0.10/1 = 0.4 -> suffix min 0.4
    fc = feature_calibration(
        {"alpha": 10.0, "bravo": 0.4, "charlie": 1.5, "delta": 2.0},
        _grid_ref(),
    )
    assert list(fc["per_feature"]) == ["alpha", "bravo", "charlie", "delta"]
    assert fc["per_feature"]["alpha"] == {
        "value": 10.0, "percentile": 100.0, "p_two_sided": 0.1, "q_value": 0.4,
    }
    assert fc["per_feature"]["bravo"] == {
        "value": 0.4, "percentile": 10.0, "p_two_sided": 0.2, "q_value": 0.4,
    }
    assert fc["per_feature"]["charlie"] == {
        "value": 1.5, "percentile": 37.5, "p_two_sided": 0.75, "q_value": 1.0,
    }
    assert fc["per_feature"]["delta"] == {
        "value": 2.0, "percentile": 50.0, "p_two_sided": 1.0, "q_value": 1.0,
    }
    assert fc["family_policy"] == {
        "method": "benjamini_hochberg",
        "family": ("reference features with finite reading value "
                   "and stored quantile grid"),
        "m": 4,
        "sidedness": "two_sided",
        "p_resolution_floor": 0.1,
    }
    assert fc["reference_n"] == 9


def test_feature_calibration_p_floors_at_both_ends():
    # F=0 (below every calibration point) and F=1 (above) must BOTH
    # floor at 1/(n+1): 2*min(F, 1-F) is 0.0 at either end, and an
    # n-point calibration set cannot resolve a p below its floor.
    fc = feature_calibration({"alpha": -5.0, "bravo": 99.0}, _grid_ref())
    assert fc["per_feature"]["alpha"]["percentile"] == 0.0
    assert fc["per_feature"]["bravo"]["percentile"] == 100.0
    assert fc["per_feature"]["alpha"]["p_two_sided"] == 0.1
    assert fc["per_feature"]["bravo"]["p_two_sided"] == 0.1
    # BH on tied ps [0.1, 0.1], m=2: rank 2 gives 2*0.1/2 = 0.1;
    # rank 1 gives 2*0.1/1 = 0.2, suffix-min -> 0.1 for both.
    assert fc["per_feature"]["alpha"]["q_value"] == 0.1
    assert fc["per_feature"]["bravo"]["q_value"] == 0.1


def test_feature_calibration_nan_drops_family_by_one():
    # delta=2.0 -> p=1.0 in both runs; bravo going NaN shrinks m from
    # 2 to 1 and the family_policy records it, so the multiplicity
    # correction stays auditable against the family actually tested.
    full = feature_calibration({"bravo": 0.4, "delta": 2.0}, _grid_ref())
    dropped = feature_calibration(
        {"bravo": float("nan"), "delta": 2.0}, _grid_ref(),
    )
    assert full["family_policy"]["m"] == 2
    assert dropped["family_policy"]["m"] == 1
    assert list(dropped["per_feature"]) == ["delta"]


def test_feature_calibration_family_membership():
    # In the family: stored grid AND finite value. Out: NaN, inf,
    # doc features with no grid, and reference grids the doc lacks
    # (charlie has a grid but no reading here).
    fc = feature_calibration(
        {
            "alpha": 2.0,
            "bravo": float("inf"),
            "delta": float("nan"),
            "not_in_reference": 1.0,
        },
        _grid_ref(),
    )
    assert fc["family_policy"]["m"] == 1
    assert list(fc["per_feature"]) == ["alpha"]
    # m=1: q = 1*p/1 = p.
    assert fc["per_feature"]["alpha"]["q_value"] == (
        fc["per_feature"]["alpha"]["p_two_sided"]
    )


def test_feature_calibration_seed_reference_degrades_explicitly():
    assert feature_calibration({"alpha": 1.0}, _seed_ref()) == {
        "status": "reference_lacks_feature_quantiles"
    }


def test_feature_calibration_all_nan_doc_has_empty_family():
    fc = feature_calibration(
        {"alpha": float("nan"), "bravo": float("-inf")}, _grid_ref(),
    )
    assert fc["status"] == "no_finite_features_for_calibration"
    assert fc["family_policy"]["m"] == 0
    assert fc["family_policy"]["method"] == "benjamini_hochberg"
    assert "per_feature" not in fc
    assert feature_calibration({}, _grid_ref())["status"] == (
        "no_finite_features_for_calibration"
    )


# ---------- distances_as_records percentile ------------------------------------

def test_distance_records_carry_percentile_when_null_persisted():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[3]
    set_reference_dir(repo_root / "fixtures" / "references")
    fixture_sd = load_reference("fixture_prose", "v1").self_distance
    assert fixture_sd.values is not None  # the committed reference has a null
    records = distances_as_records({
        ("fixture_prose", "v1"): 1.5,
        ("llm_technical_prose", "v2"): 1.5,   # seed: no null persisted
        ("academic_prose", "v2"): None,       # unmeasurable distance
    })
    by_name = {r["name"]: r for r in records}
    assert by_name["fixture_prose"]["percentile"] is not None
    assert by_name["llm_technical_prose"]["percentile"] is None
    assert by_name["academic_prose"]["percentile"] is None
    # Sort order unchanged: (name, version) ascending.
    assert [r["name"] for r in records] == sorted(r["name"] for r in records)


# ---------- emit-level: the committed fixture reference -------------------------

def _held_out_text() -> str:
    """An odd-parity (held-out) fixture segment the build never saw."""
    from tools.fixture_corpus import iter_segments
    odd = {sid: t for sid, t in iter_segments()
           if int(sid.rsplit("_", 1)[1]) % 2 == 1}
    return odd["academic_long_001"]


def test_emit_against_fixture_reference_carries_full_evidence():
    from pathlib import Path
    from instrument.emit import emit
    repo_root = Path(__file__).resolve().parents[3]
    set_reference_dir(repo_root / "fixtures" / "references")
    em = asdict(emit(_held_out_text(), register_hint="fixture_prose"))
    ev = em["register"]["evidence"]
    env = ev["reference_envelope"]
    assert env["basis"] == "cross_validated_10fold"
    assert env["percentile_method"] == "midrank"
    assert 0.0 <= env["percentile"] <= 100.0
    assert 0.0 <= env["empirical_exceedance"] <= 1.0
    prov = ev["reference_provenance"]
    assert prov["collection_window"] == "repo fixtures (static)"
    assert prov["recalibration_policy"]["policy_version"] == "1"
    assert set(prov["stability_summary"]) == {
        "max_centroid_shift_std", "min_loading_alignment",
    }
    rec = {r["name"]: r for r in ev["distances_to_all_references"]}
    assert rec["fixture_prose"]["percentile"] is not None


def test_emit_against_seed_keeps_degraded_statuses():
    from pathlib import Path
    from instrument.emit import emit
    repo_root = Path(__file__).resolve().parents[3]
    set_reference_dir(repo_root / "fixtures" / "references")
    em = asdict(emit(_held_out_text(), register_hint="llm_technical_prose"))
    ev = em["register"]["evidence"]
    assert ev["reference_envelope"] == {
        "status": "seed_reference_no_confidence_envelope"
    }
    assert ev["reference_provenance"] == {
        "provenance_status": "pre_0_10_reference"
    }
    # Seeds carry no per_feature_quantiles either; the calibration
    # block says so rather than implying calibrated p-values.
    assert ev["feature_calibration"] == {
        "status": "reference_lacks_feature_quantiles"
    }


def test_emit_fixture_reference_carries_feature_calibration():
    from pathlib import Path
    from instrument.emit import emit
    repo_root = Path(__file__).resolve().parents[3]
    set_reference_dir(repo_root / "fixtures" / "references")
    em = asdict(emit(_held_out_text(), register_hint="fixture_prose"))
    fc = em["register"]["evidence"]["feature_calibration"]
    policy = fc["family_policy"]
    assert policy["method"] == "benjamini_hochberg"
    assert policy["sidedness"] == "two_sided"
    assert policy["family"] == (
        "reference features with finite reading value and stored quantile grid"
    )
    # The doc's 57 routing features cap the family; NaN features and
    # features the reference stores no grid for drop out.
    assert 0 < policy["m"] <= 57
    assert fc["reference_n"] == 15
    assert policy["p_resolution_floor"] == 0.0625  # 1 / (15 + 1)
    names = list(fc["per_feature"])
    assert names == sorted(names)
    assert len(names) == policy["m"]
    for row in fc["per_feature"].values():
        assert 0.0 <= row["percentile"] <= 100.0
        # p is floored at the calibration resolution; BH can only
        # raise a p, never lower it, so q >= p always.
        assert policy["p_resolution_floor"] <= row["p_two_sided"] <= 1.0
        assert row["p_two_sided"] <= row["q_value"] <= 1.0


def test_emit_feature_calibration_is_deterministic():
    from pathlib import Path
    from instrument.emit import emit
    repo_root = Path(__file__).resolve().parents[3]
    set_reference_dir(repo_root / "fixtures" / "references")
    text = _held_out_text()
    first = asdict(emit(text, register_hint="fixture_prose"))
    second = asdict(emit(text, register_hint="fixture_prose"))
    fc1 = first["register"]["evidence"]["feature_calibration"]
    fc2 = second["register"]["evidence"]["feature_calibration"]
    assert fc1 == fc2
    assert list(fc1["per_feature"]) == list(fc2["per_feature"])
