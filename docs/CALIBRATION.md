# Why Calibration Runs on Your Data

*…and why it cannot ship pre-built.*

**The short version.** hashfold ships frozen measurement *primitives* and requires
you to calibrate the baseline they are compared against — in your own
environment, on your own model output. This is not the maintainer offloading work.
A baseline calibrated anywhere other than your deployment is not a conservative
default; it is a wrong answer wearing the costume of a default. Below is the
precise reason, grounded in how the distance is actually computed.

---

## 1. The metric is *defined by* the reference, not merely compared to it

The instrument does not emit absolute verdicts. It emits a position in feature
space and a **distance** from each reference profile. That distance
(`distance_method = feature_zscore_l2`) is computed in four steps, and the
reference supplies the parameters at **every** step:

1. **Per-feature z-score.** Each feature is centered and scaled by the
   reference's own mean and standard deviation
   (`reference.pc_zscore_mean`, `pc_zscore_std`): `z = (value − mean) / std`.
2. **Projection onto a learned basis.** The z-scored features are projected onto
   the reference's principal-component axes (`reference.pc_loadings`) — a basis
   *learned from the reference's distribution*.
3. **Per-component standardisation.** Each projected component is centered on the
   reference's centroid and divided by the reference's per-component standard
   deviation (`reference.pc_centroid`, `pc_composites[…].std`).
4. **L2.** The standardised components are combined by Euclidean distance.

Read step by step, this is the whole argument: the centering mean, the per-axis
scale, the **basis** the distance is measured along, and the **centroid** it is
measured from are all properties of the reference. The reference does not give
you a point to compare against — it defines the entire coordinate system the
comparison happens in.

## 2. "Normal" is a property of *your* deployment

A reference is "what normal output looks like." But the output the instrument
measures is LLM output, and that is a function of the prompt, the model, the
decoding parameters, the system instructions, the task, and the domain. Every
one of those is a deployment variable. "Normal" is therefore defined by *your*
prompt/model/domain stack. It is not a universal constant that anyone could
measure once and ship.

## 3. A foreign baseline is the wrong coordinate system, not a rough one

Because all four layers above are reference-derived, a baseline built on someone
else's distribution does not hand you a slightly imperfect coordinate system; it
hands you the wrong one. If a reference were calibrated on one model answering
general questions and you run another model drafting contracts, every distance
becomes *"how many of the reference's standard deviations, along the reference's
principal axes, is my output from the reference's centroid"* — a quantity with
no defensible interpretation for detecting drift in your deployment. The
failure mode is concrete and two-sided:

- **False alarms:** ordinary domain difference reads as large distance, because
  your output sits far from a centroid that was never yours.
- **Missed drift:** real movement in your output goes undetected, because the
  axes and scale that would have made it visible were learned from the wrong
  distribution.

This is not a tuning imperfection. With the wrong reference, the distance is not
*approximately* right — it is measuring a different thing.

## 4. Why this is the rigorous choice, not the lazy one

The "lazy maintainer" reading has it backwards. Shipping a confident-looking
baseline calibrated on someone else's data is the *easy* thing to do. In an
audit context it is also the *dangerous* thing to do, because it manufactures
false confidence in a number that does not mean what it appears to mean — and a
confidently-wrong measurement is worse than an honest absence of one.

The rigorous choice is to freeze the measurement primitives — the features,
computed bit-identically on every conforming host and attested by
`core_code_sha256` — and require the baseline to be built where the data
actually lives. The library can attest *what was measured and by exactly which
code*; it cannot attest *what is normal for you*, because nobody but you
has your input distribution. It is the difference between a scale
manufacturer, who can certify the scale, and the act of weighing your luggage,
which only you can do — with your luggage.

## 5. What the bundled references are for

The shipped reference profiles are **seeds**. They establish the shape of the
output and let you sanity-check the pipeline end to end — that features compute,
that distances populate, that the record hashes and verifies. They are
explicitly **not** a production baseline. Treat any distance computed against
them as illustrative until you have calibrated on your own corpus.

