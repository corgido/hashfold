# METROLOGY — every measurement, with formula and provenance

This document is the regulator-facing handbook. For every numeric
quantity the instrument emits, this file records:

- name (as it appears in the JSON output)
- one-line meaning
- formula in plain text
- input domain and output range
- NaN semantics
- file:line of the implementation

If a measurement is not in this document, it is not a canonical
measurement. Inference layers (flags, band labels, register
match/drift/break) are documented separately and explicitly marked
ADVISORY in their module docstrings.

---

## 1. Tokenisation and segmentation

These produce the inputs every later measurement depends on.

### 1.1 word tokens

- **Source**: `kernel/tokens.py:25-27` (`word_tokens`)
- **Formula**: `[m.lower() for m in re.finditer(r"[A-Za-z]+(?:['-][A-Za-z]+)*", text)]`
- **Notes**: ASCII-only. Excludes digits, accented letters, emoji.
  Hyphens and apostrophes preserved inside tokens (`well-defined`,
  `it's`).

### 1.2 sentences

- **Source**: `kernel/sentences.py:26-43` (`split_sentences`)
- **Formula**: split on `(?<=[.!?])\s+(?=[A-Z])`, then merge
  fragments ending in any of 26 known abbreviations
  (`kernel/sentences.py`).
- **Note**: a single canonical sentence stream — the
  paragraph-first `tokens.sentences`. Every consumer of "sentence"
  inside the instrument uses this stream (M2 A1).

### 1.3 paragraphs

- **Source**: `kernel/paragraphs.py:10-12` (`split_paragraphs`)
- **Formula**: split on regex `\n\s*\n` (blank lines).

### 1.4 canonicalisation and cleaning

- **Source**: `kernel/cleaning.py` (`canonicalise`, and
  `clean = strip_fenced_code ∘ strip_frontmatter ∘
  normalise_apostrophes`)
- **canonicalise (0.9.1)**: every measurement is a function of the
  canonical text: leading BOM stripped, CRLF/CR → LF, trailing
  horizontal whitespace stripped per line, runs of 3+ newlines
  collapsed to one blank line. This defines the semantic-whitespace
  boundary — a paragraph break (blank line present) and single line
  breaks are semantic; the newline convention, trailing spaces, and
  blank-run length are not, and cannot move any measured number.
  Applied at `tokenise()`/`joint_reading()`/`emit()` entry
  (idempotent).
- **clean effect**: removes YAML frontmatter (the `---\n...\n---`
  block at the start) and blanks the interior of fenced code blocks
  (preserves line count). Malformed fences are restored as prose
  and surfaced via the `malformed_fence_recovered` soft flag.
  Cleaning happens once at document level; slices are cut from the
  cleaned text (0.9.1 — no per-slice re-cleaning).

---

## 2. Flat reading — 13 dimensions

The "shaper" view. All features have a 150-word envelope: below
that, every feature returns NaN and `below_envelope = True`.

### 2.1 SFL — three features

Source: `kernel/features/sfl.py`. Six process buckets: `mental`,
`verbal`, `relational`, `behavioral`, `material`, `existential`.
Token classification at `classify_token_with_rule` (file:84-118).

#### sfl.process_proxy_entropy

- **Formula**: `H = −Σ p_i log₂(p_i)` over the six bucket counts
  where `p_i = count_i / total`.
- **Range**: `[0, log₂(6)] ≈ [0, 2.585]`.
- **NaN**: returns NaN when below envelope (n_words < 150).
- **File**: `kernel/features/sfl.py:200-208` (counts), `:107-112`
  (`_shannon_entropy`).

#### sfl.stative_active_ratio

- **Formula**: `(relational + existential) / max(mental + verbal +
  material, 1)`. Behavioral processes are intentionally not
  bucketed (they sit between active and stative in transitivity).
- **Range**: `[0, ∞)` — high = descriptive, low = active.
- **NaN**: when below envelope.
- **File**: `kernel/features/sfl.py`.
- **Validity note (2026-06 discriminant study)**: ~34% of this
  feature's variance is explained by surface confounds
  (length/TTR/sentence length); interpret relative to your own
  baseline, not absolutely. The 0.9.1 MATERIAL-lexicon fix removed
  its largest known bias (material verbs undercounted → ratio
  inflated); values dropped accordingly (see CHANGES-0.9.1.md).

#### sfl.projection_frequency

- **Formula**: `(mental + verbal) / n_words × 100`.
- **Range**: `[0, 100]` — per-100-words count.
- **NaN**: when below envelope.
- **File**: `kernel/features/sfl.py:215`.

### 2.2 RST — three features

Source: `kernel/features/rst.py`.

#### rst.marker_density

- **Formula**: `total_marker_hits / n_sentences`. Per-sentence
  dedup: each relation counted ≤1 per sentence.
- **Range**: `[0, ~5]`.
- **NaN**: below 150 words OR no `.!?` in cleaned text.
- **File**: `kernel/features/rst.py:203`.

#### rst.elaboration_marker_density

*(renamed from `rst.elaboration_pressure` in 0.9.1: the feature
counts surface elaboration markers, not rhetorical elaboration.)*

