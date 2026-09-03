"""Shared types — the currency that flows between layers.

These are the structural types every layer agrees on. Measurement
primitives (kernel/features) emit floats; the composition layer
packages a `Tokens` struct once and passes it down so no reader
re-tokenises.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Slice:
    """A character-offset span of the original text.

    `start` and `end` are offsets into the *original* text, not the
    cleaned text. `content` is the cleaned content of the span.
    """
    start: int
    end: int
    content: str


@dataclass(frozen=True)
class Tokens:
    """Tokenisation-once container.

    `text` is the original input. `cleaned` is after frontmatter +
    fenced-code stripping. `words` is the lowercased word-token
    sequence over `cleaned`. `sentences` and `paragraphs` are
    segment strings (not Slices) because downstream readers
    tokenise by string; the Slice form is available via the
    slicer in `kernel.slicer`.
    """
    text: str
    cleaned: str
    words: tuple[str, ...]
    sentences: tuple[str, ...]
    paragraphs: tuple[str, ...]
    n_words: int
    has_unclosed_fence: bool
    # Sentences grouped by paragraph, aligned 1:1 with `paragraphs`. The flat
    # `sentences` stream is the concatenation of these. Carried so the
    # extended view can reuse the canonical split instead of re-running it
    # (the "single canonical sentence stream"). Defaulted for constructors
    # that predate it.
    paragraph_sentences: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class Reading:
    """A feature vector as an ordered list + a name table.

    The two are kept separate so `FEATURE_ORDER` stays a module
    constant shared across views (a Reading carries values; the
    order is out-of-band).
    """
    values: tuple[float, ...]
    below_envelope: bool
    n_words: int
    metadata: Optional[dict] = None
