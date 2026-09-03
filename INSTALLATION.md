# Installation and usage

This document describes how to install and run hashfold. It has no
runtime dependencies beyond the Python standard library.

## Requirements

- Python 3.11 or later (the CI matrix covers 3.11–3.14)
- POSIX or Windows host (the instrument is import-safe on both)
- ~50 MB disk for the source tree; no per-document state on disk
- No network access required at runtime

The instrument does not call out to any external service. The
runtime hot path performs zero file I/O after a one-time lazy load
of the bundled reference distributions.

## Install (development mode)

```
git clone https://github.com/corgido/hashfold
cd hashfold
pip install -e .
```

The `-e` flag installs in editable mode, so local changes to the
source can be tested without reinstalling. For an installed
non-editable package use `pip install .` instead.

Run the test suite to verify the install:

```
pytest instrument/
```

The expected result is `651 passed`. The same suite passes on every
cell of the CI matrix; if it fails on your host, open an issue with
the failing test names, your OS, and your Python version.

## Install (container)

A reference container build is intentionally not bundled — the
library is small enough to embed in your own base image. A minimal
`Dockerfile` looks like:

```
FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["python", "-m", "instrument.serve.http"]
```

## Running hashfold

Three modes are supported. All three execute the same
measurement pipeline; the difference is only in transport.

### CLI (one-shot)

```
python run.py path/to/document.md
```

Emits the full JSON record on stdout. The default response shape is
`audit` (the canonical record).

### HTTP server

```
python -m instrument.serve.http
```

or, once installed, the `hashfold` console script — the same server:

```
hashfold
```

Default bindings: `0.0.0.0:8000`. POST a document body to `/`:

```
curl -sX POST --data-binary @document.md http://localhost:8000/
```

Configure via environment variables (see below).

Sizing: the measurement is CPU-bound, single-threaded per request
(~5 ms per kB on commodity x86-64; a maximum-size 80 kB request
costs roughly 0.4 s of one core). Scale with processes or
replicas, not threads. Benchmark on your own hardware.

## Environment variables

All settings have safe defaults. None are required.

| Variable | Default | Effect |
|---|---|---|
| `INSTRUMENT_HOST` | `0.0.0.0` | HTTP server bind address |
| `INSTRUMENT_PORT` | `8000` | HTTP server bind port |
| `INSTRUMENT_RESPONSE_SHAPE` | `audit` | Default `?shape=` value when not specified |
| `INSTRUMENT_MAX_WORDS` | `10000` | Reject inputs above this word count (`0` = unlimited) |
| `INSTRUMENT_CATALOG_VERSION` | `v2` | Catalog version to load |
| `INSTRUMENT_REFERENCES_DIR` | unset | Directory of your own reference JSONs, registered (and validated) at server boot; see `docs/CALIBRATION.md` |

Environment reads are confined to `instrument/config.py` and
`instrument/serve/`. This is enforced by an AST-level test
(`test_no_env_reads.py`).

## Pinning for reproducibility

For a record you intend to re-verify later, pin the following four
values from the emission's `metadata` block on day one and verify
them on every subsequent emission:

- `instrument_version`
- `lexicon_version`
- `catalog_sha256`
- `distance_method`

These four together uniquely determine the measurement procedure.
A `reproducibility_hash` field in the metadata folds them into a
single SHA256 along with the input bytes, so you can verify a
stored emission with a single comparison.

## Verification

After install, verify the build is intact:

```
python -m tools.build_lexicons   --version v1 --check
python -m tools.build_catalog    --version v2 --check
python -m tools.build_joint_golden            --check
python -m tools.build_emit_golden             --check
python -m tools.check_layers
```

All five must report success. If any reports drift, the install is
not the canonical build; reinstall from the repository at the
tagged release.

See `docs/VERIFICATION.md` for a fuller verification protocol, and
`CONTRIBUTING.md` for the full set of gates CI runs.

## Upgrading

hashfold follows semantic versioning on the `instrument_version`
field. When upgrading:

1. Re-run the verification commands above on the new tree.
2. Run your own representative-sample regression on measurements
   that were captured on the old version. If the new
   version produces materially different numbers on the same input,
   document the change and re-baseline before adopting.
3. Pin the new `(instrument_version, lexicon_version, catalog_sha256)`
   triple in your records.

A published version's measurement behaviour does not change; numeric
drift on an unchanged version is a defect, not a feature — report it. See `CHANGELOG.md` for the version history.

## Removal

`pip uninstall hashfold`. The library writes nothing outside its own
source tree, so removal is complete.
