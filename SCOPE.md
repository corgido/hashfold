# SCOPE — what hashfold is and is not

This document defines the scope of hashfold. It is the load-bearing
definition of what the library does, what it does not do, and what
guarantees it makes.

## What the instrument is

A **deterministic measurement device** for long-form prose. Given an
input text, it produces a fixed-shape numeric record (the "audit
shape" output) describing surface features of the prose:

- per-word counts in six SFL process buckets (mental, verbal,
  relational, behavioral, material, existential)
- rhetorical-structure **cue-marker densities** (`rst.contrast_marker_density`,
  `rst.elaboration_marker_density`, `rst.marker_density`, and the
  extended per-relation densities). These count surface discourse
  markers per sentence; they are deliberately NOT named as RST
  relation counts, because that is not what a deterministic
  surface instrument can measure (renamed in 0.9.1)
- lexical cohesion measures (type-token ratio, pronoun density,
  repetition, lexical chains)
- register / stylistic measures (sentence-length variance, modal
  density, negation density, lexical novelty)
- stylometric measures (compression ratio, punctuation densities,
  subordination density, quotation density)
- per-slice trajectory streams of the four register features, with
  raw adjacent-slice deltas
- five-axis cross-view convergence between two structurally parallel
  measurement pipelines (the "shaper" and "other-shaper" views)
- distances to five fixed reference distributions
  (academic_prose, dialogue_prose, journalism_prose,
  literary_prose, llm_technical_prose) in standardised PC space

Every number in the output is a deterministic function of the input
bytes plus the pinned `(instrument_version, lexicon_version,
catalog_sha256)`. The instrument runs entirely on the Python
standard library — no numpy, no sklearn, no learned weights, no
network calls in the measurement hot path.

## What the instrument is not

The instrument **does not interpret**. It does not produce a verdict
on the prose. Specifically, the instrument is **not**:

- a content classifier (it does not say "this is X kind of writing")
- a quality scorer (it does not say "this is good or bad writing")
- a hallucination detector
- a bias detector
- a harm detector
- a toxicity / safety classifier
- a plagiarism detector
- a watermark detector
- a reading-level estimator

Where the API surface exposes labels — `register.label` (match /
drift / break), `coherence.label` (high / moderate / low), the 12
flags, the cohort pick — those labels are **advisory convenience
over the underlying numbers**. They are not the canonical record.
The audit shape (`?shape=audit`) excludes them by design. Catalog
v2 thresholds (which decide when each label fires) are explicitly
documented as pre-calibration placeholders.

The instrument does **not** attempt to interpret what an LLM "meant"
or "should have said". It measures what was written.

## Determinism guarantee

For a pinned `(instrument_version, lexicon_version, catalog_sha256,
distance_method)` and a given input byte sequence, the instrument
produces the same numeric output, every time, on any host that runs
the Python standard library.

The metadata block on every emission carries these four pin values
plus an `input_sha256` and a `reproducibility_hash` (SHA256 over the
ten stable components: `instrument_version`, `schema_version`,
`emission_version`, `lexicon_version`, `catalog_sha256`,
`distance_method`, `input_sha256`, `content_sha256`, `reading_sha256`,
`core_code_sha256`). The latter three hash the measured numbers
(`content_sha256`), the reference-independent reading
(`reading_sha256`), and the measurement-core source
(`core_code_sha256`), so the reproducibility hash fails if the
*numbers* or the *algorithm* change, not only if a version pin moves.
A user storing an emission can re-run the input later and verify
byte-equality of every output field except `timestamp`, or rehash a
stored record offline against its own `content_sha256` /
`reading_sha256`.

The only non-deterministic field is `metadata.timestamp` (clock
read at serialisation time). The `reproducibility_hash` does not
include `timestamp`.

Two integrity surfaces, deliberately separate (0.9.1):

- **Raw-byte integrity** — `input_sha256` is the SHA256 of the raw
  transport bytes (the file's bytes on the CLI, the request body on
  HTTP), before any decode or normalisation. Change one byte of the
  input and it fails. It identifies *what was submitted*.
- **Measurement integrity** — `reading_sha256` / `content_sha256`
  hash the quantised canonical *measurement*. The measurement is a
  function of the canonicalised text (newline convention, BOM,
  trailing spaces, and blank-line run length are normalised away),
  so two byte-different inputs that differ only in non-semantic
  formatting share the same measurement hashes — an *equivalence
  fingerprint* of what was measured, not a character-level
  integrity check. A byte-tamper that changes only non-semantic
  formatting moves `input_sha256` (and therefore
  `reproducibility_hash`) but never the measurement hashes; a
  tamper that changes any surfaced number fails offline
  recomputation of `content_sha256`/`reading_sha256`.

The per-slice trajectory is part of the joint reading (0.9.1), so
every surfaced trajectory number is covered by both measurement
hashes; the arc block (deltas, per-dimension summaries, slice
labels) is a derived advisory view, recomputable from the attested
trajectory values.

## Reproducible, and validated at method-demonstration scale

The determinism guarantee above is a *reproducibility* claim. The
numbers are proven to be exact functions of the input bytes plus
pins; they are **not** proven to track human SFL/RST analysis or
human register judgment. Discriminant testing (2026-06) shows
several features carry signal that is not reducible to surface
confounds (`sfl.process_proxy_entropy`, `sfl.projection_frequency`,
`cohesion.pronoun_density`) while others are substantially surface
artifacts and are documented as such in `docs/METROLOGY.md`
(`cohesion.lexical_repetition` in particular).

Since 0.10.0 the reproducibility claim is joined by a **validation
study at method-demonstration scale** (`docs/VALIDATION.md`,
generated and CI-gated): eight deterministic mechanical
perturbations at four intensities over held-out fixture segments,
detection rates with exact Clopper–Pearson intervals, EWMA
batch-power statements, and a **negative control pinned at the
nominal operating point** — a failing negative control fails CI.
Read it at its stated size: the calibration null has n=15, the
held-out "documents" are segments of 8 fixtures, and the
perturbations are surface edits, not a model of real LLM drift. The
study demonstrates the *method* — reference → percentile →
operating point → batch SPC detects known injected changes at rates
that track realized effect size; the claim that scales is earned by
running the same protocol (documented there) on your own data. **Criterion validity — agreement with gold-standard human
annotation — remains untested and out of scope for this release.**
The defensible use is relative: measure your own deployment's
output against your own calibrated baseline
(`docs/CALIBRATION.md`), where "drift" means movement in your
coordinate system, not an absolute linguistic verdict.

## Cross-view consistency (what convergence is, and is not)

The instrument was built as **two structurally parallel pipelines**.
The "shaper" view (13 dimensions) and the "other-shaper" view
(37 dimensions) measure the same text with different reduction
strategies, measurement granularity, and threshold design. They are
**not independent measurements**: both share the L1 kernel
infrastructure (cleaning, paragraph splitting, sentence splitting)
and — measured, not assumed — substantially the same vocabulary
(identical process lexicons and stopword lists, a shared RST marker
inventory, 71%-shared modals). A bias in a shared lexicon corrupts
both views identically, and they still agree.

The convergence block therefore reports **internal consistency
across substantially shared computation**, on five axes
(sfl_process_complexity, rst_contrast, rst_elaboration,
cohesion_repetition, register_modality). Each axis carries an
`independence` annotation in the record itself: only `rst_contrast`
is substantially independent in practice; `cohesion_repetition` is
one measurement counted twice (its two views agree ~100% of the
time by construction) and is excluded from the coherence scalar.
High convergence means the two reductions made the same
observation; low convergence is information about the prose's
measurability, not its quality.

What this buys, honestly stated: cross-view consistency catches
implementation divergence between two reductions (a real class of
defect), and on the genuinely-independent axis it is weak
corroboration. It does not make a shared-lexicon bias visible, and
it is not independent replication. Claims stronger than this are
not made.

## Defensibility — SFL trace

SFL (Halliday's Systemic Functional Linguistics) is the only layer
of the instrument that makes semantic claims about individual
tokens. To support audit, the instrument can emit a per-token
classification trace via `?include=sfl_trace` (attached to `audit`
or `full` shapes).

For each token, the trace records:

- the surface form
- the lowercased lemma used for lookup
- the bucket assigned (mental / verbal / relational / behavioral /
  material / none)
- the rule that fired (`lexicon_<bucket>` for direct lexicon hits —
  including `lexicon_material` since 0.9.1, when the material
  lexicon became a consulted classification source rather than
  morphology-only, `lexicon_copula_be` for the be-verb path,
  `denylist_plural_noun` / `denylist_adjectival_participle` /
  `denylist_non_process` for the noun/adjective/closed-class guards
  on the morphology fallback, `morphology_ing` / `morphology_ed`
  for suffix heuristics, `default` for the no-classification
  fallthrough)

The trace also records every existential pattern match
(`there is/are/was/were/exists/existed`) and the copula-existential
debit applied to relational counts.

An auditor reviewing a contested classification can:

1. Pull the per-token record from the trace.
2. See the rule that fired.
3. Compare to the lexicon (versioned via `lexicon_version` in
   metadata) and the `KNOWN_PLURAL_NOUNS` /
   `KNOWN_ADJECTIVAL_PARTICIPLES` / `KNOWN_NON_PROCESS` deny-lists
   in `kernel/features/sfl.py`.
4. Verify that `summary.counts` in the trace (after the copula
   debit) reconciles to the headline `process_proxy_entropy` value
   in the reading.

## Out of scope

The instrument is not designed to:

- compare two LLMs' outputs and pick a winner
- predict whether a downstream task will succeed
- anonymise, redact, or transform the input
- reject, gate, or filter LLM outputs at runtime
- measure non-Latin-script prose. The word tokeniser is
  ASCII-Latin; substantively non-Latin input is refused loudly
  (`register.label = "unprojectable"`, subtype
  `unsupported_script`, script counts in evidence), and a mixed
  document that still projects carries the
  `substantive_non_latin_content` soft flag in its reading (0.9.1).

Pipelines that need any of these should treat the instrument as a
measurement source feeding their own logic.

## Versioning policy

- **Lexicons** are pinned by file (`instrument/lexicons/_v1.py`)
  and exposed as `LEXICON_VERSION = "v1"`. Any change ships as
  `_v2.py` with a new `LEXICON_VERSION`. Users can pin and
  verify.
- **Catalog** is pinned by version string (`v2`) and a SHA256 over
  the source JSON. Any change to the source JSON requires
  regenerating `catalog_v2.py` (the build tool's `--check` mode
  fails until done) and produces a new `SOURCE_SHA256` that
  surfaces in `EmissionMetadata.catalog_sha256`.
- **Instrument** version is single-sourced at
  `instrument.__version__` (currently `0.10.0`). Bumps follow
  semantic versioning; while the major version is 0, a minor bump
  signals a change to the measurement surface (precedent: 0.8.0's
  compression_ratio migration, 0.9.0's tokenisation and SFL
  corrections). **0.9.1 is a deliberate, documented exception**: it
  changed the measurement surface (input canonicalisation, fence
  handling, MATERIAL lexicon, renamed RST keys, trajectory in the
  reading) but shipped as a patch-numbered release-candidate line by
  release-management decision. The version cannot lie about the
  numbers regardless: `reproducibility_hash` folds `content_sha256`
  and `core_code_sha256`, both of which moved — see
  `CHANGES-0.9.1.md` for the full surface delta. **0.10.0 took the
  minor bump the convention requires** (the reading gained
  `dist.mattr`; the emission gained evidence blocks; the core hash
  moved) — the 0.9.1 deviation was not repeated. See
  `CHANGES-0.10.0.md`.
- **Distance method** is named in metadata
  (`distance_method = "feature_zscore_l2"` today). Future
  migrations (e.g. true Mahalanobis) become explicit and
  version-traceable.
- **Schema** is pinned at `SCHEMA_VERSION` in `reading/joint.py`
  (currently `0.10.0`, aligned with the instrument version because
  0.10.0 changed the reading shape: `dist.mattr` joined the
  distributional view. 0.9.1 previously added the trajectory block,
  per-axis independence annotations, and renamed RST keys). Any
  change to the output shape bumps schema_version. The catalog's
  embedded stamps still read `0.9.1` — deliberately: they name the
  version the catalog was last regenerated and checked against, and
  no catalog byte changed in 0.10.0
  (`instrument/tests/test_version_alignment.py`).

## Pre-calibration warning

The catalog thresholds shipped at `catalog_v2.py` are explicitly
**pre-calibration placeholders**. They were sanity-checked against
a 515-trace LLM-output corpus to ensure they do not
false-positive-flood on normal prose, but they have not been
empirically tuned against a large calibration corpus. A planned v3
catalog with empirical tuning was on the original roadmap; under
the measurement-only posture described in this document, that
calibration is no longer planned, because calibrated thresholds would be a
normative claim about what "drift" or "high coherence" means in
absolute terms — i.e. inference, not measurement.

The roadmap instead adds reference points (more cohorts as
feature-space coordinates you can compare against), not
decision rules.

0.10.0 delivered on exactly that roadmap: it adds calibrated
**descriptive** coordinates with known empirical error rates
against a *named* baseline — the percentile and empirical
exceedance of a distance within a reference's persisted
cross-validated null, per-feature empirical p-values and
Benjamini–Hochberg q-values under a stated family policy,
deterministic bootstrap intervals, and offline control-chart states
(`in_control` / `isolated_exceedance` / `sustained_shift_signal`).
These are still **not decision rules**: no alpha ships, nothing
fires on them, and the worked operating points in the documentation
(features with q ≤ 0.05; percentile > 95) are documentation
examples, not shipped policy. The catalog remains
placeholder-thresholded and byte-unchanged in 0.10.0
(`catalog_sha256` stable); the decision layer — thresholds, alarms,
and what to do about them — belongs to your deployment.

## Reading an emission

The order an auditor — or you, six months later — should read a
stored record in:

1. Confirm `metadata.reproducibility_hash` matches the stored value
   for that input.
2. Read the audit shape (`reading`, `distances`, `metadata`).
3. Read each distance together with its `percentile` — the mid-rank
   position of that distance within that reference's own persisted
   null — and, for the chosen reference (full shape),
   `register.evidence.reference_envelope.empirical_exceedance`: the
   fraction of the baseline's own documents at least this far out,
   i.e. the empirical false-positive rate of alarming here. A `null`
   percentile or an explicit degraded status
   (`seed_reference_no_confidence_envelope`,
   `reference_predates_null_distribution`) means the baseline cannot
   vouch for the distance — treat the distance as uncalibrated.
4. For per-feature claims, read
   `register.evidence.feature_calibration`: q-values are quoted
   under the recorded `family_policy` (method, family size `m`,
   sidedness, p-value floor) — check the policy before comparing
   q-values across documents. Status
   `reference_lacks_feature_quantiles` means no per-feature claim is
   supported.
5. If the record carries an `uncertainty` block, read each point
   estimate with its `ci_low`/`ci_high`/`se`; the block replays
   byte-for-byte from the input bytes (`method`, `b`, `seed` are in
   the record) and rides outside the content hashes.
6. For stream-level claims ("the process shifted"), ask for the
   offline control-chart report (`tools.control_chart`): the chart
   state in `summary.state`, and the baseline-age check
   (`baseline_age.age_status` against the reference's own
   `recalibration_policy`) — a stale baseline is itself a finding.
7. Note that `flags`, `register.label`, `coherence.label`, and the
   single-cohort pick are advisory and not the canonical record.
8. Note that `instrument_version`, `lexicon_version`,
   `catalog_sha256`, and `distance_method` together pin the
   measurement surface; any reproducibility test must pin all four.
   For calibrated coordinates, additionally pin the reference JSON
   by its SHA256 — the reference bytes are the coordinate system.
