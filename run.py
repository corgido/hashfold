#!/usr/bin/env python3
"""Entry point for running hashfold locally.

With no arguments: boots the stdlib HTTP server from
`instrument.serve.http` (default 0.0.0.0:8000, audit shape).

    python run.py                            # start the server
    python run.py path.md                    # emit() once on a file and print JSON
    python run.py path.md --uncertainty      # + per-feature bootstrap CIs

All measurement lives under the `instrument` package (the import
path is the API contract and is unchanged by the project rename);
see `instrument/serve/shape.py` for the request-handler surface.
The installed console script `hashfold` starts the same server.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path


def _emit_file(path: Path, *, uncertainty: bool = False) -> None:
    from instrument.emit import emit

    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        # Parity with the HTTP transport's 400 `invalid_utf8`: fail
        # loudly and cleanly instead of dumping a traceback.
        print(
            f"unreadable input: {path} is not valid UTF-8 "
            f"(byte offset {e.start})",
            file=sys.stderr,
        )
        sys.exit(2)
    emission = emit(text, input_bytes=raw)
    if not uncertainty:
        # No flag -> output stays byte-identical to the legacy CLI.
        print(json.dumps(asdict(emission), ensure_ascii=False, indent=2))
        return
    from instrument.reading.bootstrap import bootstrap_uncertainty

    # Seeded from the emission's own input_sha256 (the raw file bytes),
    # so the intervals are replayable from the file alone.
    block = bootstrap_uncertainty(
        text, seed=emission.metadata.input_sha256,
    )
    print(json.dumps(
        {"emission": asdict(emission), "uncertainty": block},
        ensure_ascii=False, indent=2,
    ))


def _run_server() -> None:
    from instrument.serve.http import main

    main()


def main() -> None:
    args = sys.argv[1:]
    uncertainty = "--uncertainty" in args
    args = [a for a in args if a != "--uncertainty"]
    if not args:
        if uncertainty:
            print("--uncertainty requires a file path", file=sys.stderr)
            sys.exit(1)
        _run_server()
        return
    path = Path(args[0])
    if not path.exists():
        print(f"file not found: {path}", file=sys.stderr)
        sys.exit(1)
    _emit_file(path, uncertainty=uncertainty)


if __name__ == "__main__":
    main()
