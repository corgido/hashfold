"""CONTRACT: paragraphs split on blank lines; empty paragraphs dropped."""

from __future__ import annotations

from instrument.kernel.paragraphs import split_paragraphs


def test_single_paragraph():
    assert split_paragraphs("one para") == ["one para"]


def test_blank_line_separates():
    assert split_paragraphs("first\n\nsecond") == ["first", "second"]


def test_multiple_blank_lines_collapse():
    assert split_paragraphs("a\n\n\n\nb") == ["a", "b"]


def test_whitespace_only_line_treated_as_blank():
    assert split_paragraphs("a\n  \n b") == ["a", "b"]


def test_empty_input_is_empty_list():
    assert split_paragraphs("") == []


def test_paragraphs_stripped():
    assert split_paragraphs("  hello  \n\n  world  ") == ["hello", "world"]
