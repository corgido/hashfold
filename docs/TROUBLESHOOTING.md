# Troubleshooting

This document maps common symptoms to causes and fixes. Items are
ordered by how often they came up in real deployments.

## Determinism

### Symptom: same input produces different `reproducibility_hash`

Cause: the `(instrument_version, lexicon_version, catalog_sha256,
distance_method)` pin has changed between the two runs. Verify all
four fields in the metadata block.

Fix: pin to a single version. If you upgraded without
re-baselining, either pin back to the old version or accept the
new measurements as a new baseline. A published version's
measurement behaviour does not change; if the four pin values match
and the hash differs, that is a defect — report it.

### Symptom: stored emission's `reproducibility_hash` differs from a fresh run

Cause: either the storage representation was modified
(re-canonicalised, re-formatted, re-encoded) after the hash was
computed, or the input bytes were modified.

Fix: store emissions byte-for-byte. The hash is computed over a
specific canonical form of the JSON; any modification invalidates
it. Re-run the input bytes through the same pin to get a fresh hash
that matches the stored one.

## Routing

### Symptom: register reports `unprojectable`

Cause: the document is below the 150-word measurement envelope,
contains too much non-prose structure (table-heavy, code-heavy), or
has too many features that could not be measured.

Fix: this is the correct behaviour for inputs the instrument
cannot meaningfully measure. The audit shape still produces a
structurally complete record with `null` for the unmeasurable
fields. Your downstream analysis must decide whether to exclude or
specially handle unprojectable emissions.

If a document you expect to be projectable is reporting
unprojectable, inspect:

- `metadata.n_words` — is the document under the 150-word floor?
- `register.evidence.unprojectable_subtype` — what was the
  classification? `reference_table`, `instrument_format`,
  `mixed_structural_fp`, or `insufficient_prose`?
- `register.evidence.structural_profile` — what fraction of the
  document is non-prose?

### Symptom: `register.distance` is null

Cause: at least one feature value was NaN, which contaminates the
PC projection. The instrument refuses partial projections (a
partial projection would silently omit features).

Fix: inspect the `reading.shaper.features` and
`reading.other_shaper.features` blocks for NaN values. The most
common cause is the `register.sentence_length_variance` feature
being undefined on a single-sentence document, or any feature
gated by the 150-word envelope returning NaN below the envelope.

## Cross-view divergence

### Symptom: many documents fire the `cross_view_diverge` flag

Cause: the shaper (13-d) and other-shaper (37-d) views are reading
the same prose differently, on a majority of axes (4 of 5).

The flag is informational — it does not say which view is correct.
Common causes when both views are right:

- The document is in a register the references were not calibrated
  on (e.g. very technical mathematical prose). Both views measure
  it correctly, but the calibrated normalisation ranges paper over
  axis-specific differences in unusual prose.
- The document contains a structural element (large code block,
  reference table) that affects the two views differently.

Fix: this is not a defect; it is the cross-validation premise
working as intended. Investigate the raw per-axis values in the convergence block, not just the flag. See
`SCOPE.md` "Cross-validation premise".

## Per-token classification

### Symptom: SFL classification appears wrong

Cause: the SFL classifier uses a frozen lexicon plus morphology
heuristics. Common false positives:

- `-ing` and `-ed` morphology heuristics misclassify adjectives
  as material processes when the adjective is not in the
  `KNOWN_ADJECTIVAL_PARTICIPLES` deny-list.
- `-s` plural nouns are not generally tagged as verbs, but the
  deny-list (`KNOWN_PLURAL_NOUNS`) is incomplete.

Fix: request the per-token trace via `?include=sfl_trace` to see
exactly which rule fired. Each token reports its `rule` field. If
a misclassification is structural (a deny-list omission rather
than a genuine ambiguity), report it as a defect for review
against the next lexicon snapshot.

If you need a custom deny-list for your domain (e.g. medical
terminology, legal jargon), this is a lexicon-snapshot request. The
v1 deny-lists are English-language; extension is via a new lexicon
version (see `CONTRIBUTING.md`).

## Performance

