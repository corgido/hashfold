"""CONTRACT: every stored record rehashes offline to its own
content_sha256 / reading_sha256 — including the trajectory surface
(A-prime) and degenerate inputs.

`content_sha256` covers canonical_json({"reading", "distances"}) with
`reading.ts` dropped; the reading now embeds the per-slice trajectory,
so no surfaced trajectory number can move without moving the attesting
hashes. A tampered trajectory value must be detectable by offline
recomputation.
"""

from __future__ import annotations

import copy
import hashlib
import json

from instrument.serve.shape import handle_json

_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)
_LONG = _PARA * 8
_BELOW_ENVELOPE = "Too short to measure."
_DEGENERATE = ("spam " * 400).strip()   # unprojectable-class input


def _canonical_json(obj) -> str:
    from instrument.kernel.quantize import canonical_json
    return canonical_json(obj)


def _audit_record(text: str) -> dict:
    status, body = handle_json("POST", "/?shape=audit", text)
    assert status == 200, body
    return json.loads(body)


def _rehash(rec: dict) -> tuple[str, str]:
    reading = dict(rec["reading"])
    reading.pop("ts", None)
    content = hashlib.sha256(
        _canonical_json(
            {"reading": reading, "distances": rec["distances"]}
        ).encode("utf-8")
    ).hexdigest()
    reading_h = hashlib.sha256(
        _canonical_json(reading).encode("utf-8")
    ).hexdigest()
    return content, reading_h


def test_audit_record_rehashes_for_every_input_class():
    for text in (_LONG, _BELOW_ENVELOPE, _DEGENERATE):
        rec = _audit_record(text)
        content, reading_h = _rehash(rec)
        assert rec["metadata"]["content_sha256"] == content
        assert rec["metadata"]["reading_sha256"] == reading_h


def test_audit_reading_carries_trajectory():
    rec = _audit_record(_LONG)
    traj = rec["reading"]["trajectory"]
    assert traj["n_slices"] >= 1
    assert set(traj["features"]) == {
        "lexical_novelty", "sentence_length_variance",
        "modal_density", "negation_density",
    }


def test_tampered_trajectory_value_fails_offline_rehash():
    rec = _audit_record(_LONG)
    tampered = copy.deepcopy(rec)
    series = tampered["reading"]["trajectory"]["features"]["modal_density"]
    assert series, "expected at least one slice"
    series[0] = (series[0] or 0.0) + 1.0
    content, reading_h = _rehash(tampered)
    assert content != tampered["metadata"]["content_sha256"]
    assert reading_h != tampered["metadata"]["reading_sha256"]


def test_full_shape_record_rehashes_too():
    status, body = handle_json("POST", "/?shape=full", _LONG)
    assert status == 200
    rec = json.loads(body)
    reading = dict(rec["reading"])
    reading.pop("ts", None)
    distances = (
        rec["emission"]["register"]["evidence"]["distances_to_all_references"]
    )
    recomputed = hashlib.sha256(
        _canonical_json(
            {"reading": reading, "distances": distances}
        ).encode("utf-8")
    ).hexdigest()
    assert rec["emission"]["metadata"]["content_sha256"] == recomputed
