"""control_chart — offline SPC report over a JSONL stream of emissions.

Runs the three ``instrument.spc`` charts (individuals / CUSUM / EWMA,
~ ISO 7870-2/-4/-6) over the per-document distances in a JSONL capture,
using the reference's persisted calibration self-distance distribution
as the in-control null, and writes a byte-stable JSON report. The
report is descriptive — chart states, never actions: the user owns
the out-of-control action plan.

Usage:
    python -m tools.control_chart --emissions out.jsonl --reference ref.json \
        [--lam 0.2] [--L 3.0] [--k 0.5] [--h 5.0] [--individuals-p 99.5] \
        [--arl] [--as-of YYYY-MM-DD] [--out report.json]

Input stream: one JSON object per line, ``full`` or ``audit`` shape.
The distance to the reference is extracted per line from (in order)
the ``(name, version)`` record in the top-level ``distances`` list
(audit shape), the record in
``register.evidence.distances_to_all_references`` (full shape — the
``register`` block is found at the top level or under ``emission``),
and finally ``register.distance`` when
``register.evidence.reference_name/reference_version`` match. Lines
with no usable distance (unprojectable/null, wrong reference,
malformed JSON) are counted and listed in ``skipped`` — never
silently dropped.

The reference file is read as PLAIN JSON (no ``instrument.routing``
import): it must carry ``self_distance.values`` + ``self_distance.basis``
(persisted by the 0.10 builder). ``calibration_date`` and
``recalibration_policy`` feed the baseline-age check.

``--arl``: empirical average-run-length table. Because the distance
null is non-negative and right-skewed, normal-theory ARL values for
EWMA/CUSUM are an idealisation; this table resamples the reference's
OWN null (DetRandom, seeded from the reference file bytes, so the
table is a pure function of the inputs) with step shifts of
0/0.5/1/1.5/2 sigma0 and reports the mean first-signal index.

Determinism: the wall clock is used ONLY for the ``--as-of`` default,
and ``as_of`` is always echoed into the report — a report is a pure
function of its echoed arguments and input bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from instrument.kernel.detrandom import DetRandom
from instrument.kernel.quantize import q
from instrument.kernel.stats import mean
from instrument.spc import (
    ControlParams,
    _cusum_walk,
    _ewma_walk,
    cusum,
    ewma,
    in_control_params,
    individuals,
    summarize,
)

# ---- ARL simulation size ---------------------------------------------------
#
# M streams per shift, each up to H points. Run lengths are roughly
# geometric, so the relative standard error of an ARL estimate is
# ~ 1/sqrt(M) ~ 7% at M=200 — enough to characterise the chart without
# pretending to more precision than a resampled null supports. H=1000
# caps the in-control (delta=0) row: streams still open at H are
# censored at H (making the delta=0 ARL a lower bound) and the
# censored fraction is reported. At these sizes the whole table is
# ~1e6 draws and computes in a few seconds.
ARL_SHIFTS: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0)
ARL_STREAMS: int = 200   # M
ARL_HORIZON: int = 1000  # H


def _extract_distance(obj, name: str, version: str):
    """Distance of one emission line to the reference ``(name, version)``.

    Returns ``(distance, None)`` on success, ``(None, reason)`` otherwise.
    """
    if not isinstance(obj, dict):
        return None, "not_a_json_object"
    record_lists = []
    top = obj.get("distances")  # audit shape
    if isinstance(top, list):
        record_lists.append(top)
    register = obj.get("register")  # full emission dict
    if not isinstance(register, dict):
        emission = obj.get("emission")  # serve `full` shape wrapper
        if isinstance(emission, dict):
            register = emission.get("register")
    evidence = register.get("evidence") if isinstance(register, dict) else None
    if isinstance(evidence, dict):
        recs = evidence.get("distances_to_all_references")
        if isinstance(recs, list):
            record_lists.append(recs)
    found_null = False
    for recs in record_lists:
        for rec in recs:
            if not isinstance(rec, dict):
                continue
            if rec.get("name") == name and rec.get("version") == version:
                d = rec.get("distance")
                if isinstance(d, (int, float)) and not isinstance(d, bool):
                    return float(d), None
                found_null = True
    # Fallback: the register's own distance, when the emission was
    # registered against exactly this reference.
    if (
        isinstance(evidence, dict)
        and evidence.get("reference_name") == name
        and evidence.get("reference_version") == version
    ):
        d = register.get("distance")
        if isinstance(d, (int, float)) and not isinstance(d, bool):
            return float(d), None
        found_null = True
    if found_null:
        return None, "distance_is_null_for_reference"
    return None, "no_distance_record_for_reference"


def _read_stream(path: Path, name: str, version: str):
    """Parse the JSONL stream; return ``(distances, skipped)``.

    ``skipped`` records are ``{"line_no", "reason"}`` (1-based line
    numbers). Blank lines are ignored (a trailing newline is not a
    skipped document).
    """
    xs: list[float] = []
    skipped: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                skipped.append({"line_no": line_no, "reason": "invalid_json"})
                continue
            d, reason = _extract_distance(obj, name, version)
            if d is None:
                skipped.append({"line_no": line_no, "reason": reason})
            else:
                xs.append(d)
    return xs, skipped


def _age_check(reference: dict, as_of: str) -> dict:
    """Baseline-age block: ``as_of`` minus ``calibration_date`` (date
    part), judged against ``recalibration_policy.max_age_days`` when
    the reference carries that block."""
    out: dict = {
        "as_of": as_of,
        "baseline_age_days": None,
        "age_within_policy": None,
    }
    calibration_date = reference.get("calibration_date")
    if not calibration_date:
        out["age_status"] = "reference_has_no_calibration_date"
        return out
    cal_day = date.fromisoformat(str(calibration_date).split("T")[0])
    age_days = (date.fromisoformat(as_of) - cal_day).days
    out["baseline_age_days"] = age_days
    policy = reference.get("recalibration_policy") or {}
    max_age_days = policy.get("max_age_days")
    if max_age_days is None:
        out["age_status"] = "reference_has_no_recalibration_policy"
        return out
    within = age_days <= max_age_days
    out["age_within_policy"] = within
    out["max_age_days"] = max_age_days
    out["age_status"] = "within_policy" if within else "beyond_policy"
    return out


def _first_signals(stream, params, *, lam, L, k, h):
    """First-signal indices (1-based; None = never) for both memoried
    charts on one stream, via the module's shared recursions —
    exactly the chart math ``ewma``/``cusum`` report."""
    ewma_first = None
    cusum_first = None
    for (i, _x, _z, _u, _l, beyond), (_i, _x2, _cp, _cm, signal) in zip(
        _ewma_walk(stream, params, lam, L), _cusum_walk(stream, params, k, h)
    ):
        if ewma_first is None and beyond:
            ewma_first = i + 1
        if cusum_first is None and signal:
            cusum_first = i + 1
        if ewma_first is not None and cusum_first is not None:
            break
    return ewma_first, cusum_first


def _arl_row(run_lengths: list[int]) -> dict:
    censored = sum(1 for r in run_lengths if r > ARL_HORIZON)
    arl = mean([float(min(r, ARL_HORIZON)) for r in run_lengths])
    return {
        "arl": q(arl),
        "censored_fraction": q(censored / len(run_lengths)),
    }


def _arl_table(
    values: list[float], params: ControlParams, seed: str,
    *, lam: float, L: float, k: float, h: float,
) -> dict:
    """Empirical ARL: resample the reference's own null (bootstrap,
    with replacement) plus a step shift of delta*sigma0, and average
    the first-signal index over ARL_STREAMS runs. Streams still open
    at ARL_HORIZON count as ARL_HORIZON (censored). The draw sequence
    is fixed by the seed and (M, H) alone, so the same reference file
    always simulates the same streams whatever the chart parameters.
    """
    rng = DetRandom(seed=seed)
    n = len(values)
    shifts = []
    for delta in ARL_SHIFTS:
        shift = delta * params.sigma0
        ewma_runs: list[int] = []
        cusum_runs: list[int] = []
        for _ in range(ARL_STREAMS):
            stream = [
                values[rng.randbelow(n)] + shift for _ in range(ARL_HORIZON)
            ]
            e_first, c_first = _first_signals(
                stream, params, lam=lam, L=L, k=k, h=h
            )
            ewma_runs.append(e_first if e_first is not None else ARL_HORIZON + 1)
            cusum_runs.append(c_first if c_first is not None else ARL_HORIZON + 1)
        shifts.append({
            "delta_sigma0": q(delta),
            "ewma": _arl_row(ewma_runs),
            "cusum": _arl_row(cusum_runs),
        })
    return {
        "n_streams": ARL_STREAMS,
        "horizon": ARL_HORIZON,
        "seed": seed,
        "shifts": shifts,
    }


def _build_report(args, as_of: str) -> tuple[dict, int]:
    """Assemble the full report dict; returns ``(report, exit_code)``."""
    reference_path = Path(args.reference)
    reference_bytes = reference_path.read_bytes()
    reference_sha256 = hashlib.sha256(reference_bytes).hexdigest()
    reference = json.loads(reference_bytes.decode("utf-8"))

    self_distance = reference.get("self_distance") or {}
    values = self_distance.get("values")
    basis = self_distance.get("basis")
    if not values or not basis:
        print(
            f"{args.reference}: reference lacks a persisted null "
            "distribution; rebuild with the 0.10 builder "
            "(self_distance.values + self_distance.basis required)",
            file=sys.stderr,
        )
        return {}, 2

    values = [float(v) for v in values]
    sorted_values = sorted(values)
    try:
        params = in_control_params(values, basis)
    except ValueError as exc:
        print(f"{args.reference}: unusable null distribution: {exc}",
              file=sys.stderr)
        return {}, 2

    emissions_path = Path(args.emissions)
    name = reference.get("name")
    version = reference.get("version")
    xs, skipped = _read_stream(emissions_path, name, version)

    individuals_result = individuals(xs, sorted_values, p=args.individuals_p)
    ewma_result = ewma(xs, params, lam=args.lam, L=args.L)
    cusum_result = cusum(xs, params, k=args.k, h=args.h)
    summary = summarize(individuals_result, ewma_result, cusum_result)

    report = {
        "tool": "control_chart",
        "parameters": {
            "lam": q(args.lam), "L": q(args.L),
            "k": q(args.k), "h": q(args.h),
            "individuals_p": q(args.individuals_p),
        },
        "reference": {
            "path": str(args.reference),
            "sha256": reference_sha256,
            "name": name,
            "version": version,
            "basis": basis,
            "n_reference": params.n_reference,
            "mu0": q(params.mu0),
            "sigma0": q(params.sigma0),
        },
        "emissions": {
            "path": str(args.emissions),
            "sha256": hashlib.sha256(emissions_path.read_bytes()).hexdigest(),
        },
        "baseline_age": _age_check(reference, as_of),
        "n_documents": len(xs),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "charts": {
            "individuals": individuals_result,
            "ewma": ewma_result,
            "cusum": cusum_result,
        },
        "summary": summary,
    }
    if args.arl:
        report["arl"] = _arl_table(
            values, params, "control_chart:arl:" + reference_sha256,
            lam=args.lam, L=args.L, k=args.k, h=args.h,
        )
    return report, 0


def _human_summary(report: dict) -> str:
    summary = report["summary"]
    age = report["baseline_age"]
    lines = [
        f"control_chart: {report['n_documents']} document(s), "
        f"{report['n_skipped']} skipped",
        f"reference: {report['reference']['name']} "
        f"{report['reference']['version']} "
        f"(basis={report['reference']['basis']}, "
        f"n={report['reference']['n_reference']})",
        f"baseline age: {age['baseline_age_days']} day(s) as of "
        f"{age['as_of']} — {age['age_status']}",
        f"state: {summary['state']} "
        f"(ewma_signals={summary['ewma_n_signals']}, "
        f"cusum_signals={summary['cusum_n_signals']}, "
        f"individuals_exceedances={summary['individuals_n_exceedances']})",
    ]
    if "arl" in report:
        row0 = report["arl"]["shifts"][0]
        lines.append(
            f"arl (delta=0): ewma={row0['ewma']['arl']} "
            f"cusum={row0['cusum']['arl']} "
            f"(M={report['arl']['n_streams']}, H={report['arl']['horizon']})"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="control_chart",
        description="Offline SPC charts over a JSONL emission stream.",
    )
    ap.add_argument("--emissions", required=True,
                    help="JSONL stream of emissions (full or audit shape)")
    ap.add_argument("--reference", required=True,
                    help="reference JSON with self_distance.values (0.10 builder)")
    ap.add_argument("--lam", type=float, default=0.2, help="EWMA weight")
    ap.add_argument("--L", type=float, default=3.0, help="EWMA limit width")
    ap.add_argument("--k", type=float, default=0.5, help="CUSUM reference value")
    ap.add_argument("--h", type=float, default=5.0, help="CUSUM decision interval")
    ap.add_argument("--individuals-p", type=float, default=99.5,
                    dest="individuals_p",
                    help="individuals exceedance percentile")
    ap.add_argument("--arl", action="store_true",
                    help="append the empirical average-run-length table")
    ap.add_argument("--as-of", dest="as_of", default=None,
                    help="YYYY-MM-DD for the baseline-age check "
                         "(default: today; always echoed into the report)")
    ap.add_argument("--out", default=None, help="report path (default: stdout)")
    args = ap.parse_args(argv)

    # The ONLY wall-clock read in this tool: the --as-of default. It is
    # echoed into the report, so any report is reproducible from its
    # own arguments.
    as_of = args.as_of if args.as_of is not None else date.today().isoformat()
    date.fromisoformat(as_of)  # validate early, fail loudly

    report, code = _build_report(args, as_of)
    if code != 0:
        return code

    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(_human_summary(report))
        print(f"wrote {args.out}")
    else:
        sys.stdout.write(payload)
        print(_human_summary(report), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
