"""CONTRACTS for slicer: clamps, proposal, and contract validation."""

from __future__ import annotations

from instrument.kernel.slicer import (
    MIN_CONTENT_TYPES,
    MIN_PROCESS_TOKENS,
    MIN_WORDS_PER_SLICE,
    check_cohesion_load,
    check_sfl_load,
    check_word_envelope,
    find_paragraph_breaks,
    find_section_breaks,
    find_sentence_breaks,
    find_word_breaks,
    propose_slices_at_level,
    resolve_elegant,
    validate_slicing,
)
from instrument.kernel.tokens import word_tokens


def test_word_envelope_clamp_rejects_short():
    ok, n = check_word_envelope(word_tokens("short text"))
    assert ok is False
    assert n < MIN_WORDS_PER_SLICE


def test_word_envelope_clamp_accepts_long():
    text = "word " * 200
    ok, n = check_word_envelope(word_tokens(text))
    assert ok is True
    assert n >= MIN_WORDS_PER_SLICE


def test_sfl_load_clamp_rejects_empty():
    text = "banana apple orange"
    ok, n = check_sfl_load(word_tokens(text), text)
    assert ok is False
    assert n < MIN_PROCESS_TOKENS


def test_cohesion_load_clamp_counts_content_types():
    text = " ".join(
        f"alpha{chr(97 + i % 26)}{chr(97 + (i // 26) % 26)}"
        for i in range(50)
    )
    ok, n = check_cohesion_load(word_tokens(text))
    assert n >= MIN_CONTENT_TYPES
    assert ok is True


def test_find_breaks_return_ordered_offsets():
    text = "# Section\n\nPara one.\n\nPara two.\n\n## Another\n\nPara three."
    for finder in (find_section_breaks, find_paragraph_breaks,
                   find_sentence_breaks, find_word_breaks):
        breaks = finder(text)
        assert breaks == sorted(breaks)


def test_propose_slices_returns_coverage():
    text = "word " * 1000
    slices = propose_slices_at_level(text, find_word_breaks, 3)
    assert slices
    assert slices[0][0] == 0
    assert slices[-1][1] == len(text)
    for i in range(len(slices) - 1):
        assert slices[i][1] == slices[i + 1][0]


def test_validate_slicing_trivial_single_slice():
    # Build a document that can be a valid single slice.
    text = (
        "The committee argued that the proposal was flawed. "
        "They believed the costs were too high. "
        "The chair said the decision would be deferred. "
    ) * 10
    ok, failures = validate_slicing(text, [(0, len(text))])
    assert ok, failures


def test_resolve_elegant_on_short_doc_falls_back_to_document():
    r = resolve_elegant("short text")
    assert r["full_resolution"] == 1
    assert r["slices"] == [(0, len("short text"))]


def test_resolve_elegant_on_long_doc_finds_multi_slice():
    para = (
        "The committee argued that the proposal was flawed. "
        "They believed the costs were too high. "
        "The chair said the decision would be deferred. "
        "The minutes stated further evidence was needed. "
    ) * 5
    text = para + "\n\n" + para + "\n\n" + para + "\n\n" + para
    r = resolve_elegant(text)
    assert r["full_resolution"] >= 1
    # coverage
    assert r["slices"][0][0] == 0
    assert r["slices"][-1][1] == len(text)
