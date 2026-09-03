"""CONTRACT: clean = strip_fenced_code ∘ strip_frontmatter."""

from __future__ import annotations

from instrument.kernel import cleaning


def test_clean_composition_identity_for_prose():
    text = "A single paragraph with no special syntax."
    assert cleaning.clean(text) == text


def test_strip_frontmatter_removes_yaml_block():
    text = "---\ntitle: Foo\n---\n\nBody here."
    assert cleaning.strip_frontmatter(text).strip() == "Body here."


def test_strip_frontmatter_is_idempotent_without_yaml():
    text = "No frontmatter here."
    assert cleaning.strip_frontmatter(text) == text


def test_strip_fenced_code_preserves_line_count():
    text = "before\n```\ncode line\nanother\n```\nafter"
    result = cleaning.strip_fenced_code(text)
    assert result.count("\n") == text.count("\n")
    assert "code line" not in result
    assert "before" in result and "after" in result


def test_strip_fenced_code_recovers_unclosed_fence():
    text = "before\n```\nnever closed\nand more"
    result = cleaning.strip_fenced_code(text)
    assert "never closed" in result, "unclosed fence must be restored, not blanked"


def test_has_unclosed_fence_flags_open_block():
    assert cleaning.has_unclosed_fence("```\nopen forever")


def test_has_unclosed_fence_negative_on_closed_block():
    assert not cleaning.has_unclosed_fence("```\nfoo\n```")


def test_clean_composition_matches_chained_calls():
    text = "---\nmeta: x\n---\n\nprose\n\n```\ncode\n```\n\nmore prose"
    assert cleaning.clean(text) == cleaning.strip_fenced_code(
        cleaning.strip_frontmatter(text)
    )
