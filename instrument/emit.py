"""emit — the canonical top-level emission entry.

Composes reading + routing + emissions into a single pure
function: text in, `DocumentEmission` out.

Flow:
    1. joint_reading(text)                    — flat + extended + stylometry
                                                 + convergence + soft_flags
    2. per-slice trajectory on elegant slices
    3. routing.route(features)                — pick the reference cohort;
                                                 compute standardised PC distance
    4. register_band_label(distance, catalog) — match/drift/break
    5. assemble(...)                          — four-part DocumentEmission

Graceful degradation (mirrors legacy `shaper.metrology.api.emissions`):
when the router can't project the reading, the structural_profile
classifies the document into a subtype. If `instruction_format`,
recovery is attempted via `strip_scaffolding` + re-projection.
Otherwise the emission is `structural` (reference_table) or
`unprojectable` with the subtype in register evidence. Flags,
coherence, and any measurable arc still flow through.
"""

from __future__ import annotations

from typing import Optional

from instrument.emissions.assembler import assemble, register_band_label
from instrument.emissions.catalog import load_catalog
from instrument.emissions.structural_profile import (
    StructuralProfile,
    profile as structural_profile,
    strip_scaffolding,
)
from instrument.emissions.types import DocumentEmission
from instrument.kernel.cleaning import canonicalise
from instrument.kernel.quantize import canonical_json
from instrument.kernel.tokens import tokenise
from instrument.reading.joint import SCHEMA_VERSION as _SCHEMA_VERSION, joint_reading
from instrument.routing.calibration import (
    envelope_block,
    feature_calibration,
    provenance_block,
)
from instrument.routing.router import (
    NoComparableReferenceError,
    UnknownRegisterHintError,
    distances_as_records,
    distances_to_all_references,
    route,
)

import hashlib

from instrument._core_provenance import CORE_CODE_SHA256

from instrument import __version__ as _INSTRUMENT_VERSION


def _reading_hash(jr: dict) -> str:
    """SHA256 over the pure-core reading alone (no reference-dependent
    distances), excluding the volatile `ts`. The immutable witness of what
    was measured — comparable across users regardless of reference set.
    """
    reading = {k: v for k, v in jr.items() if k != "ts"}
    return hashlib.sha256(canonical_json(reading).encode("utf-8")).hexdigest()


def _content_hash(jr: dict, distances: list) -> str:
    """SHA256 over the quantised canonical measurement record.

    Covers the audit-canonical content (the joint reading + the distances
    to all references), excluding the volatile `ts` field. Folded into
    `reproducibility_hash` so the hash changes when the numbers change.
    A user recomputes it from the audit shape by dropping `reading.ts`
    and hashing `canonical_json({"reading": reading, "distances": distances})`.
    """
    reading = {k: v for k, v in jr.items() if k != "ts"}
    payload = canonical_json({"reading": reading, "distances": distances})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()



def _flat_features(jr: dict) -> dict:
    """Concatenate all feature blocks in a joint reading into one dict.

    Matches shaper.metrology.api._flat_features: shaper + extended +
    stylometry. Stylometry keys are already `stylometry.*`-prefixed
    inside the joint reading.
    """
    out: dict = {}
    out.update(jr["shaper"]["features"])
    out.update(jr["other_shaper"]["features"])
    out.update(jr.get("stylometry", {}).get("features", {}))
    return out


def _reference_envelope(reference, distance) -> dict:
    """Advisory confidence envelope for the chosen reference (0.9.1).

    Thin wrapper over `routing.calibration.envelope_block` (0.10.0),
    which owns the semantics: seed degradation, within/beyond-p95
    position, and — for references persisting the full cross-validated
    null distribution — percentile + empirical exceedance.
    """
    return envelope_block(reference, distance)


