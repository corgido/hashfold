# Verification protocol

This document describes how to verify that a deployed instrument
matches the canonical build. Verification is your primary defence
against silent corruption: a supply-chain compromise that
altered any compiled artefact would change the verification output.

Run the protocol on first install, before each release adoption,
and on a periodic schedule (recommended monthly) for long-running
deployments.

## Quick check (one minute)

```
pytest instrument/                           # unit + golden tests
python -m tools.build_lexicons   --version v1 --check
python -m tools.build_catalog    --version v2 --check
python -m tools.build_core_hash               --check
python -m tools.build_joint_golden            --check
python -m tools.build_emit_golden             --check
python -m tools.check_layers
```

Expected output:

- `651 passed` from pytest
- `instrument/lexicons/_v1.py: ok` and `_data/lexicons/v1/manifest.json: ok`
  from build_lexicons
- `instrument/emissions/catalog_v2.py: ok` from build_catalog
- `instrument/_core_provenance.py: ok` from build_core_hash
- `14 goldens ok` from build_joint_golden
- `14 emit goldens ok` from build_emit_golden
- silent success (exit 0) from check_layers

Any failure indicates the install is not the canonical build. Do
not deploy.

## What each check verifies

### `pytest instrument/`

Runs 651 tests covering the kernel, reading layer, emissions,
routing, SPC, the bootstrap, and the HTTP adapter. Includes 14
joint-reading goldens (regression on real fixture documents), 14
emit goldens (full emission output regression), and the
uncertainty goldens (`fixtures/uncertainty_golden/`, pinning the
deterministic bootstrap cross-platform). A failure here means
the runtime behaviour has changed.

### `tools.build_lexicons --check`

Re-runs the lexicon compilation in memory and compares to
`instrument/lexicons/_v1.py`. A `drift` failure means either the
source JSONs in `_data/lexicons/` were edited without
regenerating, or the compiled module was edited directly. The
compiled module's `BODY_SHA256` field carries an attestation; the
check verifies the recompilation produces the same bytes.

### `tools.build_catalog --check`

Same pattern for the emission catalog. The compiled module
carries a `SOURCE_SHA256` field; the check verifies the JSON
source has not changed without regenerating.

### `tools.build_core_hash --check`

Recomputes the build-time hash of the measurement-core *source*
(kernel + reading + lexicons) and compares it to the frozen value in
`instrument/_core_provenance.py`. This is the gate that pins the
*algorithm* — including frozen decision constants such as convergence
`AGREE_TOLERANCE`. A mismatch means the core source differs from the
audited build; confirm the frozen value also equals the
`metadata.core_code_sha256` stamped on records you are verifying. A
record whose `core_code_sha256` does not match your audited core was
produced by different code.

### `tools.build_joint_golden --check`

Re-runs the joint reading on each of the 14 fixture documents and
compares to the committed golden JSONs. A `DRIFT` here means the
reading-layer behaviour has changed since the goldens were
captured. This is the strictest check; any change to the
measurement layer surfaces as a drift here.

### `tools.build_emit_golden --check`

Same pattern for the full emission output. Tests the emission
layer (assembler, flags, coherence, register routing) end-to-end
on each fixture.

### `tools.check_layers`

Walks every `from instrument.X import ...` statement in the source
tree and asserts the import does not violate the L1→L4 layering
DAG. The runtime depends on this DAG; a violation means the
instrument is not the architecture documented in `SCOPE.md`.

## End-to-end reproducibility check

Beyond the build-tool checks, periodically verify the determinism
contract end-to-end. Pick a stored emission from your record store. Recover the original
input bytes. Re-run them through the deployed instrument and
compare:

```
python run.py original_input.md > fresh.json

python -c "
import json
fresh = json.load(open('fresh.json'))
stored = json.load(open('stored.json'))

# Strip the wall-clock timestamp; everything else must match.
fresh['metadata'].pop('timestamp', None)
stored['metadata'].pop('timestamp', None)

assert fresh == stored, 'determinism violation: outputs differ'
assert fresh['metadata']['reproducibility_hash'] == \
       stored['metadata']['reproducibility_hash'], 'hash mismatch'

print('OK: emission matches')
"
```

A determinism violation indicates either:

- The pin has changed without your knowledge (verify
  `instrument_version`, `lexicon_version`, `catalog_sha256` match
  the stored values);
- A non-deterministic edit has been introduced (open an issue —
  non-determinism is a security issue; see `SECURITY.md`).

### Offline verification (rehash a stored record)

Re-running the instrument proves determinism but requires the original
input and a deployed build. Because the wire form equals the hashed
canonical form (non-finite floats serialise as `null`, never bare
`NaN`), a stored record can also be verified *offline* by recomputing
its own hashes:

