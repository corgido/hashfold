"""Structural profile — line-level classification of documents whose
normal projection fails.

The emissions layer calls this on documents that the router
declares unprojectable. The profile answers:

    1. What kind of document is this? (table-dominated,
       instruction-formatted, insufficient-prose, mixed)
    2. Is there a prose residue worth re-projecting? (strip
       scaffolding and try again)

Per-line classification is deterministic; no NLP, no lexicons,
pattern matching only. That lets the profile compute on inputs
the feature pipeline can't measure.

Subtypes (aligned with emission catalog v2):

    unsupported_script   Substantively non-Latin content (0.9.1). The
                         tokeniser is ASCII-Latin; this input class is
                         out of measurement scope and says so loudly
                         instead of masquerading as insufficient
                         prose. Emit `register.label =
                         "unprojectable"` with script counts in
                         evidence.
    reference_table      Tables dominate; too-thin prose residue.
                         Emit `register.label = "structural"`.
    instruction_format   Code/list-heavy but enough prose to retry.
                         Emit normally if recovery succeeds, else
                         fall through to insufficient_prose.
    mixed_structural_fp  Prose > 200 words with modest structure —
                         safety net for docs that should project.
    insufficient_prose   Too little prose to project against any
                         reference. Emit `register.label =
                         "unprojectable"`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from instrument.kernel.scripts import nonlatin_stats

# Loud-refusal thresholds for non-Latin content (0.9.1, D5). Named
# constants, not calibration: 50 letters is "a sentence or two", 0.30
# is "not an incidental quotation".
UNSUPPORTED_SCRIPT_MIN_LETTERS = 50
UNSUPPORTED_SCRIPT_MIN_RATIO = 0.30

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_HR_RE = re.compile(r"^\s*(?:[-*_]\s*){3,}$")
_TABLE_RE = re.compile(r"^\s*\|")
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_INDENT_CODE_RE = re.compile(r"^\s{4,}\S")
_FRONTMATTER_FENCE_RE = re.compile(r"^---\s*$")


@dataclass(frozen=True)
class StructuralProfile:
    """Counts by line type + derived ratios + subtype label."""
    n_lines: int
    n_content_lines: int
    n_prose_lines: int
    n_code_lines: int
    n_table_lines: int
    n_heading_lines: int
    n_bullet_lines: int
    n_hr_lines: int
    n_frontmatter_lines: int
    n_blank_lines: int
    prose_ratio: float
    table_ratio: float
    code_ratio: float
    structure_ratio: float
    n_latin_letters: int
    n_nonlatin_letters: int
    nonlatin_ratio: float
    subtype: str


def _find_frontmatter_end(lines: list[str]) -> int:
    first_nonblank = next((i for i, ln in enumerate(lines) if ln.strip()), -1)
    if first_nonblank < 0:
        return -1
    if not _FRONTMATTER_FENCE_RE.match(lines[first_nonblank]):
        return -1
    for j in range(first_nonblank + 1, len(lines)):
        if _FRONTMATTER_FENCE_RE.match(lines[j]):
            return j
    return -1


def _profile_lines(text: str) -> tuple[int, int, int, int, int, int, int, int, int]:
    """Return `(n_prose, n_code, n_table, n_heading, n_bullet, n_hr,
    n_frontmatter, n_blank, n_total)`. Walks once, tracking
    frontmatter and fence state."""
    lines = text.split("\n")
    n_total = len(lines)
    frontmatter_end = _find_frontmatter_end(lines)
    if frontmatter_end >= 0:
        first_nonblank = next((i for i, ln in enumerate(lines) if ln.strip()), -1)
        n_frontmatter = (frontmatter_end - first_nonblank + 1)
    else:
        n_frontmatter = 0

    in_code_fence = False
    fence_marker = ""
    n_prose = n_code = n_table = n_heading = n_bullet = n_hr = 0
    n_blank = 0

    for i, ln in enumerate(lines):
        if i <= frontmatter_end:
            continue
        stripped = ln.strip()
        if not stripped:
            n_blank += 1
            continue
        if in_code_fence:
            n_code += 1
            if stripped.startswith(fence_marker):
                in_code_fence = False
                fence_marker = ""
            continue
        if _FENCE_RE.match(ln):
            in_code_fence = True
            fence_marker = "```" if stripped.startswith("```") else "~~~"
            n_code += 1
            continue
        if _INDENT_CODE_RE.match(ln):
            n_code += 1
            continue
        if _HR_RE.match(ln):
            n_hr += 1
            continue
        if _HEADING_RE.match(ln):
            n_heading += 1
            continue
        if _TABLE_RE.match(ln):
            n_table += 1
            continue
        if _BULLET_RE.match(ln):
            n_bullet += 1
            continue
        n_prose += 1

    return (
        n_prose, n_code, n_table, n_heading, n_bullet, n_hr,
        n_frontmatter, n_blank, n_total,
    )


def _prose_word_count(text: str) -> int:
    """Approximate prose-word count from prose lines only.

    Overcounts vs. the shared tokenizer (which also strips
    frontmatter + fences) but good enough for subtype
    classification.
    """
    lines = text.split("\n")
    frontmatter_end = _find_frontmatter_end(lines)
    in_code_fence = False
    fence_marker = ""
    prose_words = 0
    for i, ln in enumerate(lines):
        if i <= frontmatter_end:
            continue
        stripped = ln.strip()
        if not stripped:
            continue
        if in_code_fence:
            if stripped.startswith(fence_marker):
                in_code_fence = False
                fence_marker = ""
            continue
        if _FENCE_RE.match(ln):
            in_code_fence = True
            fence_marker = "```" if stripped.startswith("```") else "~~~"
            continue
        if (_INDENT_CODE_RE.match(ln) or _HR_RE.match(ln) or
                _HEADING_RE.match(ln) or _TABLE_RE.match(ln) or
                _BULLET_RE.match(ln)):
            continue
        prose_words += len(stripped.split())
    return prose_words


def classify_subtype(
    *,
    n_prose: int,
    n_code: int,
    n_table: int,
    n_heading: int,
    n_bullet: int,
    n_hr: int,
    n_content: int,
    prose_words_available: int,
    min_words_floor: int = 150,
    n_latin_letters: int = 0,
    n_nonlatin_letters: int = 0,
) -> str:
    """Pick one of the five subtype labels."""
    # Checked first (0.9.1): a substantively non-Latin document is out
    # of measurement scope — say so, don't call it insufficient prose.
    total_letters = n_latin_letters + n_nonlatin_letters
    if (n_nonlatin_letters >= UNSUPPORTED_SCRIPT_MIN_LETTERS
            and total_letters > 0
            and n_nonlatin_letters / total_letters
            >= UNSUPPORTED_SCRIPT_MIN_RATIO):
        return "unsupported_script"
    if n_content == 0:
        return "insufficient_prose"
    table_ratio = n_table / n_content
    structure_ratio = (
        n_code + n_table + n_heading + n_bullet + n_hr
    ) / n_content

    if table_ratio > 0.50 and prose_words_available < min_words_floor:
        return "reference_table"
    if (structure_ratio > 0.40
            and prose_words_available >= 100
            and prose_words_available < min_words_floor * 2):
        return "instruction_format"
    if (prose_words_available >= min_words_floor * 2
            and structure_ratio < 0.50):
        return "mixed_structural_fp"
    return "insufficient_prose"


def profile(text: str) -> StructuralProfile:
    """Compute the full structural profile for a text."""
    (n_prose, n_code, n_table, n_heading, n_bullet, n_hr,
     n_frontmatter, n_blank, n_total) = _profile_lines(text)
    n_content = n_prose + n_code + n_table + n_heading + n_bullet + n_hr
    prose_words = _prose_word_count(text) if n_prose > 0 else 0
    n_latin, n_nonlatin = nonlatin_stats(text)
    subtype = classify_subtype(
        n_prose=n_prose, n_code=n_code, n_table=n_table,
        n_heading=n_heading, n_bullet=n_bullet, n_hr=n_hr,
        n_content=n_content,
        prose_words_available=prose_words,
        n_latin_letters=n_latin,
        n_nonlatin_letters=n_nonlatin,
    )
    prose_ratio = (n_prose / n_content) if n_content > 0 else 0.0
    table_ratio = (n_table / n_content) if n_content > 0 else 0.0
    code_ratio = (n_code / n_content) if n_content > 0 else 0.0
    structure_ratio = (
        (n_code + n_table + n_heading + n_bullet + n_hr) / n_content
    ) if n_content > 0 else 0.0
    return StructuralProfile(
        n_lines=n_total,
        n_content_lines=n_content,
        n_prose_lines=n_prose,
        n_code_lines=n_code,
        n_table_lines=n_table,
        n_heading_lines=n_heading,
        n_bullet_lines=n_bullet,
        n_hr_lines=n_hr,
        n_frontmatter_lines=n_frontmatter,
        n_blank_lines=n_blank,
        prose_ratio=prose_ratio,
        table_ratio=table_ratio,
        code_ratio=code_ratio,
        structure_ratio=structure_ratio,
        n_latin_letters=n_latin,
        n_nonlatin_letters=n_nonlatin,
        nonlatin_ratio=(
            n_nonlatin / (n_latin + n_nonlatin)
            if (n_latin + n_nonlatin) > 0 else 0.0
        ),
        subtype=subtype,
    )


def strip_scaffolding(text: str) -> str:
    """Aggressive prose-residue extraction.

    Strips frontmatter, fenced code, indent-code, headings, table
    rows, bullets, and horizontal rules. Returns what's left.
    Used by the emissions fallback when the router fails but the
    profile suggests recovery is plausible (`instruction_format`).

    Goes further than `kernel.cleaning.clean` (which strips only
    frontmatter + fenced code). The output is a reprojection
    fallback, not a generic text cleaner.
    """
    lines = text.split("\n")
    frontmatter_end = _find_frontmatter_end(lines)
    in_code_fence = False
    fence_marker = ""
    out: list[str] = []
    for i, ln in enumerate(lines):
        if i <= frontmatter_end:
            continue
        stripped = ln.strip()
        if not stripped:
            out.append("")
            continue
        if in_code_fence:
            if stripped.startswith(fence_marker):
                in_code_fence = False
                fence_marker = ""
            continue
        if _FENCE_RE.match(ln):
            in_code_fence = True
            fence_marker = "```" if stripped.startswith("```") else "~~~"
            continue
        if _INDENT_CODE_RE.match(ln):
            continue
        if _HR_RE.match(ln) or _TABLE_RE.match(ln):
            continue
        if _HEADING_RE.match(ln):
            out.append(re.sub(r"^\s{0,3}#{1,6}\s+", "", ln))
            continue
        if _BULLET_RE.match(ln):
            out.append(re.sub(r"^\s*(?:[-*+]|\d+\.)\s+", "", ln))
            continue
        out.append(ln)
    return "\n".join(out)
