# On the limits of inferential measurement

The distinction between measurement and inference is not always
preserved in the literature on automated text analysis, and yet it
remains foundational to any defensible methodology. A measurement
device is one whose outputs depend only on the inputs and a fixed
deterministic procedure; an inferential device is one whose outputs
additionally depend on a learned model, a calibration corpus, or a
threshold derived from such a corpus. The two should not be conflated.

It is sometimes argued that the boundary between the two is a matter
of degree rather than kind. This position appears to have some merit
when one considers, for instance, the role of stop-word lists or
tokenisation rules: any segmentation step encodes assumptions about
the language, and these assumptions could in principle be revised on
the basis of new evidence. The argument from continuity, however,
overlooks an important asymmetry. A tokenisation rule, once fixed,
applies identically to every input; its assumptions are explicit and
auditable. A learned threshold, by contrast, embeds the statistical
properties of a particular corpus in a way that is rarely transparent
and is, by construction, sensitive to the corpus from which it was
derived.

The implications for compliance contexts are considerable. Where the
purpose of a measurement device is to produce a record of what was
observed — rather than a judgement about what was observed — the
introduction of inferential elements may be counterproductive. Each
threshold a device applies is a claim about what should be considered
significant; each label it assigns is an interpretation. Such claims
and interpretations may be perfectly defensible in a research setting,
where their warrant can be examined and revised, but they sit
uneasily in a compliance setting, where the device's outputs may be
treated as authoritative.

It does not follow from this that inferential analysis has no place
in the compliance pipeline. The argument is rather that the
measurement layer and the analysis layer should be kept distinct.
The measurement layer should produce numbers whose provenance can be
traced to the input bytes and a published procedure; the analysis
layer should consume those numbers and apply whatever interpretive
machinery the user finds appropriate, with the user — not the device
— bearing responsibility for the resulting claims.

This separation is not merely cosmetic. It allows the same
measurement layer to support multiple analytic purposes without
requiring re-calibration; it permits the analysis layer to be
revised without disturbing the historical record; and, perhaps most
importantly, it places the burden of justification on whoever is
making interpretive claims, rather than on the device itself.

In what follows, I shall consider three specific consequences of
this separation, drawing on examples from automated text measurement
in regulatory contexts. The first concerns the question of what
should be reported and what should be withheld; the second concerns
the temporal stability of the measurement; and the third concerns
the proper division of responsibility between supplier and consumer
of the measurements.
