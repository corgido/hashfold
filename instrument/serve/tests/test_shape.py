"""CONTRACTS for the pure request handler + response-shape filter."""

from __future__ import annotations

import hashlib
import json
from instrument.kernel.quantize import canonical_json
from pathlib import Path

import pytest

from instrument.config import Config, DEFAULT_CONFIG
from instrument.reading.bootstrap import SCHEME as BOOTSTRAP_SCHEME
from instrument.serve.shape import (
    VALID_INCLUDES,
    VALID_SHAPES,
    handle,
    handle_json,
    shape_response,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def long_text() -> str:
    return (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text(encoding="utf-8")


def test_valid_shapes():
    assert VALID_SHAPES == {"full", "flags_only", "reading_only", "compact", "audit"}


def test_valid_includes():
    assert VALID_INCLUDES == {"sfl_trace", "uncertainty"}


def test_unknown_include_returns_400(long_text):
    status, payload = handle("POST", "/?shape=audit&include=nope", long_text)
    assert status == 400
    assert "unknown include" in payload["error"]


def test_sfl_trace_attached_to_audit_when_requested(long_text):
    status, payload = handle(
        "POST", "/?shape=audit&include=sfl_trace", long_text,
    )
    assert status == 200
    assert "sfl_trace" in payload
    trace = payload["sfl_trace"]
    assert "tokens" in trace
    assert "existential" in trace
    assert "summary" in trace
    assert len(trace["tokens"]) > 0


def test_sfl_trace_not_attached_to_compact(long_text):
    status, payload = handle(
        "POST", "/?shape=compact&include=sfl_trace", long_text,
    )
    assert status == 200
    # compact ignores sfl_trace include.
    assert "sfl_trace" not in payload


# ---- ?include=uncertainty -------------------------------------------------

# Small b keeps the bootstrap cheap in tests; the block records it.
_UNC_CFG = Config(bootstrap_b=8)


@pytest.mark.parametrize("shape", ["audit", "full"])
def test_uncertainty_attached_to_audit_and_full(long_text, shape):
    status, payload = handle(
        "POST", f"/?shape={shape}&include=uncertainty", long_text, _UNC_CFG,
    )
    assert status == 200
    assert "uncertainty" in payload
    block = payload["uncertainty"]
    assert block["method"] == BOOTSTRAP_SCHEME
    assert block["b"] == 8  # threaded from Config.bootstrap_b
    assert block["features"]
    # Seeded from the emission's provenance hash.
    metadata = (
        payload["metadata"] if shape == "audit"
        else payload["emission"]["metadata"]
    )
    assert block["seed"] == metadata["input_sha256"]


@pytest.mark.parametrize("shape", ["flags_only", "compact", "reading_only"])
def test_uncertainty_not_attached_to_other_shapes(long_text, shape):
    status, payload = handle(
        "POST", f"/?shape={shape}&include=uncertainty", long_text, _UNC_CFG,
    )
    assert status == 200
    # Mirrors sfl_trace semantics: non-record shapes ignore the include.
    assert "uncertainty" not in payload


def test_uncertainty_rides_outside_the_hash_chain(long_text):
    """The hash-chain guarantee: content_sha256 / reproducibility_hash
    are computed inside emit, so the opt-in uncertainty block cannot
    perturb them — assert, don't assume."""
    _, without = handle("POST", "/?shape=audit", long_text, _UNC_CFG)
    _, with_unc = handle(
        "POST", "/?shape=audit&include=uncertainty", long_text, _UNC_CFG,
    )
    assert "uncertainty" not in without
    assert "uncertainty" in with_unc
    for field in ("content_sha256", "reproducibility_hash", "input_sha256",
                  "reading_sha256"):
        assert without["metadata"][field] == with_unc["metadata"][field]


def test_audit_shape_returns_pure_measurement(long_text):
    status, payload = handle("POST", "/?shape=audit", long_text)
    assert status == 200
    # Audit shape returns only reading + distances + metadata.
    assert set(payload.keys()) == {"reading", "distances", "metadata"}
    # No inference layer (no flags, no register label, no coherence band).
    assert "flags" not in payload
    assert "register" not in payload
    assert "coherence" not in payload
    # Distances list contains every bundled reference.
    distances = payload["distances"]
    assert isinstance(distances, list)
    assert len(distances) == 5
    for record in distances:
        # 0.10.0: records carry the mid-rank percentile against that
        # reference's persisted null distribution (None on the bundled
        # seeds, which persist none).
        assert set(record.keys()) == {"name", "version", "distance", "percentile"}
        assert record["percentile"] is None  # seeds carry no null
    # Reading carries the raw feature dicts.
    assert "shaper" in payload["reading"]
    assert "other_shaper" in payload["reading"]
    assert "convergence" in payload["reading"]
    # Metadata carries reproducibility_hash and provenance.
    md = payload["metadata"]
    assert md["reproducibility_hash"]
    assert md["input_sha256"]
    assert md["lexicon_version"]
    assert md["catalog_sha256"]
    assert md["distance_method"] == "feature_zscore_l2"


def test_get_health_returns_ok():
    status, payload = handle("GET", "/health", "")
    assert status == 200
    assert payload == {"status": "ok"}


def test_non_post_returns_405():
    status, payload = handle("DELETE", "/", "body")
    assert status == 405
    assert payload["error"] == "POST only"


def test_empty_body_returns_400():
    status, payload = handle("POST", "/", "")
    assert status == 400
    assert "empty" in payload["error"]


def test_unknown_shape_returns_400(long_text):
    status, payload = handle("POST", "/?shape=bogus", long_text)
    assert status == 400
    assert "bogus" in payload["error"]


def test_max_words_cap_returns_413(long_text):
    tiny_cap = Config(max_words=100)
    status, payload = handle("POST", "/", long_text, tiny_cap)
    assert status == 413
    assert payload["error"] == "size_cap_exceeded"
    assert payload["max_words"] == 100
    assert payload["n_words"] > 100


def test_max_words_zero_means_unlimited(long_text):
    unlimited = Config(max_words=0, response_shape="flags_only")
    status, _ = handle("POST", "/", long_text, unlimited)
    assert status == 200


def test_default_shape_is_audit(long_text):
    status, payload = handle("POST", "/", long_text)
    assert status == 200
    assert "reading" in payload
    assert "metadata" in payload


def test_full_shape_returns_emission_and_reading(long_text):
    cfg = Config(response_shape="full")
    status, payload = handle("POST", "/", long_text, cfg)
    assert status == 200
    assert "emission" in payload
    assert "reading" in payload
    assert payload["reading"]["schema_version"] == "0.10.0"
    assert "register" in payload["emission"]
    assert "arc" in payload["emission"]


def test_reading_only_shape(long_text):
    status, payload = handle("POST", "/?shape=reading_only", long_text)
    assert status == 200
    assert set(payload.keys()) == {"shaper", "other_shaper", "convergence"}


def test_compact_shape(long_text):
    status, payload = handle("POST", "/?shape=compact", long_text)
    assert status == 200
    assert set(payload.keys()) == {"flags", "register", "coherence", "n_words"}
    assert isinstance(payload["flags"], list)
    assert all(isinstance(f, str) for f in payload["flags"])
    assert payload["n_words"] > 0


def test_handle_json_encodes_utf8(long_text):
    status, body = handle_json("POST", "/?shape=compact", long_text)
    assert status == 200
    parsed = json.loads(body)
    assert set(parsed.keys()) == {"flags", "register", "coherence", "n_words"}


def test_shape_response_unknown_shape_raises():
    with pytest.raises(ValueError):
        shape_response({}, {}, "not_real")


def test_handle_json_is_strict_valid_json_on_nonfinite():
    """Regression: below-envelope/short input yields NaN features internally;
    the wire must still be strict-valid JSON (JS JSON.parse rejects bare NaN).
    parse_constant fires on NaN/Infinity/-Infinity, so this raises if any
    bare non-finite token survives serialisation."""
    status, body = handle_json("POST", "/?shape=audit", "Too short.")
    assert status == 200

    def _reject(tok):
        raise AssertionError(f"non-finite token on the wire: {tok}")

    rec = json.loads(body, parse_constant=_reject)  # strict parse
    # And the record rehashes to its own content_sha256 (audit-grade).
    reading = dict(rec["reading"])
    reading.pop("ts", None)
    recomputed = hashlib.sha256(
        canonical_json({"reading": reading, "distances": rec["distances"]}).encode()
    ).hexdigest()
    assert rec["metadata"]["content_sha256"] == recomputed
