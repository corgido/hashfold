"""build_reference — produce a reference JSON from readings + PCA.

    python -m tools.calibration.build_reference \
        --name llm_technical_prose --version v2 \
        --cohort llm_technical_prose \
        --scope "Calibration on in-repo technical docs" \
        --reliability exploratory
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READINGS = REPO_ROOT / "tools" / "calibration" / "out" / "readings.jsonl"
DEFAULT_PCA = REPO_ROOT / "tools" / "calibration" / "out" / "pca.json"
REFERENCES_DIR = REPO_ROOT / "instrument" / "routing" / "references"


def _percentiles(arr):
    return {
        "p05": float(np.percentile(arr, 5)),
        "p25": float(np.percentile(arr, 25)),
        "p50": float(np.percentile(arr, 50)),
        "p75": float(np.percentile(arr, 75)),
        "p95": float(np.percentile(arr, 95)),
    }


def _commit_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT, text=True,
        ).strip()
    except Exception:
        return "unknown"


def run(
    readings_path: Path,
    pca_path: Path,
    output: Path,
    name: str,
    version: str,
    cohort: str,
    scope: str,
    reliability: str,
    corpus_description: str,
) -> int:
    lines = readings_path.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(line) for line in lines]
    pca = json.loads(pca_path.read_text(encoding="utf-8"))

    if not records:
        print("no readings", file=sys.stderr)
        return 1

    feature_names = pca["feature_names"]
    zscore_mean = pca["zscore_mean"]
    zscore_std = pca["zscore_std"]
    loadings = pca["loadings"]
    pc_names = pca["pc_names"]

    n_docs = len(records)
    n_feats = len(feature_names)
    matrix = np.zeros((n_docs, n_feats))

    for row, r in enumerate(records):
        for col, feat in enumerate(feature_names):
            val = r["features"].get(feat)
            matrix[row, col] = val if val is not None else zscore_mean[feat]

    per_feature = {}
    for col, feat in enumerate(feature_names):
        vals = matrix[:, col]
        per_feature[feat] = {
            "mean": float(vals.mean()),
            "std": float(vals.std(ddof=0)),
            **_percentiles(vals),
        }

    z_matrix = np.zeros_like(matrix)
    for col, feat in enumerate(feature_names):
        std = zscore_std[feat]
        z_matrix[:, col] = (matrix[:, col] - zscore_mean[feat]) / (std if std > 0 else 1.0)

    pc_values = np.zeros((n_docs, len(pc_names)))
    for pc_idx, pc_name in enumerate(pc_names):
        pc_loadings = loadings[pc_name]
        for col, feat in enumerate(feature_names):
            weight = pc_loadings.get(feat, 0.0)
            pc_values[:, pc_idx] += z_matrix[:, col] * weight

    pc_centroid = {}
    pc_composites = {}
    for pc_idx, pc_name in enumerate(pc_names):
        vals = pc_values[:, pc_idx]
        pc_centroid[pc_name] = float(vals.mean())
        pc_composites[pc_name] = {
            "mean": float(vals.mean()),
            "std": float(vals.std(ddof=0)),
            **_percentiles(vals),
        }

    word_counts = [r["n_words"] for r in records]

    reference = {
        "name": name,
        "version": version,
        "status": "active",
        "register_cohort": cohort,
        "length_cohort": {
            "label": "mixed",
            "n_words_min": min(word_counts),
            "n_words_max": max(word_counts),
            "n_words_p25": int(np.percentile(word_counts, 25)),
            "n_words_median": int(np.percentile(word_counts, 50)),
            "n_words_p75": int(np.percentile(word_counts, 75)),
        },
        "scope_statement": scope,
        "calibration_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "corpus_description": corpus_description,
        "n": n_docs,
        "instrument_version": "0.7.0",
        "schema_version": "0.7.0",
        "commit_hash": _commit_hash(),
        "reliability": reliability,
        "per_feature": per_feature,
        "pc_centroid": pc_centroid,
        "pc_composites": pc_composites,
        "pc_loadings": {pc: dict(loadings[pc]) for pc in pc_names},
        "pc_zscore_mean": dict(zscore_mean),
        "pc_zscore_std": dict(zscore_std),
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(reference, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output} (n={n_docs}, {len(pc_names)} PCs, {reliability})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a reference distribution JSON.")
    ap.add_argument("--readings", type=Path, default=DEFAULT_READINGS)
    ap.add_argument("--pca", type=Path, default=DEFAULT_PCA)
    ap.add_argument("--name", required=True)
    ap.add_argument("--version", default="v2")
    ap.add_argument("--cohort", required=True)
    ap.add_argument("--scope", required=True)
    ap.add_argument("--reliability", default="exploratory",
                    choices=["exploratory", "production"])
    ap.add_argument("--corpus-description", default="")
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args(argv)

    output = args.output or (REFERENCES_DIR / f"{args.name}_{args.version}.json")
    return run(
        args.readings, args.pca, output,
        args.name, args.version, args.cohort, args.scope,
        args.reliability, args.corpus_description,
    )


if __name__ == "__main__":
    raise SystemExit(main())