(A practical corollary: any feature that is `null`/non-finite contaminates the
projection — a NaN feature makes every component, and therefore the distance,
unmeasurable for that reference. Below-envelope inputs will not produce
meaningful distances. This is by design: a partial projection that silently
dropped features would be worse than refusing to project.)

## 6. Calibrating your baseline

Calibration is building a reference distribution from *your* output, plus
measuring how much the instrument's numbers move on their own in *your*
environment. A workable recipe:

- **Span the register you care about.** Choose calibration prompts/problems that
  cover the range of tasks and domains your deployment actually serves; a
  baseline is only valid across the territory it was built on.
- **Measure the noise floor.** Run the same prompt repeatedly at your real
  decoding settings (temperature, top-p, etc.) and observe how far the output
  moves from sampling alone. That spread is the instrument breathing, not the
  model drifting — and you cannot call any distance "large" until you know it.
  The noise floor is itself deployment-specific.
- **Make comparability explicit.** Persist each calibration trace as a full
  emission record, carrying its `core_code_sha256`, `lexicon_version`, and
  `catalog_sha256`. A baseline is only comparable to live readings produced by
  the same core and data; those fields are how you prove it, rather than
  assuming it.

Once your baseline exists, the distances mean what they should: movement
measured in *your* coordinate system, against *your* normal — which is the only
frame in which "drift" is a claim you can defend.

## 7. The null distribution is cross-validated (0.10.0)

Before 0.10.0 the builder persisted only the median and p95 of the
calibration corpus's own self-distances, and computed them by
**resubstitution**: each document scored against a reference built
*including that document*. That is a biased estimate — a document in
the fit pulls the centroid toward itself and inflates the spread along
its own direction, so its measured distance is systematically smaller
than a fresh document's would be. A `beyond_p95` position calibrated
that way fires on well over 5% of genuinely in-distribution data.

0.10.0 replaces the persisted null with a **10-fold cross-validated**
one: the path-sorted corpus is cut into ten contiguous blocks; each
block is scored against a model fitted on the other nine; the pooled
held-out distances — every document scored by a model that never saw
it, which is the situation every future document is in — are persisted
in full (`self_distance: {n, median, p95, values, basis}`). Two
consequences to expect:

- **Rebuilt references will usually show a larger p95 than their
  0.9.1 build did.** That is the fix, not a regression: the old number
  was optimistic, the new one is what in-distribution data actually
  does. Thresholds tuned against a 0.9.1 p95 should be re-derived.
- **The runtime can now quote a percentile.** With the full null
  persisted, every projected emission carries
  `reference_envelope.percentile` (mid-rank position of the document's
  distance within the null) and `empirical_exceedance` — the fraction
  of the baseline's own documents at least this far out, i.e. the
  empirical false-positive rate of alarming at this distance.

Per-fold feature screens may differ slightly from the full model's;
that fold-to-fold variation is part of the honest spread and is
deliberately not suppressed. Corpora under 10 documents (or `--no-cv`)
fall back to resubstitution and say so in `basis` — the runtime quotes
that basis verbatim, so a resubstitution envelope is visibly weaker.
One caveat at very small n: with only one or two documents per
register in the corpus, a fold model can be *blind* to a held-out
document's deviation direction (its axes never learned it), which can
make individual held-out distances smaller, not larger. The stability
block (section 8) is how you detect that regime.

## 8. Reading the stability block

The builder reuses the ten fold fits as delete-10% jackknife
replicates and persists `stability`:

- `centroid_shift_std_units` (per PC, mean/max over replicates): how
  far the centroid moves, in reference std units, when a 10% block of
  the corpus is deleted. Values well below 1 mean no single block
  steers where "normal" sits. A max approaching 1 means one block of
  documents is dragging the centroid a full standard deviation — the
  baseline is that block's opinion, not the corpus's.
- `loading_alignment_abs_cos` (per PC, min/mean): |cos| between the
  full model's loading vectors and each replicate's, matched by PC
  rank. Near 1 means the axes themselves are stable. A low value
  (especially on trailing PCs) means the *coordinate system* rotates
  when part of the corpus is removed — distances along that axis are
  not trustworthy, and more data is needed before the geometry
  settles.