- **Formula**: `elaboration_marker_hits / n_sentences`.
- **Range**: `[0, ~1]`.
- **File**: `kernel/features/rst.py`.
- **Validity note**: ~46% of variance explained by surface
  confounds; the cue inventory is dominated by polysemous
  high-frequency words (`for`, `that` — structurally guarded but
  not disambiguated). Responds monotonically to injected/removed
  markers (pinned by `test_rst_validity`).

#### rst.contrast_marker_density

*(renamed from `rst.contrast_pressure` in 0.9.1 — same reason.)*

- **Formula**: `contrast_marker_hits / n_sentences`.
- **Range**: `[0, ~1]`.
- **File**: `kernel/features/rst.py`.
- **Validity note**: substantially raw contrast-marker frequency
  (r≈0.72); 57% of cue hits come from `but`+`only`, and `only` is
  often restrictive rather than rhetorical. Monotonic under marker
  injection/removal (pinned by `test_rst_validity`).

### 2.3 cohesion — three features

Source: `kernel/features/cohesion.py`.

#### cohesion.type_token_ratio

- **Formula**: `|unique words| / n_words`.
- **Range**: `[0, 1]`.
- **File**: `kernel/features/cohesion.py:78-79`.
- **Length note**: length-dependent by construction (falls
  mechanically as documents grow); compare only within a length
  cohort — see docs/LENGTH_RESPONSE.md; `dist.mattr` (§6) is the
  length-corrected alternative.

#### cohesion.pronoun_density

- **Formula**: `pronouns / n_words × 100` over a 31-token pronoun
  set.
- **Range**: `[0, 100]`.
- **File**: `kernel/features/cohesion.py:79-80`.

#### cohesion.lexical_repetition

- **Formula**: `|stems appearing in ≥2 sentences| / |unique
  content stems|`. Stopwords (80+ tokens) excluded.
- **Range**: `[0, 1]`.
- **File**: `kernel/features/cohesion.py:82-99`.
- **Validity note (2026-06 discriminant study)**: ~75% of this
  feature's variance is explained by document length and
  type-token ratio — it is largely a surface artifact, retained as
  a defined surface measure, not an independent cohesion signal.
  Its convergence axis (`cohesion_repetition`) is a duplicate
  computation of `coh.lexical_repetition_rate` and is excluded from
  the coherence scalar (§8).

### 2.4 register — four features

Source: `kernel/features/register.py`.

#### register.lexical_novelty

- **Formula**: `unique_content_words / total_content_tokens`.
  Content = tokens not in STOPWORDS, length > 2.
- **Range**: `[0, 1]`.
- **File**: `kernel/features/register.py:34-40`.
- **Length note**: length-dependent by construction (falls
  mechanically as documents grow); compare only within a length
  cohort — see docs/LENGTH_RESPONSE.md; `dist.mattr` (§6) is the
  length-corrected alternative.

#### register.sentence_length_variance

- **Formula**: population variance (ddof=0) of per-sentence word
  counts: `Σ(len_i − μ)² / n`. Uses the canonical paragraph-first
  sentence stream `tokens.sentences` (M2 A1).
- **Range**: `[0, ~10000]`.
- **NaN**: 0.0 when fewer than two sentences.
- **File**: `kernel/features/register.py:43-61`.

#### register.modal_density

- **Formula**: `modals / n_words × 100` over a 10-token modal set
  (`can / could / may / might / must / shall / should / will /
  would / ought`).
- **Range**: `[0, 100]`.
- **File**: `kernel/features/register.py:63-67`.

#### register.negation_density

- **Formula**: `negations / n_words × 100` over a 16-token
  negation set.
- **Range**: `[0, 100]`.
- **File**: `kernel/features/register.py:70-74`.

---

## 3. Extended reading — 37 dimensions

The "other-shaper" view. Source: `reading/extended/`.

### 3.1 SFL extended (11)

Per-process percentages and density / modality measures. See
`reading/extended/sfl.py`. Names: `sfl.pct_{material, mental,
relational, verbal, behavioral, existential}`,
`sfl.process_density`, `sfl.modal_density`, `sfl.hedge_density`,
`sfl.booster_density`, `sfl.modality_balance`. All densities are
per-100-words. Modality balance: `(booster − hedge) / (booster +
hedge)` in `[−1, 1]`.

### 3.2 RST extended (13)

Nine relation densities (`rst.{contrast, concession, cause,
result, elaboration, sequence, condition, purpose,
summary}_density`), `rst.total_marker_density`,
`rst.relation_diversity` (normalised entropy in `[0, 1]`),
`rst.branching_score` and `rst.max_depth_score` (sentence-dominant
relation rollups in `[0, 1]`). See `reading/extended/rst.py`.

### 3.3 Cohesion extended (13)

`coh.{pronoun, demonstrative, definite_article,
reference}_density`, `coh.{additive, adversative, causal,
temporal}_density`, `coh.conjunction_balance`,
`coh.type_token_ratio`, `coh.lexical_repetition_rate`,
`coh.lexical_chain_count`, `coh.lexical_chain_span`. See
`reading/extended/cohesion.py`. `coh.type_token_ratio`
(`reading/extended/cohesion.py:134`) is length-dependent by
construction; compare only within a length cohort — see
docs/LENGTH_RESPONSE.md; `dist.mattr` (§6) is the length-corrected
alternative.

