"""CONTRACT — byte-equal parity between bootstrap_uncertainty and the
committed goldens.

Each golden under `fixtures/uncertainty_golden/*.json` is the
canonical `{"source", "input_sha256", "uncertainty"}` record for the
corresponding source file at `GOLDEN_B` replicates, seeded from the
file's raw-byte `input_sha256`. This test reproduces the record and
asserts byte-equal JSON — pinning the whole determinism chain:
bytes -> seed -> DetRandom stream -> resample plan -> intervals.

If a golden fails, the fix is one of:
  1. Code regression — trace the drift back to the changed module.
  2. Intentional scheme bump — regenerate goldens with
     `python -m tools.build_uncertainty_golden` and commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_uncertainty_golden import FIXTURES, _canonical_json, _generate_one

GOLDEN_DIR = (
    Path(__file__).resolve().parents[3] / "fixtures" / "uncertainty_golden"
)


@pytest.mark.parametrize("name,source_path", FIXTURES)
def test_uncertainty_matches_golden(name: str, source_path: Path) -> None:
    assert source_path.exists(), f"source missing: {source_path}"
    golden_path = GOLDEN_DIR / f"{name}.json"
    assert golden_path.exists(), f"golden missing: {golden_path}"

    regenerated = _canonical_json(_generate_one(source_path))
    committed = golden_path.read_text(encoding="utf-8")

    if regenerated != committed:
        # Show a concrete diff on mismatch — compare per-feature first.
        new_parsed = json.loads(regenerated)
        old_parsed = json.loads(committed)
        new_feats = new_parsed.get("uncertainty", {}).get("features", {})
        old_feats = old_parsed.get("uncertainty", {}).get("features", {})
        mismatches = [
            k for k in sorted(set(new_feats) | set(old_feats))
            if new_feats.get(k) != old_feats.get(k)
        ]
        raise AssertionError(
            f"{name}: drift in features {mismatches}\n"
            "Regenerate with `python -m tools.build_uncertainty_golden` "
            "if the drift is intentional."
        )
