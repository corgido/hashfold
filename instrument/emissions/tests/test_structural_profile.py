"""CONTRACTS for structural profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from instrument.emissions.structural_profile import (
    classify_subtype,
    profile,
    strip_scaffolding,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_empty_text_is_insufficient_prose():
    p = profile("")
    assert p.subtype == "insufficient_prose"


def test_table_dominated_becomes_reference_table():
    text = "\n".join(
        ["| A | B |", "|---|---|"] + ["| x | y |" for _ in range(20)]
    )
    p = profile(text)
    assert p.subtype == "reference_table"


def test_classify_subtype_direct():
    assert classify_subtype(
        n_prose=0, n_code=0, n_table=20, n_heading=0, n_bullet=0, n_hr=0,
        n_content=20, prose_words_available=30,
    ) == "reference_table"


def test_strip_scaffolding_removes_fences_and_bullets():
    text = (
        "# Heading\n\n"
        "Some prose here.\n\n"
        "```\ncode block\n```\n\n"
        "- bullet item\n\n"
        "More prose."
    )
    stripped = strip_scaffolding(text)
    assert "code block" not in stripped
    assert "Some prose here." in stripped
    assert "More prose." in stripped


# Real markdown fixtures: just smoke-test that `profile` returns a
# well-formed result. Numeric stability is covered by joint+emit goldens.
FIXTURE_PATHS = [
    "fixtures/source/academic_long.md",
    "fixtures/source/journalism.md",
    "fixtures/source/literary.md",
    "fixtures/source/llm_technical.md",
    "fixtures/source/structural_table.md",
]


@pytest.mark.parametrize("rel_path", FIXTURE_PATHS)
def test_profile_smoke(rel_path):
    text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    p = profile(text)
    assert p.n_lines > 0
    assert 0.0 <= p.prose_ratio <= 1.0
    assert 0.0 <= p.structure_ratio <= 1.0
    assert p.subtype in (
        "reference_table", "instruction_format",
        "mixed_structural_fp", "insufficient_prose",
    )
