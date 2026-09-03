"""CONTRACT: the SPC module (instrument/spc.py) and its offline CLI
(tools/control_chart.py).

- EWMA/CUSUM recursions are exact against hand-computed vectors.
- An injected step shift produces `sustained_shift_signal` from BOTH
  memoried charts; the same in-control stream stays `in_control`.
  DetRandom seeds make these exact assertions, not flaky ones.
- The CLI extracts distances from full/audit shaped JSONL lines,
  counts (never drops) unusable lines, judges baseline age against a
  fixed --as-of, and writes byte-identical reports on repeat runs.
"""

from __future__ import annotations

import json

import pytest

from instrument.kernel.detrandom import DetRandom
from instrument.kernel.quantize import q
from instrument.spc import (
    ControlParams,
    cusum,
    ewma,
    in_control_params,
    individuals,
    summarize,
)
from tools.control_chart import main as control_chart_main

_PARAMS = ControlParams(mu0=2.0, sigma0=0.5, n_reference=100, basis="test")


# ---- in_control_params -----------------------------------------------------

def test_in_control_params_mean_pstdev():
    p = in_control_params([1.0, 2.0, 3.0], "cross_validated_10fold")
    assert p.mu0 == 2.0
    # population std of [1, 2, 3] = sqrt(2/3)
    assert q(p.sigma0) == q((2.0 / 3.0) ** 0.5)
    assert p.n_reference == 3
    assert p.basis == "cross_validated_10fold"


def test_in_control_params_too_few_values_raises():
    with pytest.raises(ValueError):
        in_control_params([1.0], "resubstitution")


def test_in_control_params_degenerate_null_raises():
    with pytest.raises(ValueError):
        in_control_params([2.0, 2.0, 2.0], "resubstitution")


# ---- EWMA: hand-computed known answers --------------------------------------

def test_ewma_hand_computed_vector():
    # mu0=2, sigma0=0.5, lam=0.2, L=3; z_{-1} = 2.0
    #   z0 = .2*2.0 + .8*2.0   = 2.0
    #   z1 = .2*2.5 + .8*2.0   = 2.1
    #   z2 = .2*1.5 + .8*2.1   = 0.3 + 1.68  = 1.98
    #   z3 = .2*3.5 + .8*1.98  = 0.7 + 1.584 = 2.284
    #   z4 = .2*2.0 + .8*2.284 = 0.4 + 1.8272 = 2.2272
    # half-width_i = 3*0.5*sqrt(0.2/1.8*(1-0.8^(2i+2))) = 0.5*sqrt(1-0.8^(2i+2))
    #   i=0: 0.5*sqrt(1-0.64) = 0.5*0.6 = 0.3 -> ucl 2.3, lcl 1.7
    out = ewma([2.0, 2.5, 1.5, 3.5, 2.0], _PARAMS, lam=0.2, L=3.0)
    zs = [pt["z"] for pt in out["points"]]
    assert zs == [q(2.0), q(2.1), q(1.98), q(2.284), q(2.2272)]
    assert out["points"][0]["ucl"] == q(2.3)
    assert out["points"][0]["lcl"] == q(1.7)
    # remaining limits pin the formula itself (12 sig figs via q)
    for i, pt in enumerate(out["points"]):
        half = 0.5 * (1.0 - 0.8 ** (2 * (i + 1))) ** 0.5
        assert pt["ucl"] == q(2.0 + half)
        assert pt["lcl"] == q(2.0 - half)
        assert pt["beyond_limits"] is False
    assert out["n_signals"] == 0
    assert out["first_signal_index"] is None
    assert out["lam"] == q(0.2)
    assert out["L"] == q(3.0)


def test_ewma_signals_and_reports_raw_lcl():
    # Constant 4.0 stream: z = 2.4, 2.72, 2.976, ... all above the
    # growing ucl (2.3, 2.384..., asymptote 2.5) -> beyond from i=0.
    out = ewma([4.0] * 5, _PARAMS)
    assert [pt["beyond_limits"] for pt in out["points"]] == [True] * 5
    assert out["n_signals"] == 5
    assert out["first_signal_index"] == 0
    # lcl is the raw normal-theory value, not clamped at zero.
    assert out["points"][0]["lcl"] == q(1.7)


