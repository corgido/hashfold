# API reference

The instrument exposes one HTTP endpoint and one CLI entry point.
The compute path is identical; the transport differs.

## HTTP

```
POST /                        the only endpoint
?shape=<shape>                response shape selector
?include=<comma-separated>    optional expansions
```

### Request

| Aspect | Value |
|---|---|
| Method | `POST` only. Other methods return `405`. |
| Body | The text to measure. UTF-8 expected. |
| Content-Type | Ignored — the body is treated as text. |
| Body size cap | `INSTRUMENT_MAX_WORDS` words (default 10000). Above the cap, returns `413`. |
| Authentication | None. Deploy behind a proxy that handles auth. |

### Response

| Status | Meaning |
|---|---|
| `200` | Measurement record, JSON body |
| `400` | Empty body or malformed query |
| `413` | Body exceeds `INSTRUMENT_MAX_WORDS` cap |
| `405` | Method other than POST |
| `500` | Internal error (should not occur — the instrument is total over byte input) |

`Content-Type: application/json; charset=utf-8` on every 200.

### Query parameters

#### `shape` — response shape

Five values; the underlying computation is identical for all. The
default is `audit` (configurable via `INSTRUMENT_RESPONSE_SHAPE`).

| `shape=` | Returns | Recommended use |
|---|---|---|
| `audit` | `{reading, distances, metadata, sfl_trace?}` | Compliance recording. The canonical record. |
| `full` | `{emission, reading}` | Audit content + advisory inference layer |
| `flags_only` | `{flags, coherence}` | Low-latency monitoring (sub-second up to ~10k words; see README "Performance envelope"). Advisory only. |
| `reading_only` | `{shaper, other_shaper, convergence}` | Clients that build their own emission logic |
| `compact` | `{flags, register, coherence, n_words}` | Log pipelines. Four-field envelope. |

The `audit` shape carries no inference: no flag firing, no register
match/drift/break label, no coherence band. It is the recommended
response for EU AI Act-style logging. See `COMPLIANCE.md`.

#### `include` — optional expansions

Comma-separated list. Two values are defined:

| `include=` | Effect |
|---|---|
| `sfl_trace` | Adds a per-token classification trace to the response. Each entry reports the token, the classification (mental / verbal / relational / behavioral / material / existential / none), and the rule that fired (lexicon hit, morphology heuristic, deny-list, default). Significantly larger payload. |
| `uncertainty` | Adds a top-level `uncertainty` block: deterministic per-feature bootstrap confidence intervals (see "Uncertainty block" below). Applies to the `audit` and `full` shapes only; other shapes silently omit it. Significantly more compute per request (see the cost note below). |

Multiple values can be combined:
`?shape=audit&include=sfl_trace,uncertainty`. Unknown include
values return `400`. Both expansions attach at the top level of the
response and ride **outside** `content_sha256` /
`reproducibility_hash`, which are computed before any include
exists.

## Audit shape (canonical record)

The audit shape is the recommended record for compliance pipelines.
The schema:

```
{
  "reading": <joint reading>,
  "distances": [
    {"name": "academic_prose",      "version": "v1", "distance": <float | null>, "percentile": <float | null>},
    {"name": "dialogue_prose",      "version": "v1", "distance": <float | null>, "percentile": <float | null>},
    {"name": "journalism_prose",    "version": "v1", "distance": <float | null>, "percentile": <float | null>},
    {"name": "literary_prose",      "version": "v1", "distance": <float | null>, "percentile": <float | null>},
    {"name": "llm_technical_prose", "version": "v1", "distance": <float | null>, "percentile": <float | null>}
  ],
  "metadata": {
    "emission_version":     "v2",
    "instrument_version":   "0.10.0",
    "schema_version":       "0.10.0",
    "lexicon_version":      "v1",
    "catalog_sha256":       "<sha256 of catalog source JSON>",
    "distance_method":      "feature_zscore_l2",
    "input_sha256":         "<sha256 of input bytes>",
    "content_sha256":       "<sha256 of quantised {reading, distances} minus ts>",
    "reading_sha256":       "<sha256 of the pure-core reading>",
    "core_code_sha256":     "<build-time hash of core source>",
    "reproducibility_hash": "<sha256 of the ten stable fields>",
    "n_words":              <int>,
    "n_sentences":          <int>,
    "timestamp":            "<UTC ISO 8601>"
  },
  "sfl_trace":   [<...>],  // present only if ?include=sfl_trace
  "uncertainty": {<...>}   // present only if ?include=uncertainty
}
```

The `reading` block is the joint reading dict described under
"Reading shape" below.

