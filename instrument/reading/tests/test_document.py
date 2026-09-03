"""CONTRACTS for the Document currency used by the extended view."""
from __future__ import annotations
from instrument.kernel.tokens import tokenise
from instrument.reading.document import Document, Paragraph, Sentence, Token, parse

def test_parse_returns_document():
    doc = parse('One paragraph. Two sentences.\n\nSecond paragraph.')
    assert isinstance(doc, Document)
    assert doc.n_paragraphs == 2
    assert doc.n_sentences >= 2

def test_token_tags_words_not_punctuation():
    doc = parse('hello, world!')
    word_tokens = [t for t in doc.tokens if t.is_word]
    punct_tokens = [t for t in doc.tokens if not t.is_word]
    assert any((t.lower == 'hello' for t in word_tokens))
    assert any((t.lower == 'world' for t in word_tokens))
    assert len(punct_tokens) >= 2

def test_document_strips_frontmatter_and_code_fences():
    text = '---\ntitle: foo\n---\n\nProse.\n\n```\ncode\n```\n\nMore prose.'
    doc = parse(text)
    assert 'title' not in [t.lower for t in doc.tokens]
    assert 'code' not in [t.lower for t in doc.tokens]
    assert any((t.lower == 'prose' for t in doc.tokens))
