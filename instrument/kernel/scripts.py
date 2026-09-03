"""scripts — pure codepoint-range script counting (0.9.1).

The instrument's word tokeniser is ASCII-Latin ([A-Za-z]); non-Latin
scripts contribute zero word tokens. This module gives the emissions
layer a deterministic way to notice that (D5: unsupported input must
fail loudly, not read as "insufficient prose").

Deliberately NOT `unicodedata`: the stdlib Unicode database version
differs across Python minors (3.11 ships a different table than
3.14), so `unicodedata.category` on a new codepoint could change
results across supported hosts. A frozen literal range table is
byte-stable everywhere, forever, and is versioned with the core
source via `core_code_sha256`.

Coverage is intentionally coarse — major letter-bearing ranges, not
the full Unicode script property. The consumer thresholds are ratio
heuristics; a rare unlisted script simply counts as "other".
"""

from __future__ import annotations

# (start, end, script) — inclusive codepoint ranges of LETTERS.
# U+00D7 (×) and U+00F7 (÷) are excluded from the Latin-1 block below.
SCRIPT_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0041, 0x005A, "latin"),      # A-Z
    (0x0061, 0x007A, "latin"),      # a-z
    (0x00C0, 0x00D6, "latin"),      # Latin-1 letters (À-Ö)
    (0x00D8, 0x00F6, "latin"),      # Latin-1 letters (Ø-ö)
    (0x00F8, 0x024F, "latin"),      # Latin-1 tail + Extended-A/B
    (0x1E00, 0x1EFF, "latin"),      # Latin Extended Additional
    (0x0370, 0x03FF, "greek"),
    (0x0400, 0x04FF, "cyrillic"),
    (0x0500, 0x052F, "cyrillic"),   # Cyrillic Supplement
    (0x0590, 0x05FF, "hebrew"),
    (0x0600, 0x06FF, "arabic"),
    (0x0750, 0x077F, "arabic"),     # Arabic Supplement
    (0x0900, 0x097F, "devanagari"),
    (0x0E00, 0x0E7F, "thai"),
    (0x1100, 0x11FF, "hangul"),     # Hangul Jamo
    (0x3040, 0x309F, "hiragana"),
    (0x30A0, 0x30FF, "katakana"),
    (0x3400, 0x4DBF, "cjk"),        # CJK Extension A
    (0x4E00, 0x9FFF, "cjk"),        # CJK Unified Ideographs
    (0xAC00, 0xD7AF, "hangul"),     # Hangul Syllables
)


def count_script_letters(text: str) -> dict[str, int]:
    """Count letters per script group. Codepoints outside every range
    (digits, punctuation, whitespace, symbols, unlisted scripts) are
    not counted. Returns only nonzero entries."""
    counts: dict[str, int] = {}
    for ch in text:
        cp = ord(ch)
        for start, end, script in SCRIPT_RANGES:
            if start <= cp <= end:
                counts[script] = counts.get(script, 0) + 1
                break
    return counts


def nonlatin_stats(text: str) -> tuple[int, int]:
    """Return `(n_latin_letters, n_nonlatin_letters)` over the text."""
    counts = count_script_letters(text)
    n_latin = counts.get("latin", 0)
    n_nonlatin = sum(v for k, v in counts.items() if k != "latin")
    return n_latin, n_nonlatin