# ---- CUSUM: hand-computed known answers -------------------------------------

def test_cusum_hand_computed_vector():
    # mu0=2, sigma0=0.5, k=0.5, h=5; s = (x-2)/0.5 = [0, 1, -1, 3, 0]
    #   c+ : max(0, 0+0-.5)=0; max(0, 0+1-.5)=.5; max(0, .5-1-.5)=0;
    #        max(0, 0+3-.5)=2.5; max(0, 2.5+0-.5)=2.0
    #   c- : max(0, 0-0-.5)=0; max(0, 0-1-.5)=0; max(0, 0+1-.5)=.5;
    #        max(0, .5-3-.5)=0; max(0, 0-0-.5)=0
    out = cusum([2.0, 2.5, 1.5, 3.5, 2.0], _PARAMS, k=0.5, h=5.0)
    assert [pt["c_plus"] for pt in out["points"]] == [
        q(0.0), q(0.5), q(0.0), q(2.5), q(2.0)]
    assert [pt["c_minus"] for pt in out["points"]] == [
        q(0.0), q(0.0), q(0.5), q(0.0), q(0.0)]
    assert all(pt["signal"] is False for pt in out["points"])
    assert out["n_signals"] == 0
    assert out["first_signal_index"] is None
    assert out["k"] == q(0.5)
    assert out["h"] == q(5.0)


def test_cusum_signal_ramp():
    # Constant 3.0 stream: s = 2 each; c+ climbs 1.5, 3.0, 4.5, 6.0, ...
    # first > h=5 at i=3, and every point after.
    out = cusum([3.0] * 8, _PARAMS)
    assert [pt["c_plus"] for pt in out["points"]] == [
        q(1.5), q(3.0), q(4.5), q(6.0), q(7.5), q(9.0), q(10.5), q(12.0)]
    assert out["first_signal_index"] == 3
    assert out["n_signals"] == 5


# ---- injected step shift (deterministic resample) ----------------------------

# Synthetic right-skewed null on [1, 5] — monotone in i, so already sorted.
_NULL = [1.0 + 4.0 * (i / 199.0) ** 2 for i in range(200)]
_NULL_PARAMS = in_control_params(_NULL, "synthetic")
_SHIFT_SEED = "test:spc:step-shift:1"


def _streams() -> tuple[list[float], list[float]]:
    """30 in-control points, then the same 30 + 20 shifted +2*sigma0."""
    rng = DetRandom(seed=_SHIFT_SEED)
    base = [_NULL[rng.randbelow(200)] for _ in range(30)]
    shifted = base + [
        _NULL[rng.randbelow(200)] + 2.0 * _NULL_PARAMS.sigma0 for _ in range(20)
    ]
    return base, shifted


def test_step_shift_signals_sustained():
    _, shifted = _streams()
    e = ewma(shifted, _NULL_PARAMS)
    c = cusum(shifted, _NULL_PARAMS)
    ind = individuals(shifted, _NULL)
    assert e["n_signals"] > 0
    assert c["n_signals"] > 0
    # Both memoried charts catch the shift shortly after it starts (i=30).
    assert e["first_signal_index"] >= 30
    assert c["first_signal_index"] >= 30
    summary = summarize(ind, e, c)
    assert summary["state"] == "sustained_shift_signal"
    assert summary["ewma_first_signal_index"] == e["first_signal_index"]
    assert summary["cusum_first_signal_index"] == c["first_signal_index"]


def test_in_control_stream_stays_in_control():
    base, _ = _streams()
    e = ewma(base, _NULL_PARAMS)
    c = cusum(base, _NULL_PARAMS)
    ind = individuals(base, _NULL)
    assert e["n_signals"] == 0
    assert c["n_signals"] == 0
    assert ind["n_exceedances"] == 0
    assert summarize(ind, e, c)["state"] == "in_control"


# ---- individuals -------------------------------------------------------------

def test_individuals_percentiles_and_exceedance():
    ref = [float(i) for i in range(1, 11)]  # 1..10 sorted
    out = individuals([5.0, 10.0, 11.0], ref, p=99.5)
    # x=5:  (4 below + 0.5*1 equal)/10 -> 45.0
    # x=10: (9 below + 0.5*1 equal)/10 -> 95.0
    # x=11: beyond the null max -> 100.0 > 99.5 -> exceeds
    assert [pt["percentile"] for pt in out["points"]] == [
        q(45.0), q(95.0), q(100.0)]
    assert [pt["exceeds"] for pt in out["points"]] == [False, False, True]
    assert out["n_exceedances"] == 1
    assert out["p"] == q(99.5)


