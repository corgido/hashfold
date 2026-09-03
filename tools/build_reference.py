"""build_reference — build a user reference from your own corpus.

THE SUPPORTED CALIBRATION PATH. `docs/CALIBRATION.md` explains why
the distance metric is only meaningful against a baseline built on
YOUR deployment's output (the reference defines the coordinate
system, not just a comparison point). This tool is how your data
science team builds that baseline, with zero dependencies beyond
the Python standard library — same as the runtime.

    python -m tools.build_reference \
        --corpus-dir /path/to/your/llm/outputs \
        --name acme_support_normal --version v1 \
        --cohort acme_support_normal \
        --scope "Acme support-bot answers, prod prompts, May 2026" \
        --collection-window "2026-05-01..2026-05-31" \
        --out /etc/instrument/references

Then point the server at the directory:

    INSTRUMENT_REFERENCES_DIR=/etc/instrument/references \
        python -m instrument.serve.http

and route against your baseline explicitly with
`?register_hint=acme_support_normal` (the hint must equal the
--cohort string exactly), or let auto-routing consider it alongside
the bundled references.

What it does, in order:

1. Measure every `*.md` / `*.txt` under --corpus-dir (sorted walk)
   with `joint_reading`; keep docs with >= --min-words words.
2. Keep features that are finite across the whole corpus AND have
   non-zero variance (a zero-variance feature makes z-scores
   undefined; the runtime projector would refuse to project).
3. Z-score, then PCA via a deterministic cyclic Jacobi
   eigendecomposition of the covariance matrix (pure Python; no
   numpy). Components are sign-fixed (largest-|loading| entry
   positive) and named pc_1..pc_k.
4. Project the corpus onto its own components; record the centroid
   and per-component spread the runtime distance uses.
5. Validate by round-tripping through the runtime loader and
   self-routing every corpus document (every doc must project; the
   tool prints the resubstitution self-distance distribution as a
   sanity check).
6. Build the HONEST null distribution by 10-fold cross-validation
   (0.10.0): each contiguous block of documents is scored against a
   model fitted WITHOUT it, so the persisted `self_distance`
   (n, median, p95, full sorted `values`, `basis`) describes how far
   genuinely in-distribution data lands — resubstitution understates
   that spread. Corpora under 10 documents (or `--no-cv`) fall back
   to resubstitution and say so in `basis`.
7. Measure baseline stability by delete-10% block jackknife over the
   same fold fits (`stability`: centroid shift, loading alignment,
   held-out p95 range), persist per-feature percentile grids
   (`per_feature_quantiles`), and stamp provenance
   (`collection_window`, `provenance`, `recalibration_policy`).
8. Write `<name>_<version>.json` plus its SHA256. Commit or archive
   the file: the reference BYTES are the pin. Rebuilding on another
   host may differ in last-ULP float digits; the shipped file, not
   the build, is what reproducibility attaches to. For a rebuild
   that can be byte-compared, pass `--calibration-date` (the
   wall-clock stamp is the only nondeterministic byte on a fixed
   host + commit).

Optionally `--readings-out readings.jsonl` writes one line per
document (path, n_words, flat features) for your own analysis —
percentiles, drift dashboards, whatever your team builds. The
instrument deliberately does not build it for you.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from instrument.kernel.quantize import q
from instrument.kernel.stats import (
    mean as _mean,
    percentile_linear as _percentile,
    pstdev as _std,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

_CV_FOLDS = 10
_VALUES_THIN_ABOVE = 10_000
_THIN_GRID_POINTS = 1001

RECALIBRATION_TRIGGERS = [
    "model_update",
    "prompt_change",
    "baseline_age_exceeds_max",
    "n_new_docs>=100",
]


class FitError(ValueError):
    """The corpus (or a CV fold of it) cannot support a model fit."""


# ---- small deterministic stats (kernel-backed) ------------------------------
#
# _mean/_std/_percentile are `instrument.kernel.stats.mean/pstdev/
# percentile_linear` — bit-identical to the private helpers this tool
# carried before 0.10.0 (same expressions, same summation order), so
# references rebuilt from the same corpus print the same numbers.

def _stats_block(xs: list[float]) -> dict:
    s = sorted(xs)
    return {
        "mean": _mean(xs),
        "std": _std(xs),
        "p05": _percentile(s, 5),
        "p25": _percentile(s, 25),
        "p50": _percentile(s, 50),
        "p75": _percentile(s, 75),
        "p95": _percentile(s, 95),
    }


# ---- deterministic PCA via cyclic Jacobi ------------------------------------

def _jacobi_eigh(a: list[list[float]], max_sweeps: int = 200,
                 eps: float = 1e-12) -> tuple[list[float], list[list[float]]]:
    """Eigendecomposition of a small symmetric matrix.

    Cyclic-by-row Jacobi rotations: deterministic (fixed visit
    order, no pivot search ties), numerically robust for the
    feature-count-sized matrices this tool sees. Returns
    (eigenvalues, eigenvectors-as-columns).
    """
    n = len(a)
    a = [row[:] for row in a]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = math.sqrt(sum(a[p][q] ** 2
                            for p in range(n) for q in range(n) if p != q))
        if off < eps:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) < eps / (n * n):
                    continue
                theta = (a[q][q] - a[p][p]) / (2.0 * apq)
                t = math.copysign(1.0, theta) / (
                    abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    eigvals = [a[i][i] for i in range(n)]
    return eigvals, v


def _pca(z_rows: list[list[float]], n_components: int) -> list[list[float]]:
    """Top-k principal axes of z-scored rows (rows = docs).

    Returns k loading vectors (each len n_features), eigenvalue-
    descending, sign-fixed so the largest-|weight| entry is
    positive (ties break to the lowest index).
    """
    n = len(z_rows)
    f = len(z_rows[0])
    cov = [[sum(z_rows[r][i] * z_rows[r][j] for r in range(n)) / n
            for j in range(f)] for i in range(f)]
    eigvals, eigvecs = _jacobi_eigh(cov)
    order = sorted(range(f), key=lambda i: (-eigvals[i], i))
    k = min(n_components, f, max(1, n - 1))
    loadings: list[list[float]] = []
    for idx in order[:k]:
        vec = [eigvecs[row][idx] for row in range(f)]
        pivot = max(range(f), key=lambda i: (abs(vec[i]), -i))
        if vec[pivot] < 0:
            vec = [-x for x in vec]
        loadings.append(vec)
    return loadings


# ---- model fit ---------------------------------------------------------------

def _fit_model(rows: list[dict], n_components: int) -> dict:
    """Feature screen + z-score + PCA + centroid + composites on `rows`.

    THE single estimator: the main build, the CV fold fits, and the
    jackknife replicates all call this, so the null distribution and
    the stability figures describe exactly the model that ships.
    Behaviour is byte-identical to the pre-0.10 inline construction
    (same expressions, same iteration order).

    Returns the model piece of a reference dict:
        kept, dropped, cols, per_feature, pc_zscore_mean,
        pc_zscore_std, pc_loadings, pc_centroid, pc_composites.
    Raises FitError when fewer than 2 usable features survive the
    screen.
    """
    all_keys = sorted(rows[0]["features"].keys())
    kept: list[str] = []
    dropped: list[tuple[str, str]] = []
    for key in all_keys:
        col = [r["features"].get(key) for r in rows]
        if not all(_finite(v) for v in col):
            dropped.append((key, "non-finite in corpus"))
            continue
        if _std([float(v) for v in col]) == 0.0:
            dropped.append((key, "zero variance (z-score undefined)"))
            continue
        kept.append(key)
    if len(kept) < 2:
        raise FitError("fewer than 2 usable features; corpus too uniform")

    cols = {k: [float(r["features"][k]) for r in rows] for k in kept}
    zmean = {k: _mean(cols[k]) for k in kept}
    zstd = {k: _std(cols[k]) for k in kept}
    z_rows = [[(cols[k][i] - zmean[k]) / zstd[k] for k in kept]
              for i in range(len(rows))]

    loadings = _pca(z_rows, n_components)
    pc_names = [f"pc_{i + 1}" for i in range(len(loadings))]
    pc_loadings = {pc_names[i]: {kept[j]: loadings[i][j] for j in range(len(kept))}
                   for i in range(len(loadings))}

    projected = {name: [] for name in pc_names}
    for zr in z_rows:
        for i, name in enumerate(pc_names):
            projected[name].append(
                sum(zr[j] * loadings[i][j] for j in range(len(kept))))

    return {
        "kept": kept,
        "dropped": dropped,
        "cols": cols,
        "per_feature": {k: _stats_block(cols[k]) for k in kept},
        "pc_zscore_mean": zmean,
        "pc_zscore_std": zstd,
        "pc_loadings": pc_loadings,
        "pc_centroid": {name: _mean(projected[name]) for name in pc_names},
        "pc_composites": {name: _stats_block(projected[name])
                          for name in pc_names},
    }


def _typed_fold_reference(fit: dict, n: int):
    """Assemble a fold fit into a runtime ReferenceDistribution.

    Round-trips through JSON + `reference_from_dict` — the exact
    loader path the runtime uses — so a fold model can never score a
    held-out document differently than a shipped reference would.
    The metadata is placeholder: fold references are never persisted.
    """
    import instrument
    from instrument.reading.joint import SCHEMA_VERSION
    from instrument.routing.types import reference_from_dict

    ref = {
        "name": "cv_fold",
        "version": "v0",
        "status": "active",
        "register_cohort": "cv_fold",
        "reliability": "exploratory",
        "scope_statement": "internal cross-validation fold model; never persisted",
        "corpus_description": "internal cross-validation fold",
        "calibration_date": "1970-01-01T00:00:00Z",
        "commit_hash": "internal",
        "n": n,
        "instrument_version": instrument.__version__,
        "schema_version": SCHEMA_VERSION,
        "per_feature": fit["per_feature"],
        "pc_zscore_mean": fit["pc_zscore_mean"],
        "pc_zscore_std": fit["pc_zscore_std"],
        "pc_loadings": fit["pc_loadings"],
        "pc_centroid": fit["pc_centroid"],
        "pc_composites": fit["pc_composites"],
    }
    return reference_from_dict(json.loads(json.dumps(ref)))


# ---- cross-validated null ----------------------------------------------------

def _cross_validated_null(
    rows: list[dict],
    n_components: int,
    resub: list[float],
) -> tuple[list[dict], list[float], list[str]]:
    """Held-out self-distance null via 10-fold contiguous-block CV.

    Fold j holds out rows[floor(j*n/10) : floor((j+1)*n/10)] of the
    path-sorted corpus; a model is fitted on the other rows with
    `_fit_model` and the held-out documents are scored against it with
    the runtime projector + distance. Pooling all n held-out distances
    gives an honest estimate of the self-distance spread: every
    document is scored against a model that never saw it, which is the
    situation every future document is in. (Resubstitution — scoring a
    document against a model built including it — understates the
    spread, so its p95 fires on well over 5% of in-distribution data.)

    Per-fold feature screens may differ slightly from the full model's
    (a feature can be zero-variance or non-finite in 90% of the corpus
    but not in all of it). That fold-to-fold variation is part of the
    honest spread this null is meant to capture, so the folds are
    deliberately NOT forced onto the full model's screen.

    A held-out document that fails to project against its fold model
    (or a fold whose fit fails outright) falls back to that document's
    resubstitution distance; the caller warns, naming the documents.

    Returns (folds, pooled_distances, fallback_paths) where `folds` is
    a list of dicts — {"held", "train", "fit", "held_distances"} — the
    jackknife reuses as its delete-10% replicates.
    """
    from instrument.routing.pc import project_pc_composites
    from instrument.routing.router import _standardised_distance

    n = len(rows)
    folds: list[dict] = []
    pooled: list[float] = []
    fallback_paths: list[str] = []
    for j in range(_CV_FOLDS):
        lo = (j * n) // _CV_FOLDS
        hi = ((j + 1) * n) // _CV_FOLDS
        held = list(range(lo, hi))
        train = [i for i in range(n) if i < lo or i >= hi]
        fold: dict = {"held": held, "train": train,
                      "fit": None, "held_distances": []}
        if held:
            train_rows = [rows[i] for i in train]
            try:
                fit = _fit_model(train_rows, n_components)
            except FitError:
                fit = None
            fold["fit"] = fit
            typed = (_typed_fold_reference(fit, len(train_rows))
                     if fit is not None else None)
            for i in held:
                d = None
                if typed is not None:
                    pcs = project_pc_composites(rows[i]["features"], typed)
                    d = _standardised_distance(pcs, typed)
                if d is None:
                    pooled.append(resub[i])
                    fallback_paths.append(rows[i]["path"])
                else:
                    fold["held_distances"].append(d)
                    pooled.append(d)
        folds.append(fold)
    return folds, pooled, fallback_paths


def _thin_to_grid(sorted_values: list[float]) -> list[float]:
    """Thin a huge null to a fixed percentile grid (p0..p100 by 0.1).

    Only reached when the pooled null exceeds 10,000 points; keeps the
    persisted reference bounded while preserving percentile lookups to
    0.1pp resolution.
    """
    step = 100.0 / (_THIN_GRID_POINTS - 1)
    return [_percentile(sorted_values, i * step)
            for i in range(_THIN_GRID_POINTS)]


# ---- jackknife stability -------------------------------------------------------

def _abs_cos(u: dict[str, float], v: dict[str, float]) -> float:
    """|cos| between two loading vectors over the union of features.

    A feature absent from one vector contributes 0 (the vectors live
    in the union space). Deterministic: the dot product iterates the
    sorted feature union.
    """
    feats = sorted(set(u) | set(v))
    dot = sum(u.get(f, 0.0) * v.get(f, 0.0) for f in feats)
    nu = math.sqrt(sum(u.get(f, 0.0) ** 2 for f in feats))
    nv = math.sqrt(sum(v.get(f, 0.0) ** 2 for f in feats))
    if nu == 0.0 or nv == 0.0:
        return 0.0
    return abs(dot) / (nu * nv)


def _jackknife_stability(
    folds: list[dict],
    full_fit: dict,
    full_pcs: list[dict],
) -> dict | None:
    """Delete-10%-block jackknife over the CV fold fits.

    Each fold fit already IS a delete-one-block replicate (it was
    fitted on 90% of the corpus), so stability costs no extra fits.
    Per replicate, against the full model:

      (a) centroid shift per PC — the replicate's retained rows,
          projected with the FULL model, averaged per PC, minus the
          full centroid, divided by the full per-PC std (|shift| in
          reference std units: how far does the centroid move when
          this 10% block is deleted?);
      (b) loading alignment — |cos| between full and replicate loading
          vectors matched by PC rank (a replicate that fitted fewer
          PCs compares shared ranks only, noted in the block);
      (c) the replicate's held-out distances' p95 — how much does the
          null's tail move fold to fold?

    Returns the stability dict, or None when no replicate fit
    succeeded.
    """
    pc_names = list(full_fit["pc_centroid"].keys())
    shifts: dict[str, list[float]] = {pc: [] for pc in pc_names}
    aligns: dict[str, list[float]] = {pc: [] for pc in pc_names}
    p95s: list[float] = []
    n_replicates = 0
    fewer_pcs = False
    for fold in folds:
        fit = fold["fit"]
        if fit is None or not fold["train"]:
            continue
        n_replicates += 1
        for pc in pc_names:
            rep_mean = _mean([full_pcs[i][pc] for i in fold["train"]])
            full_std = full_fit["pc_composites"][pc]["std"]
            shifts[pc].append(
                abs((rep_mean - full_fit["pc_centroid"][pc]) / full_std))
            if pc in fit["pc_loadings"]:
                aligns[pc].append(
                    _abs_cos(full_fit["pc_loadings"][pc],
                             fit["pc_loadings"][pc]))
            else:
                fewer_pcs = True
        if fold["held_distances"]:
            p95s.append(_percentile(sorted(fold["held_distances"]), 95))
    if n_replicates == 0:
        return None
    stability: dict = {
        "method": "delete_block_jackknife",
        "d_fraction": round(1.0 / _CV_FOLDS, 4),
        "n_replicates": n_replicates,
        "centroid_shift_std_units": {
            pc: {"mean": q(_mean(shifts[pc])), "max": q(max(shifts[pc]))}
            for pc in pc_names if shifts[pc]
        },
        "loading_alignment_abs_cos": {
            pc: {"min": q(min(aligns[pc])), "mean": q(_mean(aligns[pc]))}
            for pc in pc_names if aligns[pc]
        },
    }
    if p95s:
        stability["self_p95_replicate_range"] = [q(min(p95s)), q(max(p95s))]
    if fewer_pcs:
        stability["note"] = (
            "some replicates fitted fewer PCs than the full model; "
            "loading alignment compares shared ranks only"
        )
    return stability


def _print_stability(stability: dict) -> None:
    shifts = stability["centroid_shift_std_units"]
    aligns = stability["loading_alignment_abs_cos"]
    worst_shift_pc = max(shifts, key=lambda pc: shifts[pc]["max"])
    print("stability (delete-10% block jackknife over the CV folds, "
          f"{stability['n_replicates']} replicates):")
    print(f"  max centroid shift: {shifts[worst_shift_pc]['max']:.4f} "
          f"std units ({worst_shift_pc})")
    if aligns:
        worst_align_pc = min(aligns, key=lambda pc: aligns[pc]["min"])
        print(f"  min loading alignment |cos|: "
              f"{aligns[worst_align_pc]['min']:.4f} ({worst_align_pc})")
    rng = stability.get("self_p95_replicate_range")
    if rng:
        print(f"  held-out p95 across replicates: "
              f"[{rng[0]:.4f}, {rng[1]:.4f}]")
    print("  interpretation: centroid shifts well below 1 std unit and "
          "|cos| near 1 mean no single 10% block of the corpus steers "
          "the baseline's geometry; large shifts or low alignment mean "
          "the baseline is fragile — collect more data before relying "
          "on it.")


# ---- corpus measurement ------------------------------------------------------

def _measure_corpus(corpus_dir: Path, min_words: int,
                    readings_out: Path | None) -> tuple[list[dict], int]:
    from instrument.reading.joint import joint_reading

    files = sorted(p for p in corpus_dir.rglob("*")
                   if p.suffix.lower() in (".md", ".txt") and p.is_file())
    if not files:
        raise SystemExit(f"no .md/.txt files under {corpus_dir}")
    rows: list[dict] = []
    skipped = 0
    sink = readings_out.open("w", encoding="utf-8") if readings_out else None
    try:
        for path in files:
            text = path.read_text(encoding="utf-8", errors="replace")
            jr = joint_reading(text)
            n_words = jr["n_words"]["shaper"]
            feats: dict = {}
            feats.update(jr["shaper"]["features"])
            feats.update(jr["other_shaper"]["features"])
            feats.update(jr.get("stylometry", {}).get("features", {}))
            row = {"path": str(path), "n_words": n_words, "features": feats}
            if sink:
                sink.write(json.dumps(row, sort_keys=True) + "\n")
            if n_words < min_words:
                skipped += 1
                continue
            rows.append(row)
    finally:
        if sink:
            sink.close()
    print(f"measured {len(files)} files; kept {len(rows)} "
          f"(skipped {skipped} below {min_words} words)")
    if not rows:
        raise SystemExit("no documents above the word floor; nothing to calibrate")
    return rows, len(files)


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v)


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip()
    except OSError:
        pass
    return "unversioned"


def _resolve_calibration_date(override: str | None) -> str:
    """The build timestamp, or the caller's ISO-8601 override.

    `--calibration-date` exists for deterministic rebuilds: on a fixed
    host + commit the wall-clock stamp is the only nondeterministic
    byte in the output, so pinning it makes two builds of the same
    corpus byte-comparable. Validated (loosely) as ISO-8601.
    """
    if override is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        datetime.fromisoformat(override.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit(
            f"--calibration-date must be ISO-8601, got {override!r}")
    return override


# ---- main --------------------------------------------------------------------

def build(args) -> int:
    calibration_date = _resolve_calibration_date(args.calibration_date)
    rows, n_files_measured = _measure_corpus(
        Path(args.corpus_dir), args.min_words,
        Path(args.readings_out) if args.readings_out else None)
    n = len(rows)

    if n < 10:
        print("WARNING: fewer than 10 usable documents — the null "
              "distribution falls back to resubstitution, which "
              "understates spread (a beyond_p95 position will fire on "
              "well over 5% of in-distribution data). Treat this "
              "reference as a smoke-test artifact, not a baseline. "
              "Aim for 30+ documents; 100+ recommended.", file=sys.stderr)
    elif n < 30:
        print("WARNING: fewer than 30 usable documents — statistically "
              "thin: the null's p95 rests on its top one or two order "
              "statistics and percentile resolution is coarse "
              "(no empirical p-value below 1/(n+1)). Aim for 30+ "
              "documents; 100+ recommended.", file=sys.stderr)

    try:
        fit = _fit_model(rows, args.n_components)
    except FitError as e:
        raise SystemExit(str(e))
    for key, why in fit["dropped"]:
        print(f"  dropping feature {key}: {why}")

    n_words_list = sorted(r["n_words"] for r in rows)
    from instrument.routing.types import classify_length_cohort
    doc_labels = {classify_length_cohort(nw) for nw in n_words_list}
    length_cohort = {
        "label": doc_labels.pop() if len(doc_labels) == 1 else "mixed",
        "n_words_min": n_words_list[0],
        "n_words_max": n_words_list[-1],
        "n_words_p25": round(_percentile(n_words_list, 25)),
        "n_words_median": round(_percentile(n_words_list, 50)),
        "n_words_p75": round(_percentile(n_words_list, 75)),
    }

    import instrument
    from instrument.reading.joint import SCHEMA_VERSION

    ref = {
        "name": args.name,
        "version": args.version,
        "status": "active",
        "register_cohort": args.cohort,
        "reliability": args.reliability,
        "scope_statement": args.scope,
        "corpus_description": args.corpus_description or (
            f"{n} documents from {args.corpus_dir} "
            f"(customer-calibrated; built by tools/build_reference)"),
        "calibration_date": calibration_date,
        "commit_hash": _git_commit(),
        "n": n,
        "instrument_version": instrument.__version__,
        "schema_version": SCHEMA_VERSION,
        "length_cohort": length_cohort,
        "per_feature": fit["per_feature"],
        "pc_zscore_mean": fit["pc_zscore_mean"],
        "pc_zscore_std": fit["pc_zscore_std"],
        "pc_loadings": fit["pc_loadings"],
        "pc_centroid": fit["pc_centroid"],
        "pc_composites": fit["pc_composites"],
        # 0.10.0 provenance blocks — static facts about how this
        # baseline came to be, echoed into every emission's
        # register.evidence.reference_provenance.
        "collection_window": args.collection_window,
        "provenance": {
            "tool": "tools.build_reference",
            "min_words": args.min_words,
            "n_components": args.n_components,
            "n_files_measured": n_files_measured,
            "n_kept": n,
            "dropped_features": [[name, why] for name, why in fit["dropped"]],
        },
        "recalibration_policy": {
            "max_age_days": args.max_age_days,
            "triggers": RECALIBRATION_TRIGGERS,
            "note": args.recalibration_note,
            "policy_version": "1",
        },
    }

    # Validate against the SAME loader and distance code the runtime
    # uses: every calibration document must project against the full
    # model (resubstitution sanity loop — kept even though the
    # persisted null is cross-validated, because a doc that cannot
    # project against the model built FROM it signals a builder bug).
    from instrument.routing.pc import project_pc_composites
    from instrument.routing.router import _standardised_distance
    from instrument.routing.types import reference_from_dict
    typed = reference_from_dict(json.loads(json.dumps(ref)))
    resub: list[float] = []
    full_pcs: list[dict] = []
    for r in rows:
        pcs = project_pc_composites(r["features"], typed)
        d = _standardised_distance(pcs, typed)
        if d is None:
            raise SystemExit(
                f"self-validation failed: {r['path']} does not project "
                "against the reference built from it — report this")
        resub.append(d)
        full_pcs.append(pcs)
    resub_sorted = sorted(resub)
    print("self-distance over the calibration corpus "
          f"(median {_percentile(resub_sorted, 50):.3f}, "
          f"p95 {_percentile(resub_sorted, 95):.3f}) — new outputs scoring near "
          "the median look like this corpus; the user decides what "
          "deviation matters (docs/INTEGRATION.md).")

    # Honest null (0.10.0): cross-validated when the corpus supports
    # it. Resubstitution scores each doc against a model built
    # including it, so it understates the spread new documents will
    # show; the CV null holds each block out and is what the runtime
    # percentile / exceedance figures are quoted against.
    folds: list[dict] | None = None
    if args.no_cv or n < _CV_FOLDS:
        pooled_sorted = resub_sorted
        basis = "resubstitution"
        if n < _CV_FOLDS and not args.no_cv:
            print(f"null distribution: resubstitution (corpus has {n} < "
                  f"{_CV_FOLDS} documents; cross-validation impossible)")
        else:
            print("null distribution: resubstitution (--no-cv)")
    else:
        folds, pooled, fallback_paths = _cross_validated_null(
            rows, args.n_components, resub)
        pooled_sorted = sorted(pooled)
        basis = f"cross_validated_{_CV_FOLDS}fold"
        if fallback_paths:
            print("WARNING: "
                  f"{len(fallback_paths)} held-out document(s) failed to "
                  "project against their fold model; using their "
                  "resubstitution distance instead: "
                  + ", ".join(sorted(fallback_paths)), file=sys.stderr)
        print(f"cross-validated null ({_CV_FOLDS}-fold contiguous blocks): "
              f"n={len(pooled_sorted)}, "
              f"median {_percentile(pooled_sorted, 50):.3f}, "
              f"p95 {_percentile(pooled_sorted, 95):.3f} — persisted as "
              "self_distance; expect it wider than the resubstitution "
              "figures above (that is the point).")

    values = pooled_sorted
    if len(values) > _VALUES_THIN_ABOVE:
        values = _thin_to_grid(pooled_sorted)
        basis += "_thinned"
        print(f"self_distance.values thinned to a {_THIN_GRID_POINTS}-point "
              f"percentile grid (pooled n={len(pooled_sorted)} > "
              f"{_VALUES_THIN_ABOVE})")

    # Quantized like every emitted number. Quantisation is monotone,
    # so the persisted values stay sorted.
    ref["self_distance"] = {
        "n": len(pooled_sorted),
        "median": q(_percentile(pooled_sorted, 50)),
        "p95": q(_percentile(pooled_sorted, 95)),
        "values": [q(v) for v in values],
        "basis": basis,
    }

    # Per-feature percentile grids (0.10.0): p0..p100 for every kept
    # feature, so offline tooling can place any single feature value
    # within the calibration distribution without the raw corpus.
    if not args.no_feature_quantiles:
        ref["per_feature_quantiles"] = {
            k: [q(_percentile(sorted(fit["cols"][k]), p)) for p in range(101)]
            for k in fit["kept"]
        }

    # Stability (0.10.0): reuses the CV fold fits as delete-10%
    # jackknife replicates.
    if not args.no_stability:
        stability = _jackknife_stability(folds, fit, full_pcs)\
            if folds is not None else None
        if stability is not None:
            ref["stability"] = stability
            _print_stability(stability)
        else:
            print("stability: skipped (requires the cross-validated fold "
                  "fits; corpus under 10 documents or --no-cv)")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.name}_{args.version}.json"
    payload = json.dumps(ref, sort_keys=True, indent=2,
                         ensure_ascii=False) + "\n"
    out_path.write_text(payload, encoding="utf-8")
    sha = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    print(f"wrote {out_path}")
    print(f"reference sha256: {sha}")
    print("Pin this file. Deploy with "
          f"INSTRUMENT_REFERENCES_DIR={out_dir} and route with "
          f"?register_hint={args.cohort} (hint must equal --cohort exactly).")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Build a user reference from a corpus of your "
                    "own LLM outputs (stdlib-only).")
    ap.add_argument("--corpus-dir", required=True,
                    help="directory of .md/.txt sample outputs")
    ap.add_argument("--name", required=True,
                    help="reference name (filename stem becomes <name>_<version>.json)")
    ap.add_argument("--cohort", required=True,
                    help="register_cohort label; also the exact ?register_hint= value")
    ap.add_argument("--scope", required=True,
                    help="scope statement: model, prompts, period this baseline covers")
    ap.add_argument("--collection-window", required=True,
                    help="when the corpus was collected (free string, e.g. "
                         "'2026-05-01..2026-06-30'); persisted and echoed in "
                         "every emission's reference_provenance")
    ap.add_argument("--version", default="v1")
    ap.add_argument("--reliability", default="production",
                    choices=["production", "exploratory"],
                    help="production references are preferred by auto-routing")
    ap.add_argument("--corpus-description", default=None)
    ap.add_argument("--out", default=".",
                    help="output directory (becomes INSTRUMENT_REFERENCES_DIR)")
    ap.add_argument("--min-words", type=int, default=150,
                    help="drop corpus docs below this word count (measurement envelope)")
    ap.add_argument("--n-components", type=int, default=4,
                    help="PC axes to keep (bundled v1 references use 4)")
    ap.add_argument("--max-age-days", type=int, default=180,
                    help="recalibration policy: baseline age (days) beyond "
                         "which offline checks should flag it stale")
    ap.add_argument("--recalibration-note", default="",
                    help="free-text note persisted in recalibration_policy")
    ap.add_argument("--calibration-date", default=None,
                    help="ISO-8601 override of the build timestamp "
                         "(deterministic rebuilds); default: now, UTC")
    ap.add_argument("--no-cv", action="store_true",
                    help="skip the cross-validated null; persist the "
                         "resubstitution distribution instead (understates "
                         "spread — for debugging only)")
    ap.add_argument("--no-stability", action="store_true",
                    help="skip the jackknife stability block")
    ap.add_argument("--no-feature-quantiles", action="store_true",
                    help="skip the per-feature percentile grids")
    ap.add_argument("--readings-out", default=None,
                    help="optional JSONL of per-document flat features for your "
                         "own analysis")
    return build(ap.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
