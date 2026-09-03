"""CONTRACT: the register pick carries a confidence envelope (0.9.1).

The 0.9.0 output reported a single-cohort `match` on prose far from
every reference with no out-of-distribution signal. Every projected
emission now carries `register.evidence.reference_envelope`:

- references built by `tools.build_reference` under 0.9.1 persist the
  calibration corpus's own self-distance distribution
  (`self_distance: {n, median, p95}`); the envelope compares the
  document's distance against it — positional, deterministic, quantized
  arithmetic only ("within_p95" / "beyond_p95" of the calibration
  corpus's own spread — not a quality verdict);
- the bundled migrated seeds carry no such distribution, so the
  envelope says `seed_reference_no_confidence_envelope` explicitly —
  a seed cannot vouch for any distance.

Also: the router's auto-select path is the normal path — its flag is
the neutral `auto_routed`, not the alarming-sounding
`undeclared_hint` (0.9.0 noise finding).
"""

from __future__ import annotations

from dataclasses import asdict, replace

from instrument.emit import _reference_envelope, emit
from instrument.routing.reference import load_reference
from instrument.routing.router import route
from instrument.routing.types import (
    SelfDistanceStats,
    reference_from_dict,
    reference_to_dict,
)

_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)


def _calibrated_ref():
    ref = load_reference("llm_technical_prose", "v2")
    return replace(
        ref, self_distance=SelfDistanceStats(n=30, median=1.5, p95=3.0),
    )


def test_envelope_positions_flip_at_p95():
    ref = _calibrated_ref()
    within = _reference_envelope(ref, 2.9)
    beyond = _reference_envelope(ref, 3.1)
    # 0.10.0: a summary-only self_distance block (no persisted null
    # distribution) is a 0.9.1-era reference; the envelope keeps the
    # positional fields and says explicitly why no percentile appears.
    assert within == {
        "self_distance_n": 30, "self_distance_median": 1.5,
        "self_distance_p95": 3.0, "position": "within_p95",
        "percentile_status": "reference_predates_null_distribution",
    }
    assert beyond["position"] == "beyond_p95"


def test_seed_reference_says_so():
    seed = load_reference("llm_technical_prose", "v2")
    assert seed.self_distance is None
    env = _reference_envelope(seed, 2.0)
    assert env == {"status": "seed_reference_no_confidence_envelope"}


def test_none_distance_yields_no_position():
    env = _reference_envelope(_calibrated_ref(), None)
    assert env["position"] is None


def test_self_distance_round_trips_through_dict():
    ref = _calibrated_ref()
    again = reference_from_dict(reference_to_dict(ref))
    assert again.self_distance == SelfDistanceStats(n=30, median=1.5, p95=3.0)
    # A 0.9.1-era block serialises WITHOUT the 0.10 keys (old shape
    # preserved byte-for-byte, values/basis appear only when present).
    d = reference_to_dict(ref)
    assert d["self_distance"] == {"n": 30, "median": 1.5, "p95": 3.0}
    # And a dict WITHOUT the block still loads (backward-compatible).
    d.pop("self_distance")
    assert reference_from_dict(d).self_distance is None


def test_full_null_distribution_round_trips_through_dict():
    """0.10.0 shape: values + basis survive to_dict/from_dict symmetric."""
    ref = load_reference("llm_technical_prose", "v2")
    full = replace(
        ref,
        self_distance=SelfDistanceStats(
            n=4, median=1.5, p95=2.9,
            values=(1.0, 1.4, 1.6, 3.0), basis="cross_validated_10fold",
        ),
    )
    d = reference_to_dict(full)
    assert d["self_distance"]["values"] == [1.0, 1.4, 1.6, 3.0]
    assert d["self_distance"]["basis"] == "cross_validated_10fold"
    again = reference_from_dict(d)
    assert again.self_distance == full.self_distance
    assert isinstance(again.self_distance.values, tuple)


def test_partial_new_shape_loads():
    """values without basis (and vice versa) round-trips as-is."""
    ref = load_reference("llm_technical_prose", "v2")
    partial = replace(
        ref,
        self_distance=SelfDistanceStats(
            n=2, median=1.0, p95=1.9, values=(0.5, 1.9), basis=None,
        ),
    )
    again = reference_from_dict(reference_to_dict(partial))
    assert again.self_distance.values == (0.5, 1.9)
    assert again.self_distance.basis is None


def test_emission_carries_the_envelope():
    d = asdict(emit(_PARA * 8))
    env = d["register"]["evidence"]["reference_envelope"]
    assert env == {"status": "seed_reference_no_confidence_envelope"}


def test_auto_select_flag_is_neutral():
    features = dict(load_reference("llm_technical_prose", "v2").pc_zscore_mean)
    ref, match = route(features, register_hint=None, reading_n_words=2000)
    assert "auto_routed" in match.flags
    assert "undeclared_hint" not in match.flags
