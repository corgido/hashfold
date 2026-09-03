# Surface-feature measurement and the demarcation problem

## 1. Introduction

The automated analysis of long-form text has, in recent decades,
moved decisively from rule-based methods toward statistical and,
more recently, neural approaches. Each successive generation of
methods has promised greater accuracy at the cost of decreased
interpretability, and the trade-off has generally been accepted as
worthwhile. There are, however, settings in which the trade-off
appears less attractive than it might at first seem. Among these
are settings governed by formal compliance regimes, where the
auditability of an instrument's outputs is itself a legal
requirement.

It is the contention of this paper that surface-feature measurement
— that is, the determination of textual properties that can be
computed from the raw input by a fixed and inspectable procedure —
remains a legitimate and indeed essential category of analysis,
notwithstanding the apparent primitiveness of the methods involved.
The argument proceeds in three parts. First, I shall sketch the
demarcation problem as it arises in compliance contexts. Second, I
shall consider what kinds of textual properties are amenable to
surface-feature measurement and what kinds are not. Third, I shall
suggest that the proper response to the inevitable limits of such
measurement is not to abandon the category in favour of inferential
methods, but to ensure that those limits are themselves explicit
and audit-traceable.

## 2. The demarcation problem

A measurement device is sometimes characterised, somewhat
informally, as one whose outputs are determined by its inputs
together with a published procedure. This characterisation is
adequate for many purposes but tends to break down at the margins.
Consider, for instance, a thermometer: it is uncontroversially a
measurement device, yet its outputs are determined not only by the
temperature of the medium and a published procedure but also by a
calibration that was performed against some external reference.
Are we to say that the thermometer is, after all, an inferential
device, since its calibration encodes assumptions about the
external reference?

The natural response is to distinguish between the calibration of
a measurement device — which fixes its scale relative to some
agreed reference — and the inferential application of a model —
which uses the device's outputs to draw conclusions that go
beyond what the device itself measures. The thermometer is
calibrated; the conclusion that the patient has a fever is an
inference. This distinction is workable, but it places considerable
weight on what counts as "going beyond" what the device measures.

The difficulty is sharpest when the device's calibration itself
encodes a normative judgement. Suppose, for instance, that a
text-analysis device reports a "drift" label whenever a document's
distance from a calibrated centroid exceeds some threshold. The
threshold is, in a formal sense, a calibration: it fixes the
device's scale. But it is also, in another sense, an inference,
because it embeds a claim about what should count as drift, and
that claim is rarely traceable to anything other than the
particular corpus on which the threshold was determined.

I shall argue that this case admits of two distinct readings,
which have very different consequences for the compliance status
of the device. On the first reading, the threshold is a feature of
the device, comparable to the calibration of a thermometer; the
device reports drift, and the user is responsible for any further
interpretation. On the second reading, the threshold is the result
of an embedded model — a model of what the calibration corpus
looked like — and the device's claim that a given document has
drifted is therefore an inference, not a measurement.

The choice between these readings is not merely terminological.
It determines what the device must document, what claims it can
defensibly make about its own outputs, and where liability for
interpretation properly resides.

## 3. Surface features as measurement

Surface features of text — token counts, type-token ratios,
punctuation densities, lexical-class distributions — share an
important property that distinguishes them from most other
analytic outputs: they can be computed by a procedure that
depends only on the input text and a published rule. There is no
hidden model, no learned parameter, no embedded judgement about
what the text should look like. The price of this transparency is
that surface features capture only what is on the surface; they
say nothing about meaning, intention, or quality.

This limitation is sometimes treated as a fatal objection. The
argument, in its strongest form, runs that surface features are
not really informative about anything that matters; that the
properties of texts which affect downstream consequences — whether
a document is persuasive, accurate, or appropriate — are precisely
those properties which surface features fail to capture. The
implication is that we should abandon surface measurement in
favour of methods which engage with content directly.

The response to this objection is, I suggest, threefold. First,
the inference from "surface features do not capture what
matters" to "surface features are not informative" is a
non-sequitur; it confuses sufficiency with relevance. Surface
features may not be sufficient to determine the properties that
matter, but they may nevertheless be informative about them.
Second, the methods proposed in place of surface measurement —
typically, learned classifiers — face their own well-known
problems with auditability and stability, problems which are
themselves obstacles in compliance contexts. Third, and most
importantly, the comparison is not between surface measurement
and inference but between surface measurement and inference
*plus surface measurement*. There is no setting in which one
must choose between them; any inferential method consumes surface
features as input, and the question is therefore whether the
surface measurements should be made transparent to the user or
hidden inside the inferential machinery.

The case for transparency is, I think, decisive. A user who
receives both the surface measurements and the inferential
output is in a strictly better position than one who receives
only the inferential output. The former can audit the inference;
the latter cannot. In compliance contexts, where the user is
typically also the party responsible for any claims made on the
basis of the device's outputs, this asymmetry is significant.

## 4. The limits of surface measurement

It would be a mistake to conclude from the foregoing that surface
measurement is a complete or adequate methodology for all
analytic purposes. There are properties of texts which surface
measurement cannot capture, and any defensible practice of
surface measurement must be explicit about what these are.

The clearest examples are properties which depend on the
relationship between the text and an external referent: whether a
factual claim is correct, whether a description is accurate,
whether a recommendation is appropriate to a particular context.
These properties are, in principle, beyond the reach of any
analytic method that depends only on the text itself, and so
they are beyond the reach of surface measurement *a fortiori*.

A more subtle category includes properties which depend on the
reader's interpretation: whether a passage is clear, whether an
argument is convincing, whether a tone is appropriate. These
properties are not strictly external in the way that factual
correctness is, but they vary across readers in ways that no
fixed procedure can capture. Surface features may correlate with
these properties — sentence-length variance with readability, for
instance — but the correlation is empirical rather than
constitutive, and it should not be presented as if it were the
latter.

The proper response to these limitations is not to ignore them,
nor to compensate for them by adding inferential machinery to
the measurement layer, but to document them. A surface-feature
measurement device should state clearly what it does and does
not measure. The user is then in a position to decide whether
its outputs are useful for the user's purpose; the device is
not in the position of having to decide for them.

## 5. Conclusion

The case for surface-feature measurement, in its compliance
application, rests on three claims. First, the demarcation
between measurement and inference is real and consequential; it
is not merely a matter of degree. Second, surface features are
genuinely informative, and the methods that capture them are
genuinely transparent; the trade-off against inferential methods
is favourable in any setting where auditability is required.
Third, the limitations of surface measurement are themselves
amenable to clear documentation, and the proper response to
those limitations is to document them rather than to compensate
for them by introducing inferential elements.

None of this is to deny the value of inferential methods in
their proper place. The argument is rather that the measurement
layer of any compliance pipeline should remain at the surface,
where it can be audited; the inferential layer should be built
on top of the measurement layer by whoever wishes to consume the
measurements; and the responsibility for the inferential claims
should rest with the consumer, not the device.
