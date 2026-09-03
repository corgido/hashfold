"""run_corpus — measure a directory of markdown files.

Runs joint_reading() on every *.md file in a directory tree,
extracts the flat feature dict (shaper + extended + stylometry),
and writes one JSON object per line to a JSONL output file.

    python -m tools.calibration.run_corpus --corpus-dir .
    python -m tools.calibration.run_corpus --corpus-dir /path/to/corpus --output out/readings.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _flat_features(jr: dict) -> dict:
    out: dict = {}
    out.update(jr["shaper"]["features"])
    out.update(jr["other_shaper"]["features"])
    out.update(jr.get("stylometry", {}).get("features", {}))
    return out


def run(corpus_dir: Path, output: Path, min_words: int = 150) -> int:
    from instrument.reading.joint import joint_reading

    corpus_dir = corpus_dir.resolve()
    md_files = sorted(corpus_dir.rglob("*.md"))
    md_files = [f for f in md_files if ".git" not in f.parts]

    if not md_files:
        print(f"no *.md files found under {corpus_dir}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    n_skipped = 0

    with output.open("w", encoding="utf-8") as fh:
        for path in md_files:
            text = path.read_text(encoding="utf-8")
            try:
                jr = joint_reading(text)
            except Exception as exc:
                print(f"SKIP {path.name}: {exc}", file=sys.stderr)
                n_skipped += 1
                continue

            n_words = jr["n_words"]["shaper"]
            if n_words < min_words:
                n_skipped += 1
                continue

            features = _flat_features(jr)

            nan_features = [k for k, v in features.items()
                           if isinstance(v, float) and v != v]
            if len(nan_features) > len(features) * 0.5:
                n_skipped += 1
                continue

            clean_features = {
                k: (None if isinstance(v, float) and v != v else v)
                for k, v in features.items()
            }

            record = {
                "source": str(path.relative_to(corpus_dir)),
                "n_words": n_words,
                "features": clean_features,
            }
            fh.write(json.dumps(record, sort_keys=True) + "\n")
            n_written += 1

    print(f"wrote {n_written} readings to {output} ({n_skipped} skipped)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run joint_reading over a corpus of markdown files.")
    ap.add_argument("--corpus-dir", type=Path, default=REPO_ROOT,
                    help="Root directory to scan for *.md files")
    ap.add_argument("--output", type=Path,
                    default=REPO_ROOT / "tools" / "calibration" / "out" / "readings.jsonl")
    ap.add_argument("--min-words", type=int, default=150)
    args = ap.parse_args(argv)
    return run(args.corpus_dir, args.output, args.min_words)


if __name__ == "__main__":
    raise SystemExit(main())
