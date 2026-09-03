"""CONTRACT: tokenise() is the single entry; Tokens carries the shared currency."""

from __future__ import annotations

from instrument.kernel.tokens import tokenise, word_tokens
from instrument.types import Tokens


def test_word_tokens_preserves_contractions():
    assert word_tokens("don't worry") == ["don't", "worry"]


def test_word_tokens_preserves_hyphenated_compounds():
    assert word_tokens("up-to-date info") == ["up-to-date", "info"]


def test_word_tokens_lowercased():
    assert word_tokens("Hello World") == ["hello", "world"]


def test_word_tokens_excludes_digits_and_punctuation():
    assert word_tokens("hello 2024 world!") == ["hello", "world"]


def test_tokenise_returns_frozen_tokens_struct():
    t = tokenise("Hello world.")
    assert isinstance(t, Tokens)
    assert t.words == ("hello", "world")
    assert t.n_words == 2


def test_tokenise_includes_sentences_and_paragraphs():
    t = tokenise("First para.\n\nSecond para.")
    assert len(t.paragraphs) == 2
    assert len(t.sentences) == 2


def test_tokenise_strips_frontmatter():
    t = tokenise("---\ntitle: x\n---\n\nBody text here.")
    assert "title" not in t.words


def test_tokenise_strips_fenced_code_preserving_line_count():
    t = tokenise("Prose here.\n\n```\ncode\n```\n\nMore prose.")
    assert "code" not in t.words
    assert "prose" in t.words


def test_tokenise_detects_unclosed_fence():
    t = tokenise("prose\n```\nopen forever")
    assert t.has_unclosed_fence is True


def test_tokenise_determinism():
    text = "Dr. Smith arrived. He was late.\n\nLater, Prof. Jones called."
    a = tokenise(text)
    b = tokenise(text)
    assert a == b
