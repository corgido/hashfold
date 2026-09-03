"""spc — statistical process control over the per-document distance stream.

Drift detection over a document stream IS statistical process control:
the reference's persisted calibration self-distance distribution plays
the in-control ("null") distribution, each document's distance to that
reference is one observation of the process, and the classic control
charts — the ISO 7870 family, the regulator-legible framework — say
whether the stream still looks like calibration. Three charts, three
clauses of the same standard:

    individuals   one point vs the empirical null    ~ ISO 7870-2
    CUSUM         cumulative standardised drift      ~ ISO 7870-4
    EWMA          exponentially weighted mean        ~ ISO 7870-6

Everything here is DESCRIPTIVE. The outputs are chart states —
``in_control``, ``isolated_exceedance`` (one weird document),
``sustained_shift_signal`` (the process has shifted) — never an action
and never a shipped decision rule. The instrument's posture is
reference points, not decision rules: the user owns the
out-of-control action plan (recalibrate, investigate the pipeline,
quarantine a batch), because only the user knows what a shift
costs in their process.

Offline by design: the runtime is per-document and stateless (a
document's emission must never depend on which documents preceded it),
so there is deliberately no runtime batch state. SPC runs after the
fact over a JSONL capture the user drives — see
``tools/control_chart.py``.

Imports are stdlib + ``instrument.kernel`` only (layer 3 in
``tools/check_layers.py``; the level bound allows more, the imports
stay kernel-only). Every float in an output dict passes through
``kernel.quantize.q`` so chart results are byte-stable records.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

from instrument.kernel.quantize import q
from instrument.kernel.stats import mean, midrank_percentile, pstdev


@dataclass(frozen=True)
class ControlParams:
    """In-control distribution parameters, estimated from the
    reference's calibration self-distance null. Unquantised: chart
    functions quantise at their output boundary."""
    mu0: float
    sigma0: float
    n_reference: int
    basis: str


def in_control_params(values: list[float], basis: str) -> ControlParams:
    """Estimate the in-control (mu0, sigma0) from the reference null.

    ``values`` is the reference's persisted ``self_distance.values``
    (the calibration corpus's own distances to the reference built
    from it); ``basis`` records how that null was obtained (e.g.
    "cross_validated_10fold" or "resubstitution") and travels with
    the params so every chart output can say what its baseline was.

    mean / population std (ddof=0) via ``kernel.stats`` — the same
    conventions as the reference builder. Raises ``ValueError`` when
    the null is too small to set limits (fewer than 2 values) or
    degenerate (sigma0 == 0: every chart statistic would divide by
    zero, and a null with no spread cannot calibrate a chart).
    """
    if len(values) < 2:
        raise ValueError(
            f"in_control_params requires >= 2 null values, got {len(values)}"
        )
    mu0 = mean(values)
    sigma0 = pstdev(values)
    if sigma0 == 0.0:
        raise ValueError("in_control_params requires sigma0 > 0 (degenerate null)")
    return ControlParams(
        mu0=mu0, sigma0=sigma0, n_reference=len(values), basis=basis
    )


def _ewma_walk(
    xs: Iterable[float], params: ControlParams, lam: float, L: float,
) -> Iterator[tuple[int, float, float, float, float, bool]]:
    """Shared EWMA recursion (single source of truth for the chart
    math): yields unquantised ``(i, x, z, ucl, lcl, beyond_limits)``.
    Consumed by ``ewma`` and by the offline ARL simulation in
    ``tools/control_chart.py``."""
    z = params.mu0  # z_{-1} = mu0
    for i, x in enumerate(xs):
        z = lam * x + (1.0 - lam) * z
        half = L * params.sigma0 * math.sqrt(
            lam / (2.0 - lam) * (1.0 - (1.0 - lam) ** (2 * (i + 1)))
        )
        ucl = params.mu0 + half
        lcl = params.mu0 - half
        yield i, x, z, ucl, lcl, (z > ucl or z < lcl)


def _cusum_walk(
    xs: Iterable[float], params: ControlParams, k: float, h: float,
) -> Iterator[tuple[int, float, float, float, bool]]:
    """Shared CUSUM recursion: yields unquantised
    ``(i, x, c_plus, c_minus, signal)``. See ``_ewma_walk``."""
    c_plus = 0.0
    c_minus = 0.0
    for i, x in enumerate(xs):
        s = (x - params.mu0) / params.sigma0
        c_plus = max(0.0, c_plus + s - k)
        c_minus = max(0.0, c_minus - s - k)
        yield i, x, c_plus, c_minus, (c_plus > h or c_minus > h)


def ewma(
    xs: list[float], params: ControlParams, lam: float = 0.2, L: float = 3.0,
) -> dict:
    """EWMA chart (~ ISO 7870-6) over the distance stream.

    ``z_i = lam * x_i + (1 - lam) * z_{i-1}`` with ``z_{-1} = mu0``;
    time-varying limits ``mu0 +/- L * sigma0 *
    sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * (i + 1))))``.

    The distance stream is non-negative and right-skewed, so these
    normal-theory limits are an approximation: the upper side is the
    meaningful direction, and the raw ``lcl`` is reported even where
    it is negative (below any possible observation) rather than
    clamped — the honest chart characterisation is the empirical ARL
    simulation in ``tools/control_chart.py --arl``, run against the
    reference's actual null.
    """
    points = []
    n_signals = 0
    first_signal_index: Optional[int] = None
    for i, x, z, ucl, lcl, beyond in _ewma_walk(xs, params, lam, L):
        if beyond:
            n_signals += 1
            if first_signal_index is None:
                first_signal_index = i
        points.append({
            "i": i, "x": q(x), "z": q(z),
            "ucl": q(ucl), "lcl": q(lcl), "beyond_limits": beyond,
        })
    return {
        "lam": q(lam), "L": q(L), "points": points,
        "n_signals": n_signals, "first_signal_index": first_signal_index,
    }


def cusum(
    xs: list[float], params: ControlParams, k: float = 0.5, h: float = 5.0,
) -> dict:
    """Tabular CUSUM chart (~ ISO 7870-4) over the distance stream.

    Standardised ``s_i = (x_i - mu0) / sigma0``;
    ``c_plus_i  = max(0, c_plus_{i-1}  + s_i - k)``;
    ``c_minus_i = max(0, c_minus_{i-1} - s_i - k)``;
    signal when either side exceeds ``h``. ``k`` is the reference
    value (half the shift, in sigma0 units, the chart is tuned to
    detect); ``h`` the decision interval.
    """
    points = []
    n_signals = 0
    first_signal_index: Optional[int] = None
    for i, x, c_plus, c_minus, signal in _cusum_walk(xs, params, k, h):
        if signal:
            n_signals += 1
            if first_signal_index is None:
                first_signal_index = i
        points.append({
            "i": i, "x": q(x), "c_plus": q(c_plus), "c_minus": q(c_minus),
            "signal": signal,
        })
    return {
        "k": q(k), "h": q(h), "points": points,
        "n_signals": n_signals, "first_signal_index": first_signal_index,
    }


def individuals(
    xs: list[float], sorted_reference_values: list[float], p: float = 99.5,
) -> dict:
    """Individuals chart (~ ISO 7870-2), empirical form.

    Each point is placed at its mid-rank percentile within the sorted
    reference null (``kernel.stats.midrank_percentile``) rather than
    against normal-theory 3-sigma limits — the null is right-skewed,
    and the reference's own distribution is the honest yardstick. A
    point ``exceeds`` when its percentile is strictly above ``p``.
    One exceedance is one weird document, not evidence of a shift;
    see ``summarize``.
    """
    points = []
    n_exceedances = 0
    for i, x in enumerate(xs):
        pct = midrank_percentile(sorted_reference_values, x)
        exceeds = pct > p
        if exceeds:
            n_exceedances += 1
        points.append({"i": i, "x": q(x), "percentile": q(pct), "exceeds": exceeds})
    return {"p": q(p), "points": points, "n_exceedances": n_exceedances}


def summarize(
    individuals_result: dict, ewma_result: dict, cusum_result: dict,
) -> dict:
    """Fold the three charts into one descriptive chart state.

    ISO 7870 vocabulary mapping: ``individuals`` is the Shewhart-type
    individuals chart (ISO 7870-2), ``cusum`` the cumulative sum chart
    (ISO 7870-4), ``ewma`` the exponentially weighted moving average
    chart (ISO 7870-6).

    The state answers one descriptive question — "does the stream
    still look like calibration?":

        sustained_shift_signal   EWMA or CUSUM signalled: the memoried
                                 charts accumulate evidence across
                                 points, so a signal means the process
                                 has shifted, not that one document is
                                 odd.
        isolated_exceedance      no memoried signal, but at least one
                                 individuals exceedance: one (or a few)
                                 weird documents against a stream that
                                 is otherwise where calibration put it.
        in_control               none of the above.

    Descriptive only: what the user does about either state is the
    user's out-of-control action plan, not this instrument's.
    """
    first_exceedance_index: Optional[int] = None
    for pt in individuals_result["points"]:
        if pt["exceeds"]:
            first_exceedance_index = pt["i"]
            break
    if ewma_result["n_signals"] > 0 or cusum_result["n_signals"] > 0:
        state = "sustained_shift_signal"
    elif individuals_result["n_exceedances"] > 0:
        state = "isolated_exceedance"
    else:
        state = "in_control"
    return {
        "state": state,
        "ewma_n_signals": ewma_result["n_signals"],
        "ewma_first_signal_index": ewma_result["first_signal_index"],
        "cusum_n_signals": cusum_result["n_signals"],
        "cusum_first_signal_index": cusum_result["first_signal_index"],
        "individuals_n_exceedances": individuals_result["n_exceedances"],
        "individuals_first_exceedance_index": first_exceedance_index,
    }
