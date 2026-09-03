"""validation_study — detection rate vs realized effect size, demonstrated.

Injects the known mechanical perturbations of `tools/perturb.py` into
the HELD-OUT half of the fixture corpus (the odd-parity segments of
`tools/fixture_corpus.py`; the even half calibrated
`fixtures/references/fixture_prose_v1.json`) and publishes, per
(perturbation x intensity) cell: the detection rate at a documented
operating point with its exact Clopper-Pearson 95% CI, the realized
effect size in reference-sigma units, realized-edit counts, a negative
control at the nominal false-positive rate, and batch-power statements
from `instrument.spc.ewma` over DetRandom-resampled batches.

HONESTY IS THE PRODUCT. This is a small-N demonstration of the METHOD:
the held-out segments are cut from the same 8 prose fixtures that
calibrated the reference (segments of 8 documents are not independent
samples), the calibration null has n=15, and mechanical edits are not
a model of real LLM drift. The scaling deliverable is the USER
PROTOCOL: run this tool's `--corpus-dir` mode against your own regime-B
corpus and your own regime-A reference, where n and independence are
yours. The generated docs/VALIDATION.md says all of this first.

Detection policy: detected := reference_envelope percentile > 95 — the
illustrative 5% operating point. Raw percentile/distance streams are
always included in the artifacts so any other operating point can be
recomputed without rerunning.

Modes:
    python -m tools.validation_study --profile smoke --write
    python -m tools.validation_study --profile smoke --check
    python -m tools.validation_study --profile full  --write
    python -m tools.validation_study --profile full  --check
    python -m tools.validation_study --corpus-dir DIR --reference REF.json \
        [--hint COHORT] [--out REPORT.json]

`--write` regenerates the committed artifacts
(fixtures/validation/study_smoke.json for smoke;
fixtures/validation/study_full.json + docs/VALIDATION.md for full);
`--check` regenerates to memory and byte-compares (mirrors
tools/length_invariance). `--check` also exits 1 — loudly — when the
negative control's CI excludes the nominal rate: that means the
calibration/held-out pairing itself is broken, not that the committed
bytes drifted. The user mode runs ONLY the unperturbed analysis
(percentile stream, detection rate vs nominal, EWMA/CUSUM/individuals
summary) and never touches the pinned fixtures.

Determinism: all randomness is `instrument.kernel.detrandom.DetRandom`
under the documented seed scheme; every float in a written artifact
passes through `instrument.kernel.quantize`; elapsed time is printed
to stdout only and never written. Stdlib + instrument only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from instrument.emit import emit
from instrument.kernel.detrandom import DetRandom
from instrument.kernel.quantize import q, quantize
from instrument.kernel.stats import (
    binomial_ci_clopper_pearson,
    percentile_linear,
    pstdev,
)
from instrument.routing.reference import set_reference_dir
from instrument.spc import cusum, ewma, in_control_params, individuals, summarize
from tools.fixture_corpus import write_split
from tools.perturb import PERTURBATIONS, donor_fixture_for, donor_sentences

REPO_ROOT = Path(__file__).resolve().parents[1]
REFERENCES_DIR = REPO_ROOT / "fixtures" / "references"
REFERENCE_NAME = "fixture_prose"
REFERENCE_VERSION = "v1"
SMOKE_JSON = REPO_ROOT / "fixtures" / "validation" / "study_smoke.json"
FULL_JSON = REPO_ROOT / "fixtures" / "validation" / "study_full.json"
MD_PATH = REPO_ROOT / "docs" / "VALIDATION.md"

# Intensity grid for the full profile.
EPSILONS: tuple[float, ...] = (0.1, 0.25, 0.5, 1.0)

# Detection operating point: detected := percentile > DETECT_PERCENTILE.
# Illustrative 5% point; raw streams always accompany the verdicts.
DETECT_PERCENTILE = 95.0

# Batch power: N_BATCHES resampled batches per (perturbation, eps, N),
# each appended to an in-control prefix resampled from the reference
# null; the EWMA chart (instrument.spc defaults) must signal within
# the batch region.
BATCH_SIZES: tuple[int, ...] = (5, 10, 20)
N_BATCHES = 100
IN_CONTROL_PREFIX = 30
EWMA_LAM = 0.2  # instrument.spc.ewma defaults, passed explicitly so
EWMA_L = 3.0    # the artifact echo cannot drift from what ran

# eps=0.0 identity check runs through this perturbation (present in
# both profiles).
IDENTITY_CHECK_PERTURBATION = "hedge_modal_insert"

PROFILES: dict[str, dict] = {
    # CI gate: two perturbations x two intensities, batch power at one
    # N. Committed as fixtures/validation/study_smoke.json.
    "smoke": {
        "perturbations": ("hedge_modal_insert", "register_mix"),
        "epsilons": (0.25, 1.0),
        "max_docs": 20,
        "batch_sizes": (10,),
    },
    # Everything: all 8 perturbations x 4 intensities x all held-out
    # docs, batch power at N in {5, 10, 20}. Regenerates
    # docs/VALIDATION.md.
    "full": {
        "perturbations": tuple(sorted(PERTURBATIONS)),
        "epsilons": EPSILONS,
        "max_docs": None,
        "batch_sizes": BATCH_SIZES,
    },
}

HONESTY_STATEMENT = (
    "Small-N demonstration of the METHOD, not a production drift claim: "
    "the held-out documents are ~200-word segments of the same 8 prose "
    "fixtures whose even-parity segments calibrated the reference "
    "(segments of 8 documents are not independent samples), the "
    "calibration null has n=15, and the perturbations are mechanical "
    "surface edits, not a model of real LLM drift. The deliverable that "
    "scales is the user-run protocol: the same tool in --corpus-dir "
    "mode against the user's own reference and corpus."
)


# ---- seed scheme ------------------------------------------------------------


def _perturb_seed(perturbation_id: str, eps: float, input_sha256: str) -> str:
    """One DetRandom stream per (document, perturbation, intensity)."""
    return f"validation:{perturbation_id}:{eps}:{input_sha256}"


def _power_seed(perturbation_id: str, eps: float, batch_size: int) -> str:
    """One DetRandom stream per batch-power cell (prefix + batches)."""
    return f"validation:power:{perturbation_id}:{eps}:{batch_size}"


# ---- reference loading ------------------------------------------------------


def _load_reference_meta(path: Path) -> dict:
    """Reference file as plain JSON (no routing import): identity,
    cohort, and the persisted cross-validated null. Raises with a
    clear message when the reference predates the 0.10 null."""
    if not path.exists():
        raise FileNotFoundError(f"reference not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    sd = data.get("self_distance") or {}
    values = sd.get("values")
    if not values or len(values) < 2:
        raise ValueError(
            f"reference {path} carries no self_distance.values null "
            "distribution — rebuild it with tools.build_reference (0.10)"
        )
    return {
        "path": path,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "name": data["name"],
        "version": data["version"],
        "cohort": data["register_cohort"],
        "n": data["n"],
        "basis": sd.get("basis", "unknown"),
        "values": [float(v) for v in values],
    }


@contextmanager
def _reference_dir(path: "Path | None"):
    """Register a reference directory for the duration, restoring the
    previous registration afterwards so a pytest-driven run cannot
    leak the fixture reference into later tests. Reads the loader's
    private `_EXTRA_DIR` because no getter exists; restore-only use."""
    from instrument.routing import reference as _reference_module
    previous = _reference_module._EXTRA_DIR
    set_reference_dir(path)
    try:
        yield
    finally:
        set_reference_dir(previous)


# ---- measurement ------------------------------------------------------------


def _measure(text: str, hint: str, expected: tuple[str, str]) -> dict:
    """Emit `text` under `hint` and read off the envelope evidence.

    Returns unquantised-enough plain values (the emission already
    quantised them): distance, envelope percentile, and the two
    drop/report conditions. Verifies that hint routing actually chose
    the expected reference — a mismatch means the registered reference
    directory does not contain what the caller thinks it does.
    """
    emission = emit(text, register_hint=hint)
    evidence = emission.register.evidence
    distance = emission.register.distance
    if distance is not None:
        chosen = (evidence.get("reference_name"),
                  evidence.get("reference_version"))
        if chosen != expected:
            raise RuntimeError(
                f"hint {hint!r} routed to {chosen}, expected {expected}; "
                "pass --hint or clean the reference directory"
            )
    envelope = evidence.get("reference_envelope") or {}
    return {
        "distance": distance,
        "percentile": envelope.get("percentile"),
        "below_envelope": any(
            flag.type == "below_envelope_shaper" for flag in emission.flags
        ),
        "unprojectable": distance is None,
    }


# ---- cell mathematics (pure; unit-tested without emissions) -----------------


def detection_summary(
    percentiles: list, threshold: float = DETECT_PERCENTILE,
) -> dict:
    """Detection rate + exact Clopper-Pearson 95% CI over a percentile
    stream. `None` entries (unmeasurable emissions) are excluded from
    the denominator and counted separately — no silent drops."""
    scored = [p for p in percentiles if p is not None]
    n = len(scored)
    k = sum(1 for p in scored if p > threshold)
    out: dict = {
        "threshold_percentile": threshold,
        "n_scored": n,
        "n_unmeasurable": len(percentiles) - n,
        "n_detected": k,
    }
    if n:
        lo, hi = binomial_ci_clopper_pearson(k, n)
        out["detection_rate"] = k / n
        out["ci95"] = [lo, hi]
    else:
        out["detection_rate"] = None
        out["ci95"] = None
    return out


def realized_effect_size(
    distances: list[float], unperturbed_median: float, sigma0: float,
) -> Optional[float]:
    """(median perturbed distance - median unperturbed distance) /
    sigma0, where sigma0 is the pstdev of the reference's null."""
    if not distances:
        return None
    return (
        percentile_linear(sorted(distances), 50.0) - unperturbed_median
    ) / sigma0


