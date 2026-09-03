"""document — richer segmentation currency for the extended view.

The extended view's feature modules consume `Document` objects
(paragraphs → sentences → tokens with `is_word` flags). The
compact view uses the flatter `Tokens` struct.

Both views share the L1 kernel primitives for cleaning,
paragraph, and sentence splitting. They differ only in the
token-level representation: `Tokens.words` is lowercased
word-only strings; `Document.tokens` includes punctuation + digits
+ surface case via `Token.text`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from instrument.kernel.cleaning import clean
from instrument.kernel.paragraphs import split_paragraphs
from instrument.kernel.sentences import split_sentences

# Captures: words (with apostrophes/hyphens), numbers, punctuation.
# U+2019 (typographic apostrophe) is accepted as a joiner so the
# extended view tokenises curly-apostrophe contractions identically
# to ASCII; `tokenize` normalises it to `'` in `Token.lower` so
# lexicon lookups match. (`parse` receives cleaned text, which is
# already normalised, but standalone callers may pass raw strings.)
_TOKEN_RE = re.compile(
    r"[A-Za-z]+(?:['\u2019-][A-Za-z]+)*|\d+(?:\.\d+)?|[^\sA-Za-z0-9]"
)
_WORD_RE = re.compile(r"^[A-Za-z]+(?:['\u2019-][A-Za-z]+)*$")


@dataclass
class Token:
    text: str
    lower: str
    is_word: bool


@dataclass
class Sentence:
    text: str
    tokens: list

    @property
    def n_tokens(self) -> int:
        return len(self.tokens)

    @property
    def n_words(self) -> int:
        return sum(1 for t in self.tokens if t.is_word)


@dataclass
class Paragraph:
    text: str
    sentences: list


@dataclass
class Document:
    text: str
    paragraphs: list

    @property
    def sentences(self) -> list:
        return [s for p in self.paragraphs for s in p.sentences]

    @property
    def tokens(self) -> list:
        return [t for s in self.sentences for t in s.tokens]

    @property
    def words(self) -> list:
        return [t for t in self.tokens if t.is_word]

    @property
    def n_words(self) -> int:
        return len(self.words)

    @property
    def n_sentences(self) -> int:
        return len(self.sentences)

    @property
    def n_paragraphs(self) -> int:
        return len(self.paragraphs)


def tokenize(text: str) -> list:
    """Tokenise into `Token` objects (punctuation + digits + words)."""
    out: list = []
    for m in _TOKEN_RE.finditer(text):
        s = m.group(0)
        out.append(Token(
            text=s,
            lower=s.lower().replace("\u2019", "'"),
            is_word=bool(_WORD_RE.match(s)),
        ))
    return out


def parse(
    text: str,
    *,
    cleaned: str | None = None,
    sentences_by_paragraph: tuple[tuple[str, ...], ...] | None = None,
) -> Document:
    """Parse raw text into a `Document`.

    Frontmatter and fenced code are stripped (via kernel.cleaning)
    before paragraph/sentence splitting. This matches the compact
    view's cleaning exactly.

    If *cleaned* is supplied the caller has already run ``clean(text)``
    and we skip the redundant call. If *sentences_by_paragraph* is supplied
    (the canonical grouping from ``Tokens``, aligned 1:1 with
    ``split_paragraphs(cleaned)``), the per-paragraph sentence split is
    reused rather than recomputed — both views then share one canonical
    sentence stream. The produced ``Document`` is identical either way.
    """
    cleaned = cleaned if cleaned is not None else clean(text)
    para_texts = split_paragraphs(cleaned)
    if sentences_by_paragraph is None:
        sentences_by_paragraph = tuple(
            tuple(split_sentences(pt)) for pt in para_texts
        )
    paragraphs: list = []
    for ptext, stexts in zip(para_texts, sentences_by_paragraph):
        sentences = [
            Sentence(text=stext, tokens=tokenize(stext)) for stext in stexts
        ]
        if sentences:
            paragraphs.append(Paragraph(text=ptext, sentences=sentences))
    return Document(text=text, paragraphs=paragraphs)