---

## 4. Trajectory — per-slice streams

Source: `kernel/features/trajectory_features.py`, embedded in the
joint reading at `reading.trajectory` (0.9.1). Four streams, one
value per slice. The slicer (`kernel/slicer.py`) partitions the
document-level CLEANED text into structural slices using a
contract-validated hierarchy (section → paragraph → sentence →
word); cleaning happens once, before slicing, so a fence spanning a
slice boundary cannot be resurrected as prose (0.9.1 FENCE fix).

`reading.trajectory` = `{regime, boundary_level, n_slices, slices,
features}` where `slices` are offsets into the cleaned text and
`features` are the four per-slice streams. Because the block is
inside the reading, every surfaced trajectory number is covered by
`reading_sha256` and `content_sha256` and appears in the audit
shape. The arc emission (per-slice deltas, per-dimension summaries,
slice labels) is a DERIVED advisory view — pure arithmetic over the
attested values, recomputable offline (pinned by
`test_arc_derived`).

### 4.1 lexical_novelty (per slice)

- **Formula**: `|new_content_words_in_slice| / |slice_content_words|`,
  where `new` excludes any content word already seen in earlier
  slices.
- **Slice 0**: NaN by design (no prior context).
- **File**: `kernel/features/trajectory_features.py:49-54`.

### 4.2 sentence_length_variance (per slice)

- **Formula**: population variance of per-sentence word counts
  within the slice.
- **NaN**: 0.0 when fewer than two sentences in the slice.
- **File**: `kernel/features/trajectory_features.py:57-65`.

### 4.3 modal_density (per slice)

- **Formula**: `modals / n_tokens × 100` within the slice.
- **File**: `kernel/features/trajectory_features.py:68-72`.

### 4.4 negation_density (per slice)

- **Formula**: `negations / n_tokens × 100` within the slice.
- **File**: `kernel/features/trajectory_features.py:75-79`.

### 4.5 adjacent deltas (per slice)

- **Formula**: `delta[i][k] = value[i][k] − value[i−1][k]` for
  each feature `k`; `None` on slice 0; `None` per-feature when
  either neighbour is `None` / NaN.
- **No normalisation** — pure raw deltas. Compliance pipelines
  threshold these against their own baselines rather than relying
  on the doc-internal `register_shift` advisory flag (M2 A4).
- **File**: `emissions/assembler.py` (delta computation in
  `_assemble_arc`).

---

## 5. Stylometry — seven features

Source: `kernel/features/stylometry.py`. Single-pass over cleaned
text.

- **stylometry.compression_ratio** = normalised LZ78 complexity,
  `compressibility(cleaned)` from `kernel/compress.py` — the UTF-8
  byte string is greedily parsed into distinct LZ78 phrases and the
  value is `n_phrases / n_bytes`. Range `(0, 1]`: ~1.0 for
  incompressible / highly varied text, lower as repetition rises;
  `null` on empty input. Pure integer arithmetic, so bit-identical
  across hosts. **Replaces** the former
  `len(gzip.compress(cleaned, mtime=0)) / len(cleaned.encode("utf-8"))`,
  whose compressed length depended on the linked zlib build and was
  therefore not host-portable (P1-1). *Calibration note:* this is a
  different measurement from the old gzip ratio — discriminative
  ordering is preserved but absolute values differ, so any reference
  statistics calibrated on the gzip distribution are stale on the
  LZ78 scale.
- **stylometry.semicolon_per_1k_words** = `semicolons / n_words × 1000`.
- **stylometry.comma_per_sentence** = `commas / n_sentences`.
- **stylometry.question_rate** = `sentences_ending_in_? / n_sentences`.
- **stylometry.exclamation_rate** =
  `sentences_ending_in_! / n_sentences`.
- **stylometry.quotation_density** = `quote_chars / len(cleaned) × 1000`.
- **stylometry.subordination_density** =
  `subordinator_hits / n_words × 1000`.

Files: `kernel/features/stylometry.py:55-103`.

---

## 6. Distributional — twelve features

The `distributional` view. Source: `reading/distributional.py`.
Vocabulary structure, predictability, and temporal texture computed
directly from the token stream — no lexicons, no classification.
Features appear in the record under `reading.distributional.features`
keyed `dist.<name>`. All twelve share a 150-word envelope: below
`MIN_WORDS = 150` every feature is `null` (`reading/distributional.py:244-245`).

- **dist.hapax_ratio** = `hapax_types / unique_types` (words occurring
  exactly once). Range `[0, 1]`. File `:52-59`.
- **dist.yule_k** = `1e4 · (Σ i²·V_i − N) / N²` over the frequency
  spectrum (`V_i` = number of types occurring `i` times, `N` = token
  count). Range `[0, ∞)`; higher = more repetition concentration.
  File `:61-71`.
- **dist.growth_slope** = slope of the vocabulary-growth curve
  (cumulative distinct types vs token index), `cov(i, seen) / var(i)`
  then divided by `N`. Range ≈ `(0, 1]`. File `:74-89`.
- **dist.mean_word_length** = `Σ len(word) / n_words` (characters).
  File `:92-95`.