def batch_power_cell(
    perturbed_distances: list[float],
    null_values: list[float],
    params,
    batch_size: int,
    seed: str,
    *,
    n_batches: int = N_BATCHES,
    prefix_len: int = IN_CONTROL_PREFIX,
) -> dict:
    """Empirical EWMA power for one (perturbation, eps, N) cell.

    Each of `n_batches` trials resamples (with replacement, one
    DetRandom stream per cell) `prefix_len` in-control points from the
    reference null followed by `batch_size` points from the cell's
    perturbed distances; the trial signals when the EWMA chart
    (instrument.spc, explicit default parameters) goes beyond limits
    anywhere in the batch region. Power = signalling fraction, with
    its exact Clopper-Pearson 95% CI.
    """
    rng = DetRandom(seed)
    n_null = len(null_values)
    n_perturbed = len(perturbed_distances)
    n_signalled = 0
    for _ in range(n_batches):
        stream = [
            null_values[rng.randbelow(n_null)] for _ in range(prefix_len)
        ] + [
            perturbed_distances[rng.randbelow(n_perturbed)]
            for _ in range(batch_size)
        ]
        chart = ewma(stream, params, lam=EWMA_LAM, L=EWMA_L)
        if any(pt["beyond_limits"] for pt in chart["points"][prefix_len:]):
            n_signalled += 1
    lo, hi = binomial_ci_clopper_pearson(n_signalled, n_batches)
    return {
        "batch_size": batch_size,
        "n_batches": n_batches,
        "n_signalled": n_signalled,
        "power": n_signalled / n_batches,
        "ci95": [lo, hi],
    }


