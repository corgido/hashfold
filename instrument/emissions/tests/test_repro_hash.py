"""CONTRACT: reproducibility_hash attests to the measured numbers.

Before P0-2 the hash covered only version pins + input_sha256, so two runs
that produced different numbers (e.g. cross-libm float drift) shared an
identical hash — the hash was blind to the failure it existed to catch.
These tests pin the fix: the hash includes content_sha256, content_sha256 is
recomputable by a user from the audit shape, and it changes when any
measured number changes.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import asdict

from instrument.emit import emit_with_reading
from instrument.kernel.quantize import canonical_json

_TEXT = (
    "The pipeline reduces latency by removing a redundant serialization copy. "
    "Profiling shows the queue stays below thirty percent utilization. "
) * 12


def _customer_content_hash(reading: dict, distances: list) -> str:
    reading_no_ts = {k: v for k, v in reading.items() if k != "ts"}
    payload = canonical_json({"reading": reading_no_ts, "distances": distances})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_repro_hash_folds_content_hash():
    em, _ = emit_with_reading(_TEXT)
    md = asdict(em)["metadata"]
    assert md["content_sha256"]
    recomputed = hashlib.sha256("|".join([
        md["instrument_version"], md["schema_version"], md["emission_version"],
        md["lexicon_version"], md["catalog_sha256"], md["distance_method"],
        md["input_sha256"], md["content_sha256"], md["reading_sha256"],
        md["core_code_sha256"],
    ]).encode("utf-8")).hexdigest()
    assert recomputed == md["reproducibility_hash"]


def test_customer_can_recompute_content_hash_from_audit_shape():
    em, reading = emit_with_reading(_TEXT)
    md = asdict(em)["metadata"]
    distances = asdict(em)["register"]["evidence"]["distances_to_all_references"]
    assert _customer_content_hash(reading, distances) == md["content_sha256"]


def test_perturbing_a_feature_changes_the_hash():
    em, reading = emit_with_reading(_TEXT)
    md = asdict(em)["metadata"]
    distances = asdict(em)["register"]["evidence"]["distances_to_all_references"]

    tampered = copy.deepcopy(reading)
    k = "sfl.process_proxy_entropy"
    tampered["shaper"]["features"][k] += 1e-6
    assert _customer_content_hash(tampered, distances) != md["content_sha256"]


def test_within_host_determinism_holds():
    a, _ = emit_with_reading(_TEXT)
    b, _ = emit_with_reading(_TEXT)
    da, db = asdict(a), asdict(b)
    da["metadata"]["timestamp"] = db["metadata"]["timestamp"] = "X"
    assert da == db


def test_reading_sha256_is_pure_core_and_recomputable():
    from instrument.kernel.quantize import canonical_json
    em, reading = emit_with_reading(_TEXT)
    md = asdict(em)["metadata"]
    reading_no_ts = {k: v for k, v in reading.items() if k != "ts"}
    expected = hashlib.sha256(
        canonical_json(reading_no_ts).encode("utf-8")
    ).hexdigest()
    assert md["reading_sha256"] == expected
    # The pure-core witness excludes reference-dependent distances, so it
    # differs from the full-content hash.
    assert md["reading_sha256"] != md["content_sha256"]


def test_core_code_sha256_matches_frozen_constant():
    from instrument._core_provenance import CORE_CODE_SHA256
    em, _ = emit_with_reading(_TEXT)
    assert asdict(em)["metadata"]["core_code_sha256"] == CORE_CODE_SHA256
    assert len(CORE_CODE_SHA256) == 64