- **dist.char_entropy** = Shannon entropy (bits) of the alphabetic
  character distribution. Range `[0, ~4.75]`. File `:47-49`, `_shannon`
  `:37-43`.
- **dist.bigram_entropy** = Shannon entropy (bits) of the word-bigram
  distribution. File `:98-103`.
- **dist.compression_ratio** = `compressibility(cleaned)` — the same
  normalised LZ78 measure as `stylometry.compression_ratio` (§5),
  surfaced here for the distributional vector. One measurement, not
  two. Range `(0, 1]`. File `:106-107`.
- **dist.sentence_length_entropy** = Shannon entropy over six
  sentence-length bins (`≤5, ≤10, ≤15, ≤20, ≤30, >30` words). Range
  `[0, log₂6] ≈ [0, 2.585]`. File `:110-128`.
- **dist.burstiness** = mean over the top-20 content words of
  `(σ − μ) / (σ + μ)` for the gaps between occurrences. Range
  `[−1, 1]`; higher = more clumped/bursty recurrence. File `:131-152`.
- **dist.repetition_halflife** = the position (as a fraction of the
  bigram stream) by which half of all repeating bigrams have first
  recurred. Range `[0, 1]`; defaults to `0.5` when there are too few
  words or no repeats. File `:155-175`.
- **dist.entropy_drift** = `|char_entropy(first half) −
  char_entropy(second half)|` of the cleaned text. Range `[0, ~4.75]`.
  File `:185-189`.
- **dist.mattr** = Moving-Average Type-Token Ratio: mean over all
  `n − W + 1` sliding windows of `W = 100` word tokens
  (`_MATTR_WINDOW`) of `distinct_types_in_window / W`, computed as
  `Σ distinct / ((n − W + 1) · W)`. Range `(0, 1]`. Fixed-width
  windows remove the mechanical length term that makes raw
  type/token quotients (`cohesion.type_token_ratio`,
  `coh.type_token_ratio`, `register.lexical_novelty`) fall as
  documents grow — the length-robust alternative; a reported
  measurement and invariance-audit instrument (see
  docs/LENGTH_RESPONSE.md), not a routing coordinate. NaN behavior:
  `null` below the 150-word envelope like the rest of the view;
  total within the envelope since `MIN_WORDS = 150 > W = 100` (a
  defensive `n < W` NaN branch exists but is unreachable through
  the public path). File `:192-235`.

---

## 7. Convergence — five axes

Source: `reading/convergence.py`. Each axis maps a flat-view
("shaper") feature to one or more extended-view ("other") features,
normalises both to `[0, 1]` using calibrated ranges, and reports
a per-axis tuple `(shaper_value, shaper_normalised, other_value,
other_normalised, direction, confidence)`.

The five axes:

| Axis | Shaper | Other | Reducer |
|---|---|---|---|
| sfl_process_complexity | sfl.process_proxy_entropy | sfl.pct_{6 buckets} | entropy_of_proportions |
| rst_contrast | rst.contrast_pressure | rst.{contrast,concession}_density | sum |
| rst_elaboration | rst.elaboration_pressure | rst.elaboration_density | sum |
| cohesion_repetition | cohesion.lexical_repetition | coh.lexical_repetition_rate | sum |
| register_modality | register.modal_density | sfl.{modal,hedge}_density | sum |

- **shaper_normalised** = `clamp01((shaper_value − lo) / (hi − lo))`
  using the per-axis `shaper_range`.
- **other_normalised** = same, using `other_range`.
- **confidence** = `1 − |shaper_normalised − other_normalised|`,
  range `[0, 1]`.
- **direction** = `agree_*` when `confidence ≥ 0.80`, else
  `diverge`. (`incomparable` if shaper is NaN.) The agree-band
  splits into `agree_high` / `agree_mid` / `agree_low` based on
  the mean position around `BAND_HIGH = 0.66` and `BAND_LOW = 0.33`.

The shaper-side and other-side ranges are calibrated empirical
percentiles on the 81-document self-audit corpus with a 15%
buffer; see comments in `reading/convergence.py`.

**Independence annotations (0.9.1).** Each axis dict carries an
`independence` field stating how independent its two views actually
are (measured): `rst_contrast` = `independent` (the only axis whose
views genuinely discriminate, r≈0.41); `cohesion_repetition` =
`duplicate_computation` (identical stopword lists; r≈0.99, ~100%
within-tolerance agreement — one measurement counted twice);
`sfl_process_complexity` and `register_modality` =
`shared_lexicons`; `rst_elaboration` = `shared_marker_inventory`.
Convergence is internal consistency across substantially shared
computation, not independent corroboration (SCOPE.md).

---

## 8. Coherence scalar

Source: `emissions/coherence.py`.

- **Formula**: `value = n_axes_agree / n_axes_measurable`, where
  `n_axes_measurable = n_axes_agree + n_axes_diverge`.
  Incomparable axes (shaper NaN) are excluded from both numerator
  and denominator. **Excluded axes (0.9.1)**: `cohesion_repetition`
  (a duplicate computation whose agreement is structural) leaves
  both numerator and denominator; four axes are coherence-eligible.
  `evidence.excluded_axes` lists the exclusions.
