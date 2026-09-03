"""CONTRACT: float quantisation makes the record byte-portable.

The measurement path uses libm-delegated ops (log2/log1p) whose last-ULP
results are not guaranteed identical across C libraries / CPUs. A single-host
golden cannot detect that; these tests simulate cross-host drift by perturbing
a value by one ULP and asserting the canonical record is unchanged.
"""
from __future__ import annotations

import math

from instrument.kernel.quantize import canonical_json, q, quantize
from instrument.reading.joint import joint_reading


def test_q_passes_non_floats_through():
    assert q(3) == 3 and isinstance(q(3), int)
    assert q(True) is True
    assert q(None) is None
    assert q("x") == "x"


def test_q_collapses_one_ulp_neighbours():
    x = 1.626826764023617
    assert q(x) == q(math.nextafter(x, math.inf))
    assert q(x) == q(math.nextafter(x, -math.inf))


def test_q_maps_nonfinite_to_none_and_normalises_negative_zero():
    # Non-finite floats serialise as JSON null (valid JSON; the "not
    # measurable" meaning is carried by the below_envelope flag). This keeps
    # the wire and the hashed canonical form identical and parseable.
    assert q(float("nan")) is None
    assert q(float("inf")) is None
    assert q(float("-inf")) is None
    assert q(-0.0) == 0.0 and math.copysign(1.0, q(-0.0)) == 1.0


def test_quantize_normalises_tuples_to_lists():
    assert quantize((1.0, (2.0, 3.0))) == [1.0, [2.0, 3.0]]


def test_quantize_collapses_observed_cross_host_drift():
    # Actual (this-host, golden-host) pairs observed during the audit: real
    # last-ULP differences from libm-delegated log2/pow. Quantisation must
    # collapse every one.
    pairs = [
        (0.9872545130181418, 0.9872545130181416),
        (1.626826764023617, 1.6268267640236167),
        (8.663130813390275, 8.66313081339027),
        (-0.19361338158617675, -0.19361338158617677),
        (4.107384581939417, 4.10738458193942),
        (0.010522949910394708, 0.01052294991039382),
        (81.1404958677686, 81.14049586776859),
        (115.6095041322314, 115.60950413223141),
    ]
    for a, b in pairs:
        assert q(a) == q(b), f"{a!r} and {b!r} did not collapse"


def test_canonical_json_stable_under_relative_ulp_on_real_fixture():
    # Cross-host drift is a *relative* last-ULP difference on a computed
    # value. Perturb every nonzero feature relatively by ~1 ULP and assert
    # the canonical record is unchanged. (Exact-zero values have no relative
    # ULP and need no perturbation.)
    reading = joint_reading(
        "The committee reviewed the proposal carefully, then deferred its "
        "decision. Several members raised concerns about cost. Others "
        "argued the timeline was already too tight to revisit. " * 8
    )
    base = canonical_json(reading)
    feats = reading["shaper"]["features"]
    rel = 2 ** -52  # ~1 ULP relative
    for k, v in feats.items():
        if not isinstance(v, float) or v == 0.0:
            continue
        perturbed = {**reading, "shaper": {
            **reading["shaper"], "features": {**feats, k: v * (1 + rel)},
        }}
        assert canonical_json(perturbed) == base, f"feature {k} not stable"


def test_canonical_json_changes_on_real_difference():
    reading = joint_reading(
        "The committee reviewed the proposal carefully, then deferred its "
        "decision. Several members raised concerns about cost. Others "
        "argued the timeline was already too tight to revisit. " * 8
    )
    feats = reading["shaper"]["features"]
    # Perturb the first finite, nonzero feature by a clearly above-grid amount.
    k = next(
        key for key, v in feats.items()
        if isinstance(v, float) and v == v and v != 0.0
    )
    other = {**reading, "shaper": {
        **reading["shaper"], "features": {**feats, k: feats[k] * 1.01},
    }}
    assert canonical_json(other) != canonical_json(reading)
