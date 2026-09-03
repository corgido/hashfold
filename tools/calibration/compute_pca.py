"""compute_pca — derive z-score params and PCA from corpus readings.

Reads the JSONL from run_corpus, computes per-feature z-score
parameters and PCA loadings (5 components), writes pca.json.

    python -m tools.calibration.compute_pca
    python -m tools.calibration.compute_pca --readings out/readings.jsonl --n-components 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READINGS = REPO_ROOT / "tools" / "calibration" / "out" / "readings.jsonl"
DEFAULT_OUTPUT = REPO_ROOT / "tools" / "calibration" / "out" / "pca.json"


def run(readings_path: Path, output: Path, n_components: int = 5,
        max_nan_ratio: float = 0.2) -> int:
    lines = readings_path.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(line) for line in lines]

    if not records:
        print("no readings found", file=sys.stderr)
        return 1

    all_features = set()
    for r in records:
        all_features.update(r["features"].keys())
    feature_names = sorted(all_features)

    n_docs = len(records)
    n_feats = len(feature_names)
    feat_idx = {name: i for i, name in enumerate(feature_names)}

    matrix = np.full((n_docs, n_feats), np.nan)
    for row, r in enumerate(records):
        for name, val in r["features"].items():
            if val is not None:
                matrix[row, feat_idx[name]] = val

    nan_ratio = np.isnan(matrix).sum(axis=0) / n_docs
    keep_mask = nan_ratio <= max_nan_ratio
    kept_names = [feature_names[i] for i in range(n_feats) if keep_mask[i]]
    matrix = matrix[:, keep_mask]

    if not kept_names:
        print("no features survived NaN filtering", file=sys.stderr)
        return 1

    col_means = np.nanmean(matrix, axis=0)
    for col in range(matrix.shape[1]):
        nan_rows = np.isnan(matrix[:, col])
        matrix[nan_rows, col] = col_means[col]

    means = matrix.mean(axis=0)
    stds = matrix.std(axis=0, ddof=0)
    stds[stds == 0] = 1.0

    z_matrix = (matrix - means) / stds

    actual_components = min(n_components, min(z_matrix.shape) - 1)
    if actual_components < 1:
        print(f"need at least 2 documents for PCA, got {n_docs}", file=sys.stderr)
        return 1

    U, S, Vt = np.linalg.svd(z_matrix, full_matrices=False)
    total_var = (S ** 2).sum()
    explained = (S[:actual_components] ** 2) / total_var

    loadings = {}
    for pc_idx in range(actual_components):
        pc_name = f"pc{pc_idx + 1}"
        loadings[pc_name] = {
            kept_names[j]: float(Vt[pc_idx, j])
            for j in range(len(kept_names))
        }

    result = {
        "n_documents": n_docs,
        "n_features": len(kept_names),
        "feature_names": kept_names,
        "zscore_mean": {kept_names[i]: float(means[i]) for i in range(len(kept_names))},
        "zscore_std": {kept_names[i]: float(stds[i]) for i in range(len(kept_names))},
        "n_components": actual_components,
        "explained_variance_ratio": [float(e) for e in explained],
        "total_explained": float(explained.sum()),
        "pc_names": [f"pc{i+1}" for i in range(actual_components)],
        "loadings": loadings,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"PCA: {n_docs} docs × {len(kept_names)} features → {actual_components} components")
    print(f"  explained variance: {[f'{e:.1%}' for e in explained]}")
    print(f"  total explained: {explained.sum():.1%}")
    print(f"wrote {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compute PCA from corpus readings.")
    ap.add_argument("--readings", type=Path, default=DEFAULT_READINGS)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    ap.add_argument("--n-components", type=int, default=5)
    args = ap.parse_args(argv)
    return run(args.readings, args.output, args.n_components)


if __name__ == "__main__":
    raise SystemExit(main())