# ---- the study --------------------------------------------------------------


def run_study(profile_name: str) -> dict:
    """Run one profile end to end. Deterministic: the result is a pure
    function of the fixture bytes, the reference bytes, and the
    profile constants."""
    profile = PROFILES[profile_name]
    reference = _load_reference_meta(
        REFERENCES_DIR / f"{REFERENCE_NAME}_{REFERENCE_VERSION}.json"
    )
    params = in_control_params(reference["values"], reference["basis"])
    sigma0 = pstdev(reference["values"])
    expected = (reference["name"], reference["version"])

    with tempfile.TemporaryDirectory() as tmp:
        paths = sorted(write_split(tmp, "odd"))
        documents = [
            (p.stem, p.read_text(encoding="utf-8")) for p in paths
        ]
    if profile["max_docs"] is not None:
        documents = documents[: profile["max_docs"]]

    with _reference_dir(REFERENCES_DIR):
        # -- unperturbed pass: measure, and drop (loudly) what cannot
        # be scored ------------------------------------------------------
        kept: list[dict] = []
        dropped: list[dict] = []
        for doc_id, text in documents:
            measured = _measure(text, reference["cohort"], expected)
            if measured["unprojectable"] or measured["below_envelope"]:
                dropped.append({
                    "doc": doc_id,
                    "unprojectable": measured["unprojectable"],
                    "below_envelope": measured["below_envelope"],
                })
                continue
            kept.append({
                "doc": doc_id,
                "text": text,
                "input_sha256": hashlib.sha256(
                    text.encode("utf-8")
                ).hexdigest(),
                "distance": measured["distance"],
                "percentile": measured["percentile"],
            })
        if not kept:
            raise RuntimeError(
                "no held-out segment survived the unperturbed pass — "
                "the reference and the corpus do not belong together"
            )

        unperturbed_median = percentile_linear(
            sorted(doc["distance"] for doc in kept), 50.0
        )

        # -- negative control ---------------------------------------------
        negative = detection_summary([doc["percentile"] for doc in kept])
        nominal = 1.0 - DETECT_PERCENTILE / 100.0
        ci = negative["ci95"]
        negative["nominal_rate"] = nominal
        negative["consistent_with_nominal"] = bool(
            ci is not None and ci[0] <= nominal <= ci[1]
        )

        # -- eps=0.0 identity check ----------------------------------------
        identity_perturbation = PERTURBATIONS[IDENTITY_CHECK_PERTURBATION]
        for doc in kept:
            rng = DetRandom(_perturb_seed(
                IDENTITY_CHECK_PERTURBATION, 0.0, doc["input_sha256"]
            ))
            out, counts = identity_perturbation.apply(doc["text"], 0.0, rng)
            if out != doc["text"] or counts["edited"] != 0:
                raise RuntimeError(
                    f"identity check failed: {IDENTITY_CHECK_PERTURBATION} "
                    f"at eps=0.0 changed {doc['doc']}"
                )
        identity_check = {
            "perturbation": IDENTITY_CHECK_PERTURBATION,
            "epsilon": 0.0,
            "n_docs": len(kept),
            "all_identical": True,
        }

        # -- perturbation cells + batch power -------------------------------
        cells: list[dict] = []
        power_rows: list[dict] = []
        for perturbation_id in sorted(profile["perturbations"]):
            perturbation = PERTURBATIONS[perturbation_id]
            for eps in profile["epsilons"]:
                per_doc: list[dict] = []
                for doc in kept:
                    rng = DetRandom(_perturb_seed(
                        perturbation_id, eps, doc["input_sha256"]
                    ))
                    kwargs = (
                        {"donor": donor_sentences(
                            donor_fixture_for(doc["doc"])
                        )}
                        if perturbation_id == "register_mix" else {}
                    )
                    perturbed_text, counts = perturbation.apply(
                        doc["text"], eps, rng, **kwargs
                    )
                    measured = _measure(
                        perturbed_text, reference["cohort"], expected
                    )
                    per_doc.append({
                        "doc": doc["doc"],
                        "sites": counts["sites"],
                        "edited": counts["edited"],
                        "distance": measured["distance"],
                        "percentile": measured["percentile"],
                        "below_envelope": measured["below_envelope"],
                    })
                distances = [
                    row["distance"] for row in per_doc
                    if row["distance"] is not None
                ]
                effect = realized_effect_size(
                    distances, unperturbed_median, sigma0
                )
                n_docs = len(per_doc)
                cells.append({
                    "perturbation": perturbation_id,
                    "epsilon": eps,
                    "n_docs": n_docs,
                    "n_below_envelope": sum(
                        1 for row in per_doc if row["below_envelope"]
                    ),
                    "detection": detection_summary(
                        [row["percentile"] for row in per_doc]
                    ),
                    "median_distance": (
                        percentile_linear(sorted(distances), 50.0)
                        if distances else None
                    ),
                    "effect_size_sigma0": effect,
                    "mean_sites": sum(r["sites"] for r in per_doc) / n_docs,
                    "mean_edited": sum(r["edited"] for r in per_doc) / n_docs,
                    "per_doc": per_doc,
                })
                for batch_size in profile["batch_sizes"]:
                    seed = _power_seed(perturbation_id, eps, batch_size)
                    if distances:
                        row = batch_power_cell(
                            distances, reference["values"], params,
                            batch_size, seed,
                        )
                    else:
                        row = {
                            "batch_size": batch_size,
                            "n_batches": N_BATCHES,
                            "n_signalled": None,
                            "power": None,
                            "ci95": None,
                            "note": "no measurable perturbed distances",
                        }
                    power_rows.append({
                        "perturbation": perturbation_id,
                        "epsilon": eps,
                        "effect_size_sigma0": effect,
                        **row,
                    })

    return {
        "study": "validation_study",
        "profile": profile_name,
        "generated_by": (
            f"python -m tools.validation_study --profile {profile_name} "
            "--write"
        ),
        "honesty_statement": HONESTY_STATEMENT,
        "reference": {
            "path": str(
                reference["path"].relative_to(REPO_ROOT).as_posix()
            ),
            "sha256": reference["sha256"],
            "name": reference["name"],
            "version": reference["version"],
            "cohort": reference["cohort"],
            "n": reference["n"],
            "self_distance_basis": reference["basis"],
            "self_distance_n": len(reference["values"]),
            "mu0": params.mu0,
            "sigma0": sigma0,
        },
        "detection_policy": {
            "rule": f"detected := reference_envelope.percentile > "
                    f"{DETECT_PERCENTILE:g}",
            "note": (
                "illustrative 5% operating point; raw percentile and "
                "distance streams are included per cell so any other "
                "operating point can be recomputed without rerunning"
            ),
        },
        "effect_size_definition": (
            "(median perturbed distance - median unperturbed distance) "
            "/ sigma0, sigma0 = pstdev(reference self_distance.values)"
        ),
        "seed_scheme": {
            "perturb": "validation:<perturbation_id>:<epsilon>:"
                       "<input_sha256(unperturbed doc)>",
            "power": "validation:power:<perturbation_id>:<epsilon>:"
                     "<batch_size>",
        },
        "params": {
            "perturbations": sorted(profile["perturbations"]),
            "epsilons": list(profile["epsilons"]),
            "max_docs": profile["max_docs"],
            "batch_sizes": list(profile["batch_sizes"]),
            "n_batches": N_BATCHES,
            "in_control_prefix": IN_CONTROL_PREFIX,
            "ewma": {"lam": EWMA_LAM, "L": EWMA_L},
        },
        "held_out": {
            "split": "odd",
            "source": "tools.fixture_corpus.write_split(dest, 'odd')",
            "n_segments": len(documents),
            "n_kept": len(kept),
            "n_dropped": len(dropped),
            "dropped": dropped,
            "unperturbed_median_distance": unperturbed_median,
            "docs": [
                {
                    "doc": doc["doc"],
                    "input_sha256": doc["input_sha256"],
                    "distance": doc["distance"],
                    "percentile": doc["percentile"],
                }
                for doc in kept
            ],
        },
        "negative_control": negative,
        "identity_check": identity_check,
        "cells": cells,
        "batch_power": power_rows,
    }


