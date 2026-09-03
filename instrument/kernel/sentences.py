"""sentences — abbreviation-aware sentence splitter.

Splits on sentence-boundary punctuation followed by an uppercase
letter, then iteratively merges fragments whose final token (after
period strip) is a known abbreviation. Supports chained
abbreviations ("Dr. e.g. foo" stays one fragment).
"""

from __future__ import annotations

import re

ABBREVIATIONS: frozenset[str] = frozenset({
    "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "st", "ave",
    "inc", "ltd", "co", "corp", "vs", "etc", "e.g", "i.e",
    "fig", "eq", "vol", "pp", "p", "ch", "sec",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "mon", "tue", "wed", "thu", "fri", "sat", "sun",
    "ca", "approx", "min", "max",
})

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_WHITESPACE = re.compile(r"\s+")


def split_sentences(text: str) -> list[str]:
    """Abbreviation-aware sentence split."""
    raw = _SENT_SPLIT.split(text)
    merged: list[str] = []
    buffer = ""
    for piece in raw:
        piece = piece.strip()
        if not piece:
            continue
        buffer = f"{buffer} {piece}" if buffer else piece
        last_word = _WHITESPACE.split(buffer)[-1].rstrip(".").lower()
        if last_word in ABBREVIATIONS:
            continue
        merged.append(buffer)
        buffer = ""
    if buffer:
        merged.append(buffer)
    return [s for s in merged if s]
