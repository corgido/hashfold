# Short note

This document is intentionally short. It exists to exercise the
pipeline's behaviour when the input falls below the 150-word
measurement envelope.

The expected behaviour is that the shaper view returns the
`below_envelope` flag, the routing layer raises and falls back
to the structural-profile classification, and the resulting
register label is `unprojectable`.

If you are reading this and the pipeline did something else,
something has changed.
