"""cleaning — strip YAML frontmatter and fenced code blocks.

Pure text-in / text-out. Preserves line count across fenced-code
blanking so downstream offsets are not disturbed. Malformed fence
(opened but never closed) is restored as prose.

Typographic-apostrophe normalisation: U+2019 (RIGHT SINGLE
QUOTATION MARK) is mapped to ASCII `'` as the first cleaning step.
LLM and word-processor output routinely uses U+2019 as the
apostrophe in contractions ("don\u2019t"); without normalisation the
word tokeniser fragments those into junk tokens and every
apostrophe-form lexicon entry ("don't", "won't", ...) silently
stops matching. The mapping is 1 char -> 1 char, so offsets and
line counts are unchanged. U+2019-as-closing-quote also maps to
`'`, which is exactly what ASCII text does with that role, so
quotation counting is unaffected (`'` is already in the stylometry
quote-char set).
"""

from __future__ import annotations

import re

_YAML_FRONTMATTER = re.compile(r"\A---\s*\n.*?\n---\s*(?:\n|$)", re.DOTALL)
_FENCE_MARKERS = ("```", "~~~")

_TYPOGRAPHIC_APOSTROPHE = "\u2019"  # RIGHT SINGLE QUOTATION MARK

_BOM = "\ufeff"
_TRAILING_HORIZONTAL_WS = re.compile(r"[ \t]+$", re.MULTILINE)
_BLANK_LINE_RUNS = re.compile(r"\n{3,}")


def canonicalise(text: str) -> str:
    """Normalise the input to the canonical measurement text (0.9.1).

    Defines the instrument's semantic-whitespace boundary. Semantic:
    the presence of a paragraph break (a blank line), single line
    breaks, and all non-whitespace characters. Non-semantic (erased
    here, before any measurement): the newline convention (CRLF / CR
    vs LF), a leading UTF-8 BOM, trailing spaces/tabs at line ends,
    and the *run length* of consecutive blank lines. Two inputs that
    differ only in non-semantic whitespace produce byte-identical
    readings; only `input_sha256` (raw transport bytes) may differ.

    Steps, in order (each depends on the previous):
        1. strip one leading BOM (U+FEFF at position 0 only)
        2. CRLF / CR -> LF
        3. strip trailing horizontal whitespace per line
        4. collapse runs of 3+ newlines to exactly two

    Idempotent: canonicalise(canonicalise(x)) == canonicalise(x).
    """
    if text.startswith(_BOM):
        text = text[len(_BOM):]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _TRAILING_HORIZONTAL_WS.sub("", text)
    return _BLANK_LINE_RUNS.sub("\n\n", text)


def normalise_apostrophes(text: str) -> str:
    """Map U+2019 to ASCII `'`. Length-preserving (1:1 chars)."""
    return text.replace(_TYPOGRAPHIC_APOSTROPHE, "'")


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from the start of the document, if any."""
    return _YAML_FRONTMATTER.sub("", text, count=1)


def strip_fenced_code(text: str) -> str:
    """Blank the interior of fenced code blocks, preserving line count.

    Malformed-fence recovery: if a fence opens but never closes,
    the unclosed span is restored as prose rather than silently
    deleted. Consumers that want to surface the recovery call
    `has_unclosed_fence(original_text)`.
    """
    input_lines = text.split("\n")
    out_lines: list[str] = []
    in_fence = False
    fence_marker = ""
    fence_open_idx = -1
    for line in input_lines:
        ls = line.lstrip()
        if not in_fence and any(ls.startswith(m) for m in _FENCE_MARKERS):
            in_fence = True
            fence_marker = "```" if ls.startswith("```") else "~~~"
            fence_open_idx = len(out_lines)
            out_lines.append("")
            continue
        if in_fence:
            if ls.startswith(fence_marker):
                in_fence = False
                fence_marker = ""
                fence_open_idx = -1
            out_lines.append("")
            continue
        out_lines.append(line)
    if in_fence and fence_open_idx >= 0:
        out_lines[fence_open_idx:] = input_lines[fence_open_idx:]
    return "\n".join(out_lines)


def has_unclosed_fence(text: str) -> bool:
    """Advisory: did the document open a fence and never close it?"""
    in_fence = False
    fence_marker = ""
    for line in text.split("\n"):
        ls = line.lstrip()
        if not in_fence and any(ls.startswith(m) for m in _FENCE_MARKERS):
            in_fence = True
            fence_marker = "```" if ls.startswith("```") else "~~~"
            continue
        if in_fence and ls.startswith(fence_marker):
            in_fence = False
            fence_marker = ""
    return in_fence


def clean(text: str) -> str:
    """Normalise apostrophes, strip frontmatter, then fenced code.

    `clean = strip_fenced_code ∘ strip_frontmatter ∘ normalise_apostrophes`.
    Line count is preserved modulo the frontmatter block.
    """
    return strip_fenced_code(strip_frontmatter(normalise_apostrophes(text)))
