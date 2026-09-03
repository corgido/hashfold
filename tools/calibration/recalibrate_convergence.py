"""recalibrate_convergence — compute new axis normalisation ranges.

Reads the JSONL from run_corpus, computes p05/p95 with 15%
symmetric buffer for each convergence axis, prints the values.

    python -m tools.calibration.recalibrate_convergence
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_READINGS = REPO_ROOT / "tools" / "calibration" / "out" / "readings.jsonl"

AXES = {
    "sfl_process_complexity": {
        "shaper_key": "sfl.process_proxy_entropy",
        "other_keys": [
            "sfl.pct_material", "sfl.pct_mental", "sfl.pct_relational",
            "sfl.pct_verbal", "sfl.pct_behavioral", "sfl.pct_existential",
        ],
        "other_reducer": "entropy_of_proportions",
    },
    "rst_contrast": {
        "shaper_key": "rst.contrast_marker_density",
        "other_keys": ["rst.contrast_density", "rst.concession_density"],
        "other_reducer": "sum",
    },
    "rst_elaboration": {
        "shaper_key": "rst.elaboration_marker_density",
        "other_keys": ["rst.elaboration_density"],
        "other_reducer": "sum",
    },
    "cohesion_repetition": {
        "shaper_key": "cohesion.lexical_repetition",
        "other_keys": ["coh.lexical_repetition_rate"],
        "other_reducer": "sum",
    },
    "register_modality": {
        "shaper_key": "register.modal_density",
        "other_keys": ["sfl.modal_density", "sfl.hedge_density"],
        "other_reducer": "sum",
    },
}

BUFFER = 0.15

import math

def _reduce(values: list[float], reducer: str) -> float:
    if reducer == "sum":
        return sum(v for v in values if v == v)
    if reducer == "entropy_of_proportions":
        clean = [v for v in values if v == v and v > 0]
        if not clean:
            return 0.0
        return -sum(p * math.log2(p) for p in clean if p > 0)
    return sum(values)


def run(readings_path: Path) -> int:
    lines = readings_path.read_text(encoding="utf-8").strip().split("\n")
    records = [json.loads(line) for line in lines]

    if not records:
        print("no readings", file=sys.stderr)
        return 1

    print(f"Computing convergence ranges from {len(records)} documents\n")
    print("AXES = {")

    for axis_name, axis_def in AXES.items():
        shaper_vals = []
        other_vals = []

        for r in records:
            feats = r["features"]
            sv = feats.get(axis_def["shaper_key"])
            if sv is None or (isinstance(sv, float) and sv != sv):
                continue
            shaper_vals.append(sv)

            ov_parts = [feats.get(k) for k in axis_def["other_keys"]]
            if any(v is None or (isinstance(v, float) and v != v) for v in ov_parts):
                continue
            other_vals.append(_reduce(ov_parts, axis_def["other_reducer"]))

        if not shaper_vals or not other_vals:
            print(f'    # "{axis_name}": insufficient data ({len(shaper_vals)} shaper, {len(other_vals)} other)')
            continue

        sa = np.array(shaper_vals)
        oa = np.array(other_vals)

        s05, s95 = np.percentile(sa, 5), np.percentile(sa, 95)
        o05, o95 = np.percentile(oa, 5), np.percentile(oa, 95)

        s_span = s95 - s05
        o_span = o95 - o05

        s_lo = round(s05 - BUFFER * s_span, 4)
        s_hi = round(s95 + BUFFER * s_span, 4)
        o_lo = round(o05 - BUFFER * o_span, 4)
        o_hi = round(o95 + BUFFER * o_span, 4)

        print(f'    "{axis_name}": {{')
        print(f'        "shaper_key": "{axis_def["shaper_key"]}",')
        print(f'        "shaper_range": ({s_lo}, {s_hi}),')
        print(f'        "other_keys": {axis_def["other_keys"]},')
        print(f'        "other_reducer": "{axis_def["other_reducer"]}",')
        print(f'        "other_range": ({o_lo}, {o_hi}),')
        print(f'    }},')

    print("}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--readings", type=Path, default=DEFAULT_READINGS)
    args = ap.parse_args(argv)
    return run(args.readings)


if __name__ == "__main__":
    raise SystemExit(main())
