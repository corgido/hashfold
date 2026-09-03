"""CONTRACT — emit() matches its committed goldens byte-for-byte.

Each golden under `fixtures/emit_golden/*.json` was frozen by
`tools/build_emit_golden.py`. This test runs `emit()` on the same
source file, normalises NaN → None, sets `timestamp` to
"GOLDEN", and asserts byte-equal JSON.

This is the regression surface for the emit() output. The
joint_golden JSONs validate the reading layer; the emit_golden
JSONs extend that to the full emission.

If a golden fails, the fix is one of:

    1. Code regression — trace the drift back to the changed
       feature or detector.
    2. Intentional schema bump — regenerate with
       `python -m tools.build_emit_golden` and commit.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from tools.build_joint_golden import FIXTURES
from instrument.emit import emit

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "emit_golden"


def _normalise(obj):
    if isinstance(obj, dict):
        return {k: _normalise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalise(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name,source_path", FIXTURES)
def test_emit_matches_golden(name: str, source_path: Path) -> None:
    assert source_path.exists(), f"source missing: {source_path}"
    golden_path = GOLDEN_DIR / f"{name}.json"
    assert golden_path.exists(), f"golden missing: {golden_path}"

    text = source_path.read_text(encoding="utf-8")
    out = asdict(emit(text))
    out["metadata"]["timestamp"] = "GOLDEN"
    regenerated = _canonical_json(_normalise(out))
    committed = golden_path.read_text(encoding="utf-8")

    if regenerated != committed:
        new_parsed = json.loads(regenerated)
        old_parsed = json.loads(committed)
        mismatched = sorted(
            k for k in set(new_parsed) | set(old_parsed)
            if new_parsed.get(k) != old_parsed.get(k)
        )
        raise AssertionError(
            f"{name}: emit drift in top-level keys {mismatched}\n"
            "Regenerate with `python -m tools.build_emit_golden` "
            "if the drift is intentional."
        )
