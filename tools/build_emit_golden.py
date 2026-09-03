"""build_emit_golden — freeze emit() outputs as byte-equal fixtures.

Runs `instrument.emit.emit(text)` on each fixture in
`tools.build_joint_golden.FIXTURES`, strips the wall-clock
`metadata.timestamp`, and writes canonical JSON to
`fixtures/emit_golden/<name>.json`.

These goldens are the regression surface for `emit()`. The
joint_golden JSONs validate the reading layer; the emit_golden
JSONs extend that to the full emission output.

Usage:
    python -m tools.build_emit_golden
    python -m tools.build_emit_golden --check
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from tools.build_joint_golden import FIXTURES

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "emit_golden"


def _normalise(obj):
    """JSON-safe: NaN -> None; tuples -> lists (already handled by asdict)."""
    if isinstance(obj, dict):
        return {k: _normalise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalise(v) for v in obj]
    if isinstance(obj, float) and obj != obj:
        return None
    return obj


def _canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _emit_one(source_path: Path) -> dict:
    from instrument.emit import emit  # lazy import
    text = source_path.read_text(encoding="utf-8")
    d = asdict(emit(text))
    d["metadata"]["timestamp"] = "GOLDEN"
    return _normalise(d)


def generate() -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name, source_path in FIXTURES:
        if not source_path.exists():
            print(f"MISSING: {source_path}", file=sys.stderr)
            return 1
        out = _emit_one(source_path)
        (GOLDEN_DIR / f"{name}.json").write_text(
            _canonical_json(out), encoding="utf-8",
        )
        print(f"wrote {GOLDEN_DIR.relative_to(REPO_ROOT)}/{name}.json")
    return 0


def check() -> int:
    drifted: list[str] = []
    for name, source_path in FIXTURES:
        if not source_path.exists():
            print(f"MISSING: {source_path}", file=sys.stderr)
            return 1
        expected = GOLDEN_DIR / f"{name}.json"
        if not expected.exists():
            print(f"MISSING GOLDEN: {expected}", file=sys.stderr)
            return 1
        regenerated = _canonical_json(_emit_one(source_path))
        committed = expected.read_text(encoding="utf-8")
        if regenerated != committed:
            drifted.append(name)
            print(f"DRIFT: {name}", file=sys.stderr)
    if drifted:
        print(
            f"{len(drifted)} emit golden(s) drifted — regenerate with "
            "`python -m tools.build_emit_golden`",
            file=sys.stderr,
        )
        return 1
    print(f"{len(FIXTURES)} emit goldens ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    return check() if args.check else generate()


if __name__ == "__main__":
    raise SystemExit(main())
