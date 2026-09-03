"""shape — pure request handler + response-shape filter.

The pure handler: `handle(method, path, body, config) -> (status,
payload)`. `http.py` is a thin transport layer over this one
function. ("Pure" = no env reads, no file
reads, deterministic payloads; the single exception is a
crash-diagnostic traceback written to stderr on the 500 path.)

Response shapes (via `?shape=` query or `Config.response_shape`):

    audit         Compliance-grade record. {"reading", "distances",
                  "metadata"}. Pure measurement: no flags, no
                  register match label, no coherence band — just
                  the numbers and the provenance. Recommended for
                  EU AI Act-style record-keeping pipelines.
    full          Full DocumentEmission + joint reading block.
    flags_only    {"flags": [...], "coherence": {...}}. Tiny
                  payload; advisory monitoring/alerting only —
                  the inference layer, not the canonical record.
    reading_only  {"shaper": ..., "other_shaper": ...,
                  "convergence": ...}. For clients that build
                  their own emission logic.
    compact       Four-field envelope: flags list, register label,
                  coherence label, n_words. Fits log pipelines.

Computation is the same across shapes — shape is a response
filter only, not a mode. Latency is stable regardless of choice.
"""

from __future__ import annotations

import json
import sys
import traceback
from dataclasses import asdict
from typing import Any
from urllib.parse import parse_qs, urlsplit

from instrument.config import DEFAULT_CONFIG, Config
from instrument.emit import emit_with_reading
from instrument.kernel.features.sfl import compute_sfl_trace
from instrument.kernel.quantize import quantize
from instrument.kernel.tokens import tokenise
from instrument.reading.bootstrap import bootstrap_uncertainty

VALID_SHAPES: frozenset[str] = frozenset({
    "full", "flags_only", "reading_only", "compact", "audit",
})

VALID_INCLUDES: frozenset[str] = frozenset({"sfl_trace", "uncertainty"})


def _parse_query(path: str) -> dict[str, str]:
    """Parse a URL path's query string into a flat str-keyed dict."""
    parts = urlsplit(path)
    qs = parse_qs(parts.query, keep_blank_values=False)
    return {k: v[0] for k, v in qs.items() if v}


def _count_words(text: str) -> int:
    """Cheap word count for the `max_words` gate. Matches the legacy
    gate (whitespace split), not the full kernel tokenisation."""
    return len(text.split())


def _shape_full(emission_dict: dict, reading: dict) -> dict:
    return {"emission": emission_dict, "reading": reading}


def _shape_flags_only(emission_dict: dict) -> dict:
    return {
        "flags": emission_dict["flags"],
        "coherence": emission_dict["coherence"],
    }


def _shape_reading_only(reading: dict) -> dict:
    return {
        "shaper": reading.get("shaper"),
        "other_shaper": reading.get("other_shaper"),
        "convergence": reading.get("convergence"),
    }


def _shape_compact(emission_dict: dict) -> dict:
    """Four-field envelope for log pipelines."""
    return {
        "flags": [f["type"] for f in emission_dict["flags"]],
        "register": emission_dict["register"]["label"],
        "coherence": (emission_dict["coherence"] or {}).get("label"),
        "n_words": emission_dict["metadata"]["n_words"],
    }


def _shape_audit(emission_dict: dict, reading: dict) -> dict:
    """Compliance-grade record: pure measurement, no inference labels.

    Returns the joint reading (raw feature dicts + per-axis convergence
    values), the distances to every bundled reference (so the user
    sees position rather than a winner pick), and the full metadata
    (with provenance fields and `reproducibility_hash`).

    Excludes flags, register match label, coherence band, register
    cohort pick — those are the inference layer; consult `full` if
    needed.
    """
    distances = (
        emission_dict.get("register", {})
        .get("evidence", {})
        .get("distances_to_all_references", [])
    )
    return {
        "reading": reading,
        "distances": distances,
        "metadata": emission_dict["metadata"],
    }


def shape_response(
    emission_dict: dict,
    reading: dict,
    shape: str,
    *,
    sfl_trace: dict | None = None,
    uncertainty: dict | None = None,
) -> dict:
    """Apply a response-shape filter to a pre-computed emission.

    `sfl_trace` and `uncertainty` are optional; when supplied they are
    attached at the top level of `audit` and `full` shapes (other
    shapes ignore them). Both ride OUTSIDE the emission's
    `content_sha256` / `reproducibility_hash` — those are computed
    inside emit, before any include exists.

    Unknown shapes raise `ValueError`.
    """
    if shape == "full":
        out = _shape_full(emission_dict, reading)
    elif shape == "flags_only":
        out = _shape_flags_only(emission_dict)
    elif shape == "reading_only":
        out = _shape_reading_only(reading)
    elif shape == "compact":
        out = _shape_compact(emission_dict)
    elif shape == "audit":
        out = _shape_audit(emission_dict, reading)
    else:
        raise ValueError(
            f"unknown shape: {shape!r}; valid: {sorted(VALID_SHAPES)}"
        )
    if sfl_trace is not None and shape in ("audit", "full"):
        out["sfl_trace"] = sfl_trace
    if uncertainty is not None and shape in ("audit", "full"):
        out["uncertainty"] = uncertainty
    return out