### Symptom: HTTP responses take longer than expected

Cause: tokenisation cost scales linearly with input size, but
specific edge cases (extremely long unbroken paragraphs, very
deeply nested markdown) can show O(n²) behaviour in the slicer.

Fix: profile the request to identify the bottleneck. Typical
performance is ~1 ms per kB of input on commodity hardware. If
you are seeing >100 ms on a <100 kB document, open an issue with
the input attached.

### Symptom: out of memory on very large inputs

Cause: the instrument loads the input as a single string. A 100 MB
input loads as a 100 MB Python string plus working memory.

Fix: enforce `INSTRUMENT_MAX_WORDS` at the proxy level if your
pipeline can encounter very large inputs. The default cap (10 000
words) corresponds to ~70 kB of typical English prose; adjust it for
longer-document workflows.

## Configuration

### Symptom: HTTP server returns the wrong default shape

Cause: `INSTRUMENT_RESPONSE_SHAPE` environment variable is set to
something other than the intended default.

Fix: check the deployment's environment. The shipped default is
`audit`; some legacy deployments may have inherited
`flags_only` from earlier versions.

### Symptom: env-firewall test fails after a local modification

Cause: an `os.environ` read was added to a non-config /
non-serve module. The firewall test (`test_no_env_reads.py`)
allows `os.environ` only in `instrument/config.py` and
`instrument/serve/`.

Fix: route configuration through `instrument/config.py`. If you
need to inject configuration into the kernel, the
correct pattern is to have config read the env, then pass values
explicitly into the kernel call. Do not bypass the firewall.

## Tests

### Symptom: golden tests fail on first run

Cause: a fixture, a kernel feature, or a build artefact was
modified without regenerating goldens.

Fix: run `tools.build_joint_golden --check` to identify which
goldens drifted. If the drift is intentional, regenerate with
`tools.build_joint_golden` (no `--check`) and commit. If the
drift is unintentional, revert the change and re-run the suite.

### Symptom: layering test fails

Cause: a new import in `instrument/X` violates the L1→L4 DAG.

Fix: see `tools.check_layers` output for the specific violation.
The fix is generally to either move the imported symbol to a
lower layer, or to invert the dependency by passing the symbol in
as a parameter rather than importing it.

## Reporting defects

If the symptoms above do not match your situation, open an issue
(`.github/ISSUE_TEMPLATE/bug_report.md` lists the fields). Useful
reports include:

- The exact input bytes that triggered the symptom (or a
  minimised reproducer)
- The pinned `(instrument_version, lexicon_version,
  catalog_sha256, distance_method)`
- The `reproducibility_hash` of the offending emission
- The expected behaviour and the observed behaviour
- The output of the verification protocol
  (`docs/VERIFICATION.md`) on your deployment

This is a solo-maintained project; there is no response SLA.


## `register.label` is `unprojectable` with subtype `unsupported_script` (0.9.1)

The document is substantively non-Latin (≥50 non-Latin letters and
≥30% of all letters). The instrument measures Latin-script prose
only (`SCOPE.md`, "Out of scope"); the tokeniser is ASCII-Latin, so
non-Latin text contributes zero word tokens. This is a loud refusal,
not a failure — the evidence block carries the script counts
(`n_latin_letters`, `n_nonlatin_letters`, `nonlatin_ratio`). Mixed
documents that still project carry the
`substantive_non_latin_content` soft flag in the reading instead.

## Boot log shows `reference_feature_schema_mismatch` (0.9.1)

A registered reference file uses feature keys the running instrument
no longer emits (typically `rst.contrast_pressure` /
`rst.elaboration_pressure` from a pre-0.9.1 build). That reference
cannot project — every distance against it is `null`. Rebuild it
with `python -m tools.build_reference` under the current instrument
version, shipped as a new `--version` (never edit a reference file
in place — its bytes are the coordinate system).

## `router_flags` shows `auto_routed`

Normal. No `register_hint` was supplied, so the router auto-selected
the nearest reference; the flag states how the reference was chosen.
(Before 0.9.1 this state was misleadingly named `undeclared_hint`.)
