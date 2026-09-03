"""Typed shapes for the four-part primary emission surface.

Primary emission (always produced; depends only on the text):

    DocumentEmission
      register   RegisterEmission      label + evidence
      arc        ArcEmission           decomposed per-slice + per-dimension
      flags      tuple[Flag, ...]      discrete events, possibly empty
      coherence  CoherenceEmission     confidence scalar + per-axis evidence
      metadata   EmissionMetadata      provenance

Overlays (opt-in; require external inputs):

    DeviationOverlay  — deviation from a reference distribution
    PairOverlay       — coherence with a paired reading

All dataclasses are frozen. `dataclasses.asdict` produces a
JSON-serialisable dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------- Register -------------------------------------------------------

@dataclass(frozen=True)
class RegisterEmission:
    """Register assignment for the text.

    `label` is the catalog-driven verdict relative to the
    auto-selected or hinted register cohort (match / drift / break
    in v2; structural / unprojectable for degraded emissions).
    `distance` is the standardised PC-centroid distance.
    `evidence` carries per-axis deviation, reference name+version,
    routing flags.
    """
    label: str
    cohort: str
    distance: Optional[float]
    evidence: dict[str, Any] = field(default_factory=dict)


# ---------- Arc — per-slice × per-dimension --------------------------------

@dataclass(frozen=True)
class SliceEmission:
    """One slice's readings and labels.

    `values` holds the four trajectory feature values for this
    slice (novelty is None on slice 0 by design). `deltas` is each
    feature's raw `value[i] - value[i-1]` (None on slice 0, and
    None per-feature when either neighbour is None/NaN). The deltas
    are pure measurement — no normalisation, no doc-internal scaling
    — so a compliance pipeline can build its own threshold against
    its own baseline rather than relying on the doc-relative
    `register_shift` flag. `labels` is zero to N overlapping
    per-slice labels.
    """
    index: int
    values: dict[str, Optional[float]]
    deltas: dict[str, Optional[float]]
    labels: tuple[str, ...]


@dataclass(frozen=True)
class DimensionSummary:
    """Per-feature arc summary across slices: start / end / slope /
    range / monotonicity.
    """
    start: Optional[float]
    end: Optional[float]
    slope: Optional[float]
    range: Optional[float]
    monotone: Optional[bool]


@dataclass(frozen=True)
class ArcEmission:
    """Arc as two views of the same trajectory.

    `per_slice` is the slice-by-slice walk ("where").
    `per_dimension` is the feature-by-feature rollup ("what overall
    shape did each trajectory feature follow"). Four dimensions:
    lexical_novelty, sentence_length_variance, modal_density,
    negation_density.
    """
    per_slice: tuple[SliceEmission, ...]
    per_dimension: dict[str, DimensionSummary]
    n_slices: int


# ---------- Flag — discrete event ------------------------------------------

@dataclass(frozen=True)
class Flag:
    """One discrete event that crossed a document-internal threshold.

    Flags are events, not descriptions. Empty `flags` means
    "nothing document-internal crossed a threshold." Pipelines can
    route on `type` and drill into `evidence` only where it fires.
    """
    type: str
    severity: str = "notable"
    evidence: dict[str, Any] = field(default_factory=dict)


# ---------- Coherence ------------------------------------------------------

@dataclass(frozen=True)
class CoherenceEmission:
    """Confidence in the reading as a whole.

    Derived from the five-axis convergence signal (the scalar counts the four coherence-eligible axes; cohesion_repetition is excluded as a duplicate computation) (flat view vs
    extended view, both measuring the same text). Scalar = fraction
    of measurable axes where the two views agree; `label` comes
    from catalog bands on that scalar.
    """
    value: Optional[float]
    label: Optional[str]
    n_axes_measurable: int
    n_axes_agree: int
    diverging_axes: tuple[str, ...]
    incomparable_axes: tuple[str, ...]
    evidence: dict[str, Any] = field(default_factory=dict)


# ---------- Primary emission -----------------------------------------------

@dataclass(frozen=True)
class EmissionMetadata:
    """Provenance for the emission.

    Compliance-grade traceability. All fields except `timestamp` are
    deterministic functions of the input + the pinned instrument /
    lexicon / catalog. A user storing an emission can re-run the
    same input under the same versions and verify byte-equality of
    every field except `timestamp`.

    `reproducibility_hash` is a single SHA256 over the stable
    components (instrument_version, schema_version, emission_version,
    lexicon_version, catalog_sha256, distance_method, input_sha256,
    content_sha256, reading_sha256, core_code_sha256) so a verifier can
    compare one scalar instead of many. `content_sha256` is a SHA256 over
    the quantised canonical measurement record (reading + distances,
    excluding the volatile `ts`), so the reproducibility hash changes when
    the measured numbers change — not only when a version pin changes.

    `reading_sha256` hashes the pure-core reading alone (no
    reference-dependent distances): the immutable, cross-user witness
    of what was measured. `core_code_sha256` is a build-time hash of the
    measurement core source (kernel + reading + lexicons), pinning the
    exact algorithm — including frozen decision constants such as
    convergence's `AGREE_TOLERANCE` — that produced the reading.
    """
    emission_version: str
    instrument_version: str
    schema_version: str
    n_words: int
    n_sentences: int
    timestamp: str
    lexicon_version: str
    catalog_sha256: str
    distance_method: str
    input_sha256: str
    content_sha256: str
    reading_sha256: str
    core_code_sha256: str
    reproducibility_hash: str


@dataclass(frozen=True)
class DocumentEmission:
    """The four-part primary emission for a single document."""
    register: RegisterEmission
    arc: ArcEmission
    flags: tuple[Flag, ...]
    coherence: CoherenceEmission
    metadata: EmissionMetadata


# ---------- Optional overlays ----------------------------------------------

@dataclass(frozen=True)
class DeviationOverlay:
    """Reading's deviation from a named reference distribution."""
    reference_name: str
    reference_version: str
    rms_delta_std: Optional[float]
    band_counts: dict[str, int]
    flagged_features: tuple[str, ...]
    n_features_measured: int


@dataclass(frozen=True)
class PairOverlay:
    """Coherence between two readings, relative to a reference's scale."""
    reference_name: str
    reference_version: str
    agreement_rate: Optional[float]
    label: Optional[str]
    n_features_measured: int
    n_agreeing: int
    flagged_features: tuple[str, ...]


# ---------- Corpus aggregate -----------------------------------------------

@dataclass(frozen=True)
class CorpusEmissionReport:
    """Aggregated view of DocumentEmissions across a corpus."""
    n_docs: int
    emission_version: str
    instrument_version: str
    schema_version: str
    register_label_counts: dict[str, int]
    register_cohort_counts: dict[str, int]
    slice_label_counts: dict[str, int]
    flag_counts: dict[str, int]
    coherence_mean: Optional[float]
    coherence_p05: Optional[float]
    coherence_p50: Optional[float]
    coherence_p95: Optional[float]
    coherence_label_counts: dict[str, int]
