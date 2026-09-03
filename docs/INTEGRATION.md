# Integration patterns

This document describes how to wire hashfold into a pipeline. The
patterns below assume you have read `SCOPE.md` and
`INSTALLATION.md` and have decided to use the audit shape as the
canonical record.

## The baseline-and-deviation pattern

The intended workflow is:

1. **Day X — capture baseline.** Run the instrument over a
   representative sample of LLM outputs. The sample should be
   large enough that your downstream metric of interest has a
   stable distribution, and it should reflect your actual operating
   conditions (same prompts, same model, same
   temperature, same audience).
2. **Compute baseline statistics.** From the audit-shape output of
   each sample document, derive whatever statistics you need: per-feature percentiles, per-axis
   convergence rates, per-cohort distances, per-flag rates if
   inference is being consumed at all.
3. **Day X+1 onward — measure each new output.** Run the
   instrument on every new LLM output. Store the audit-shape JSON
   alongside the input, indexed by `reproducibility_hash`.
4. **Detect deviation against the baseline.** Compute your
   statistics on each new emission and compare to the baseline
   distribution. You decide what counts as significant deviation —
   the instrument does not.

The instrument's role is to provide the same numbers from the same
bytes. Detecting whether a new emission is "drifted" from the
baseline is your analysis. This is by design and is the
load-bearing claim of the measurement-only posture: the library
ships measurements; you ship interpretation. Calibrating the
baseline on your own deployment is not optional — the distance
metric is defined in the reference's coordinate system, so a
baseline built elsewhere would measure the wrong thing. See
`CALIBRATION.md` for why — and for the supported procedure: step 1
above is `python -m tools.build_reference` (stdlib-only), and step 4
gains a first-class anchor by deploying the produced reference via
`INSTRUMENT_REFERENCES_DIR` and reading the distance to your own
cohort out of every emission.

### Step 4, made concrete: control charts over the emission stream (0.10.0)

Step 4 ("detect deviation") has a supported implementation since
0.10.0. The runtime stays per-document and stateless by design (an
emission never depends on which documents preceded it); the stream
analysis runs offline, on a capture you drive:

1. **Capture emissions as JSONL** — one JSON object per line, `audit`
   or `full` shape, in time order. The simplest wiring is to append
   each response body to a dated file:

   ```
   curl -sX POST --data-binary @output.md \
        'http://instrument:8000/?shape=audit&register_hint=acme_normal' \
        >> emissions-2026-07.jsonl
   echo >> emissions-2026-07.jsonl
   ```

2. **Run the control charts on a cadence** (daily or weekly batch,
   and after any deployment change):

   ```
   python -m tools.control_chart \
       --emissions emissions-2026-07.jsonl \
       --reference /etc/instrument/references/acme_normal_v1.json \
       --as-of 2026-07-31 --arl --out report-2026-07.json
   ```

   The tool extracts each line's distance to the named reference
   (lines with no usable distance are counted and listed in
   `skipped`, never silently dropped), runs the three
   `instrument.spc` charts — individuals, CUSUM, EWMA (~ ISO
   7870-2/-4/-6) — against the reference's persisted cross-validated
   null, and writes a byte-stable JSON report. Requires a reference
   built by the 0.10 builder (`self_distance.values` persisted);
   older references exit with an error telling you to rebuild.

3. **Read the chart state** (`summary.state`), which separates the
   two events a naive per-document threshold conflates:

   - `in_control` — the stream still looks like calibration. No
     action.
   - `isolated_exceedance` — one (or a few) individual documents
     beyond the stated percentile, with no memoried-chart signal.
     Operationally: inspect those documents (the report lists the
     exceeding indices); do not re-baseline over one outlier.
   - `sustained_shift_signal` — the EWMA or CUSUM signalled: evidence
     has accumulated across documents that the process mean has
     moved. Operationally: treat as a regime change — investigate
     the pipeline (model version, prompt template, decoding
     parameters), and if the change is intentional, recalibrate
     (new reference `--version`).

   The states are descriptive, never actions: the out-of-control
   action plan — who investigates, what gets quarantined, when to
   recalibrate — is yours, by design (`instrument/spc.py`).

4. **Check the baseline's age while you are there.** The report's
   `baseline_age` block judges the reference's `calibration_date`
   against its own persisted `recalibration_policy.max_age_days`
   (`--as-of` is echoed into the report so it stays reproducible; a
   stale baseline is itself a finding). The policy's
   `triggers` list names the standing reasons to rebuild: model
   update, prompt change, age beyond `max_age_days`, or 100+ new
   documents to calibrate on.

5. **Calibrate the alarm thresholds against your own ARL.** `--arl`
   appends an empirical average-run-length table — the reference's
   own null resampled under injected shifts of 0/0.5/1/1.5/2 σ₀ —
   so "how often will this chart false-alarm on in-control data,
   and how fast does it catch a real shift" is measured on your
   distribution, not assumed from normal theory.

