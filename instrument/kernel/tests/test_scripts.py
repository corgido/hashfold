"""CONTRACT: script detection is pure codepoint-range arithmetic (0.9.1).

The word tokeniser is ASCII-Latin only ([A-Za-z]); non-Latin scripts
produce n_words = 0 and, before 0.9.1, degraded SILENTLY to
`insufficient_prose`. Detection uses a frozen literal range table —
deliberately NOT `unicodedata`, whose database version differs across
Python minors and would break the "same numbers on any host"
guarantee.
"""

from __future__ import annotations

from instrument.kernel.scripts import count_script_letters, nonlatin_stats


def test_pure_latin():
    counts = count_script_letters("Hello, wonderful world! 42 times.")
    assert counts.get("latin", 0) > 0
    assert sum(v for k, v in counts.items() if k != "latin") == 0


def test_cyrillic_detected():
    counts = count_script_letters("Комитет рассмотрел предложение подробно.")
    assert counts["cyrillic"] > 20
    assert counts.get("latin", 0) == 0


def test_cjk_hiragana_hangul_detected():
    counts = count_script_letters("委員会は提案を検討した ひらがな 한국어 텍스트")
    assert counts["cjk"] > 0
    assert counts["hiragana"] > 0
    assert counts["hangul"] > 0


def test_digits_punctuation_whitespace_not_counted():
    assert count_script_letters("1234 !?;:,. \n\t —…") == {}


def test_nonlatin_stats():
    n_latin, n_nonlatin = nonlatin_stats("abc где abc где")
    assert n_latin == 6
    assert n_nonlatin == 6


def test_accented_latin_counts_as_latin():
    counts = count_script_letters("déjà vu naïve façade")
    assert counts.get("latin", 0) >= 15
    assert sum(v for k, v in counts.items() if k != "latin") == 0