# ---- summarize ----------------------------------------------------------------

def _ind_result(points):
    return {
        "p": q(99.5), "points": points,
        "n_exceedances": sum(1 for pt in points if pt["exceeds"]),
    }


def _chart_result(n_signals, first):
    return {"n_signals": n_signals, "first_signal_index": first}


def test_summarize_three_states():
    quiet = [{"i": 0, "exceeds": False}, {"i": 1, "exceeds": False}]
    loud = [{"i": 0, "exceeds": False}, {"i": 1, "exceeds": True}]

    s = summarize(_ind_result(quiet), _chart_result(0, None), _chart_result(0, None))
    assert s["state"] == "in_control"
    assert s["individuals_first_exceedance_index"] is None

    s = summarize(_ind_result(loud), _chart_result(0, None), _chart_result(0, None))
    assert s["state"] == "isolated_exceedance"
    assert s["individuals_first_exceedance_index"] == 1

    # A memoried-chart signal outranks an exceedance (or its absence).
    s = summarize(_ind_result(quiet), _chart_result(2, 7), _chart_result(0, None))
    assert s["state"] == "sustained_shift_signal"
    assert s["ewma_first_signal_index"] == 7
    s = summarize(_ind_result(loud), _chart_result(0, None), _chart_result(1, 4))
    assert s["state"] == "sustained_shift_signal"
    assert s["cusum_first_signal_index"] == 4


# ---- CLI: tools/control_chart -------------------------------------------------

_REF_NAME, _REF_VERSION = "customer_cohort", "v1"


def _write_reference(tmp_path, *, policy=True, with_null=True):
    values = [1.0 + 3.0 * (i / 119.0) ** 2 for i in range(120)]
    self_distance = {"n": len(values), "median": values[60], "p95": values[113]}
    if with_null:
        self_distance["values"] = values
        self_distance["basis"] = "cross_validated_10fold"
    ref = {
        "name": _REF_NAME,
        "version": _REF_VERSION,
        "calibration_date": "2026-01-15T00:00:00Z",
        "self_distance": self_distance,
    }
    if policy:
        ref["recalibration_policy"] = {"max_age_days": 365}
    path = tmp_path / "ref.json"
    path.write_text(json.dumps(ref), encoding="utf-8")
    return path


def _dist_records(d):
    return [
        {"name": _REF_NAME, "version": _REF_VERSION, "distance": d},
        {"name": "other_cohort", "version": "v9", "distance": 99.0},
    ]


def _write_emissions(tmp_path):
    """One line per supported shape, plus two unusable lines."""
    lines = [
        # full emission dict (top-level register), record in evidence
        {"register": {"distance": 2.0, "evidence": {
            "reference_name": _REF_NAME, "reference_version": _REF_VERSION,
            "distances_to_all_references": _dist_records(2.0)}}},
        # serve `full` shape ({"emission": ..., "reading": ...})
        {"emission": {"register": {"distance": 2.5, "evidence": {
            "reference_name": _REF_NAME, "reference_version": _REF_VERSION,
            "distances_to_all_references": _dist_records(2.5)}}},
         "reading": {}},
        # audit shape (top-level distances list)
        {"reading": {}, "distances": _dist_records(2.2), "metadata": {}},
        # register.distance fallback (no distances_to_all_references)
        {"register": {"distance": 1.8, "evidence": {
            "reference_name": _REF_NAME, "reference_version": _REF_VERSION}}},
        # unusable: unprojectable (distance null for our reference)
        {"reading": {}, "distances": _dist_records(None), "metadata": {}},
        # unusable: no record for our reference at all
        {"reading": {}, "distances": [
            {"name": "other_cohort", "version": "v9", "distance": 1.0}]},
    ]
    path = tmp_path / "emissions.jsonl"
    path.write_text(
        "".join(json.dumps(obj) + "\n" for obj in lines), encoding="utf-8")
    return path