- **Range**: `[0, 1]`, or `None` when no axes are measurable.
- **Label**: `high` / `moderate` / `low` is **ADVISORY**; the
  scalar is the canonical measurement. The label degrades to
  `unmeasurable` (with `evidence.degraded_reason`) when fewer than
  3 axes are measurable, when the register outcome is
  unprojectable/structural, or when the reading is below envelope
  (0.9.1 — the band can no longer contradict the register layer on
  degenerate input).

---

## 9. PC distance to references

Source: `routing/pc.py`, `routing/router.py:_standardised_distance`.

Five reference distributions are bundled (`academic_prose`,
`dialogue_prose`, `journalism_prose`, `literary_prose`,
`llm_technical_prose`, all v1). Each reference carries its own
`pc_zscore_mean`, `pc_zscore_std`, `pc_centroid`, `pc_composites`
(per-PC mean / std / percentiles), and `pc_loadings`.

### 9.1 PC projection

For each feature `f` in the reference's `pc_zscore_mean`:
`z[f] = (value[f] − μ[f]) / σ[f]`. If any feature is `None` /
NaN / `σ = 0`, the entire projection contaminates and every PC
output is `None`. For each PC name, `PC_value = Σ loadings[f] ·
z[f]`. (`routing/pc.py:25-54`.)

### 9.2 standardised distance

`distance = √(Σ ((PC_value[k] − centroid[k]) / std[k])²)` over
the reference's PC composites. Returns `None` if any PC value is
`None`. (`routing/router.py:41-55`.)

`distance_method = "feature_zscore_l2"` is stamped in metadata.
This is feature-z-scored Euclidean in PC space — Mahalanobis
without off-diagonal covariance. Future migrations to true
Mahalanobis become explicit and version-traceable.

Because the mean, scale, PC basis, and centroid are all properties of
the reference, the reference *defines the coordinate system* the
distance is measured in — which is why the production baseline must be
calibrated on your own deployment, not supplied with the library. The bundled references are seeds, not a baseline. See
`CALIBRATION.md`.

### 9.3 distances_to_all_references

For every registered reference, compute the projection and the
distance, returning a list of `{name, version, distance,
percentile}` records sorted by `(name, version)`. Always emitted
(even on unprojectable documents, where every distance is `None`).
`percentile` (0.10.0) is the mid-rank position of the distance
within that reference's persisted null — see §12.3.
File: `routing/router.py:80-120`.

---

## 10. Metadata — provenance pins

Source: `emissions/types.py:124-156`,
`emissions/assembler.py:255-290`.

- **emission_version**: catalog version, e.g. `v2`.
- **instrument_version**: single-sourced from
  `instrument.__version__`. Currently `0.10.0`.
- **schema_version**: joint-reading schema. Currently `0.10.0`
  (aligned with the instrument version; the 0.10.0 reading added
  `dist.mattr` to the distributional view. History: the 0.9.1 shape
  added `trajectory`, per-axis `independence`, and renamed RST keys).
- **n_words**: integer count from the shaper view's tokeniser.
- **n_sentences**: integer count.
- **timestamp**: UTC ISO 8601 at serialisation time. **Not in
  reproducibility hash**; varies by clock.
- **lexicon_version**: pinned at `LEXICON_VERSION` in
  `instrument/lexicons/__init__.py`. Currently `v1`.
- **catalog_sha256**: SHA256 of the catalog source JSON,
  surfaced from `emissions/catalog_v2.py:SOURCE_SHA256`.
- **distance_method**: names the PC-distance formula.
  Currently `"feature_zscore_l2"`.
- **input_sha256**: SHA256 over the RAW transport bytes (0.9.1):
  the file's bytes on the CLI (`run.py` reads bytes before
  decoding), the request body bytes on HTTP (hashed before decode).
  Captured before any newline translation or canonicalisation, so
  the same bytes carry the same provenance identity on every
  transport (T-XPORT closed). Library callers passing a `str` get
  the documented fallback `sha256(text.encode("utf-8"))`.
- **content_sha256**: SHA256 over the quantised canonical record
  `canonical_json({reading, distances})` with volatile `ts` removed.
  This is the hash of *what was measured* (reading **and** distances).
  Changes whenever a measured number or a reference distance changes.
- **reading_sha256**: SHA256 over the pure-core `reading` alone (no
  distances) — the reference-independent witness. Two parties measuring
  the same text with the same core get the same `reading_sha256`
  regardless of their reference calibration.
- **core_code_sha256**: build-time hash of the measurement-core
  *source* (kernel + reading + lexicons), frozen in
  `instrument/_core_provenance.py` and checked by
  `tools.build_core_hash --check`. Pins the exact algorithm, including
  frozen decision constants (e.g. convergence `AGREE_TOLERANCE`).
- **reproducibility_hash**: SHA256 of the pipe-joined fold of **ten**
  components, in order (`emissions/assembler.py:53,280-291`):
  `instrument_version | schema_version | emission_version |
  lexicon_version | catalog_sha256 | distance_method | input_sha256 |
  content_sha256 | reading_sha256 | core_code_sha256`. Because it folds
  `content_sha256`, it changes when the *numbers* change, not only when
  a version pin moves.

