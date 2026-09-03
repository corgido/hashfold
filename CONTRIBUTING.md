# Contributing

hashfold is a deterministic measurement library. The one property
every change must preserve is the one the project exists for: same
input bytes, same numbers, on every host. This document explains how
to check that locally and what the CI matrix expects.

## Setup

```
git clone https://github.com/corgido/hashfold
cd hashfold
pip install -e . pytest
```

Python 3.11 or later. No other dependencies — `dependencies = []` in
`pyproject.toml` is a design decision, and pull requests that add a
runtime dependency will not be merged.

## Run the checks before you push

```
python -m pytest instrument/ -q                      # 651 tests, ~20 s

python -m tools.build_joint_golden --check
python -m tools.build_emit_golden --check
python -m tools.build_lexicons --version v1 --check
python -m tools.build_catalog --version v2 --check
python -m tools.build_core_hash --check
python -m tools.migrate_references_0_9_1 --check
python -m tools.check_layers
python -m tools.build_uncertainty_golden --check
python -m tools.length_invariance --check
python -m tools.validation_study --profile smoke --check
```

These are exactly the steps `.github/workflows/reproducibility.yml`
runs on every cell of the matrix (Linux, macOS, Windows, Alpine/musl;
CPython 3.11–3.14; C and `fr_FR.UTF-8` locales). Each `--check`
regenerates its artefact in memory and byte-compares it with the
committed file. **The matrix is the acceptance criterion** for any
pull request that touches the measurement path; a green run on your
own machine is necessary but not sufficient.

## What kind of change you are making

**Documentation, tests, tooling outside the measurement path.**
Open a pull request. Keep the voice of the existing docs: direct,
technically precise, honest about limits.

**The measurement path** — anything under `instrument/kernel/`,
`instrument/reading/`, `instrument/lexicons/`, or the data those
modules are compiled from under `_data/`. These changes alter the
numbers, so they carry extra obligations:

1. **Do not break a `--check` gate to make a test pass.** If a gate
   fails after your change, the change moved a number. Either the
   move is intended (see step 3) or it is a bug in the change.
2. **Add the test first.** Every measurement fix in the history
   landed with a test that pins the corrected behaviour
   (`CHANGES-0.9.1.md` is the model).
3. **Regenerate in the mandated order, once, in a single commit:**
   references (if the feature schema changed) → catalog → core hash
   (`tools.build_core_hash`) → joint goldens
   (`tools.build_joint_golden`) → emit goldens
   (`tools.build_emit_golden`) → uncertainty goldens
   (`tools.build_uncertainty_golden`) → length-response audit
   (`tools.length_invariance --write`) → validation study
   (`tools.validation_study --profile smoke --write` and
   `--profile full --write`). Then re-run every `--check`.
4. **Bump the version per the policy in `CHANGELOG.md`.** While the
   major version is 0, a change that alters any measured number on a
   previously supported input is a minor bump, and `schema_version`
   moves if the reading's shape changed. Say what moved and why in
   `CHANGELOG.md`.
5. **Never use `random.Random`, `math.log2`, `x ** 2`, or any
   `unicodedata` lookup in the measurement path.** `AUDIT_FINDINGS.md`
   documents why each of these broke cross-host reproducibility;
   `kernel/detrandom.py`, `kernel/quantize.py`, and
   `kernel/scripts.py` are the replacements.

**Lexicons and the catalog.** Edit the JSON under `_data/`, then
regenerate with `python -m tools.build_lexicons --version v1` or
`python -m tools.build_catalog --version v2` (no `--check`). A new
lexicon *version* (`_v2.py`, `LEXICON_VERSION = "v2"`) is the right
shape for anything beyond a correction, because users pin
`lexicon_version`; `docs/LEXICONS.md` describes the procedure.

**Layering.** `tools/check_layers.py` enforces the L1→L4 import DAG
and `test_no_env_reads.py` confines `os.environ` to
`instrument/config.py` and `instrument/serve/`. Both run in the
suite. Do not add exceptions; pass values down instead.

## Pull request checklist

- [ ] `pytest instrument/` passes locally
- [ ] every `--check` gate above exits 0
- [ ] no new runtime dependency
- [ ] if a number moved: test added, artefacts regenerated in order,
      version and `CHANGELOG.md` updated
- [ ] if a doc changed: it still says what the code does, no more

## Reporting problems

Bugs and feature requests go through GitHub issues; the templates
under `.github/ISSUE_TEMPLATE/` list the fields that make a report
reproducible. Security issues go through GitHub Security Advisories
instead (`SECURITY.md`).

## License

By contributing you agree that your contributions are licensed under
the Apache License 2.0 (`LICENSE`).