Before trusting a positive signal, run the validation protocol in
`docs/VALIDATION.md` ("User protocol — the study that scales"):
the same tooling, run against your own reference and corpus, gives
you your detection rates, your negative control, and your batch
power at your document counts.

## Practical wiring

### Synchronous pipeline (HTTP)

The simplest integration is a one-request-one-document HTTP call:

```
import json, hashlib
import urllib.request

def measure(text_bytes: bytes, base="http://instrument:8000") -> dict:
    req = urllib.request.Request(
        f"{base}/?shape=audit",
        data=text_bytes,
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())

emission = measure(open("output.txt", "rb").read())
record = {
    "input_sha256": emission["metadata"]["input_sha256"],
    "repro_hash":   emission["metadata"]["reproducibility_hash"],
    "emission":     emission,
}
```

Store `record` in your record store. The
`reproducibility_hash` is the verification primitive: a future re-
run on the same pin should produce the same hash.

### Asynchronous pipeline (queue + worker)

For high-volume or long-document workflows, run the HTTP server
behind a queue:

- **Producer:** writes `(doc_id, text_bytes)` to a queue.
- **Worker:** pulls from the queue, POSTs to the instrument,
  writes the audit-shape JSON to the record store keyed by
  `doc_id`.
- **Verifier (periodic):** picks a random sample of stored
  emissions, re-runs them, and asserts byte-equality of every
  field except `metadata.timestamp`.

Workers are stateless and can be scaled horizontally. The
instrument is import-safe and zero-I/O on the hot path, so
throughput is CPU-bound (pure-Python feature extraction; measured
~5 ms per kB single-threaded on commodity x86-64, i.e. a
maximum-size request of ~80 kB costs roughly 0.4 s of one core).
Benchmark on your own hardware before sizing; scale with
processes, not threads (GIL).

## Pinning policy

Your stored record should pin three values explicitly and verify
them on every emission:

- `instrument_version` — software version
- `lexicon_version` — lexicon snapshot (`v1`, `v2`, ...)
- `catalog_sha256` — exact bytes of the catalog source JSON

These three are sufficient to reproduce any measurement byte-for-
byte. The `reproducibility_hash` field folds them into a single
SHA256 along with the input bytes for convenience.

When a new version of any of these is published:

1. Verify the new version reproduces your stored emissions on a
   representative sample. Specifically: re-run the
   sample under the new pin and confirm that the *measurement
   layer* produces the same numbers. Inference layer outputs
   (flags, labels, bands) may legitimately change; the canonical
   record (audit shape) should not.
2. If the new version produces the same numbers, adopt it without
   re-baselining.
3. If the new version produces different numbers, treat it as a new
   measurement device and re-baseline from scratch. While the major
   version is 0, measurement-altering changes ship with a minor-
   version bump (`CHANGELOG.md` states the policy); a numeric change
   on a patch version is a defect, not a feature.

## Storage

The audit-shape JSON for a typical 1000-word document is roughly
50 kB. Storage is your responsibility; recommended
practice is to store the JSON byte-for-byte (no
re-canonicalisation, no field re-ordering) so the
`reproducibility_hash` remains valid against the stored copy.

For high-volume pipelines, consider:

- Compressing stored emissions (typical 10× ratio with gzip).
- Indexing by `(input_sha256, reproducibility_hash)` rather than
  by document content — this lets you detect duplicate inputs
  without storing them twice.
- Retaining the input bytes alongside the emission for the
  duration of your audit window. The
  `reproducibility_hash` is only useful if the input bytes can be
  re-fed to the instrument.

## Inference layer (optional)

If you want to consume the instrument's advisory inference layer (flags, register match/drift/break, coherence
bands), use the `full` shape rather than `audit`:

```
GET /?shape=full
```

`full` returns the audit content plus the inference layer. Both
are present; ignore the inference content if you choose. Storing the full shape preserves both records;
discarding the inference content later is a one-line filter.

Decide explicitly whether to consume inference at all.
Recommended: store the full shape during day-one rollout; once
your own analysis layer is in place, switch to the audit shape and
rely on your analysis for any "is this drifted?" question.

## Testing the integration

Your integration tests should:

- POST one of the provided fixtures (`fixtures/source/*.md`) and
  assert the returned `reproducibility_hash` matches the value
  stored alongside the fixture's golden under
  `fixtures/emit_golden/` (modulo `metadata.timestamp`).
- POST a 1-byte input and assert a `400` response.
- POST a too-large input and assert a `413` response.
- POST 100 identical inputs and assert all 100 emissions have the
  same `reproducibility_hash`.

These four tests confirm that your deployment is correctly
proxying the instrument and that the determinism
contract holds end-to-end.