def _run_cli(tmp_path, *extra, out_name="report.json"):
    ref = _write_reference(tmp_path)
    em = _write_emissions(tmp_path)
    out = tmp_path / out_name
    rc = control_chart_main([
        "--emissions", str(em), "--reference", str(ref),
        "--as-of", "2026-06-01", "--out", str(out), *extra,
    ])
    assert rc == 0
    return out


def test_cli_extraction_and_skipped(tmp_path):
    out = _run_cli(tmp_path)
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["n_documents"] == 4
    xs = [pt["x"] for pt in report["charts"]["individuals"]["points"]]
    assert xs == [q(2.0), q(2.5), q(2.2), q(1.8)]
    assert report["skipped"] == [
        {"line_no": 5, "reason": "distance_is_null_for_reference"},
        {"line_no": 6, "reason": "no_distance_record_for_reference"},
    ]
    assert report["n_skipped"] == 2
    assert report["reference"]["name"] == _REF_NAME
    assert report["reference"]["basis"] == "cross_validated_10fold"
    assert report["summary"]["state"] in (
        "in_control", "isolated_exceedance", "sustained_shift_signal")


def test_cli_age_within_and_beyond_policy(tmp_path):
    ref = _write_reference(tmp_path)
    em = _write_emissions(tmp_path)

    def _age_block(as_of):
        out = tmp_path / "r.json"
        assert control_chart_main([
            "--emissions", str(em), "--reference", str(ref),
            "--as-of", as_of, "--out", str(out)]) == 0
        return json.loads(out.read_text(encoding="utf-8"))["baseline_age"]

    within = _age_block("2026-06-01")  # 137 days after 2026-01-15
    assert within == {
        "as_of": "2026-06-01", "baseline_age_days": 137,
        "age_within_policy": True, "max_age_days": 365,
        "age_status": "within_policy"}
    beyond = _age_block("2027-06-01")  # 502 days
    assert beyond["baseline_age_days"] == 502
    assert beyond["age_within_policy"] is False
    assert beyond["age_status"] == "beyond_policy"


def test_cli_no_policy_reports_null(tmp_path):
    ref = _write_reference(tmp_path, policy=False)
    em = _write_emissions(tmp_path)
    out = tmp_path / "r.json"
    assert control_chart_main([
        "--emissions", str(em), "--reference", str(ref),
        "--as-of", "2026-06-01", "--out", str(out)]) == 0
    age = json.loads(out.read_text(encoding="utf-8"))["baseline_age"]
    assert age["age_within_policy"] is None
    assert age["age_status"] == "reference_has_no_recalibration_policy"
    assert age["baseline_age_days"] == 137


def test_cli_rejects_reference_without_null(tmp_path, capsys):
    ref = _write_reference(tmp_path, with_null=False)
    em = _write_emissions(tmp_path)
    rc = control_chart_main([
        "--emissions", str(em), "--reference", str(ref),
        "--as-of", "2026-06-01"])
    assert rc == 2
    assert "rebuild with the 0.10 builder" in capsys.readouterr().err


def test_cli_determinism_byte_identical(tmp_path):
    a = _run_cli(tmp_path, out_name="a.json")
    b = _run_cli(tmp_path, out_name="b.json")
    assert a.read_bytes() == b.read_bytes()


def test_cli_arl_smoke(tmp_path):
    out = _run_cli(tmp_path, "--arl")
    report = json.loads(out.read_text(encoding="utf-8"))
    arl = report["arl"]
    assert arl["n_streams"] == 200 and arl["horizon"] == 1000
    deltas = [row["delta_sigma0"] for row in arl["shifts"]]
    assert deltas == [q(0.0), q(0.5), q(1.0), q(1.5), q(2.0)]
    row0, row2 = arl["shifts"][0], arl["shifts"][-1]
    # In-control run lengths dwarf the 2-sigma-shift run lengths.
    assert row0["ewma"]["arl"] > 10.0 * row2["ewma"]["arl"]
    assert row0["cusum"]["arl"] > 10.0 * row2["cusum"]["arl"]
    for side in ("ewma", "cusum"):
        assert 0.0 <= row0[side]["censored_fraction"] <= 1.0
        assert row2[side]["censored_fraction"] == 0.0
    # The seed is derived from the reference bytes and echoed.
    assert arl["seed"].startswith("control_chart:arl:")
