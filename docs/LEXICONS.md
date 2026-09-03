# LEXICONS — provenance and policy

## What is a lexicon

A lexicon in this instrument is a **frozenset of lowercase strings**
compiled into a Python module at build time. There are 23
frozensets shipped at `instrument/lexicons/_v1.py`. They are not
learned; they are not weighted; they are exact-match sets used by
the deterministic classifiers in `kernel/features/`.

## Versioning policy

The lexicon module name encodes the version:
`instrument/lexicons/_v1.py`. The shipping version is exposed as
`LEXICON_VERSION` in `instrument/lexicons/__init__.py` and stamped
into every emission's `metadata.lexicon_version`.

To ship a new lexicon snapshot:

1. Run `python -m tools.build_lexicons --version v2` against
   updated source JSONs in `_data/lexicons/`.
2. The tool writes `instrument/lexicons/_v2.py` with a new
   `BODY_SHA256` and per-lexicon `MANIFEST` (each entry is `{sha256,
   count}`).
3. Change `instrument/lexicons/__init__.py`:
   - import path: `from ._v1 import ...` → `from ._v2 import ...`
   - `LEXICON_VERSION = "v1"` → `LEXICON_VERSION = "v2"`.
4. Users who pinned to `v1` see no change until they re-pin.

A `--check` mode (`build_lexicons --version v1 --check`) verifies
that the committed `_v1.py` matches what the source JSONs would
regenerate. Drift fails CI.

## What each lexicon is for

The 23 lexicons fall into five groups. Names below match the keys
in the `LEXICONS` dict and the entries in `MANIFEST`.

### SFL process classification (6)

Used by `kernel/features/sfl.py:classify_token_with_rule`:

- **processes_mental** — cognition / perception verbs (think,
  believe, see, …).
- **processes_verbal** — reporting / speech-act verbs (say, argue,
  claim, …).
- **processes_relational** — relational verbs other than copula-be
  (become, has, owns, …).
- **processes_behavioral** — behavioral processes (laugh, cry,
  breathe, sleep, …). Distinct from material; physical actions of
  the body.
- **processes_material** — used by the extended view only. The
  compact view uses morphology heuristics for material classification
  (`-ing` and `-ed` suffix rules).
- **processes_existential** — used by the extended view only. The
  compact view detects existential by regex pattern over text
  (`there is/are/was/were/exists/existed`).

### RST relation cues (10)

Used by `kernel/features/rst.py` (compact) and
`reading/extended/rst.py` (extended):

- **rst_contrast**, **rst_concession**, **rst_cause**,
  **rst_result**, **rst_elaboration**, **rst_sequence**,
  **rst_condition**, **rst_purpose**, **rst_summary**,
  **rst_elaboration_broad**.

Each is a frozenset of marker phrases (e.g. `"however"`, `"in
contrast"`, `"because"`). The compact view uses sentence-initial
matching plus a small set of mid-sentence rules; the extended view
matches anywhere in the sentence.

### Cohesion / register sets (6)

- **stopwords** — 80+ tokens, used by cohesion and register
  novelty to exclude function words.
- **pronouns** — 31 tokens for `cohesion.pronoun_density`.
- **demonstratives**, **definite_articles** — for the extended
  cohesion features.
- **conjunctions_additive**, **conjunctions_adversative**,
  **conjunctions_causal**, **conjunctions_temporal** — for the
  extended cohesion conjunction balance.

### Stylistic sets

- **modals** — 10 tokens for `register.modal_density`.
- **negations** — 16 tokens for `register.negation_density`.
- **subordinators_single**, **subordinators_phrase** — used by
  `stylometry.subordination_density`.

### Stance / extended-view sets

- **stance_modal** — modal-flavoured stance markers used by the
  extended view's modality balance.
- **hedges** — hedging markers (e.g. "perhaps", "approximately").
- **boosters** — boosting markers (e.g. "clearly", "definitely").

The full list with SHA256 + token count per lexicon is at
`instrument/lexicons/_v1.py:MANIFEST`.

## Deny-lists in SFL

The SFL classifier carries three **inline** deny-lists in
`kernel/features/sfl.py` (not in the lexicon tree):

- **KNOWN_PLURAL_NOUNS** (~120 tokens) — plural nouns that look
  verb-like via the `-s` suffix (`tables`, `chairs`, `processes`,
  …). Without this guard, the morphology heuristic would mis-tag
  them as material processes.
- **KNOWN_ADJECTIVAL_PARTICIPLES** (~30 tokens) — `-ed` and `-ing`
  forms that are adjectives in modern English (`interesting`,
  `tired`, `complicated`, …). Without this guard, the morphology
  heuristic would mis-tag them as material processes.
- **KNOWN_NON_PROCESS** (9 tokens, added in 0.9.0) — closed-class
  grammatical words ending in `-ing`/`-ed` that are never verbs in
  running text: indefinite pronouns (`something`, `nothing`, …),
  prepositions (`during`, `according`, `notwithstanding`), adverbs
  (`indeed`), numerals (`hundred`). High-frequency in LLM prose;
  without this guard the morphology fallback systematically
  inflated the material bucket on exactly the instrument's target
  input class. (`including`/`regarding` are lexicon-owned
  relational entries and deliberately not in this deny-list.)

These live in the SFL module rather than the lexicon tree because
they are coupled to the algorithm in `classify_token_with_rule`
— deny-lists, not measurement lexicons.

## Why not learned weights

The instrument's value proposition is byte-stable, deterministic
measurement. A learned lexicon (with weights, embeddings, or
trained classifiers) would couple the measurement to the training
corpus and would require versioning the model, the data, the
training run, and the seed. A frozen frozenset has none of those
dependencies — it is a fixed set, hash-verifiable, and trivially
deterministic.

The cost is precision: morphology heuristics misfire on edge cases
(adjectival `-ing`/`-ed` forms not in the deny-list, plural nouns
not in the deny-list). The compliance posture (see SCOPE.md)
makes this trade explicit: the instrument prefers a transparent
heuristic with a published deny-list to an opaque learned
classifier.

When an SFL classification is contested, you can request
the per-token trace via `?include=sfl_trace`, see exactly which
rule fired, and reproduce the decision against the lexicon and
deny-list for the pinned `lexicon_version`.

## Versioned references vs versioned lexicons

The five reference distributions in
`instrument/routing/references/*.json` are also pinned by version
(currently `v1`). They are **not** lexicons — they are calibrated
PC-space coordinates derived from a small reference corpus per
cohort. They share the versioning discipline (immutable file,
`reliability` field, `instrument_version` recorded in the file)
but are not part of the lexicon tree. See `SCOPE.md` "Versioning
policy".

## When a lexicon should change

Add or remove entries when:

- a new corpus surfaces a systematic mis-classification
- new vocabulary enters general use (e.g. domain-specific
  reporting verbs)
- a deny-list reveals a recurring false positive

Do not add entries to:

- bias the instrument toward a particular register
- target a specific LLM's vocabulary
- chase a specific downstream metric

The instrument measures surface features; the lexicons must remain
descriptions of the language, not knobs against an outcome.