# ---- user mode ----------------------------------------------------------


def run_customer(
    corpus_dir: Path, reference_path: Path, hint: Optional[str],
) -> dict:
    """Unperturbed analysis of a user corpus against a user
    reference: percentile stream, detection rate at the documented
    operating point, and the three SPC charts' summary. Touches
    nothing under fixtures/. Stream order is sorted file names — name
    files in time order for a time-ordered chart."""
    reference = _load_reference_meta(reference_path)
    cohort = hint if hint is not None else reference["cohort"]
    params = in_control_params(reference["values"], reference["basis"])
    null_sorted = sorted(reference["values"])
    expected = (reference["name"], reference["version"])

    files = sorted(corpus_dir.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"no *.md documents in {corpus_dir}")

    kept: list[dict] = []
    dropped: list[dict] = []
    with _reference_dir(reference_path.parent):
        for path in files:
            measured = _measure(
                path.read_text(encoding="utf-8"), cohort, expected,
            )
            if measured["unprojectable"] or measured["below_envelope"]:
                dropped.append({
                    "doc": path.stem,
                    "unprojectable": measured["unprojectable"],
                    "below_envelope": measured["below_envelope"],
                })
                continue
            kept.append({
                "doc": path.stem,
                "distance": measured["distance"],
                "percentile": measured["percentile"],
            })

    detection = detection_summary([doc["percentile"] for doc in kept])
    nominal = 1.0 - DETECT_PERCENTILE / 100.0
    ci = detection["ci95"]
    detection["nominal_rate"] = nominal
    detection["consistent_with_nominal"] = bool(
        ci is not None and ci[0] <= nominal <= ci[1]
    )

    spc_block = None
    if kept:
        stream = [doc["distance"] for doc in kept]
        individuals_result = individuals(stream, null_sorted)
        ewma_result = ewma(stream, params, lam=EWMA_LAM, L=EWMA_L)
        cusum_result = cusum(stream, params)
        spc_block = {
            "summary": summarize(
                individuals_result, ewma_result, cusum_result,
            ),
            "ewma": {
                "lam": ewma_result["lam"],
                "L": ewma_result["L"],
                "n_signals": ewma_result["n_signals"],
                "first_signal_index": ewma_result["first_signal_index"],
            },
            "cusum": {
                "k": cusum_result["k"],
                "h": cusum_result["h"],
                "n_signals": cusum_result["n_signals"],
                "first_signal_index": cusum_result["first_signal_index"],
            },
            "individuals": {
                "p": individuals_result["p"],
                "n_exceedances": individuals_result["n_exceedances"],
            },
        }

    return {
        "report": "validation_study_customer",
        "generated_by": (
            "python -m tools.validation_study --corpus-dir ... "
            "--reference ..."
        ),
        "corpus_dir": str(corpus_dir),
        "stream_order": "sorted file names",
        "reference": {
            "path": str(reference_path),
            "sha256": reference["sha256"],
            "name": reference["name"],
            "version": reference["version"],
            "cohort_hint": cohort,
            "n": reference["n"],
            "self_distance_basis": reference["basis"],
            "self_distance_n": len(reference["values"]),
            "mu0": params.mu0,
            "sigma0": pstdev(reference["values"]),
        },
        "n_documents": len(files),
        "n_scored": len(kept),
        "n_dropped": len(dropped),
        "dropped": dropped,
        "documents": kept,
        "detection": detection,
        "spc": spc_block,
    }