The `distances` array has one entry per registered reference
(`{name, version, distance, percentile}`). A `null` distance means
the reading could not be projected onto that reference's PC space
(any input feature was NaN/null). `percentile` (0.10.0) is the
mid-rank position of the distance within *that* reference's
persisted self-distance null — `null` when the reference carries no
full null (all bundled seeds, 0.9.1-era references) or the distance
is unmeasurable. The `percentile` values are part of the `distances`
list and therefore inside `content_sha256`. See
`docs/METROLOGY.md` §12.3.

The `metadata` block is the provenance record. The
`reproducibility_hash` is a SHA256 over the ten stable fields
`(instrument_version, schema_version, emission_version,
lexicon_version, catalog_sha256, distance_method, input_sha256,
content_sha256, reading_sha256, core_code_sha256)`. Anyone who
stores `(input_bytes, reproducibility_hash)` can verify a measurement
against a fresh run by re-computing the hash, or rehash a stored
record offline against its own `content_sha256` / `reading_sha256`.
The wall-clock `timestamp` is excluded from the hash. The reference
baseline the `distances` are measured against must be calibrated on
your own deployment — see `docs/CALIBRATION.md`.

## Uncertainty block (`?include=uncertainty`)

Opt-in per-feature bootstrap confidence intervals, attached at the
top level of the `audit` and `full` shapes (like `sfl_trace`). CLI
equivalent: `python run.py path.md --uncertainty`. Schema:

```
{
  "method":      "sentence_bootstrap_paragraph_shape_v1",
  "b":           <int>,      // replicate count
  "seed":        "<the document's input_sha256>",
  "n_sentences": <int>,
  "features": {
    "<feature_name>": {
      "point":    <float | null>,  // the unresampled value
      "ci_low":   <float>,         // 2.5th percentile of replicates
      "ci_high":  <float>,         // 97.5th percentile of replicates
      "se":       <float>,         // bootstrap standard error
      "n_finite": <int>            // finite replicates out of b
    }
    // or, per feature, when fewer than half the replicates are finite:
    // {"status": "unstable_under_resampling", "n_finite": <int>}
  }
}
```

Documents with fewer than 8 sentences return
`{"status": "too_few_sentences_for_bootstrap", "n_sentences": <int>,
"method": ...}` instead of intervals — a refusal, not an interval.

Semantics: sentences are resampled with replacement, preserving the
document's paragraph shape; all four scalar feature views are
recomputed per replicate. The PRNG is SHA-256 in counter mode
(`kernel/detrandom.py`) seeded `"{method}:{input_sha256}"`, so the
block is a **pure function of the input bytes and `b`** — same
bytes in, same error bars out, on any conforming host. It rides
outside `content_sha256` / `reproducibility_hash` (which are
computed before any include exists); verify it by replaying, not by
rehashing. Full field-level spec: `docs/METROLOGY.md` §12.4.

Cost: the request recomputes every feature view `b` times. At the
default B=200, expect roughly 2.5–6.5 s for a kiloword-scale
document (scales linearly in `b`). The server's replicate count is
configurable via `INSTRUMENT_BOOTSTRAP_B` (default 200); the CLI
flag uses the default.

## Reading shape

The `reading` block within `audit` and `full` has the structure
below. (The lighter `reading_only` shape is a subset — it returns
only `shaper`, `other_shaper`, and `convergence`, omitting
`stylometry` and `distributional`.)

```
{
  "schema_version":      "0.10.0",
  "ts":                  "<UTC ISO 8601>",
  "n_words":             {"shaper": <int>, "other_shaper": <int>},
  "below_envelope":      {"shaper": <bool>, "other_shaper_soft_flags": [...]},
  "soft_flags":          [...],
  "shaper": {
    "feature_order":     [<13 feature names>],
    "features":          {<feature_name>: <float>}
  },
  "other_shaper": {
    "feature_order":     [<37 feature names>],
    "features":          {<feature_name>: <float>}
  },
  "stylometry": {
    "feature_order":     [<7 feature names>],
    "features":          {<feature_name>: <float | null>}
  },
  "distributional": {
    "feature_order":     [<12 feature names, keyed dist.*>],
    "features":          {<feature_name>: <float | null>}
  },
  "convergence": {
    "axes": {
      <axis_name>: {
        "shaper_key":         <str>,
        "shaper_value":       <float | null>,
        "shaper_normalised":  <float | null>,
        "other_keys":         [<str>],
        "other_value":        <float | null>,
        "other_normalised":   <float | null>,
        "other_reducer":      <str>,
        "direction":          <"agree_high" | "agree_mid" | "agree_low" | "diverge" | "incomparable">,
        "confidence":         <float | null>
      },
      ...   // 5 axes total
    },
    "overall":              <"converge" | "diverge" | "mixed">,
    "n_axes_agree":         <int>,
    "n_axes_diverge":       <int>,
    "n_axes_incomparable":  <int>
  }
}
```

