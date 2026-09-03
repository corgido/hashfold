"""paragraphs — split text on blank lines."""

from __future__ import annotations

import re

_PARA_SPLIT = re.compile(r"\n\s*\n")


def split_paragraphs(text: str) -> list[str]:
    """Split on blank lines. Empty paragraphs dropped."""
    return [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