def _assemble_unprojectable(
    *,
    text: str,
    catalog: dict,
    jr: dict,
    features: dict,
    subtype: str,
    profile_obj: StructuralProfile,
    preprocessed: bool,
    register_label: str,
    input_sha256: str,
    extra_evidence: Optional[dict] = None,
) -> DocumentEmission:
    """Emit a degraded DocumentEmission for an unprojectable text.

    No reference was selected on this path (reference_name is None), so
    there is no reference to echo calibration provenance for — the
    emission carries neither `reference_envelope` nor
    `reference_provenance` nor `feature_calibration`, deliberately: an
    echo keyed to no reference would be provenance theatre, and
    per-feature p-values need a calibration distribution to be
    p-values against. The per-reference distance records below still
    carry their percentiles where measurable.
    """
    dist_records = distances_as_records(distances_to_all_references(features))
    register_evidence: dict = {
        "reference_name": None,
        "reference_version": None,
        "reference_cohort": None,
        "router_match": "unprojectable",
        "router_flags": [],
        "declared_hint": None,
        "detected_cohort": None,
        "unprojectable_subtype": subtype,
        "preprocessed": preprocessed,
        "structural_profile": {
            "n_prose_lines": profile_obj.n_prose_lines,
            "n_code_lines": profile_obj.n_code_lines,
            "n_table_lines": profile_obj.n_table_lines,
            "n_heading_lines": profile_obj.n_heading_lines,
            "n_bullet_lines": profile_obj.n_bullet_lines,
            "n_content_lines": profile_obj.n_content_lines,
            "prose_ratio": round(profile_obj.prose_ratio, 4),
            "structure_ratio": round(profile_obj.structure_ratio, 4),
            "table_ratio": round(profile_obj.table_ratio, 4),
            "n_latin_letters": profile_obj.n_latin_letters,
            "n_nonlatin_letters": profile_obj.n_nonlatin_letters,
            "nonlatin_ratio": round(profile_obj.nonlatin_ratio, 4),
        },
        "distances_to_all_references": dist_records,
        "_text": text,
    }
    if extra_evidence:
        register_evidence.update(extra_evidence)

    # The trajectory is part of the attested reading (A-prime); the
    # kernel guarantees it is total on degenerate inputs.
    trajectory = jr["trajectory"]["features"]

    return assemble(
        catalog=catalog,
        register_label=register_label,
        register_cohort=subtype,
        register_distance=None,
        register_evidence=register_evidence,
        trajectory=trajectory,
        features=features,
        soft_flags=tuple(jr.get("soft_flags", [])),
        convergence=jr.get("convergence"),
        n_words=jr["n_words"]["shaper"],
        n_sentences=jr.get("n_sentences", 0),
        reading_below_envelope=bool(jr.get("below_envelope", {}).get("shaper", False)),
        instrument_version=_INSTRUMENT_VERSION,
        schema_version=jr.get("schema_version", _SCHEMA_VERSION),
        input_sha256=input_sha256,
        content_sha256=_content_hash(jr, dist_records),
        reading_sha256=_reading_hash(jr),
        core_code_sha256=CORE_CODE_SHA256,
    )


def _emit_projected(
    *,
    catalog: dict,
    text: str,
    jr: dict,
    features: dict,
    reference,
    router_match,
    preprocessed: Optional[str],
    preprocessing_profile: Optional[StructuralProfile],
    input_sha256: str,
) -> DocumentEmission:
    """Normal (projectable) emission path."""
    register_distance = router_match.distance
    register_label = (
        register_band_label(register_distance, catalog) or "unmeasurable"
    )
    dist_records = distances_as_records(distances_to_all_references(features))
    register_evidence: dict = {
        "reference_name": reference.name,
        "reference_version": reference.version,
        "reference_cohort": reference.register_cohort,
        "router_match": router_match.match,
        "router_flags": list(router_match.flags),
        "declared_hint": router_match.declared_hint,
        "detected_cohort": router_match.detected_cohort,
        "reference_envelope": _reference_envelope(
            reference, router_match.distance,
        ),
        # Static echo of the chosen reference's calibration provenance
        # (0.10.0): collection window, recalibration policy, stability
        # summary. Pre-0.10 references degrade explicitly inside the
        # block; see routing/calibration.py.
        "reference_provenance": provenance_block(reference),
        # Per-feature empirical calibration with BH FDR control
        # (0.10.0): two-sided p-values against the reference's stored
        # percentile grids, q-values across the family, and the
        # family policy that makes the multiplicity correction
        # auditable. Descriptive coordinates only — no alpha ships
        # and nothing fires. References without stored grids (all
        # bundled seeds, 0.9.1 references) degrade explicitly inside
        # the block; see routing/calibration.py.
        "feature_calibration": feature_calibration(features, reference),
        "distances_to_all_references": dist_records,
        "_text": text,
    }
    if preprocessed:
        register_evidence["preprocessed"] = preprocessed
        if preprocessing_profile is not None:
            register_evidence["structural_profile"] = {
                "prose_ratio": round(preprocessing_profile.prose_ratio, 4),
                "structure_ratio": round(preprocessing_profile.structure_ratio, 4),
                "subtype_before_recovery": preprocessing_profile.subtype,
            }

    trajectory = jr["trajectory"]["features"]

    return assemble(
        catalog=catalog,
        register_label=register_label,
        register_cohort=reference.register_cohort,
        register_distance=register_distance,
        register_evidence=register_evidence,
        trajectory=trajectory,
        features=features,
        soft_flags=tuple(jr.get("soft_flags", [])),
        convergence=jr.get("convergence"),
        n_words=jr["n_words"]["shaper"],
        n_sentences=jr.get("n_sentences", 0),
        reading_below_envelope=bool(jr.get("below_envelope", {}).get("shaper", False)),
        instrument_version=_INSTRUMENT_VERSION,
        schema_version=jr.get("schema_version", _SCHEMA_VERSION),
        input_sha256=input_sha256,
        content_sha256=_content_hash(jr, dist_records),
        reading_sha256=_reading_hash(jr),
        core_code_sha256=CORE_CODE_SHA256,
    )


