# EU AI Act and standards mapping

> **What this document is.** This document describes how hashfold's
> outputs relate to EU AI Act requirements and relevant ISO standards.
> It is a technical mapping, not a compliance certification. hashfold
> is a measurement library; using it does not make a system compliant
> with any regulation. Compliance is a property of the full system,
> not of one component. Nothing here is legal advice.

> **Pre-calibration notice.** All thresholds in the instrument's
> catalog (`catalog_v2.py`) are pre-calibration placeholders. They
> have been sanity-checked but have not been empirically tuned on a
> production corpus, and 0.10.0 deliberately changed no catalog byte
> (`catalog_sha256` unchanged; the catalog's embedded stamps still
> name 0.9.1, the version it was last regenerated and checked
> against — `instrument/tests/test_version_alignment.py`). Advisory
> labels (flags, register bands, coherence bands) derived from these
> thresholds must not be treated as calibrated decisions.
>
> Distinguish that from what 0.10.0 *did* add: **calibrated
> descriptive coordinates** with known empirical error rates against
> your own named baseline — the percentile and empirical
> exceedance of a distance within the reference's persisted
> cross-validated null, per-feature q-values under a stated FDR
> family policy, deterministic bootstrap coverage intervals, and
> offline control-chart states. The catalog labels are uncalibrated
> advisories; the 0.10.0 coordinates are calibrated descriptions;
> **neither is a decision rule** — thresholds and alarms remain
> yours (`SCOPE.md`, "Pre-calibration warning"). The audit-shape
> output (raw measurements and distances) is production-grade.

The sections below describe how the instrument's record can support
obligations under the EU AI Act (Regulation (EU) 2024/1689). Treat
the mapping as a starting point for your own assessment, not as a
conclusion.

## Where the instrument fits best

The instrument's operational pattern — continuous, systematic,
versioned measurement of every production output, stored as
tamper-evident records and analysed against a baseline (the
"baseline-and-deviation" workflow in `docs/INTEGRATION.md`) — maps
most directly onto **Article 72 (post-market monitoring)**, with
**Article 12 (record-keeping)** as the capability that feeds it.
Article 12(2)(b) states this linkage explicitly: logging exists,
among other purposes, for "facilitating the post-market monitoring
referred to in Article 72". The sections below keep numeric order;
read Article 72 first if you are scoping the record-keeping case.