Serialisation note: non-finite floats (NaN/inf) serialise as JSON
`null` at the record boundary (`kernel.quantize.q`), so the record is
always strict-valid JSON and the wire form equals the hashed canonical
form. A received record therefore rehashes to its own `content_sha256`
and `reading_sha256` — anyone can verify a stored emission offline
by recomputation, not only by re-running the instrument. See
`VERIFICATION.md`.

---

## 11. Audit shape — the canonical record

`?shape=audit` returns:

```
{
  "reading":     <full joint reading dict>,
  "distances":   <list of {name, version, distance, percentile}
                  for every registered reference>,
  "metadata":    <full EmissionMetadata>,
  "sfl_trace":   <optional, when ?include=sfl_trace>,
  "uncertainty": <optional, when ?include=uncertainty — see §12.4>
}
```

This is the compliance-defensible record. It contains pure
measurements and provenance only; no flags, no register match
label, no coherence band, no register cohort pick. Since 0.9.1 the
reading embeds `trajectory` (the per-slice streams), so the audit
record carries — and its hashes attest — the full measurement
surface, and it still rehashes offline to its own `content_sha256`
/ `reading_sha256`.

Each distance record carries a `percentile` (0.10.0): the mid-rank
position of that distance within *that reference's* persisted
self-distance null — `null` when the reference persists no full
null (all bundled seeds, 0.9.1-era references) or the distance is
unmeasurable (§12.3). The distance records — including their
`percentile` values — are inside `content_sha256`.

The `sfl_trace` (when requested) carries per-token classification
records and the existential pattern matches; an auditor can
reconcile the trace's `summary.counts` to the `process_proxy_entropy`
in the reading. See `SCOPE.md` "Defensibility — SFL trace". The
`uncertainty` block (when requested) attaches at the top level like
`sfl_trace` and, like it, rides OUTSIDE `content_sha256` /
`reproducibility_hash` (§12.4, §12.7).

---

## 12. Calibrated interpretation (0.10.0)

0.10.0 adds the machinery that locates a measurement against a
named baseline with stated empirical error rates. Everything in
this section is a **descriptive reference coordinate** — a
percentile, an interval, a q-value, a chart state — never a shipped
decision rule; degradation is always an explicit status string,
never a silent absence. §12.7 states exactly which of these
quantities ride inside vs outside the content-hash chain.

### 12.1 reference_envelope — percentile and empirical exceedance

Emitted at `register.evidence.reference_envelope` for the chosen
reference (full shape).

#### reference_envelope.percentile

- **Meaning**: mid-rank position of this document's distance within
  the reference's persisted cross-validated null
  (`self_distance.values`).
- **Formula**: `100 · (n_less + 0.5 · n_equal) / n` over the sorted
  null values (ties contribute half their mass). The lookup happens
  in quantised space: `q(distance)` against the already-quantised
  stored values.
- **Domain**: `[0, 100]`; below the null's minimum → 0.0, above its
  maximum → 100.0.
- **Degradation**: bundled seeds (no `self_distance` at all) →
  `{"status": "seed_reference_no_confidence_envelope"}` (no
  envelope numbers at all). 0.9.1-era references (summary `n` /
  `median` / `p95` only, no persisted values) keep the
  within/beyond-p95 `position` but degrade the percentile to
  `"percentile_status": "reference_predates_null_distribution"`.
- **Source**: `instrument/routing/calibration.py:37-101` (`distance_percentile`,
  `envelope_block`), `instrument/kernel/stats.py:71-89`
  (`midrank_percentile`).

#### reference_envelope.empirical_exceedance

- **Meaning**: the fraction of the baseline's own (held-out)
  calibration documents at least this far out — the empirical
  false-positive rate of alarming at this distance.
- **Formula**: `1.0 − percentile / 100.0`.
- **Domain**: `[0, 1]`.
- **Companions**: `basis` (echoes `self_distance.basis`, e.g.
  `cross_validated_10fold` or `resubstitution` — a resubstitution
  null is visibly weaker) and `percentile_method` (`"midrank"`).
  The block also always carries `self_distance_n`,
  `self_distance_median`, `self_distance_p95`, and `position`
  (`within_p95` / `beyond_p95`).
- **Source**: `instrument/routing/calibration.py:95-101`.

### 12.2 feature_calibration — per-feature empirical p and BH q

Emitted at `register.evidence.feature_calibration` (full shape),
for references that persist 101-point per-feature percentile grids
(`per_feature_quantiles`, 0.10.0 builder).

#### feature_calibration.per_feature.\<name\>.percentile

- **Meaning**: the document's feature value located on the
  reference's own empirical CDF.
- **Formula**: `100 · F(value)` where `F` is inverse linear
  interpolation on the stored ascending grid (`grid[i]` = value at
  cumulative fraction `i/(m−1)`); a value inside a flat run (an
  atom of the calibration distribution) maps to the run's midpoint
  — the same mid-rank convention as §12.1. Clamped: below `grid[0]`
  → 0, above `grid[-1]` → 100. Quantised-space lookup.
- **Domain**: `[0, 100]`.
- **Source**: `instrument/routing/calibration.py:165-174`,
  `instrument/kernel/stats.py:92-134` (`grid_cdf`).

#### feature_calibration.per_feature.\<name\>.p_two_sided

- **Meaning**: two-sided empirical p-value against the reference's
  calibration distribution.