- `self_p95_replicate_range`: how much the null's tail moves fold to
  fold. A wide range means the p95 you are about to threshold against
  is itself unstable.

Every emission echoes the worst case
(`reference_provenance.stability_summary`: `max_centroid_shift_std`,
`min_loading_alignment`), so a record can be challenged on baseline
fragility without the reference file in hand.

## 9. How big must the corpus be

Hard floor 10 (below it there is no cross-validated null at all —
the builder warns and falls back to resubstitution), **minimum 30,
100+ recommended**. The reasons are quantitative, not stylistic:

- **p-value floor.** An empirical null with n points cannot support a
  p-value below 1/(n+1): nothing can be rarer than "beyond everything
  we calibrated on". At n=15 the strongest defensible claim is
  p ≈ 0.06 — you cannot even establish 5% significance. n=30 gives a
  floor of ~0.03; n=100 gives ~0.01.
- **Quantile resolution.** The p95 of a 15-point null sits between its
  14th and 15th order statistics — one document moves it. At n=30 the
  tail rests on ~2 points; at n=100 on ~5, and percentiles start to
  mean what they say.
- **Geometry stability.** Fewer than ~30 documents rarely pin down 4
  principal axes over ~50 features; the stability block will show it
  (low trailing-PC alignment). If it does, collect more data rather
  than trusting the distance.

## 10. Per-feature calibration carries its own false-discovery ledger (0.10.0)

Fifty-seven features compared on every document makes false positives
a certainty, not a risk: at a per-feature two-sided 5% level you
expect ~3 "significant" features on a perfectly ordinary document. A
record that located features against the baseline without saying so
would be an attackable gap. So references built by 0.10.0 persist a
101-point percentile grid per kept feature (`per_feature_quantiles`),
and every projected emission against such a reference carries
`register.evidence.feature_calibration`:

- `per_feature.<name>.percentile` — the document's value located on
  the reference's own grid (inverse-interpolated empirical CDF);
- `per_feature.<name>.p_two_sided` — the two-sided empirical p-value,
  floored at 1/(n+1) (section 9: an n-point calibration set supports
  nothing rarer than "beyond everything we calibrated on");
- `per_feature.<name>.q_value` — the Benjamini–Hochberg q-value across
  the whole family: the smallest false discovery rate at which this
  feature would be called discordant from the reference;
- `family_policy` — method, sidedness, the family definition, the
  p-value resolution floor, and `m`, the family size actually tested.

`m` varies per document. A feature that reads NaN on this document is
not evidence about the baseline, so it leaves the family rather than
being imputed — and the record shows the `m` the correction was
computed over, so the multiplicity control is auditable, not asserted.

**No alpha ships.** q-values are descriptive coordinates; a threshold
is a decision rule, and decision rules belong to the deployment, not
the instrument — nothing fires on this block. The intended reading,
worked: "on this document, features with q ≤ 0.05 — and only those —
would be reported discordant at a 5% false discovery rate." Your
monitoring can adopt exactly that rule, or a stricter or looser rate;
the stored record supports any of them without recomputation.

Degradation is explicit, as everywhere: bundled seeds and 0.9.1-era
references persist no grids, so the block is
`{"status": "reference_lacks_feature_quantiles"}`; a document
contributing no finite family member gets
`no_finite_features_for_calibration` with `m: 0`.

---

*See also: `METROLOGY.md` for the field-level record contract,
and `VERIFICATION.md` — note that verification confirms reproducibility
and provenance, never baseline fitness.*

**Feature-schema note (0.9.1).** Instrument 0.9.1 renamed
`rst.contrast_pressure` → `rst.contrast_marker_density` and
`rst.elaboration_pressure` → `rst.elaboration_marker_density`. The
bundled seeds were mechanically re-keyed and ship as `*_v2.json`
(statistics byte-identical; still 0.6.0-era exploratory seeds). A
reference built under an older instrument keeps its old keys and can no longer project — every distance against it is
silently `null`. The server warns loudly at boot
(`reference_feature_schema_mismatch` on stderr) for any registered
reference whose feature keys the running instrument does not emit;
rebuild such references with `tools.build_reference` under the
current version (re-calibration is a new `--version`, never an
in-place edit).