Whether Article 72 (a provider obligation) or Article 26(5)
(the deployer's duty to monitor operation) applies to you depends
on your role for the high-risk system in question; both are served
by the same audit-shape record stream.

The mapping addresses the instrument as a measurement component
within a broader high-risk AI system. The instrument itself is not
a high-risk AI system; it is a deterministic feature-extraction
tool. Whether your overall system is high-risk depends on its
purpose and deployment context, which is your determination to
make.

## Standards vocabulary — GUM, ISO 5725, ISO 7870

Conformity assessors read measurement claims in the vocabulary of
the metrology standards. This section states the mapping from
instrument terms to that vocabulary — and states which classical
concepts do **not** apply, so the record cannot be over-read.
Citations name the standard series deliberately (JCGM 100:2008; the
ISO 5725 series; the ISO 7870 series); clause-level conformity
mapping is your assessor's work, not this document's claim.

### GUM (JCGM 100:2008 — expression of uncertainty in measurement)

| GUM concept | Instrument realisation |
|---|---|
| Measurand | Each named feature quantity, operationally defined by its formula in `docs/METROLOGY.md`. The measurand is defined *by the stated procedure*; it does not estimate a separate underlying "true value". |
| Measured value | The point estimate in the record: `reading.<view>.features.<name>`, echoed as `uncertainty.features.<name>.point` when the uncertainty block is requested. |
| Type A standard uncertainty | The bootstrap standard error `uncertainty.features.<name>.se` — the population standard deviation of the feature over B sentence-resampled replicates of the document: a statistical evaluation from repeated observations under a declared resampling model. |
| Coverage interval | `uncertainty.features.<name>.ci_low` / `.ci_high` — the 2.5th–97.5th percentile interval of the finite replicate values (percentile bootstrap). |
| Statement of method | Carried inside the record: `uncertainty.method` (`sentence_bootstrap_paragraph_shape_v1`), `uncertainty.b`, `uncertainty.seed`, plus the pinned PRNG construction — SHA-256 in counter mode (`instrument/kernel/detrandom.py`), seeded with the string `"{scheme}:{input_sha256}"` — so the entire uncertainty evaluation replays byte-for-byte from the record and the input bytes. |

Honest limits, stated: the bootstrap quantifies each feature's
sensitivity to the sentence-level composition of *this document*
under the declared resampling scheme. It is not uncertainty about
agreement with an external reference value (no trueness claim —
see ISO 5725 below), and re-measurement of the same bytes
contributes exactly zero spread by construction. No Type B
evaluation is performed: a deterministic stdlib computation has no
calibration-certificate or tolerance inputs to propagate.

### ISO 5725 (accuracy — trueness and precision)

- **Repeatability.** Under repeatability conditions and the five
  pins `(instrument_version, lexicon_version, catalog_sha256,
  distance_method, core_code_sha256)`, the repeatability standard
  deviation of every emitted quantity is **exactly 0** — not
  approximately 0 — because each number is a deterministic function
  of the input bytes plus the pins. The evidence is structural, not
  asserted: `metadata.reproducibility_hash` folds the measured
  numbers (`content_sha256`), so two runs of the same bytes either
  agree byte-for-byte or visibly differ, and the CI reproducibility
  matrix (`.github/workflows/reproducibility.yml`) proves byte-equal
  output across operating systems and CPython versions.
- **Reproducibility.** Under changed conditions (different host,
  OS, Python build) the numbers do not move while the pins hold —
  the same byte-equality evidence covers it. The conditions that
  *can* move the numbers are exactly the pins; every pin is stamped
  in each record, and any pin movement is hash-detected
  (`reproducibility_hash` changes). Reproducibility across versions
  is therefore version-pinned and hash-detected rather than
  statistically estimated.
- **Trueness.** Not claimed, and not claimable: stylometric
  quantities have no conventional true value — no reference
  material, no accepted reference measurement procedure — so bias
  against an accepted reference value is explicitly **out of
  scope**, stated as a scope boundary rather than approximated with
  a proxy. The nearest neighbours are labelled for what they are:
  the perturbation study (`docs/VALIDATION.md`) demonstrates that
  the method detects known injected changes at fixture scale, and
  criterion validity against human annotation remains untested and
  out of scope (`SCOPE.md`).

### ISO 7870 (control charts)

| ISO 7870 part | Instrument realisation |
|---|---|
| ISO 7870-2 (Shewhart-type individuals) | `instrument.spc.individuals` — each document's distance placed at its mid-rank percentile within the reference's persisted null; a point `exceeds` above a stated percentile (default 99.5). |
| ISO 7870-4 (CUSUM) | `instrument.spc.cusum` — tabular CUSUM over standardised distances (defaults k = 0.5, h = 5). |
| ISO 7870-6 (EWMA) | `instrument.spc.ewma` — EWMA with time-varying limits (defaults λ = 0.2, L = 3). |

- **In-control distribution** = the reference's persisted
  cross-validated null (`self_distance.values`, basis
  `cross_validated_10fold`): the empirical distribution of held-out
  calibration documents, not an assumed normal.
- **ARL** is documented empirically, per reference: textbook
  normal-theory ARL₀ figures for these defaults (≈ 500 for the
  EWMA, ≈ 465 for the CUSUM) are approximations only, because the
  distance stream is non-negative and right-skewed. The honest
  characterisation is `python -m tools.control_chart --arl`, which
  resamples the reference's *own* null under injected shifts of
  0/0.5/1/1.5/2 σ₀ and reports the measured average run length per
  chart.
- **Division of responsibility**: the instrument reports chart
  states — `in_control`, `isolated_exceedance`,
  `sustained_shift_signal` — as descriptive statements about the
  stream. The out-of-control action plan (recalibrate, investigate,
  quarantine) is yours, consistent with the posture in `SCOPE.md`.

## Article 10 — Data and data governance

The relevant obligations concern the data used to train and
validate the AI system. The instrument is not a learned system
and has no training data. This eliminates several of Article 10's
sub-obligations entirely.

The instrument's lexicons (Article 10's nearest analogue to
"training data" for a rule-based system) are documented in
`docs/LEXICONS.md`, including:

- Per-lexicon source attribution and decision rationale
- Versioning policy (immutable snapshots, version stamped in
  every emission's `metadata.lexicon_version`)
- Deny-list documentation for the SFL classifier's morphology
  heuristics
- Provenance for each of the 23 frozensets

The five reference distributions
(`instrument/routing/references/*.json`) are calibration
artefacts, not training data. Each carries `n` (sample size),
`corpus_description`, `calibration_date`, and `commit_hash`
fields; see `docs/LEXICONS.md` "Versioned references".

## Article 11 — Technical documentation

Article 11 requires technical documentation that demonstrates
the AI system's compliance with the regulation. The instrument
contributes the following to an Article 11 file:

| Requirement | Provided by |
|---|---|
| General description | `README.md`, `SCOPE.md` |
| Detailed description of elements and process | `docs/METROLOGY.md` (every formula), `docs/API.md` (every output field), `docs/LEXICONS.md` (every frozenset) |
| Detailed information on data and data governance | `docs/LEXICONS.md` |
| Detailed description of monitoring | `docs/VERIFICATION.md`, `docs/INTEGRATION.md` (control-chart cadence) |
| Validation and testing procedures, metrics | `docs/VALIDATION.md` (perturbation-detection study, method demonstration at n=15, plus the protocol for your own data), `docs/LENGTH_RESPONSE.md` (measured per-feature length response) |
| Description of risk management | `SECURITY.md` |
| Information on changes through lifecycle | `CHANGELOG.md` |

Your Article 11 file additionally needs to describe your overall
AI system; the instrument's documentation covers only the
measurement component.

## Article 12 — Record-keeping (logs)

Article 12(1) requires that high-risk AI systems "technically
allow for the automatic recording of events ('logs') over the
lifetime of the system". Article 12(2) names the purposes the
logging capability must serve: (a) identifying situations that may
result in the system presenting a risk (Article 79(1)) or a
substantial modification, (b) facilitating the post-market
monitoring referred to in Article 72, and (c) monitoring of
operation by deployers under Article 26(5). The instrument's audit
shape *is* the per-event record serving all three purposes:

- The `reading` block records what was measured.
- The `metadata` block records *with which version* the
  measurement was made, and *over which input bytes*.
- The `reproducibility_hash` lets you verify any stored log entry against a fresh re-run, providing tamper-evidence at
  the per-event level.
- Since 0.10.0 the record also carries its own calibration
  coordinates: a `percentile` on every distance record (hash-attested
  inside `content_sha256`), and — in the full shape — the reference
  envelope (`percentile`, `empirical_exceedance`), the per-feature
  calibration ledger (`p_two_sided` / `q_value` under a stated
  `family_policy`), and the reference's provenance echo
  (`collection_window`, `recalibration_policy`,
  `stability_summary`). A stored log entry is thereby interpretable
  against its named baseline without external context, and can be
  challenged on baseline fragility or staleness from the record
  alone.

To use the record for Article 12 logging:

1. Use the `audit` response shape for all production
   measurements. This is the canonical record.
2. Store the full audit-shape JSON for every measurement, keyed
   by `metadata.input_sha256` and
   `metadata.reproducibility_hash`.
3. Store the input bytes alongside the emission for your audit
   retention window.
4. Periodically verify a sample of stored emissions per
   `docs/VERIFICATION.md`.

Retention is not in Article 12 — it sits with the actors:
**Article 19** requires providers to keep the Article 12(1) logs
under their control for at least six months (longer where other
Union or national law requires), and **Article 26(6)** places the
same six-month floor on deployers for logs under their control.
Either way it is your storage policy; the instrument does not
enforce retention. (An earlier revision of this document
attributed the six-month floor to Article 12(2); that was
incorrect.)

## Article 13 — Transparency to deployers

Article 13 requires the system's instructions for use to be
"clear and complete" and to include specified information. The
instrument's contribution:

| Article 13(3) requirement | Document |
|---|---|
| Identity and contact details of the provider | `README.md`, `LICENSE` (Apache-2.0), the repository |
| Characteristics, capabilities and limitations | `SCOPE.md` |
| Performance | `docs/METROLOGY.md` (every formula), `docs/VERIFICATION.md` (the determinism contract) |
| Specifications for input data | `docs/API.md`, `INSTALLATION.md` |
| Information enabling deployers to interpret the output | `docs/METROLOGY.md` plus `docs/INTEGRATION.md` "The baseline-and-deviation pattern" |
| Predetermined changes | `CHANGELOG.md` |
| Human oversight measures | `SCOPE.md` "Inference is advisory" |
| Computational and hardware resources | `INSTALLATION.md` "Requirements" |
| Mechanisms to record events | `docs/API.md` "Audit shape" |
| Expected lifetime and maintenance | `CHANGELOG.md`, `SECURITY.md` |

## Article 14 — Human oversight

Article 14 requires that high-risk AI systems be designed to be
"effectively overseen by natural persons". The instrument's
contribution to oversight is its measurement-only posture:

- Inference layers (flags, register match/drift/break, coherence
  bands) are explicitly marked `ADVISORY` in their module
  docstrings. A person on your side is the natural person who
  decides whether and how to act on advisory output.
- The audit shape's per-token SFL trace
  (`?include=sfl_trace`) lets a human auditor trace any
  classification decision to the rule that produced it. No
  classification is opaque.
- The reproducibility hash provides a per-event verification
  primitive that lets a human auditor independently confirm any
  stored measurement.

Document in your Article 14 procedure how
inference outputs are consumed (or not) and which human role is
responsible for any action taken on the basis of inference
output.

## Article 15 — Accuracy, robustness and cybersecurity

### Accuracy

Article 15(2) requires the appropriate level of accuracy and a
declaration of accuracy metrics. The instrument's accuracy
properties:

- **Determinism (perfect accuracy on the
  reproducibility-hash dimension):** for any pin, the same input
  bytes produce the same output bytes. The
  `reproducibility_hash` is byte-equal across runs by
  construction — formally, an ISO 5725 repeatability standard
  deviation of exactly 0 under the five pins (see "Standards
  vocabulary" above for the full statement and evidence).
- **Surface-feature accuracy:** the instrument measures what its
  formulas say it measures. `docs/METROLOGY.md` documents every
  formula. There is no learned component; there is no error
  rate against a ground-truth label, because the instrument does
  not predict labels.
- **Demonstrated detection, at method scale (0.10.0):**
  `docs/VALIDATION.md` converts "detects drift" from asserted to
  demonstrated for eight mechanical perturbations, with exact
  Clopper–Pearson intervals and a **negative control pinned at the
  nominal operating point** (unperturbed documents: 1/11 detected,
  rate 0.09 [0.00, 0.41] against nominal 0.05; a failing negative
  control fails the CI gate). Do not over-read it: the study is an
  n=15 fixture-scale demonstration of the *method*, not a production
  accuracy claim. The declaration that scales is the one you run —
  the protocol in the same document, executed against your own
  reference and corpus.
- **Per-feature error-rate discipline (0.10.0):** where the
  baseline persists percentile grids, every emission carries
  two-sided empirical p-values (floored at 1/(n+1)) and
  Benjamini–Hochberg q-values with the family policy in the record
  (`register.evidence.feature_calibration`), so multiplicity over
  the ~57-feature family is controlled and auditable rather than
  left to the reader.
- **Cohort routing:** the auto-assigned register cohort is
  advisory and depends on the small (n=7-8 for non-LLM cohorts)
  reference calibration. Do not treat the auto-cohort as a precise
  classification; calibrate a
  reference baseline on their own deployment before relying on the
  distances (see `CALIBRATION.md`).

### Robustness

Article 15(3) requires resilience to errors, faults, and
inconsistencies. The instrument:

- Is total over byte input: any sequence of bytes produces a
  structurally complete output. There is no "valid input" /
  "invalid input" gate that could be exploited to produce
  inconsistent behaviour.
- Has zero external runtime dependencies, eliminating dependency-
  related failure modes.
- Has zero network calls at runtime, eliminating network-related
  failure modes.
- Has its layering DAG enforced by AST-level test, preventing
  silent architectural regressions.
- Has its environment-variable surface enforced by AST-level
  test, preventing silent configuration-leak regressions.

### Cybersecurity

The instrument's cybersecurity posture is documented in
`SECURITY.md`. Key points:

- No outbound network access at runtime
- Read-only filesystem-safe runtime
- No per-document state on disk
- Input size cap (`INSTRUMENT_MAX_WORDS`) prevents resource
  exhaustion

You are responsible for authentication, rate limiting, and TLS
termination at the proxy layer.

## Article 72 — Post-market monitoring (the primary operational fit)

> **Timeline note (June 2026).** On 7 May 2026 the EU institutions
> reached provisional political agreement on the "Digital Omnibus
> on AI", deferring the application of high-risk obligations for
> stand-alone Annex III systems from 2 August 2026 to
> 2 December 2027 (Annex I embedded systems: 2 August 2028), and
> adjusting some post-market-monitoring flexibility. Formal
> adoption is pending; until the amending act is published in the
> Official Journal, the original dates remain the law as written.
> Track adoption and the final text yourself; this document maps
> the obligations, not the timetable.

Article 72 requires providers of high-risk AI systems to "establish
and document a post-market monitoring system" that shall "actively
and systematically collect, document and analyse relevant data …
on the performance of high-risk AI systems throughout their
lifetime", allowing the provider "to evaluate the continuous
compliance of AI systems with the requirements set out in
Chapter III, Section 2".

This is the instrument's deployment pattern stated as an
obligation. The mapping:

| Article 72 element | Instrument contribution |
|---|---|
| Systematic collection of performance data | Audit-shape emission per production output (`docs/INTEGRATION.md`, baseline-and-deviation) |
| Documentation of collected data | Stored audit JSON, keyed by `input_sha256` + `reproducibility_hash`; tamper-evident via offline re-hash (`docs/VERIFICATION.md`) |
| Analysis throughout lifetime | Your deviation analysis against your own calibrated baseline (`docs/CALIBRATION.md`) |
| Evaluating *continuous* compliance | Version pins (`instrument_version`, `lexicon_version`, `catalog_sha256`, `core_code_sha256`) make the measurement surface stable across the monitoring window, so observed drift is attributable to the monitored system, not the meter |

Boundaries you must own:

- Article 72 is a **provider** obligation. If you deploy someone
  else's high-risk system, the analogous duties are
  Article 26(5) (monitor operation per the instructions for use)
  and Article 26(6) (retain logs ≥ 6 months); the same record
  stream serves both roles.
- The instrument supplies the *measurement* leg of a post-market
  monitoring system. Article 72(3) requires a documented
  post-market monitoring **plan**, which is part of the Annex IV
  technical documentation; the plan, the analysis procedures, and
  the corrective-action loop (Article 20, Article 73 serious-
  incident reporting) are yours.
- Article 72(3) tasked the Commission with adopting an implementing
  act establishing a template for the plan by 2 February 2026.
  Structure your plan against the template once available and verify its current adoption status; this document
  does not track it.
- The instrument measures *surface features of text outputs*. A
  post-market monitoring plan will normally also cover signals the
  instrument does not measure (task success, complaints, incident
  reports); the instrument is one input, not the whole system.

## The regulator record — assembling the defensible file

When a measurement (or a drift claim built on measurements) is
challenged, the assembled record for one monitored deployment is
five artefacts:

1. **The emission** — the audit-shape response, plus the optional
   `uncertainty` block (`?include=uncertainty` / `run.py
   --uncertainty`). Where the calibrated evidence coordinates are
   part of the record, store the `full` shape: its
   `register.evidence` blocks are pure functions of the
   hash-attested distances plus the pinned reference bytes —
   derived-advisory and recomputable, like the arc
   (`docs/VERIFICATION.md`, "Derived advisory fields").
2. **The pinned reference JSON** — your baseline, archived
   with its SHA256 (`tools.build_reference` prints it; the
   control-chart report echoes it as `reference.sha256`).
3. **The control-chart report** — `python -m tools.control_chart`
   output over the stored emission stream: byte-stable JSON whose
   `--as-of` date and (optional) `--arl` table are echoed into the
   report, so the report is a pure function of its own arguments and
   input bytes.
4. **`docs/VALIDATION.md`** — the perturbation-detection method
   demonstration, its negative control, and the protocol that
   scales the claim to your own data.
5. **`docs/LENGTH_RESPONSE.md`** — the measured per-feature length
   response: the evidence for why baselines compare like lengths
   with like.

Checklist — each element of a defensible claim, its exact field
path, and the artefact that carries it:

| Claim element | Field path | Artefact |
|---|---|---|
| Point estimate | `reading.<view>.features.<name>` (`shaper`, `other_shaper`, `stylometry`, `distributional`) | emission (audit/full); hash-attested via `content_sha256` |
| Uncertainty (CI / SE) | `uncertainty.features.<name>.ci_low` / `.ci_high` / `.se` / `.n_finite`; method in `uncertainty.method` / `.b` / `.seed` | emission with `?include=uncertainty` (outside the content hashes; replayable from the input bytes) |
| Percentile vs named baseline | `distances[].percentile` (audit shape; hash-attested) — the same value the full shape presents as `register.evidence.reference_envelope.percentile` with `empirical_exceedance`, `basis`, `percentile_method` | emission |
| Chart state | `summary.state` (`in_control` / `isolated_exceedance` / `sustained_shift_signal`); per-chart detail under `charts.individuals` / `charts.ewma` / `charts.cusum`; empirical ARL under `arl` | control-chart report |
| FDR policy | `register.evidence.feature_calibration.family_policy` (`method`, `family`, `m`, `sidedness`, `p_resolution_floor`) with per-feature `p_two_sided` / `q_value` | emission (full shape) |
| Reference provenance / stability / age policy | `register.evidence.reference_provenance` (`calibration_date`, `collection_window`, `n`, `recalibration_policy`, `stability_summary`); the age check as `baseline_age` (`as_of`, `baseline_age_days`, `age_status`) in the report; full blocks (`self_distance`, `stability`, `per_feature_quantiles`, `provenance`) in the reference file | emission (full) + control-chart report + reference JSON |
| Pins / hashes | `metadata.instrument_version` / `lexicon_version` / `catalog_sha256` / `distance_method` / `core_code_sha256` / `input_sha256` / `content_sha256` / `reading_sha256` / `reproducibility_hash`; `reference.sha256` and `emissions.sha256` in the report | emission + control-chart report |
| Method validation | detection-rate tables with exact Clopper–Pearson CIs; negative control 1/11 = 0.09 [0.00, 0.41] vs nominal 0.05; batch-power statements | `docs/VALIDATION.md` — an n=15 fixture-scale method demonstration; the protocol in the same file (run on your own corpus) is how the claim is earned at production scale |
| Length comparability | per-feature ρ, median relative change, classification | `docs/LENGTH_RESPONSE.md` |

## Annex IV — Technical documentation file

For high-risk AI systems requiring conformity assessment, Annex
IV requires a technical documentation file. The instrument's
contribution to that file is the union of:

- `README.md`
- `SCOPE.md`
- `INSTALLATION.md`
- `CHANGELOG.md`
- `SECURITY.md`
- `LICENSE`
- `docs/METROLOGY.md`
- `docs/LEXICONS.md`
- `docs/API.md`
- `docs/INTEGRATION.md`
- `docs/CALIBRATION.md`
- `docs/VALIDATION.md` (generated — regenerate, never hand-edit)
- `docs/LENGTH_RESPONSE.md` (generated — regenerate, never hand-edit)
- `docs/VERIFICATION.md`
- `docs/TROUBLESHOOTING.md`
- `docs/COMPLIANCE.md` (this document)

Note that the Article 72(3) post-market monitoring plan is itself
"part of the technical documentation referred to in Annex IV" —
your plan should cite the instrument documents above as its
measurement-mechanism description.

If you are required to produce a conformity assessment, include
these documents at the version corresponding to the
deployed `instrument_version`. The documents are immutable per
version: any change is published as part of a new version with a
`CHANGELOG.md` entry.

## Personal data in stored records

The instrument does not transform or redact input. Two storage
choices determine whether the compliance record itself contains
personal data:

- The **audit shape without `sfl_trace`** contains only derived
  numbers, offsets, and hashes — the original text is not
  recoverable from it. `input_sha256` is a fingerprint, not
  content.
- The **`sfl_trace` include reproduces the document's word tokens
  in order**. A stored record containing the trace is, for data-
  protection purposes, a copy of the document's words. The same
  applies to input bytes stored alongside emissions (step 3 under
  Article 12 above).

Where inputs may contain personal data, your retention policy for
stored records must reconcile the AI Act log-retention
floor (Articles 19 / 26(6): at least six months) with data-
protection minimisation and storage-limitation duties. A common
pattern: retain the trace-free audit shape for the full window,
and apply the shorter personal-data retention schedule to inputs
and traces. This is your call; the instrument only determines what
each shape contains.

## What this document does not cover

This mapping is intentionally specific to the EU AI Act. Other
regulatory frameworks (US sector-specific rules, UK requirements,
Japan's AI guidelines) may impose different obligations. The
instrument's compliance posture (deterministic, traceable,
auditable, advisory inference layers) is broadly applicable, but
the per-Article mapping above is EU-specific.

If you are subject to multiple frameworks, use the audit shape as
the canonical record and translate that record into each
framework's required form. The instrument provides one record; you
reframe it as needed.
