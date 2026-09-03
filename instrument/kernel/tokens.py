"""tokens — word tokenisation and the Tokens struct.

`word_tokens(text)` is the single source of truth for word tokens
across the instrument; `n_words` is defined as
`len(word_tokens(cleaned_text))`. Contractions and hyphenated
compounds are preserved as single tokens.

`tokenise(text)` builds a `Tokens` container in one pass and is the
primary entry from L2 (reading) into L1.
"""

from __future__ import annotations

import re

from instrument.kernel import cleaning, paragraphs, sentences
from instrument.types import Tokens

# Contractions ("don't") and hyphenated compounds ("up-to-date") stay
# as one token. Digits and punctuation are excluded. This matches
# the token class in the prior `segmentation/__init__.py` module.
# U+2019 (typographic apostrophe) is accepted as a joiner and
# normalised to ASCII `'` in the emitted token, so callers that pass
# RAW (un-cleaned) text — e.g. the slicer's contract clauses — see
# the same tokens as callers that pass cleaned text.
_WORD_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*")


def word_tokens(text: str) -> list[str]:
    """Return lowercased word tokens from `text` (U+2019 -> `'`)."""
    return [
        m.group(0).lower().replace("\u2019", "'")
        for m in _WORD_TOKEN_RE.finditer(text)
    ]


def tokenise(text: str) -> Tokens:
    """Tokenise once. Produce the shared currency struct.

    Paragraph-first sentence splitting: long-form markdown is
    heading-segmented, and the whole-text sentence regex silently
    fails on paragraph boundaries followed by a `#` heading or
    `**bold:**` label. Splitting by paragraph first forces each
    paragraph to contribute at least one sentence — matches
    author intent, aligns compact/extended views on markdown
    inputs.

    The input is canonicalised first (`cleaning.canonicalise`):
    `Tokens.text` holds the canonical measurement text, not the raw
    transport bytes' decode. Raw-byte provenance is `input_sha256`,
    computed at the transport boundary (emit.py).
    """
    text = cleaning.canonicalise(text)
    cleaned = cleaning.clean(text)
    paras = tuple(paragraphs.split_paragraphs(cleaned))
    # Split each paragraph into sentences exactly once. The grouped form is
    # carried on Tokens (for the extended view to reuse); the flat stream is
    # its concatenation — identical to the previous per-paragraph extend.
    grouped = tuple(tuple(sentences.split_sentences(p)) for p in paras)
    sents = tuple(s for g in grouped for s in g)
    words = tuple(word_tokens(cleaned))
    return Tokens(
        text=text,
        cleaned=cleaned,
        words=words,
        sentences=tuple(sents),
        paragraphs=paras,
        n_words=len(words),
        has_unclosed_fence=cleaning.has_unclosed_fence(text),
        paragraph_sentences=grouped,
    )