`shaper` is the 13-dim flat reading; `other_shaper` is the 37-dim
extended reading. `stylometry` is 7 surface measures (LZ78
compression ratio, comma density, etc.); `distributional` is 12
distributional/information-theoretic measures (hapax ratio, Yule's K,
entropies, burstiness, and — since 0.10.0 — `dist.mattr`, the
length-corrected moving-average TTR). Convergence reports per-axis
agreement between shaper and other_shaper.

For the formula behind every feature in every block, see
`docs/METROLOGY.md`.

## Full shape (audit + inference)

The `full` shape returns `{emission, reading}` where `reading` is
as above and `emission` is the inference layer:

```
{
  "register": {"label": <str>, "cohort": <str>, "distance": <float | null>, "evidence": {...}},
  "arc":      {"per_slice": [...], "per_dimension": {...}, "n_slices": <int>},
  "flags":    [{"type": <str>, "severity": <str>, "evidence": {...}}, ...],
  "coherence": {"value": <float | null>, "label": <str | null>, ...},
  "metadata":  {...}
}
```

**Every field that is a label, band, or fired-flag entry is
advisory.** See `SCOPE.md` "Inference is advisory" and
`emissions/coherence.py` / `emissions/catalog.py` /
`emissions/flags/__init__.py` / `routing/router.py` for the
explicit `ADVISORY:` markers.

`register.evidence` carries the calibration coordinates (0.10.0),
all pure functions of the hash-attested distances plus the pinned
reference bytes (derived-advisory — `docs/VERIFICATION.md`):

- `reference_envelope` — the chosen reference's confidence
  envelope: `self_distance_n` / `self_distance_median` /
  `self_distance_p95`, `position` (`within_p95` / `beyond_p95`),
  and — when the reference persists the full null — `percentile`,
  `empirical_exceedance`, `basis`, `percentile_method`.
  Degradations: `status: seed_reference_no_confidence_envelope`
  (bundled seeds), `percentile_status:
  reference_predates_null_distribution` (0.9.1-era references).
- `reference_provenance` — static echo of the reference's
  provenance: `calibration_date`, `collection_window`, `n`,
  `recalibration_policy`, `stability_summary`
  (`max_centroid_shift_std`, `min_loading_alignment`). Degradation:
  `provenance_status: pre_0_10_reference`.
- `feature_calibration` — per-feature empirical calibration under
  BH FDR control: `per_feature.<name>` = `{value, percentile,
  p_two_sided, q_value}`, plus `family_policy` (`method`, `family`,
  `m`, `sidedness`, `p_resolution_floor`) and `reference_n`.
  Degradations: `status: reference_lacks_feature_quantiles`,
  `status: no_finite_features_for_calibration`.
- `distances_to_all_references` — the same
  `{name, version, distance, percentile}` records the audit shape
  exposes as `distances`.

Field-level formulas and degradation semantics:
`docs/METROLOGY.md` §12.

## CLI

The CLI emits one emission on stdout:

```
python run.py path/to/document.md
python run.py path/to/document.md --uncertainty
```

Reads the file's raw bytes (they become `input_sha256`), decodes as
UTF-8, and emits one JSON object. With `--uncertainty` the output
is `{"emission": <emission>, "uncertainty": <block>}` — the
bootstrap block seeded from the emission's own `input_sha256`, so
the intervals are replayable from the file alone; without the flag
the output is the emission dict, byte-identical to the legacy CLI.
The CLI always uses the default B=200 (`INSTRUMENT_BOOTSTRAP_B`
configures the HTTP server, not the CLI).

Exit codes: `0` success, `1` file not found (or `--uncertainty`
without a file path), `2` file is not valid UTF-8.

## Determinism contract

For any pin
`(instrument_version, lexicon_version, catalog_sha256, distance_method)`,
the instrument guarantees that the same input bytes produce the
same output bytes — except for the `metadata.timestamp` field,
which records when the measurement was made (and is excluded from
`reproducibility_hash` for that reason).

Anyone who stores an emission can verify it by re-running the
input through the same pin and comparing
`reproducibility_hash`. A mismatch indicates either a pin change or
a tampering event; the instrument itself never produces different
hashes for the same pinned input.

The optional `uncertainty` block is equally deterministic — a pure
function of the input bytes and the replicate count `b` (PRNG:
SHA-256 counter mode seeded from `input_sha256`) — but it rides
**outside** `content_sha256` / `reproducibility_hash`, which are
computed before any include exists. Verify it by replaying the
input with the same `b`, not by rehashing the record.
