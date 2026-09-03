# hashfold

[![reproducibility](https://github.com/corgido/hashfold/actions/workflows/reproducibility.yml/badge.svg?branch=main)](https://github.com/corgido/hashfold/actions/workflows/reproducibility.yml)

A zero-dependency deterministic measurement library for prose. Same
input bytes in, same feature vectors out — on any host, every time.

hashfold takes long-form text and produces a fixed-shape numeric
record describing its surface features: SFL process-type proxies,
discourse-marker densities, lexical cohesion, register and stylometric
measures, per-slice trajectory streams, cross-view convergence, and
distances to reference distributions. Every number is a deterministic
function of the input bytes plus a pinned `(instrument_version,
lexicon_version, catalog_sha256)`, and every record carries a SHA-256
provenance chain that lets anyone re-verify it later. The CI matrix
(Linux, macOS, Windows and Alpine; CPython 3.11–3.14; glibc and musl;
C and fr_FR locales — ten determinism gates plus the test suite in
every cell) proves the cross-host claim on every push.

The library **measures**, it does not **interpret**. Where the API
surface contains labels, bands, or fired flags, those are advisory
convenience over the underlying numbers. The canonical record is the
audit shape: raw feature vectors + per-axis convergence pair-values +
distances to all reference points + provenance metadata + a
reproducibility hash.

| Read first | Read on demand |
|---|---|
| `README.md` (this file) | `docs/METROLOGY.md` — every formula |
| `SCOPE.md` — what it is and is not | `docs/LEXICONS.md` — lexicon provenance |
| `INSTALLATION.md` — install and run | `docs/API.md` — HTTP spec |
|  | `docs/INTEGRATION.md` — pipeline patterns |
| `SECURITY.md` — threat model, supply chain | `docs/VERIFICATION.md` — install verification |
| `CONTRIBUTING.md` — how to contribute | `docs/TROUBLESHOOTING.md` — common issues |
| `docs/CALIBRATION.md` — your baseline | `docs/COMPLIANCE.md` — EU AI Act + standards vocabulary |
|  | `docs/VALIDATION.md` — perturbation-detection study (generated) |
| `LICENSE` — Apache-2.0 | `docs/LENGTH_RESPONSE.md` — per-feature length response (generated) |
| `DISCLAIMER.md` — no warranty, not a compliance product |   |

The four-part primary emission:

- **`register`** — distance-vector to all 5 reference cohorts (raw),
  plus a single-cohort pick + match/drift/break label (advisory).
- **`arc`** — per-slice trajectory values + per-slice raw deltas +
  per-dimension arc summary (start/end/slope/range/monotone). The
  per-slice values are attested inside `reading.trajectory` (covered
  by `reading_sha256`/`content_sha256`, 0.9.1); the deltas and
  summaries are derived views recomputable from those values.
- **`flags`** — 12 discrete document-internal events (advisory; all
  flag thresholds are catalog-driven, see `catalog_v2.py`).
- **`coherence`** — `n_axes_agree / n_axes_measurable` scalar from
  5-axis cross-view agreement, plus a high/moderate/low band
  (advisory; the scalar is canonical).

A document is measured by two structurally parallel pipelines (the
"shaper" 13-d view and the "other-shaper" 37-d view) on the same
text, and convergence reports their pairwise agreement on five axes.
The two views share substantially the same lexicon vocabulary, so
this is internal consistency across substantially shared computation,
not independent corroboration — each axis in the record carries an
`independence` annotation saying which it is (see SCOPE.md,
"Cross-view consistency"). Convergence does not mean correctness; it
means two reductions made the same observation.

Stdlib only. No numpy, no sklearn. Zero file I/O in the measurement
hot path (lexicons + emission catalog are compiled into Python modules
at build time; routing references load lazily once per process). The
runtime is import-safe on any read-only filesystem.

## Measurement honesty

These measurements are deterministic, reproducible, and fast. They
capture surface-level linguistic features that are informative for
relative comparison — drift detection against a calibrated baseline,
corpus characterisation, stylometric fingerprinting. They are NOT
validated against expert linguistic annotation. hashfold measures
surface features of prose; it does not interpret meaning, detect
quality, or produce compliance verdicts. The SFL process-type
classifications are lexicon-lookup proxies, not parser output. The
discourse-marker densities count surface cue phrases, not rhetorical
relations. Use accordingly.

`SCOPE.md` states the same boundary in more detail ("Reproducible,
and validated at method-demonstration scale"), together with what
the validation study does and does not show. `DISCLAIMER.md` states
the warranty position in one paragraph.

## Quickstart

```
pip install -e .
pytest instrument/                                    # 651 tests, ~20 s

python run.py fixtures/source/llm_technical.md        # emit JSON for one file
python run.py fixtures/source/llm_technical.md \
              --uncertainty                           # + per-feature bootstrap CIs
python run.py                                         # boot HTTP server on :8000
hashfold                                              # same server, installed entry point
```

Library use:

```
from instrument.emit import emit

emission = emit(open("document.md", encoding="utf-8").read())
print(emission.metadata.reproducibility_hash)
```

HTTP round-trip — the canonical record is `?shape=audit`:

```
python -m instrument.serve.http &
curl -sX POST --data-binary @fixtures/source/llm_technical.md \
     'http://localhost:8000/?shape=audit'
```

Error bars on demand (`?include=uncertainty`, audit/full shapes):
deterministic sentence-bootstrap CIs per feature — SHA-256
counter-mode PRNG seeded from the document's own `input_sha256`, so
the same bytes give the same intervals on any host (B=200 default,
`INSTRUMENT_BOOTSTRAP_B`; costs seconds per document).

Chart a stored emission stream against your baseline (offline SPC —
individuals/CUSUM/EWMA, ~ ISO 7870; see `docs/INTEGRATION.md`):

```
python -m tools.control_chart --emissions out.jsonl \
    --reference /etc/instrument/references/acme_normal_v1.json --arl
```

For the most complete record, also include the per-token SFL
classification trace. Note: the trace contains every word token of
the document in order — a record stored with `sfl_trace` inherits
the input's data-protection status (see `docs/COMPLIANCE.md`,
"Personal data in stored records"):

```
curl -sX POST --data-binary @document.md \
     'http://localhost:8000/?shape=audit&include=sfl_trace'
```

## Calibrate your own baseline

The bundled references locate prose against five generic cohorts.
Your baseline is distance to **your** normal — your model, your
prompts, your domain (`docs/CALIBRATION.md` explains why this cannot
ship pre-built). The supported path is one stdlib-only tool plus one
environment variable:

```
python -m tools.build_reference \
    --corpus-dir ./sample_outputs \
    --name acme_normal --cohort acme_normal --version v1 \
    --scope "prod prompts, model X, May 2026" \
    --collection-window "2026-05-01..2026-06-30" \
    --out /etc/instrument/references

INSTRUMENT_REFERENCES_DIR=/etc/instrument/references \
    python -m instrument.serve.http
# then: POST /?shape=audit&register_hint=acme_normal
```

The tool measures your corpus, builds the reference (deterministic
pure-Python PCA), self-validates it through the same loader and
distance code the runtime uses, and persists the cross-validated
self-distance null you baseline against — at runtime, every
emission then locates its distance as a percentile within that
null. `--collection-window` (required, 0.10.0) records when the
corpus was collected; it is echoed into every emission's
provenance, so records carry their baseline's vintage. The build
prints the **stability figures** alongside the null: jackknife
centroid shift (in reference std units), loading alignment |cos|,
and the held-out p95 range across replicates — how much of the
baseline is signal versus sampling accident, plus tiered
minimum-corpus warnings (below n=10 / n=30; see
`docs/CALIBRATION.md` §8–9). Malformed references fail at server
boot, not mid-request. `--readings-out` additionally writes
per-document features as JSONL for your own analysis.

## Response shapes (`?shape=`)

All five are response filters — the computation is identical.

- `audit` — `{reading, distances, metadata, sfl_trace?}`. Pure
  measurement: raw feature vectors, per-axis convergence pair-values,
  distances to all 5 references, full provenance. No flags, no register
  label, no coherence band. This is the canonical record. Optionally
  includes per-token SFL classification trace via `?include=sfl_trace`.
- `full` — `{emission, reading}`. Everything: the audit content plus
  the inference layer (flags, labels, bands). Use when both records
  and advisories are needed.
- `flags_only` — `{flags, coherence}`. Tiny payload for low-latency
  monitoring (see "Performance envelope" below for the measured
  latency ceiling). Advisory only — flags are catalog-thresholded
  events, not the canonical record; hashfold is not a runtime gate
  (SCOPE.md).
- `reading_only` — `{shaper, other_shaper, convergence}`. For clients
  that build their own emission logic.
- `compact` — four-field envelope: flag types, register label,
  coherence label, n_words. Fits log pipelines.

## Layout

```
instrument/                The shipping code. 67 source files; no env
  kernel/                  L1  tokens, sentences, paragraphs, cleaning,
                               slicer, regimes, grid, nanmath, distance,
                               features/{sfl,rst,cohesion,register,
                               stylometry,trajectory_features}
  lexicons/                L1  23 frozensets, generated from _data/
  reading/                 L2  flat (13d), extended (37d), convergence
                               (5-axis), embedder (flat/regime/trajectory),
                               joint, document
  emissions/               L3  types, assembler, catalog, coherence,
                               slice_labels, structural_profile,
                               flags/{12 per-flag modules}
  routing/                 L3  reference, pc, router (+ 5 bundled SEED
                               reference JSONs — not a production
                               baseline; see docs/CALIBRATION.md)
  serve/                   L4  config, shape (pure handler), http
  emit.py                  L4  top-level emit(text) orchestrator
  config.py                L4  Config + from_env() — only env reader
  types.py, errors.py      L1  Tokens, Slice, Reading + error types

_data/                     Source-of-truth JSONs (lexicons, emissions catalog).
                           Builders under tools/ compile these to Python
                           modules committed inside instrument/.

tools/                     Build and verification tooling. User-facing
                           entry points:
  build_reference.py         build your own baseline reference from
                               a corpus of your own LLM outputs
  control_chart.py           offline SPC report (individuals/CUSUM/
                               EWMA + empirical ARL) over a JSONL
                               emission stream
  validation_study.py        perturbation-detection study; --corpus-dir
                               mode runs the protocol on your own data
  length_invariance.py       per-feature length-response audit
                               (publishes docs/LENGTH_RESPONSE.md)
  build_sbom.py              emit a CycloneDX SBOM for supply-chain review
  build_lexicons.py          regenerate compiled lexicon modules
  build_catalog.py           regenerate compiled catalog modules
  build_joint_golden.py      regenerate joint-reading regression goldens
  build_emit_golden.py       regenerate emit() regression goldens
  check_layers.py            verify the L1→L4 import DAG

fixtures/
  source/                  purposeful source documents (one per
                             reference cohort + edge cases); see
                             fixtures/source/RATIONALE.md
  joint_golden/            joint_reading regression goldens
  emit_golden/             emit() regression goldens
  uncertainty_golden/      deterministic-bootstrap goldens (B=50)
  validation/              length-response + validation-study
                             artifacts (CI-gated)

docs/                      Reference documentation (API, integration,
                             verification, troubleshooting, compliance).

run.py                     Entry point: emit a file or boot the server.
pyproject.toml             Package config. testpaths = ["instrument"].
```

## Layering (enforced)

```
L1  kernel / lexicons / types / errors     ←  stdlib only
L2  reading                                ←  L1
L3  emissions / routing                    ←  L1, L2
L4  serve / emit / config                  ←  L1, L2, L3
```

`tools/check_layers.py` walks every `from instrument.X import ...`
statement and fails on any upward edge. A pytest wrapper at
`instrument/tests/test_layering.py` runs it on every suite run, so the
DAG is a test contract, not a convention. `test_no_env_reads.py`
similarly asserts that nothing outside `instrument/config.py` and
`instrument/serve/` reads `os.environ`.

## Build tools

All of these are deterministic and drift-check. The first six are
the core gates; the last four were added in 0.10.0. CI runs all ten
on every cell of the matrix:

```
python -m tools.build_lexicons --version v1 --check
python -m tools.build_catalog  --version v2 --check
python -m tools.build_core_hash --check
python -m tools.build_joint_golden --check
python -m tools.build_emit_golden  --check
python -m tools.check_layers

python -m tools.migrate_references_0_9_1 --check
python -m tools.build_uncertainty_golden --check
python -m tools.length_invariance --check
python -m tools.validation_study --profile smoke --check
```

If a source JSON changes, the corresponding `--check` fails until the
generated module is regenerated and committed. The goldens freeze
end-to-end output on the fixture set under `fixtures/source/`; any
schema bump or numerics drift surfaces as a diff.

## Running it

Direct library use (`instrument.emit.emit`) and the bundled HTTP
server are the two supported transports. `python -m
instrument.serve.http` (or the installed `hashfold` entry point) runs
the stdlib `ThreadingHTTPServer` with `INSTRUMENT_HOST`,
`INSTRUMENT_PORT`, `INSTRUMENT_RESPONSE_SHAPE`, and
`INSTRUMENT_MAX_WORDS` optionally overriding defaults.

The server is a single stdlib process and runs anywhere Python runs;
`INSTALLATION.md` has a minimal container recipe. (A Cloudflare
Workers adapter existed through 0.8.x; it shipped untested and was
removed in 0.9.0 — see CHANGELOG.)

## Provenance and reproducibility

hashfold's value is **deterministic measurement**, not analysis or
interpretation. Each emission's `metadata` block carries:

- `instrument_version` — pinned at `instrument.__version__`
- `schema_version` — joint-reading schema
- `emission_version` — catalog version (e.g. `v2`)
- `lexicon_version` — pinned by `instrument/lexicons/__init__.py`
- `catalog_sha256` — SHA256 of the source catalog JSON
- `distance_method` — names the PC-distance formula
  (`feature_zscore_l2` today)
- `input_sha256` — SHA256 of the raw transport bytes (file bytes on
  the CLI, request body on HTTP — captured before any decode or
  newline normalisation; library callers passing a `str` get
  `sha256(text.encode("utf-8"))`)
- `content_sha256` — SHA256 over the quantised canonical record
  (`reading` + `distances`, minus volatile `ts`): the hash of what was
  measured
- `reading_sha256` — SHA256 over the pure-core `reading` alone: the
  reference-independent witness
- `core_code_sha256` — build-time hash of the measurement-core source
  (kernel + reading + lexicons), pinning the algorithm
- `reproducibility_hash` — SHA256 over the ten stable components
  above; one scalar to compare instead of ten

Anyone storing an emission can re-run the same input under the
same pin and verify byte-equality of every field except `timestamp`,
or verify a stored record offline by recomputing its own
`content_sha256` / `reading_sha256` (see `docs/VERIFICATION.md`).

**Tamper semantics — two separate integrity surfaces.**
`input_sha256` is raw-byte integrity: change one byte of the input
and it (and therefore `reproducibility_hash`) fails. The measurement
hashes are an *equivalence fingerprint*, not a character-level
integrity check: the measurement is computed over the canonicalised
text (CRLF/CR→LF, BOM stripped, trailing whitespace and blank-line
run length normalised — `kernel/cleaning.canonicalise`), so two
inputs differing only in that non-semantic formatting share the same
`reading_sha256`/`content_sha256` by design. A tamper that changes
any surfaced number fails offline recomputation; a tamper that
changes only non-semantic bytes is caught by `input_sha256`. Which
hash to check depends on which question is being asked — "is this
the submitted document?" vs "are these the numbers it measures to?".

This is not a compliance product. It is a library with an unusually
strong reproducibility guarantee, which happens to make it useful for
record-keeping work; `docs/COMPLIANCE.md` maps the record to EU AI
Act and ISO vocabulary for anyone doing that work.

## Performance envelope

Measured on a commodity x86-64 container (CPython 3.12): 500 words
≈ 0.02 s · 2k ≈ 0.07 s · 10k ≈ 0.3 s · 50k ≈ 1.5 s · 100k ≈ 3 s,
scaling roughly linearly. The library is comfortably interactive
("fast enough to act as a control") **up to roughly 10k words per
document**; very large documents are batch work, not real-time work.
The serve layer's `max_words` cap (default in `config.py`) is the
control for this.
Calibration of the reference baseline is your responsibility and is
a separate concern from verification (see `docs/CALIBRATION.md`).

Inference layers are explicitly marked `ADVISORY` in their
docstrings: `emissions/coherence.py`, `emissions/catalog.py`,
`emissions/flags/__init__.py`, `routing/router.py`. Catalog v2
thresholds are documented as pre-calibration placeholders. The
project does not plan a v3 calibration pass; the roadmap instead
adds reference points (more cohorts as feature-space coordinates),
not decision rules.

## Status

Current version: **0.10.0** — calibrated claims. Where 0.9.1 proved
each number is computed correctly, 0.10.0 adds the machinery to say
how often a number lies: references built by `tools.build_reference`
persist their full cross-validated null plus provenance, stability,
and a recalibration policy, so every emission carries its distance's
percentile and empirical exceedance against a *named* baseline;
per-feature empirical p-values and Benjamini–Hochberg q-values ship
with the family policy in the record; an opt-in deterministic
bootstrap (`--uncertainty` / `?include=uncertainty`) puts replayable
error bars on every feature; `instrument.spc` + `tools.control_chart`
chart the emission stream in ISO 7870 vocabulary with empirically
measured ARL; `dist.mattr` joins as the length-corrected TTR, with
every feature's measured length response published in
`docs/LENGTH_RESPONSE.md`; and a CI-gated perturbation-detection
study with a negative control (`docs/VALIDATION.md`) demonstrates
the method at fixture scale. Everything added is a descriptive
reference coordinate, never a decision rule — no catalog byte
changed, and you still own every threshold (`CHANGES-0.10.0.md`).

Working: the full four-part emission surface, the `audit` shape as
the canonical record, optional `?include=sfl_trace` per-token
trace and `?include=uncertainty` bootstrap CIs, 14-fixture
regression goldens plus uncertainty goldens, live HTTP adapter,
all tests green (651), all build-tool `--check` modes
green, layering DAG enforced by test, env firewall enforced by
AST test, length-response audit and validation-study smoke gated
in CI.

## Background

hashfold was built as a solo project to explore whether
deterministic surface-feature measurement could support EU AI Act
compliance logging: fingerprint every LLM output the same way on
every host, chain the record to its input and its code by hash, and
let a calibrated baseline say when the output distribution moves.

The measurement layer works. It is deterministic, reproducible
across the CI matrix, and fast. What it lacks is criterion validity:
no study has tested the features against human linguistic annotation,
so the numbers are surface heuristics with known reproducibility and
unknown agreement with what a linguist would say. That gap means it
cannot be a standalone compliance product — nobody downstream closes
it by "setting their own baseline". It is released instead as an
open-source library, and as a demonstration of the engineering
thinking behind it: stdlib-only, enforced layering, cross-host
determinism as a testable property, an audit hash chain, and a strict
separation of measurement from inference.


## License

Apache-2.0. See `LICENSE`.
