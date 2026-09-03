# Security

## Threat model

hashfold is a deterministic measurement library that runs on text
supplied by the caller. The threats it is designed to
withstand are:

1. **Malformed input.** The instrument operates on raw bytes and
   must not crash, hang, or produce non-deterministic output on any
   input. Inputs above the configured word cap are rejected with a
   `400` from the HTTP server; inputs below the measurement
   envelope produce a structurally complete record with the
   `unprojectable` register label.

2. **Filesystem assumptions.** The runtime is import-safe on a
   read-only filesystem. Lexicons and the emission catalog are
   compiled to Python modules at build time; the runtime reads only
   the bundled reference JSONs (lazily, once per process). No
   per-document state is written to disk.

3. **Environment leakage.** Exactly two modules read `os.environ`:
   `instrument/config.py` (configuration parsing) and the HTTP /
   worker handlers under `instrument/serve/`. This is enforced by
   an AST-level test (`test_no_env_reads.py`) that walks every
   non-test source file under `instrument/` and fails on any
   `os.environ` access outside the two allowed surfaces.

4. **Network surface.** The instrument makes no outbound network
   calls. The bundled HTTP server accepts inbound POST requests
   only; deploy behind a reverse proxy that handles TLS,
   authentication, and rate limiting.

## What the instrument does *not* protect against

hashfold is a measurement device. It is not a content filter, a
privacy classifier, or an authentication mechanism. If you run it as
part of a larger pipeline, you are responsible for:

- Authenticating callers
- Rate-limiting requests
- Filtering inputs that should not reach the instrument at all
- Storing emissions in accordance with your own data governance
  policy

One adversarial caveat deserves its own line: the instrument's
formulas, lexicons, and deny-lists are published (deliberately —
that is the defensibility model). A party who controls the input
text and knows the formulas can author text that sits wherever
they want in feature space. The measurements remain true — the
text really does have those surface features — but **distance to a
baseline is not tamper-evidence about authorship or intent**.
Pipelines must not treat "no deviation from baseline"
as proof that nothing adversarial occurred; the instrument
measures prose, it does not authenticate it.

## Supply chain

### Dependencies

The runtime has zero external Python dependencies. `pyproject.toml`
declares no `dependencies` array; the only optional dependency is
`pytest`, used by the test suite and not at runtime. This is by
design and is the single most consequential supply-chain decision
in the project.

A CycloneDX SBOM attesting this can be generated for any release
with `python -m tools.build_sbom` (writes `sbom.cdx.json`: the
package itself plus an intentionally empty components list, with a
source-tree SHA256). A copy is committed for each release.

### Build artefacts

Three Python modules are auto-generated from JSON sources:

- `instrument/lexicons/_v1.py` — compiled from
  `_data/lexicons/v1/*.json`
- `instrument/emissions/catalog_v2.py` — compiled from
  `_data/emissions_catalog/v2.json`

Both carry SHA256 attestations (`BODY_SHA256`, `SOURCE_SHA256`) that
let you verify the compiled module corresponds to the
shipped source JSONs. The build tools support a `--check` mode
that re-runs the compilation in memory and compares to the on-disk
module; any drift fails CI.

The five reference distributions in `instrument/routing/references/`
are JSON files, not generated. Each carries a `commit_hash` field
recording the source commit at calibration time. The seeds predate
the public repository, so that commit is not resolvable here; treat
the seeds as unverifiable placeholders and calibrate your own
reference (`docs/CALIBRATION.md`).

### Code signing

The source tree ships unsigned. If your pipeline requires signed
artefacts, sign the tree yourself; the `--check` gates and
`core_code_sha256` give you the bytes to sign against.

## Vulnerability reporting

Report security issues privately through GitHub Security Advisories
on `corgido/hashfold` ("Report a vulnerability" under the Security
tab). Do not open a public issue for a security report.

This is a solo-maintained open-source project. There is no response
SLA. Reports that affect determinism, reproducibility, or the
integrity of the hash chain are treated as the highest priority;
issues confined to the advisory inference layer (flags, labels,
bands) are lower priority. Any fix that touches the measurement path
must pass the full CI reproducibility matrix before release, so a
determinism fix cannot ship faster than the matrix can prove it.

## Known limitations

The instrument's English-only lexicons mean that non-English input
produces degraded measurements. This is not a security issue per se,
but be aware that outputs on non-English input do not have the same
defensibility as on English input. A multilingual lexicon snapshot is on the roadmap.
