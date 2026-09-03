"""unbalanced_quotation — odd ASCII double-quote count or asymmetric curly pair."""

from __future__ import annotations

from typing import Any, Optional

from instrument.emissions.flags._common import FlagContext


def detect(ctx: FlagContext, params: dict) -> Optional[dict[str, Any]]:
    if not ctx.text:
        return None
    ascii_double = ctx.text.count('"')
    curly_open = ctx.text.count("\u201C")
    curly_close = ctx.text.count("\u201D")
    # Apostrophes in contractions dominate single-quote counts; we
    # only flag clearly odd double-quote counts.
    if ascii_double % 2 == 1:
        return {
            "ascii_double_count": ascii_double,
            "curly_open": curly_open,
            "curly_close": curly_close,
        }
    if curly_open != curly_close:
        return {
            "ascii_double_count": ascii_double,
            "curly_open": curly_open,
            "curly_close": curly_close,
        }
    return None
