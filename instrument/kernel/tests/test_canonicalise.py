"""CONTRACT: measurement canonicalisation (0.9.1).

The measured text is `canonicalise(input)`: BOM stripped, CRLF/CR
newlines normalised to LF, trailing horizontal whitespace stripped,
runs of 3+ newlines collapsed to a paragraph break. The semantic
whitespace boundary is: a paragraph break is "a blank line present";
the *run length* of blank lines, trailing spaces/tabs, and the
newline convention are non-semantic and must not move any measured
number. `input_sha256` (raw transport bytes) is the only hash that
may move under these perturbations.
"""

from __future__ import annotations

from instrument.kernel.cleaning import canonicalise
from instrument.kernel.tokens import tokenise
from instrument.reading.joint import joint_reading

_PROSE = (
    "The committee reviewed the proposal in detail. Several members "
    "raised concerns about the timeline, but the chair argued that the "
    "schedule was achievable.\n\nAfter a long discussion the vote was "
    "taken. The proposal passed with a clear majority, and the working "
    "group was asked to begin immediately.\n"
)


def _reading_no_ts(text: str) -> dict:
    jr = joint_reading(text)
    return {k: v for k, v in jr.items() if k != "ts"}


def test_crlf_and_cr_normalise_to_lf():
    assert canonicalise("a\r\nb\rc\nd") == "a\nb\nc\nd"


def test_bom_stripped_only_at_start():
    assert canonicalise("﻿hello") == "hello"
    # An interior ZWNBSP is content, not a BOM.
    assert canonicalise("he﻿llo") == "he﻿llo"


def test_trailing_horizontal_whitespace_stripped():
    assert canonicalise("line one   \nline two\t\nline three") == (
        "line one\nline two\nline three"
    )


def test_blank_line_runs_collapse_to_one_paragraph_break():
    assert canonicalise("a\n\n\n\nb") == "a\n\nb"
    # A blank line containing spaces is still a blank line.
    assert canonicalise("a\n  \n\t\n\nb") == "a\n\nb"
    # A single paragraph break is preserved, not collapsed further.
    assert canonicalise("a\n\nb") == "a\n\nb"


def test_idempotent():
    samples = [
        "﻿a  \r\n\r\n\r\n\r\nb\r",
        _PROSE,
        "",
        "\n\n\n",
        "x \t \r\n y",
    ]
    for s in samples:
        once = canonicalise(s)
        assert canonicalise(once) == once


def test_tokenise_canonicalises_first():
    crlf = _PROSE.replace("\n", "\r\n") + "   \n\n\n\n"
    tokens = tokenise(crlf)
    assert tokens.text == canonicalise(crlf)
    assert "\r" not in tokens.text
    assert tokens.words == tokenise(_PROSE).words


def test_reading_invariant_under_nonsemantic_formatting():
    base = _reading_no_ts(_PROSE)
    variants = [
        _PROSE.replace("\n", "\r\n"),                    # CRLF convention
        "﻿" + _PROSE,                               # BOM
        _PROSE.replace("\n\n", "\n\n\n\n"),              # blank-run inflation
        _PROSE.replace("\n", "   \n"),                   # trailing spaces
    ]
    for v in variants:
        assert _reading_no_ts(v) == base, f"reading moved for variant {v[:40]!r}"
