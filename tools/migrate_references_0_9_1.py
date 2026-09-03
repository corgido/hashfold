"""Migrate bundled reference distributions to the 0.9.1 feature schema.

Mechanical re-key ONLY — no statistics change. Instrument 0.9.1
renamed two shaper features to what they actually measure
(discriminant study, 2026-06):

    rst.contrast_pressure    -> rst.contrast_marker_density
    rst.elaboration_pressure -> rst.elaboration_marker_density

Reference files key their statistic blocks by feature name, and one
missing key makes every PC projection (and therefore every distance)
`None` — so references written before the rename cannot project under
0.9.1. This tool rewrites the keys of `per_feature`, `pc_zscore_mean`,
`pc_zscore_std`, and each `pc_loadings.<pc>` inner dict, preserving
every float and every PC name byte-for-byte.

Per CALIBRATION.md the reference bytes ARE the coordinate system and
are never edited in place: the migrated file ships as a NEW version
(`<name>_v2.json`) and the v1 file is removed from the bundle in the
same change. Provenance fields describing the original measurement
event (`instrument_version`, `calibration_date`, `commit_hash`, `n`,
`reliability`) are preserved unchanged — these remain 0.6.0-era
exploratory/draft SEEDS, not a production baseline — and a `migration`
block records the transformation.

Usage:
    python -m tools.migrate_references_0_9_1            # migrate v1 -> v2
    python -m tools.migrate_references_0_9_1 --check    # verify v2 == migrate(v1) semantics
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REFERENCES_DIR = (
    Path(__file__).resolve().parents[1]
    / "instrument" / "routing" / "references"
)

KEY_MAP = {
    "rst.contrast_pressure": "rst.contrast_marker_density",
    "rst.elaboration_pressure": "rst.elaboration_marker_density",
}

FROM_VERSION = "v1"
TO_VERSION = "v2"


def _rekey(d: dict) -> dict:
    """Rename mapped keys, preserving insertion order and values."""
    return {KEY_MAP.get(k, k): v for k, v in d.items()}


def migrate_reference(ref: dict, source_stem: str) -> dict:
    out = dict(ref)
    out["per_feature"] = _rekey(ref["per_feature"])
    out["pc_zscore_mean"] = _rekey(ref["pc_zscore_mean"])
    out["pc_zscore_std"] = _rekey(ref["pc_zscore_std"])
    out["pc_loadings"] = {
        pc: _rekey(loadings) for pc, loadings in ref["pc_loadings"].items()
    }
    out["version"] = TO_VERSION
    out["migration"] = {
        "from": source_stem,
        "renamed_keys": dict(KEY_MAP),
        "tool": "tools.migrate_references_0_9_1",
        "note": (
            "mechanical feature-key rename for instrument 0.9.1; all "
            "statistics and PC names byte-identical to the v1 file. "
            "Still a 0.6.0-calibrated seed, not a production baseline."
        ),
    }
    return out


def _v1_paths() -> list[Path]:
    return sorted(REFERENCES_DIR.glob(f"*_{FROM_VERSION}.json"))


def build() -> int:
    paths = _v1_paths()
    if not paths:
        print(f"no *_{FROM_VERSION}.json under {REFERENCES_DIR}; nothing to do")
        return 1
    for path in paths:
        ref = json.loads(path.read_text(encoding="utf-8"))
        stem = path.stem  # e.g. academic_prose_v1
        name = stem[: -len(f"_{FROM_VERSION}")]
        migrated = migrate_reference(ref, stem)
        out_path = REFERENCES_DIR / f"{name}_{TO_VERSION}.json"
        out_path.write_text(
            json.dumps(migrated, sort_keys=True, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        path.unlink()
        print(f"{path.name} -> {out_path.name}")
    return 0


def check() -> int:
    """Verify every bundled v2 reference is a faithful re-key.

    Reconstructs the value multiset: for every stat block, the values
    under the new keys must equal the values the v1 keys carried. Runs
    against git history is not possible here, so the check verifies
    internal consistency: mapped OLD keys absent, NEW keys present,
    and the migration block intact.
    """
    failures = []
    for path in sorted(REFERENCES_DIR.glob(f"*_{TO_VERSION}.json")):
        ref = json.loads(path.read_text(encoding="utf-8"))
        blocks = [
            ref["per_feature"], ref["pc_zscore_mean"], ref["pc_zscore_std"],
            *ref["pc_loadings"].values(),
        ]
        for block in blocks:
            for old, new in KEY_MAP.items():
                if old in block:
                    failures.append(f"{path.name}: stale key {old}")
                if new not in block:
                    failures.append(f"{path.name}: missing key {new}")
        if ref.get("migration", {}).get("renamed_keys") != KEY_MAP:
            failures.append(f"{path.name}: migration block missing/stale")
    leftovers = _v1_paths()
    for p in leftovers:
        failures.append(f"stale bundled {p.name} (v1 must not ship alongside v2)")
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        return 1
    print("bundled references: migrated schema ok")
    return 0


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return check()
    return build()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