- **Formula**: `min(1.0, max(2.0 · min(F, 1 − F), 1/(n+1)))` with
  `n` = the reference's corpus size. The floor `1/(n+1)` is the
  resolution of an n-point empirical null: nothing can be rarer
  than "beyond everything we calibrated on", so no smaller p is
  ever quoted (no normal approximation anywhere).
- **Domain**: `[1/(n+1), 1]`.
- **Source**: `instrument/kernel/stats.py:137-150` (`two_sided_p`).

#### feature_calibration.per_feature.\<name\>.q_value

- **Meaning**: Benjamini–Hochberg q-value across the whole tested
  family — the smallest false discovery rate at which this feature
  would be reported discordant from the reference. Descriptive
  coordinate; **no alpha ships** and nothing fires on this block.
- **Formula**: step-up BH with monotone enforcement — for sorted
  p-values `p_(1) ≤ … ≤ p_(m)`, `q_(i) = min_{j≥i}(m · p_(j) / j)`,
  clamped at 1.0. P-values are collected in sorted-feature-name
  order, so the pass is deterministic.
- **Domain**: `[0, 1]`.
- **Source**: `instrument/kernel/stats.py:153-179` (`bh_adjust`),
  `instrument/routing/calibration.py:175-177`.

#### feature_calibration.family_policy

- **Fields**: `method` (`"benjamini_hochberg"`), `family` (the
  family definition: reference features with a finite reading value
  and a stored quantile grid), `m` (family size actually tested —
  varies per document: a NaN/inf feature leaves the family rather
  than being imputed), `sidedness` (`"two_sided"`),
  `p_resolution_floor` (`1/(n+1)`). The sibling `reference_n` and
  each entry's `value` (the quantised feature value tested) make
  the correction recomputable from the record plus the reference
  file.
- **Degradation**: reference without stored grids (all bundled
  seeds, 0.9.1 references) →
  `{"status": "reference_lacks_feature_quantiles"}`; document with
  no finite family member →
  `{"status": "no_finite_features_for_calibration"}` with `m: 0`
  in the policy.
- **Source**: `instrument/routing/calibration.py:104-182`.

### 12.3 percentile on distance records