```
python -c "
import hashlib, json
from instrument.kernel.quantize import canonical_json

rec = json.loads(open('stored.json').read())   # strict JSON; must not raise
reading = dict(rec['reading']); reading.pop('ts', None)

assert hashlib.sha256(canonical_json(reading).encode()).hexdigest() \
    == rec['metadata']['reading_sha256'], 'reading_sha256 mismatch'
assert hashlib.sha256(
        canonical_json({'reading': reading, 'distances': rec['distances']}).encode()
    ).hexdigest() == rec['metadata']['content_sha256'], 'content_sha256 mismatch'
print('OK: record rehashes to its own content/reading hashes')
"
```

This confirms the record is internally consistent. It does **not**
confirm the code that produced it — for that, check that
`metadata.core_code_sha256` equals your audited core hash (run
`build_core_hash --check`). A record can be self-consistent yet
produced by a different core; both checks together close the gap. If a
stored record fails to parse under a strict JSON parser (a bare `NaN`
token), it predates the 0.8.0 serialisation fix — re-emit it.

## Sampling protocol

For large record stores, exhaustive verification is
impractical. Recommended sampling:

- **Daily:** verify ~0.1% of new emissions. Pick at random.
- **Weekly:** re-run one full fixture set
  (`pytest instrument/` plus the build-tool `--check` modes).
- **Per release:** re-run the full fixture set on the new version
  and compare emission outputs to a sample from the previous
  version. Document any differences before adopting.

A determinism failure on any sampled emission triggers an
immediate stop-deploy and full re-verification.

## Audit trail

Each verification run produces:

- `pytest`: a junit XML at `.pytest-junit.xml` (path configurable
  in `pyproject.toml`)
- `build_*` tools: stdout reports, exit codes
- `check_layers`: stdout report, exit code

If you are required to maintain a verification audit trail,
capture stdout, the junit XML, and the exit codes from each run,
keyed by date and pinned version.

## What this repository does not provide

The repository provides the runtime, the source, and the build
attestations. It does *not* provide:

- A signed binary artefact (the instrument ships as source)
- A reproducible build attestation (e.g. SLSA) — the build is
  trivially deterministic from source, but you are responsible for
  verifying that your environment runs the build faithfully
- A multi-party reproducibility attestation — you are the only
  party who can attest that your deployment matches the source

This is a deliberate trade-off: the record's integrity properties
rest on your control of your own deployment, not on a
maintainer-attested binary.

### Two integrity surfaces (0.9.1)

`input_sha256` is raw-byte integrity — it is computed over the raw
transport bytes before any decode, and any byte change fails it (and
`reproducibility_hash`, which folds it). `content_sha256` /
`reading_sha256` are measurement integrity — an equivalence
fingerprint of the canonicalised measurement. Non-semantic formatting
(newline convention, BOM, trailing whitespace, blank-run length) does
not move them, by design. Check `input_sha256` to ask "is this the
document that was submitted?"; recompute the measurement hashes to
ask "are these the numbers it measures to?".

### Derived advisory fields (0.9.1, extended 0.10.0)

The arc emission (per-slice deltas, per-dimension summaries, slice
labels) and the `register.evidence` calibration blocks —
`reference_envelope` (percentile, empirical exceedance),
`reference_provenance`, and `feature_calibration` (empirical
p-values, BH q-values) — are DERIVED advisory views: pure
deterministic arithmetic over hash-attested inputs (the reading's
`trajectory` block; the distances plus pinned reference bytes).
They are not independently hashed; an auditor verifies them by
recomputation from the attested values
(`instrument/emissions/tests/test_arc_derived.py` shows the exact
recomputation for the arc; `docs/METROLOGY.md` §12 gives the
formulas for the calibration blocks). An input perturbation
therefore cannot move any derived number without moving
`content_sha256`; substituting different reference bytes is caught
by pinning the reference JSON's SHA256 (`docs/CALIBRATION.md`).
The `percentile` values on the `distances` records themselves are
inside `content_sha256`. The opt-in `uncertainty` block (0.10.0)
also rides outside the hashes: it is a pure function of the input
bytes and the replicate count, verified by replaying the input
(`docs/API.md`, "Uncertainty block").

Verification also says nothing about **baseline fitness**. Every check
here confirms the record is self-consistent and produced by the audited
code and data; none of them confirm that the reference distribution the
`distances` are measured against fits your deployment. A
fully-green verification on an uncalibrated deployment is still not a
valid drift signal — the distance is measured in the reference's
coordinate system, and the bundled references are seeds, not a baseline.
Calibrating a baseline on your own output is a separate, mandatory
step; see `CALIBRATION.md`.