# ---- rendering --------------------------------------------------------------


def render_json(obj: dict) -> str:
    """Byte-stable JSON: sorted keys, q()-quantised floats, indent=2,
    trailing newline."""
    return json.dumps(
        quantize(obj),
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _fmt(v, spec: str = ".2f") -> str:
    return "—" if v is None else format(q(float(v)), spec)


def _fmt_ci(ci) -> str:
    if ci is None:
        return "—"
    return f"[{q(float(ci[0])):.2f}, {q(float(ci[1])):.2f}]"


def render_md(study: dict) -> str:
    """docs/VALIDATION.md, derived entirely from the full-profile study
    object so the two artifacts cannot disagree."""
    reference = study["reference"]
    negative = study["negative_control"]
    held_out = study["held_out"]
    batch_sizes = study["params"]["batch_sizes"]
    power_by_key = {
        (row["perturbation"], row["epsilon"], row["batch_size"]): row
        for row in study["batch_power"]
    }
    cells_by_perturbation: dict[str, list[dict]] = {}
    for cell in study["cells"]:
        cells_by_perturbation.setdefault(cell["perturbation"], []).append(cell)

    percentile_step = 100.0 / reference["self_distance_n"]

    lines: list[str] = []
    a = lines.append
    a("# VALIDATION — perturbation detection study (method demonstration)")
    a("")
    a("> Generated by `python -m tools.validation_study --profile full"
      " --write`.")
    a("> Do not edit by hand — regenerate with that command; verify"
      " drift with")
    a("> `python -m tools.validation_study --profile full --check`.")
    a("")
    a("**Read this first.** " + study["honesty_statement"] + " What the"
      " numbers below demonstrate is that the pipeline (reference →"
      " percentile → operating point → batch SPC) detects known injected"
      " changes at rates that track realized effect size, with a negative"
      " control at the nominal false-positive rate — on this corpus, at"
      " this size, for these mechanical edits. Treat every number as a"
      " property of the demonstration, not of your deployment; the"
      " user protocol below is how the same claim is earned on your"
      " own data.")
    a("")
    a("## Method")
    a("")
    a(f"- **Reference**: `{reference['path']}` (`{reference['name']}`"
      f" `{reference['version']}`, cohort `{reference['cohort']}`,"
      f" n={reference['n']}, null basis"
      f" `{reference['self_distance_basis']}`,"
      f" sha256 `{reference['sha256']}`), built from the EVEN-parity"
      " ~200-word fixture segments (`tools.fixture_corpus`).")
    a("- **Held-out set**: the ODD-parity segments — same fixtures,"
      " disjoint text. Segments that fail to project or read below the"
      " measurement envelope are dropped and counted, never silently.")
    a("- **Perturbations**: the 8 mechanical edits of `tools/perturb.py`,"
      " applied at intensity ε ∈ {" +
      ", ".join(f"{e:g}" for e in study["params"]["epsilons"]) + "}; rng"
      " seeded per (document, perturbation, ε) as"
      f" `{study['seed_scheme']['perturb']}`.")
    a(f"- **Detection policy**: {study['detection_policy']['rule']} —"
      " the illustrative 5% operating point"
      " (raw percentile/distance streams are in the JSON artifact, so"
      " any operating point can be recomputed). With an n="
      f"{reference['self_distance_n']} null, percentiles move in"
      f" ≈{percentile_step:.1f}-point steps, so the achievable"
      " false-positive rates are coarse — another reason this is a"
      " method demonstration.")
    a("- **Effect size**: " + study["effect_size_definition"] +
      f" (σ₀ = {_fmt(reference['sigma0'], '.3f')},"
      f" μ₀ = {_fmt(reference['mu0'], '.3f')}).")
    a("- **Intervals**: exact Clopper–Pearson 95% CIs"
      " (`instrument.kernel.stats.binomial_ci_clopper_pearson`).")
    a(f"- **Batch power**: per cell and batch size N, {study['params']['n_batches']}"
      " DetRandom-resampled batches of N perturbed distances, each"
      f" appended to a {study['params']['in_control_prefix']}-point"
      " in-control prefix resampled from the reference null (seed"
      f" `{study['seed_scheme']['power']}`); power = fraction in which"
      " the EWMA chart (`instrument.spc.ewma`, λ="
      f"{study['params']['ewma']['lam']:g}, L="
      f"{study['params']['ewma']['L']:g}) signals within the batch"
      " region.")
    a("")
    a("## Held-out set")
    a("")
    a(f"{held_out['n_segments']} odd-parity segments;"
      f" {held_out['n_kept']} scored, {held_out['n_dropped']} dropped:")
    a("")
    for row in held_out["dropped"]:
        reasons = [
            name for name in ("unprojectable", "below_envelope")
            if row[name]
        ]
        a(f"- `{row['doc']}` — {', '.join(reasons)}")
    if not held_out["dropped"]:
        a("- (none)")
    a("")
    a("## Negative control")
    a("")
    a(f"Unperturbed held-out documents against the >{DETECT_PERCENTILE:g}"
      f" operating point: {negative['n_detected']}/{negative['n_scored']}"
      f" detected — rate {_fmt(negative['detection_rate'])}"
      f" {_fmt_ci(negative['ci95'])} vs nominal"
      f" {negative['nominal_rate']:g}. " +
      ("The CI covers the nominal rate: the operating point behaves as"
       " documented on in-distribution material."
       if negative["consistent_with_nominal"] else
       "**THE CI EXCLUDES THE NOMINAL RATE — the calibration/held-out"
       " pairing is broken; `--check` fails on this condition.**"))
    a("")
    identity = study["identity_check"]
    a(f"Identity check: `{identity['perturbation']}` at ε=0 returned all"
      f" {identity['n_docs']} documents byte-identical.")
    a("")
    a("## Detection by perturbation")
    a("")
    a("Per cell: mean realized edits over found sites, realized effect"
      " size in σ₀ units, detection at the documented operating point,"
      " and EWMA batch power at N ∈ {" +
      ", ".join(str(n) for n in batch_sizes) + "}. “unm.” counts"
      " perturbed documents whose emission lost the percentile"
      " (unprojectable); they stay out of the detection denominator but"
      " are reported here.")
    a("")
    for perturbation_id in sorted(cells_by_perturbation):
        a(f"### `{perturbation_id}`")
        a("")
        a(f"{PERTURBATIONS[perturbation_id].description}.")
        a("")
        header = ("| ε | edited/sites (mean) | effect size (σ₀) |"
                  " detected | rate [95% CI] |")
        divider = "|---|---|---|---|---|"
        for n in batch_sizes:
            header += f" power N={n} |"
            divider += "---|"
        a(header)
        a(divider)
        for cell in cells_by_perturbation[perturbation_id]:
            detection = cell["detection"]
            detected = (
                f"{detection['n_detected']}/{detection['n_scored']}"
            )
            if detection["n_unmeasurable"]:
                detected += f" ({detection['n_unmeasurable']} unm.)"
            row = (
                f"| {cell['epsilon']:g}"
                f" | {_fmt(cell['mean_edited'], '.1f')}/"
                f"{_fmt(cell['mean_sites'], '.1f')}"
                f" | {_fmt(cell['effect_size_sigma0'], '+.2f')}"
                f" | {detected}"
                f" | {_fmt(detection['detection_rate'])}"
                f" {_fmt_ci(detection['ci95'])} |"
            )
            for n in batch_sizes:
                power = power_by_key[
                    (perturbation_id, cell["epsilon"], n)
                ]
                row += (
                    f" {_fmt(power['power'])} {_fmt_ci(power['ci95'])} |"
                )
            a(row)
        a("")
    a("## Batch-power statements")
    a("")
    a("Reading the table: each entry says “at batch size N, a shift of"
      " X σ₀ is signalled with probability Y [CI]”. At the highest"
      " intensity:")
    a("")
    for perturbation_id in sorted(cells_by_perturbation):
        cell = cells_by_perturbation[perturbation_id][-1]
        parts = []
        for n in batch_sizes:
            power = power_by_key[(perturbation_id, cell["epsilon"], n)]
            parts.append(
                f"{_fmt(power['power'])} {_fmt_ci(power['ci95'])} at N={n}"
            )
        a(f"- `{perturbation_id}` at ε={cell['epsilon']:g} (shift"
          f" {_fmt(cell['effect_size_sigma0'], '+.2f')} σ₀): signalled"
          " with probability " + "; ".join(parts) + ".")
    a("")
    a("## Limitations")
    a("")
    a("- **Segment non-independence**: the held-out “documents” are"
      " segments of 8 fixtures; style repeats across segments of the"
      " same fixture, so the effective sample size is closer to 8 than"
      f" to {held_out['n_kept']}, and the CIs are optimistic in that"
      " respect.")
    a(f"- **Thin calibration**: the reference null has n="
      f"{reference['self_distance_n']}; percentiles move in"
      f" ≈{percentile_step:.1f}-point steps and the >"
      f"{DETECT_PERCENTILE:g} operating point only fires beyond the"
      " null's upper tail. User references should be built on"
      " hundreds of documents (`docs/CALIBRATION.md`).")
    a("- **Mechanical ≠ model drift**: these perturbations move surface"
      " features the instrument measures; a model swap moves many"
      " features at once in correlated ways. Detection of one is"
      " evidence about the method, not a guarantee about the other.")
    a("- **Pooled cohort**: the reference pools all 8 fixture registers"
      " into one cohort, so its null is wide; register_mix moves"
      " documents *within* that pooled cloud, which bounds its realized"
      " effect size here.")
    a("- **Resampled batch power**: power figures resample the same"
      f" ≤{held_out['n_kept']} perturbed distances per cell; they are"
      " statements about the observed shift sizes, not new data.")
    a("")
    a("## User protocol — the study that scales")
    a("")
    a("The in-repo study is the rehearsal; this is the performance. To"
      " run the same validation on your own regime change (model swap,"
      " temperature, prompt template, decoding params):")
    a("")
    a("1. **Calibrate on regime A**: collect ≥100 documents produced"
      " under the current regime; build a reference —")
    a("   `python -m tools.build_reference --corpus-dir regimeA/ --name"
      " my_baseline --cohort my_baseline --scope \"...\""
      " --collection-window \"...\" --out refs/`.")
    a("2. **Capture regime B**: collect documents produced under the"
      " candidate regime into a directory of `.md` files (name them in"
      " time order if you want the SPC charts to read as a time"
      " series).")
    a("3. **Run the unperturbed analysis** (this tool, user mode):")
    a("   `python -m tools.validation_study --corpus-dir regimeB/"
      " --reference refs/my_baseline_v1.json [--hint my_baseline]"
      " [--out report.json]`")
    a("   The report carries the percentile stream, the detection rate"
      " at the documented operating point vs nominal, and the"
      " EWMA/CUSUM/individuals chart summary — the same statistics as"
      " this study's negative control, on your data.")
    a("4. **Interpret with your n**: detection CIs are exact"
      " Clopper–Pearson at your document count, and batch power scales"
      " with your batch sizes — rerun step 3 on regime-A hold-outs to"
      " get your own negative control before you trust a positive.")
    a("5. **Ongoing monitoring**: stream production emissions to JSONL"
      " and chart them with `python -m tools.control_chart --emissions"
      " out.jsonl --reference refs/my_baseline_v1.json` (see"
      " `docs/INTEGRATION.md`).")
    a("")
    a("The verdicts here are descriptive chart states, never actions:"
      " what to do when a batch signals (recalibrate, investigate,"
      " quarantine) is the user's out-of-control action plan"
      " (`instrument/spc.py`).")
    a("")
    return "\n".join(lines)


# ---- entry points -----------------------------------------------------------


def _artifacts_for(profile_name: str, study: dict) -> list[tuple[Path, str]]:
    if profile_name == "smoke":
        return [(SMOKE_JSON, render_json(study))]
    return [
        (FULL_JSON, render_json(study)),
        (MD_PATH, render_md(study)),
    ]


def _negative_control_gate(study: dict) -> bool:
    """True when the negative control is consistent with nominal;
    prints the loud message when it is not."""
    if study["negative_control"]["consistent_with_nominal"]:
        return True
    negative = study["negative_control"]
    print(
        "NEGATIVE CONTROL FAILURE: unperturbed held-out detection rate "
        f"{negative['detection_rate']} with 95% CI {negative['ci95']} "
        f"EXCLUDES the nominal rate {negative['nominal_rate']} — the "
        "reference and the held-out split no longer calibrate each "
        "other. Do not trust the detection tables; rebuild the "
        "reference (tools.build_reference on the EVEN split) before "
        "regenerating this study.",
        file=sys.stderr,
    )
    return False


def write(profile_name: str) -> int:
    started = time.monotonic()
    study = run_study(profile_name)
    for path, content in _artifacts_for(profile_name, study):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    # stdout only — wall-clock never enters an artifact.
    print(f"profile {profile_name} computed in "
          f"{time.monotonic() - started:.1f}s")
    if not _negative_control_gate(study):
        print(
            "artifacts written for inspection; --check will fail until "
            "the negative control is healthy",
            file=sys.stderr,
        )
    return 0


def check(profile_name: str) -> int:
    started = time.monotonic()
    study = run_study(profile_name)
    drifted: list[str] = []
    for path, regenerated in _artifacts_for(profile_name, study):
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            return 1
        if regenerated != path.read_text(encoding="utf-8"):
            drifted.append(str(path.relative_to(REPO_ROOT)))
            print(f"DRIFT: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
    ok = _negative_control_gate(study)
    if drifted:
        print(
            f"{len(drifted)} output(s) drifted — regenerate with "
            f"`python -m tools.validation_study --profile {profile_name} "
            "--write`",
            file=sys.stderr,
        )
        return 1
    if not ok:
        return 1
    print(f"{len(_artifacts_for(profile_name, study))} output(s) ok "
          f"(profile {profile_name}, "
          f"{time.monotonic() - started:.1f}s)")
    return 0


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        description="Perturbation detection validation study "
                    "(fixture profiles) and user-corpus analysis.",
    )
    ap.add_argument("--profile", choices=sorted(PROFILES))
    ap.add_argument("--write", action="store_true",
                    help="regenerate committed outputs")
    ap.add_argument("--check", action="store_true",
                    help="regenerate to memory, byte-compare against "
                         "committed outputs; also fails on a negative-"
                         "control violation")
    ap.add_argument("--corpus-dir", type=Path, default=None,
                    help="user mode: directory of *.md documents "
                         "(unperturbed analysis only)")
    ap.add_argument("--reference", type=Path, default=None,
                    help="user mode: reference JSON built by "
                         "tools.build_reference (must persist "
                         "self_distance.values)")
    ap.add_argument("--hint", default=None,
                    help="user mode: register hint (default: the "
                         "reference's own cohort)")
    ap.add_argument("--out", type=Path, default=None,
                    help="user mode: write the report here instead "
                         "of stdout")
    args = ap.parse_args(argv)

    if args.corpus_dir is not None or args.reference is not None:
        if args.corpus_dir is None or args.reference is None:
            ap.error("user mode needs both --corpus-dir and --reference")
        if args.profile or args.write or args.check:
            ap.error("user mode does not take --profile/--write/--check")
        report = run_customer(args.corpus_dir, args.reference, args.hint)
        rendered = render_json(report)
        if args.out is not None:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(rendered, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            sys.stdout.write(rendered)
        return 0

    if not args.profile:
        ap.error("pass --profile smoke|full (or user-mode flags)")
    if args.write == args.check:
        ap.error("pass exactly one of --write / --check")
    return write(args.profile) if args.write else check(args.profile)


if __name__ == "__main__":
    raise SystemExit(main())
