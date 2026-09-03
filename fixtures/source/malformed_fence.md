# Document with an unclosed code fence

This document begins with normal prose. It contains enough words
to clear the measurement envelope on its own, before the
malformed fence appears, so that the recovery path can be
exercised meaningfully rather than being short-circuited by the
below-envelope gate.

The recovery behaviour the pipeline is supposed to demonstrate
is straightforward. When the cleaner encounters an opening fence
marker but never finds a matching close marker, the span between
the open marker and the end of the document is treated as prose
rather than as code. The opened-but-unclosed state is recorded
as a soft flag, so consumers can know that a recovery occurred
and weigh the resulting measurements accordingly.

The motivating case is real markdown that has been truncated or
edited inattentively. A document that opens a fenced code block
to show an example, and then has its tail cut off by a
copy-paste error, would otherwise have its remaining prose
silently classified as code and excluded from measurement.
Recovery prevents that silent loss; the soft flag prevents the
recovery from being silent.

```python
def example():
    return "this fence is not closed"

# what follows is intended as prose, but the fence above is
# never terminated, so the cleaner has to decide whether to
# treat the rest of this document as code or as prose.

The instrument's cleaner will treat the unclosed span as prose,
and will set the `malformed_fence_recovered` soft flag on the
output. This is the correct behaviour, but it is worth noting
that the measurements produced from the recovered prose will be
slightly different from the measurements that would have been
produced if the fence had been closed properly. In particular,
the counts of certain stylometric features (such as
quotation-character density, since `"this fence is not closed"`
contains quote characters) will be inflated relative to what a
clean version of the document would produce.

For compliance pipelines, the recommended treatment is to
inspect the soft flag, decide whether the recovery is acceptable
for the consumer's purposes, and either accept the measurement
with the flag noted or reject it and request a corrected source.
The pipeline does not refuse to produce a measurement; it
provides the measurement plus the flag, and leaves the policy
decision to the consumer.
