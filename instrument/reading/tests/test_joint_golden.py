"""CONTRACT — byte-equal parity between joint_reading and the
committed goldens.

Each golden under `fixtures/joint_golden/*.json` is the canonical
joint_reading output for the corresponding source markdown with
the `ts` field replaced by `"GOLDEN"`. This test reproduces the
output and asserts byte-equal JSON.

If any golden fails, the fix is one of:
  1. Code regression — trace the drift back to the changed module.
  2. Intentional schema bump — regenerate goldens with
     `python -m tools.build_joint_golden` and commit.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.build_joint_golden import FIXTURES
from instrument.reading.joint import joint_reading

GOLDEN_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "joint_golden"


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name,source_path", FIXTURES)
def test_joint_reading_matches_golden(name: str, source_path: Path) -> None:
    assert source_path.exists(), f"source missing: {source_path}"
    golden_path = GOLDEN_DIR / f"{name}.json"
    assert golden_path.exists(), f"golden missing: {golden_path}"

    text = source_path.read_text(encoding="utf-8")
    new = joint_reading(text)
    new["ts"] = "GOLDEN"
    regenerated = _canonical_json(new)
    committed = golden_path.read_text(encoding="utf-8")

    if regenerated != committed:
        # Show a concrete diff on mismatch — compare top-level keys first.
        new_parsed = json.loads(regenerated)
        old_parsed = json.loads(committed)
        mismatches: list[str] = []
        for key in sorted(set(new_parsed.keys()) | set(old_parsed.keys())):
            if new_parsed.get(key) != old_parsed.get(key):
                mismatches.append(key)
        raise AssertionError(
            f"{name}: drift in keys {mismatches}\n"
            "Regenerate with `python -m tools.build_joint_golden` "
            "if the drift is intentional."
        )
