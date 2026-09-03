# Quotation handling

The instrument tracks quotation balance as part of its
stylometric measurement surface. ASCII double-quotes are
counted, and an odd count is reported via the
`unbalanced_quotation` flag; Unicode curly quotes are checked
separately, with mismatched open and close counts producing the
same flag.

The motivation is partly defensive. A document with unbalanced
quotes is often the result of editing damage — a copy-paste that
clipped a closing quote, or a search-and-replace that converted
a typographic open quote without converting its match. The flag
exists to surface this pattern without making any judgement
about whether it matters; the consumer decides.

This document deliberately exercises both paths. It contains
some plain ASCII quoted material — for example, "the cat sat on
the mat" — which is balanced. It also contains some curly-quoted
material, like "this is the right kind of quote", which should
also balance. In a passage about typesetting, you might see
references to the use of "smart quotes" in modern word
processors, which transform straight quotes into curly ones
automatically.

The pipeline must handle non-ASCII text robustly in any case,
since it commits to operating on the input bytes as given. A
correctly authored document should not produce any quotation
flag; an incorrectly authored one should produce the flag and
let the consumer decide whether the document is suitable for
their purposes.

For the purposes of this fixture, the quote counts are
deliberately balanced. The fixture's role is to exercise the
character-counting code path with a non-trivial mix of ASCII
and Unicode characters present, not to force the flag to fire.
A separate unit test in `instrument/emissions/flags/tests/`
covers the flag-firing behaviour.

The author takes the opportunity to note, parenthetically, that
the en-dash and em-dash characters – like this one – also
appear in this fixture, both as part of the prose and as
deliberate test material for the structural-elaboration
detector in the RST module. The detector matches em-dash
parentheticals as a specific elaboration cue, distinct from
colon-glosses and from explicit elaboration markers.

Finally, this fixture includes a short closing paragraph in
which all the punctuation is deliberately placed. The point is
to demonstrate that, while the instrument's measurements depend
on punctuation in significant ways, none of those dependencies
are surprising: a sentence ends where you'd expect, a quote
opens and closes where you'd expect, and a parenthetical (such
as this one) is bracketed where you'd expect. Consumers who
care about the precise rules can consult `METROLOGY.md`.
