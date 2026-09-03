"""build_joint_golden — freeze joint_reading outputs for regression.

For each `(name, source_path)` in `FIXTURES`, reads the source
text, runs `instrument.reading.joint.joint_reading(text)`, strips
the `ts` field, and writes canonical JSON to
`fixtures/joint_golden/<name>.json`.

Usage:
    python -m tools.build_joint_golden            # regenerate
    python -m tools.build_joint_golden --check    # verify no drift
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "joint_golden"

# Fixtures cover the five reference cohorts (academic, dialogue,
# journalism, literary, llm_technical_prose) plus targeted edge
# cases (below-envelope, structural-table fallback, malformed-fence
# recovery, unicode quote balance). Sources all live in-tree under
# fixtures/source/; we store paths not copies so fixtures do not
# duplicate storage.
_SRC = REPO_ROOT / "fixtures" / "source"
FIXTURES: list[tuple[str, Path]] = [
    # Cohort fixtures — one per reference distribution.
    ("academic_short",     _SRC / "academic_short.md"),
    ("academic_long",      _SRC / "academic_long.md"),
    ("dialogue",           _SRC / "dialogue.md"),
    ("journalism",         _SRC / "journalism.md"),
    ("literary",           _SRC / "literary.md"),
    ("llm_technical",      _SRC / "llm_technical.md"),
    # Adversarial fixtures — exercise previously-fixed measurement bugs.
    ("contraction_heavy",  _SRC / "contraction_heavy.md"),
    ("curly_contractions", _SRC / "curly_contractions.md"),
    ("discourse_heavy",    _SRC / "discourse_heavy.md"),
    # Edge-case fixtures — non-cohort paths the pipeline must handle.
    ("below_envelope",     _SRC / "below_envelope.md"),
    ("structural_table",   _SRC / "structural_table.md"),
    ("malformed_fence",    _SRC / "malformed_fence.md"),
    ("unicode_quotes",     _SRC / "unicode_quotes.md"),
    ("nonlatin_cyrillic",  _SRC / "nonlatin_cyrillic.md"),
]


def _generate_one(source_path: Path) -> dict:
    """Run joint_reading on a source file; strip volatile fields."""
    from instrument.reading.joint import joint_reading

    text = source_path.read_text(encoding="utf-8")
    out = joint_reading(text)
    # `ts` is wall-clock; freeze for byte-comparison.
    out["ts"] = "GOLDEN"
    return out


def _json_safe(obj):
    """Map non-finite floats (NaN/inf) to None so golden files are valid
    JSON. Matches kernel.quantize.q's wire/hash behaviour; kept local and
    precision-preserving so this touches only the NaN serialisation, not
    float values."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (obj != obj or math.isinf(obj)):
        return None
    return obj


def _canonical_json(obj: dict) -> str:
    return json.dumps(
        _json_safe(obj), sort_keys=True, indent=2, ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def generate() -> int:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name, source_path in FIXTURES:
        if not source_path.exists():
            print(f"MISSING: {source_path}", file=sys.stderr)
            return 1
        out = _generate_one(source_path)
        (GOLDEN_DIR / f"{name}.json").write_text(_canonical_json(out), encoding="utf-8")
        print(f"wrote {GOLDEN_DIR.relative_to(REPO_ROOT)}/{name}.json")
    return 0


def check() -> int:
    drifted: list[str] = []
    for name, source_path in FIXTURES:
        if not source_path.exists():
            print(f"MISSING: {source_path}", file=sys.stderr)
            return 1
        expected_path = GOLDEN_DIR / f"{name}.json"
        if not expected_path.exists():
            print(f"MISSING GOLDEN: {expected_path}", file=sys.stderr)
            return 1
        regenerated = _canonical_json(_generate_one(source_path))
        committed = expected_path.read_text(encoding="utf-8")
        if regenerated != committed:
            drifted.append(name)
            print(f"DRIFT: {name}", file=sys.stderr)
    if drifted:
        print(
            f"{len(drifted)} golden(s) drifted — regenerate with "
            "`python -m tools.build_joint_golden`",
            file=sys.stderr,
        )
        return 1
    print(f"{len(FIXTURES)} goldens ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    return check() if args.check else generate()


if __name__ == "__main__":
    raise SystemExit(main())
