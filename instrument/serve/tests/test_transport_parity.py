"""CONTRACT: transport parity (T-XPORT, closed in 0.9.1).

The same raw document bytes must produce the same `input_sha256` AND
the same `reading_sha256` whether they arrive via the HTTP transport
(`serve.shape.handle` with `body_bytes`) or the CLI/library path
(`emit(text, input_bytes=raw)`). Before 0.9.1 the CLI collapsed CRLF
while HTTP preserved it, so one document had two provenance
identities depending on transport.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict

from instrument.emit import emit
from instrument.serve.shape import handle

_PROSE = (
    "The committee reviewed the proposal in detail. Several members "
    "raised concerns about the timeline, but the chair argued that the "
    "schedule was achievable.\r\n\r\nAfter a long discussion the vote "
    "was taken. The proposal passed with a clear majority, and the "
    "working group was asked to begin immediately.\r\n"
)
_RAW = _PROSE.encode("utf-8")


def _cli_metadata() -> dict:
    # run.py's exact sequence: read bytes, strict-decode, emit.
    text = _RAW.decode("utf-8")
    return asdict(emit(text, input_bytes=_RAW))["metadata"]


def _http_metadata() -> dict:
    # http.py's exact sequence: decode (no newline translation), handle.
    body = _RAW.decode("utf-8")
    status, payload = handle(
        "POST", "/?shape=audit", body, body_bytes=_RAW,
    )
    assert status == 200, payload
    return payload["metadata"]


def test_same_bytes_same_provenance_across_transports():
    cli = _cli_metadata()
    http = _http_metadata()
    expected_input = hashlib.sha256(_RAW).hexdigest()
    assert cli["input_sha256"] == expected_input
    assert http["input_sha256"] == expected_input
    assert cli["reading_sha256"] == http["reading_sha256"]
    assert cli["content_sha256"] == http["content_sha256"]
    assert cli["reproducibility_hash"] == http["reproducibility_hash"]


def test_library_str_fallback_documented_semantics():
    # Library callers passing only a str get sha256(text.encode("utf-8")).
    text = _RAW.decode("utf-8")
    md = asdict(emit(text))["metadata"]
    assert md["input_sha256"] == hashlib.sha256(text.encode("utf-8")).hexdigest()