def emit_with_reading(
    text: str,
    register_hint: Optional[str] = None,
    emission_version: str = "v2",
    *,
    input_bytes: Optional[bytes] = None,
) -> tuple[DocumentEmission, dict]:
    """Like :func:`emit`, but also returns the joint reading that was used.

    Transport layers (`serve/shape.py`) reuse this reading for the `audit`
    / `full` / `reading_only` shapes instead of recomputing
    `joint_reading(body)` — both removing duplicate work and guaranteeing
    the returned reading is byte-identical to the one the emission's
    `content_sha256` was computed over.

    `input_bytes` is the RAW transport payload (file bytes for the CLI,
    request body bytes for HTTP). `input_sha256` is computed over it
    before any decode/normalisation, so the same bytes carry the same
    provenance identity on every transport. Library callers passing only
    a `str` get the documented fallback `sha256(text.encode("utf-8"))`.
    """
    input_sha256 = hashlib.sha256(
        input_bytes if input_bytes is not None else text.encode("utf-8")
    ).hexdigest()
    # The measurement is a function of the canonical text (idempotent;
    # tokenise/joint_reading canonicalise too — this makes the profile
    # and scaffolding paths below see the same view).
    text = canonicalise(text)
    tokens = tokenise(text)
    jr = joint_reading(text, _tokens=tokens)
    catalog = load_catalog(emission_version)
    features = _flat_features(jr)

    try:
        reference, router_match = route(
            features,
            register_hint=register_hint,
            reading_n_words=jr["n_words"]["shaper"],
        )
    except UnknownRegisterHintError:
        # A bad hint is a caller error, not an unprojectable document —
        # surface it (the serve layer maps ValueError to HTTP 400)
        # rather than silently degrading the emission.
        raise
    except NoComparableReferenceError:
        prof = structural_profile(text)
        if prof.subtype == "instruction_format":
            stripped = strip_scaffolding(text)
            if stripped and len(stripped.split()) >= 150:
                try:
                    jr_retry = joint_reading(stripped)
                    features_retry = _flat_features(jr_retry)
                    reference, router_match = route(
                        features_retry,
                        register_hint=register_hint,
                        reading_n_words=jr_retry["n_words"]["shaper"],
                    )
                    emission = _emit_projected(
                        catalog=catalog,
                        text=stripped,
                        jr=jr_retry,
                        features=features_retry,
                        reference=reference,
                        router_match=router_match,
                        preprocessed="aggressive_scaffolding_strip",
                        preprocessing_profile=prof,
                        input_sha256=input_sha256,
                    )
                    return emission, jr_retry
                except NoComparableReferenceError:
                    pass

        label = "structural" if prof.subtype == "reference_table" else "unprojectable"
        emission = _assemble_unprojectable(
            text=text,
            catalog=catalog,
            jr=jr,
            features=features,
            subtype=prof.subtype,
            profile_obj=prof,
            preprocessed=False,
            register_label=label,
            input_sha256=input_sha256,
        )
        return emission, jr

    emission = _emit_projected(
        catalog=catalog,
        text=text,
        jr=jr,
        features=features,
        reference=reference,
        router_match=router_match,
        preprocessed=None,
        preprocessing_profile=None,
        input_sha256=input_sha256,
    )
    return emission, jr


def emit(
    text: str,
    register_hint: Optional[str] = None,
    emission_version: str = "v2",
    *,
    input_bytes: Optional[bytes] = None,
) -> DocumentEmission:
    """Top-level emission for a single document.

    Composes:
        register   label + evidence from the register router
        arc        per-slice + per-dimension trajectory summary
        flags      document-internal events
        coherence  fraction of axes where the two views agree
        metadata   schema + instrument version, timestamp

    No external baseline required. Usable on response #1.

    Graceful degradation: when routing cannot project the reading,
    structural_profile classifies the document; instruction-format
    docs get a recovery attempt via strip_scaffolding. Otherwise
    register.label is "structural" (reference_table) or
    "unprojectable" with the subtype in evidence.

    `input_bytes`: raw transport payload for provenance (`input_sha256`);
    see :func:`emit_with_reading`.
    """
    return emit_with_reading(
        text, register_hint, emission_version, input_bytes=input_bytes,
    )[0]