- **Meaning**: every record in `distances_to_all_references` (and
  therefore the audit shape's `distances`) carries `percentile` —
  the §12.1 mid-rank statistic computed against *that* record's own
  reference null, so a document can be located against every
  registered baseline, not only the chosen one.
- **Formula**: identical to §12.1 (`distance_percentile`).
- **Domain**: `[0, 100]` or `null` (reference persists no full
  null, or distance unmeasurable).
- **Source**: `instrument/routing/router.py:98-120`
  (`distances_as_records`).

### 12.4 uncertainty — deterministic sentence-bootstrap CIs

Opt-in: HTTP `?include=uncertainty` (attached at top level of
`audit` / `full` shapes only), CLI `run.py --uncertainty`. Block
shape: `{method, b, seed, n_sentences, features}` with per-feature
`{point, ci_low, ci_high, se, n_finite}`.

- **Resampling scheme** (`method: "sentence_bootstrap_paragraph_shape_v1"`):
  draw `n_sentences` indices with replacement over the flat
  sentence list; reassemble a replicate document preserving the
  original paragraph shape (same paragraph count, same
  sentences-per-paragraph, drawn order); recompute the four scalar
  per-feature views (13 shaper + 37 extended + 7 stylometry + 12
  distributional) per replicate.
- **PRNG**: `kernel.detrandom.DetRandom` — SHA-256 in counter
  mode, block `i` = `sha256(f"{seed_string}:{i}")`, four big-endian
  u64s per block, rejection sampling for unbiased indices. The seed
  string is `f"{scheme}:{input_sha256}"` — the scheme name, one
  ASCII colon, then the document's `input_sha256` verbatim. Same
  bytes in, same error bars out, on any conforming host
  (`random.Random` is deliberately not used: CPython pins
  cross-version stability only for `random()` itself).
- **B**: default 200 (`DEFAULT_B`); the HTTP server reads
  `INSTRUMENT_BOOTSTRAP_B` (`instrument/config.py:31,76`); the CLI
  flag uses the default. Cost: roughly 2.5–6.5 s per
  kiloword-scale document at B=200 (B linear).
- **Per-feature summary**: `point` = the unresampled value;
  `ci_low` / `ci_high` = 2.5th / 97.5th linear-interpolation
  percentiles of the finite replicate values
  (`kernel/stats.py:43-68`); `se` = their population standard
  deviation; `n_finite` = finite replicate count.
- **Degradation**: fewer than 8 sentences (`MIN_SENTENCES`) →
  `{"status": "too_few_sentences_for_bootstrap", "n_sentences": n,
  "method": ...}` — a refusal, not an interval. Per feature, when
  fewer than half the replicates are finite (`2·n_finite < b`) →
  `{"status": "unstable_under_resampling", "n_finite": ...}`.
- **Hash placement**: OUTSIDE `content_sha256` /
  `reproducibility_hash`, exactly like `sfl_trace` (asserted by
  test) — see §12.7.
- **Source**: `instrument/reading/bootstrap.py:125-216`
  (`bootstrap_uncertainty`), `instrument/kernel/detrandom.py:29-89`
  (`DetRandom`), `instrument/serve/shape.py:224-235` (HTTP attach),
  `run.py:44-54` (CLI attach). Goldens:
  `fixtures/uncertainty_golden/` (B=50).

### 12.5 SPC statistics (offline — `instrument.spc`, `tools.control_chart`)

Offline by design: the runtime is per-document and stateless; SPC
runs after the fact over a JSONL capture. In-control parameters:
`mu0` = mean and `sigma0` = population std (ddof=0) of the
reference's persisted null (`self_distance.values`); refuses nulls
with fewer than 2 values or `sigma0 == 0`
(`instrument/spc.py:57-81`).

#### individuals chart (~ ISO 7870-2)

- **Formula**: each point placed at its mid-rank percentile (§12.1
  formula) within the sorted null; `exceeds` when strictly above
  `p` (default 99.5). Empirical form — no normal-theory 3σ limits,
  because the null is right-skewed.
- **Source**: `instrument/spc.py:182-203`.

#### CUSUM (~ ISO 7870-4)

- **Formula**: standardised `s_i = (x_i − mu0) / sigma0`;
  `C⁺_i = max(0, C⁺_{i−1} + s_i − k)`,
  `C⁻_i = max(0, C⁻_{i−1} − s_i − k)`; signal when either exceeds
  `h`. Defaults `k = 0.5` (half the shift, in σ₀ units, the chart
  is tuned to detect), `h = 5.0`.
- **Source**: `instrument/spc.py:103-114,152-179`.

#### EWMA (~ ISO 7870-6)

- **Formula**: `z_i = λ·x_i + (1−λ)·z_{i−1}`, `z_{−1} = mu0`;
  time-varying limits
  `mu0 ± L·sigma0·sqrt(λ/(2−λ)·(1 − (1−λ)^{2(i+1)}))`. Defaults
  `λ = 0.2`, `L = 3.0`.
- **Source**: `instrument/spc.py:86-100,117-149`.

#### chart states and ARL

- **States** (`summarize`): `sustained_shift_signal` (EWMA or CUSUM
  signalled — the memoried charts accumulate evidence, so a signal
  means the process shifted), `isolated_exceedance` (no memoried
  signal but ≥1 individuals exceedance — one or a few weird
  documents), `in_control` (neither). Descriptive only; the
  out-of-control action plan is yours.
  (`instrument/spc.py:206-252`.)
- **ARL**: textbook normal-theory ARL₀ for the defaults (≈ 500 for
  the EWMA at λ=0.2, L=3; ≈ 465 for the CUSUM at k=0.5, h=5) are
  approximations — the distance stream is non-negative and
  right-skewed. The honest per-reference table is
  `tools.control_chart --arl`: DetRandom-resampled streams from the
  reference's own null under step shifts of 0/0.5/1/1.5/2 σ₀
  (M=200 streams, horizon 1000, censoring reported), seeded from
  the reference file's SHA256 so the table is a pure function of
  its inputs. (`tools/control_chart.py:67-79,201-247`.)
- **Baseline age**: `tools.control_chart --as-of YYYY-MM-DD` judges
  `calibration_date` against `recalibration_policy.max_age_days`
  and echoes `as_of` into the report — the report stays a pure
  function of its arguments; the runtime never reads a clock for
  age. (`tools/control_chart.py:155-180`.)

### 12.6 Length-response audit

Every feature's measured response to document length — Spearman ρ
against log-length, median relative change 150→2400 words, monotone
fraction, and a `length_invariant` / `length_sensitive` /
`insufficient_range` classification — is published in the generated
`docs/LENGTH_RESPONSE.md` (+ `fixtures/validation/length_response.json`,
CI-gated) by `python -m tools.length_invariance --write`. Headline:
the raw TTR family collapses mechanically
(`cohesion.type_token_ratio`: ρ = −0.962, median relative change
−0.762), while `dist.mattr` (§6) moves a few percent (ρ = −0.352,
median −0.040) — and the audit is honest that even `dist.mattr`
classifies `length_sensitive` under the strict rule. These are
documentation labels for baseline construction (compare like
lengths with like), not runtime metadata.

### 12.7 Hash-chain placement

What rides inside vs outside the content-hash chain:

- **Inside `content_sha256` (and `reproducibility_hash`)**: the
  full reading (including `dist.mattr` and the trajectory), and the
  `distances` records **including their `percentile` values**
  (§12.3) — `content_sha256` hashes
  `canonical_json({reading, distances})` (§10).
- **Inside `reading_sha256`**: the reading alone — no distances, no
  percentiles.
- **Outside both** (derived-advisory or opt-in; recomputable, never
  hash-attested): the `uncertainty` block (§12.4 — pure function of
  input bytes + B, replayable); `sfl_trace`; and the
  `register.evidence` calibration blocks — `reference_envelope`,
  `reference_provenance`, `feature_calibration` — which are pure
  functions of the hash-attested distances/reading plus the pinned
  reference bytes (`docs/VERIFICATION.md`, "Derived advisory
  fields"). An input perturbation therefore cannot move any of them
  without moving `content_sha256`; a reference-file substitution is
  caught by pinning the reference JSON's SHA256
  (`docs/CALIBRATION.md` step 5).
