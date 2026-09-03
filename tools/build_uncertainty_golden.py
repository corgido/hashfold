"""build_uncertainty_golden — freeze bootstrap_uncertainty outputs.

For each `(name, source_path)` in `FIXTURES`, reads the source
file's RAW BYTES, derives `input_sha256` (the same provenance seed
the transports use), runs
`instrument.reading.bootstrap.bootstrap_uncertainty(text,
seed=input_sha256, b=GOLDEN_B)`, and writes canonical JSON to
`fixtures/uncertainty_golden/<name>.json`.

The golden pins the full determinism chain: bytes -> input_sha256 ->
DetRandom stream -> resample plan -> per-feature intervals. Any drift
means either a measurement regression or an intentional scheme bump.
`GOLDEN_B` is 50 (not the production default 200) to keep
regeneration and the byte-equal test fast; the block records its own
`b`, so the golden is self-describing.

Usage:
    python -m tools.build_uncertainty_golden            # regenerate
    python -m tools.build_uncertainty_golden --check    # verify no drift
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = REPO_ROOT / "fixtures" / "uncertainty_golden"

# Two cohort fixtures are enough to pin the scheme: journalism (many
# short paragraphs) and literary (long paragraphs) stress the
# paragraph-shape-preserving reassembly from both ends. Sources live
# in-tree under fixtures/source/; we store paths not copies.
_SRC = REPO_ROOT / "fixtures" / "source"
FIXTURES: list[tuple[str, Path]] = [
    ("journalism", _SRC / "journalism.md"),
    ("literary",   _SRC / "literary.md"),
]

GOLDEN_B = 50


def _generate_one(source_path: Path) -> dict:
    """Run bootstrap_uncertainty on a source file's raw bytes."""
    from instrument.reading.bootstrap import bootstrap_uncertainty

    raw = source_path.read_bytes()
    input_sha256 = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    return {
        # as_posix(): the golden is byte-compared on Windows too, where
        # str(Path) would flip the separators and fail the whole matrix
        # over a path spelling.
        "source": source_path.relative_to(REPO_ROOT).as_posix(),
        "input_sha256": input_sha256,
        "uncertainty": bootstrap_uncertainty(
            text, seed=input_sha256, b=GOLDEN_B,
        ),
    }


def _canonical_json(obj: dict) -> str:
    # bootstrap_uncertainty quantises every float through kernel
    # `q()` (non-finite -> None), so allow_nan=False is a pure guard.
    return json.dumps(
        obj, sort_keys=True, indent=2, ensure_ascii=False,
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
            "`python -m tools.build_uncertainty_golden`",
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