def handle(
    method: str,
    path: str,
    body: str,
    config: Config = DEFAULT_CONFIG,
    *,
    body_bytes: bytes | None = None,
) -> tuple[int, dict[str, Any]]:
    """Pure request handler. `(status, payload)` — no I/O, no env.

    `body` is the POST body as a string. Transport layers decode
    bytes → str before calling and pass the un-decoded payload as
    `body_bytes` so `input_sha256` covers the RAW transport bytes
    (transport-independent provenance). The caller serialises the
    payload dict (e.g. `json.dumps`) on the way out.
    """
    if method == "GET" and urlsplit(path).path == "/health":
        return 200, {"status": "ok"}

    if method != "POST":
        return 405, {"error": "POST only"}

    if not body or not body.strip():
        return 400, {"error": "empty body"}

    query = _parse_query(path)
    shape = query.get("shape", config.response_shape)
    if shape not in VALID_SHAPES:
        return 400, {"error": f"unknown shape: {shape!r}",
                     "valid": sorted(VALID_SHAPES)}

    register_hint = query.get("register_hint")
    include_raw = query.get("include", "")
    includes = {
        s for s in (p.strip() for p in include_raw.split(",")) if s
    }
    unknown_includes = includes - VALID_INCLUDES
    if unknown_includes:
        return 400, {
            "error": f"unknown include(s): {sorted(unknown_includes)}",
            "valid": sorted(VALID_INCLUDES),
        }

    if config.max_words > 0:
        n_words = _count_words(body)
        if n_words > config.max_words:
            return 413, {
                "error": "size_cap_exceeded",
                "max_words": config.max_words,
                "n_words": n_words,
            }

    try:
        # P1-5: emit already computes the joint reading; reuse it instead of
        # recomputing joint_reading(body). This also guarantees the returned
        # `reading` is byte-identical to the one `content_sha256` was hashed
        # over. tokenise(body) is only needed for the optional sfl_trace.
        emission, reading = emit_with_reading(
            body, register_hint=register_hint, input_bytes=body_bytes,
        )
        if shape not in ("full", "reading_only", "audit"):
            reading = {}
        sfl_trace = (
            compute_sfl_trace(tokenise(body))
            if "sfl_trace" in includes else None
        )
        # Opt-in bootstrap uncertainty (audit/full only — the shapes
        # that carry the record it annotates). Seeded from the
        # emission's input_sha256, so the intervals are a pure function
        # of the raw input bytes and config.bootstrap_b.
        uncertainty = (
            bootstrap_uncertainty(
                body,
                seed=emission.metadata.input_sha256,
                b=config.bootstrap_b,
            )
            if "uncertainty" in includes and shape in ("audit", "full")
            else None
        )
    except ValueError as e:
        return 400, {"error": str(e)}
    except Exception:
        # Controlled failure: never leak internals or crash the server on
        # adversarial input. The traceback is written to stderr HERE (the
        # one shared implementation point) — the transports only log
        # method/path/status, so without this print a 500 would be
        # undiagnosable in production.
        traceback.print_exc(file=sys.stderr)
        return 500, {"error": "internal_error"}

    emission_dict = asdict(emission)
    payload = shape_response(
        emission_dict, reading, shape, sfl_trace=sfl_trace,
        uncertainty=uncertainty,
    )
    return 200, payload


def handle_json(
    method: str,
    path: str,
    body: str,
    config: Config = DEFAULT_CONFIG,
    *,
    body_bytes: bytes | None = None,
) -> tuple[int, str]:
    """Thin wrapper that JSON-encodes the payload. Transport layers
    can use either this or `handle` depending on whether they want
    a dict or a serialised string.
    """
    status, payload = handle(method, path, body, config, body_bytes=body_bytes)
    # quantize() maps non-finite floats to null so the wire is always valid
    # JSON (JS JSON.parse rejects bare NaN) and matches the canonical/hashed
    # representation; allow_nan=False then guards against any survivor.
    return status, json.dumps(quantize(payload), ensure_ascii=False, allow_nan=False)