---

## The supported path (added in 0.9.0)

Everything above is the argument; this is the procedure. It is
designed to be completed in an afternoon with nothing installed
beyond the library itself.

1. **Collect a sample.** 30+ representative outputs (100+
   recommended — section 9) from the deployment you want to monitor —
   same prompts, same model, same decoding parameters. Save as
   `.md`/`.txt` files in a directory.
2. **Build the reference** (stdlib-only, deterministic):

       python -m tools.build_reference \
           --corpus-dir ./sample_outputs \
           --name acme_normal --cohort acme_normal --version v1 \
           --scope "what this baseline covers: model, prompts, period" \
           --collection-window "2026-05-01..2026-06-30" \
           --out /etc/instrument/references \
           --readings-out ./readings.jsonl

   `--collection-window` (required, 0.10.0) is a free-form statement
   of *when* the corpus was collected; it is persisted and echoed in
   every emission's `reference_provenance`, so records carry their
   baseline's vintage. Optional knobs: `--max-age-days` (default 180)
   and `--recalibration-note` populate the persisted
   `recalibration_policy` (age math happens offline, never at
   emission time); `--calibration-date` pins the build timestamp for
   deterministic rebuilds (on a fixed host + commit it is the only
   nondeterministic byte); `--no-cv`, `--no-stability`,
   `--no-feature-quantiles` skip the corresponding 0.10.0 blocks
   (debugging only).

   The tool prints the resubstitution self-distance as a projection
   sanity check, then builds and persists the **cross-validated null**
   (section 7) — `self_distance: {n, median, p95, values, basis}` —
   plus the jackknife **stability block** (section 8), per-feature
   percentile grids, and the provenance blocks. At runtime every
   projected emission then carries
   `register.evidence.reference_envelope` (position within/beyond the
   p95, plus percentile and empirical exceedance against the persisted
   null), `register.evidence.reference_provenance` (collection
   window, recalibration policy, stability summary), and
   `register.evidence.feature_calibration` (per-feature percentile,
   two-sided empirical p, and BH q-value against the stored grids —
   section 10). The bundled seeds
   carry none of this, and say so explicitly:
   `seed_reference_no_confidence_envelope` / `pre_0_10_reference` /
   `reference_lacks_feature_quantiles` — a seed cannot vouch for any
   distance. References built by 0.9.1 keep working; their envelope
   says `reference_predates_null_distribution` until rebuilt.
   `readings.jsonl` carries the per-document flat features for any
   further analysis your team wants to run.
3. **Deploy it.** Set `INSTRUMENT_REFERENCES_DIR` to the output
   directory. The server validates every reference at boot
   (malformed files abort startup with `ReferenceLoadError`) and
   logs which references it registered.
4. **Route against it.** `?register_hint=acme_normal` pins the
   distance to your baseline (the hint must equal `--cohort`
   exactly). Without a hint, your reference participates in
   auto-routing alongside the bundled five, and appears in every
   emission's `distances_to_all_references` (each record now carrying
   its own `percentile` where the reference persists a null).
5. **Pin the file.** The reference JSON's bytes are the
   coordinate system. Archive it with its SHA256 (the tool prints
   one); a stored emission is only re-checkable against the same
   reference bytes. Re-calibration (new prompts, new model) is a
   new `--version`, kept side by side — never an in-place edit.
   The persisted `recalibration_policy.triggers` name the standing
   reasons to rebuild: model update, prompt change, baseline age
   beyond `max_age_days`, or 100+ new documents to calibrate on.

What the tool does NOT do, by design: it does not decide
thresholds, define "drift", or score new documents. The reference
gives your team the coordinate system; the deviation policy is
yours (`docs/INTEGRATION.md`, "The baseline-and-deviation
pattern").
