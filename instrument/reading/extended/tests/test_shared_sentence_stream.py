"""CONTRACT: the extended view shares one canonical sentence stream.

`Document` must reuse `Tokens`' per-paragraph sentence grouping rather than
re-splitting, and the result must be identical to splitting independently.
This guards both the dedup and the "single canonical sentence stream" claim
against silent divergence.
"""
from __future__ import annotations

from pathlib import Path

from instrument.kernel.tokens import tokenise
from instrument.reading.document import parse

_FIXTURES = sorted((Path(__file__).resolve().parents[4] / "fixtures" / "source").glob("*.md"))


def test_shared_grouping_matches_independent_split():
    for f in _FIXTURES:
        text = f.read_text(encoding="utf-8")
        tk = tokenise(text)
        shared = parse(text, cleaned=tk.cleaned,
                       sentences_by_paragraph=tk.paragraph_sentences)
        independent = parse(text, cleaned=tk.cleaned)
        assert [s.text for s in shared.sentences] == [s.text for s in independent.sentences]
        assert shared.n_paragraphs == independent.n_paragraphs
        assert shared.n_words == independent.n_words


def test_document_stream_equals_tokens_stream():
    for f in _FIXTURES:
        text = f.read_text(encoding="utf-8")
        tk = tokenise(text)
        doc = parse(text, cleaned=tk.cleaned,
                    sentences_by_paragraph=tk.paragraph_sentences)
        assert [s.text for s in doc.sentences] == list(tk.sentences)
