"""CONTRACT: the CLI transport (run.py).

The CLI is a transport, not a second measurement path:

- `input_sha256` is the SHA256 of the file's RAW BYTES (before any
  decode or newline translation), so a record captured via the CLI
  and one captured via HTTP agree on provenance for the same bytes.
- The measurement itself is transport-invariant: a CRLF file and its
  LF twin yield the same `reading_sha256` / `content_sha256` (the
  canonicaliser owns newline semantics), while their `input_sha256`
  honestly differ (different raw bytes).
- Undecodable input fails loudly and cleanly: nonzero exit, a
  one-line diagnostic on stderr, no traceback (parity with the HTTP
  400 `invalid_utf8` path).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
_RUN_PY = _PKG_ROOT / "run.py"

_PROSE = (
    "The committee reviewed the proposal in detail. Several members "
    "raised concerns about the timeline, but the chair argued that the "
    "schedule was achievable.\n\nAfter a long discussion the vote was "
    "taken. The proposal passed with a clear majority, and the working "
    "group was asked to begin immediately.\n"
)


def _run_cli(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_RUN_PY), str(path)],
        capture_output=True,
        text=True,
        cwd=str(_PKG_ROOT),
        timeout=120,
    )


def test_valid_utf8_emits_json(tmp_path):
    f = tmp_path / "doc.md"
    f.write_bytes(_PROSE.encode("utf-8"))
    proc = _run_cli(f)
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["metadata"]["input_sha256"] == hashlib.sha256(
        f.read_bytes()
    ).hexdigest()


def test_non_utf8_fails_loudly_without_traceback(tmp_path):
    f = tmp_path / "bad.md"
    f.write_bytes(b"\xff\xfe not utf-8 \x9d\x81")
    proc = _run_cli(f)
    assert proc.returncode != 0
    assert "not valid UTF-8" in proc.stderr
    assert "Traceback" not in proc.stderr


def test_crlf_and_lf_files_measure_identically_with_honest_input_hash(tmp_path):
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(_PROSE.encode("utf-8"))
    crlf.write_bytes(_PROSE.replace("\n", "\r\n").encode("utf-8"))

    md_lf = json.loads(_run_cli(lf).stdout)["metadata"]
    md_crlf = json.loads(_run_cli(crlf).stdout)["metadata"]

    # Raw bytes differ -> provenance hashes differ (honestly).
    assert md_lf["input_sha256"] != md_crlf["input_sha256"]
    assert md_crlf["input_sha256"] == hashlib.sha256(
        crlf.read_bytes()
    ).hexdigest()
    # The measurement is newline-convention invariant.
    assert md_lf["reading_sha256"] == md_crlf["reading_sha256"]
    assert md_lf["content_sha256"] == md_crlf["content_sha256"]
