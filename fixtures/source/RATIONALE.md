# Fixture rationale

Each source document under `fixtures/source/` is here to exercise a
specific part of the measurement pipeline. The set is small,
deliberate, and original — no internal repo prose, no third-party
content with rights questions.

The fixtures freeze the regression goldens under
`fixtures/joint_golden/` and `fixtures/emit_golden/`. If a source is
edited, the goldens drift and must be regenerated with
`python -m tools.build_joint_golden` and
`python -m tools.build_emit_golden`. Treat each source as a
calibration artefact, not example prose.

## Cohort fixtures

These exercise the five reference cohorts in
`instrument/routing/references/`. Each is written to land close to its
cohort's PC centroid, using register markers characteristic of that
cohort (sentence rhythm, nominalisation density, modality, dialogue
attribution, etc.) rather than topic alone.

| File | Cohort | n_words target | Stylistic markers |
|---|---|---|---|
| `academic_short.md` | academic | ~600 | nominalisations, hedging, third-person, formal voice |
| `academic_long.md` | academic | ~3000 | as above, plus citations, structured argument |
| `dialogue.md` | dialogue | ~800 | quoted speech, contractions, attribution tags |
| `journalism.md` | journalism | ~800 | inverted pyramid, attributed quotes, place/time framing |
| `literary.md` | literary | ~1200 | long sentences, sensory imagery, narrative POV |
| `llm_technical.md` | llm_technical_prose | ~1500 | explanatory structure, hedged claims, "the X does Y" |

## Edge-case fixtures

These exercise non-cohort paths that compliance pipelines must
nevertheless handle.

| File | Path exercised | What it tests |
|---|---|---|
| `below_envelope.md` | flag `below_envelope_shaper` | document below 150-word floor — register `unprojectable`, no flat features |
| `structural_table.md` | `structural_profile.classify_subtype` → `reference_table` | table-dominated input; router falls back to structural label |
| `malformed_fence.md` | soft flag `malformed_fence_recovered` | unclosed code fence; cleaner restores the opened span as prose |
| `unicode_quotes.md` | flag `unbalanced_quotation` | mismatched curly/ASCII quotes; non-ASCII text round-trip |

## Authorship

All fixtures are original prose written for the purpose, released
under the same license as the rest of the repository. None describe
the instrument or the repo itself; this prevents a future audit from
finding the test set "self-referential" and lets the goldens stand as
representative samples of what real pipelines see.

## What is intentionally not here

- No fixtures targeting specific LLM models, prompts, or vendors. The
  instrument's job is to fingerprint *outputs*, not to detect the
  *source*. Including model-specific prose would invite over-fitting.
- No fixtures designed to fire every flag. Flags are advisory; the
  goldens cover the canonical numeric record. Flag-specific behaviour
  is unit-tested in `instrument/emissions/flags/tests/`.
- No multilingual fixtures (yet). The instrument's lexicons are
  English-only at v1; non-English prose returns degraded measurements.
  A multilingual fixture set would belong in v2, paired with a
  multilingual lexicon snapshot.
