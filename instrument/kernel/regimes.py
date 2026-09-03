"""regimes — three slicing regimes, unified interface.

Every regime returns a dict with a list of `(start_char, end_char)`
slices that cover the document exactly. The contract from
`kernel.slicer` is runnable against any regime's output.

- `flat`     null slicing: the whole document as one slice.
- `chunker`  RAG-style equal-word slicing; no structural awareness.
             Acts as the control — what happens when structure is
             ignored.
- `elegant`  contract-validated structural slicing.

The three together give at least three measures per document: one
null, one naive, one structural.
"""

from __future__ import annotations

from instrument.kernel.slicer import (
    MIN_WORDS_PER_SLICE,
    resolve_elegant,
    validate_slicing,
)


def regime_flat(text: str) -> dict:
    return {
        "regime": "flat",
        "slices": [(0, len(text))],
        "n_slices": 1,
        "notes": "document as single unit, no subdivision",
    }


def regime_chunker(text: str, n_slices: int | None = None) -> dict:
    """RAG-style fixed-window chunker by equal word count."""
    words = text.split()
    word_count = len(words)
    if n_slices is None:
        n_slices = max(1, word_count // MIN_WORDS_PER_SLICE)
    if n_slices == 1 or word_count < MIN_WORDS_PER_SLICE:
        return {
            "regime": "chunker",
            "slices": [(0, len(text))],
            "n_slices": 1,
            "notes": "document too short for multi-slice chunking",
        }

    chunk = word_count // n_slices
    slices: list[tuple[int, int]] = []
    current_char = 0
    word_idx = 0
    for i in range(n_slices):
        target_word = (i + 1) * chunk if i < n_slices - 1 else word_count
        words_seen = 0
        j = current_char
        while j < len(text) and words_seen < (target_word - word_idx):
            while j < len(text) and text[j].isspace():
                j += 1
            while j < len(text) and not text[j].isspace():
                j += 1
            words_seen += 1
        while j < len(text) and not text[j].isspace():
            j += 1
        if i == n_slices - 1:
            j = len(text)
        slices.append((current_char, j))
        current_char = j
        word_idx = target_word

    if slices[-1][1] != len(text):
        last_s, _ = slices[-1]
        slices[-1] = (last_s, len(text))

    return {
        "regime": "chunker",
        "slices": slices,
        "n_slices": len(slices),
        "notes": "RAG-style equal-word slicing, no structural awareness",
    }


def regime_elegant(text: str) -> dict:
    r = resolve_elegant(text)
    return {
        "regime": "elegant",
        "slices": r["slices"],
        "n_slices": r["full_resolution"],
        "boundary_level": r["boundary_level"],
        "notes": f"slicing at {r['boundary_level']} level, contract-validated",
    }


REGIMES = {
    "flat": regime_flat,
    "chunker": regime_chunker,
    "elegant": regime_elegant,
}


def measure_all_regimes(text: str) -> dict:
    """Run every regime. Each result carries contract_ok + failures."""
    results: dict = {}
    for name, fn in REGIMES.items():
        r = fn(text)
        ok, failures = validate_slicing(text, r["slices"])
        r["contract_ok"] = ok
        r["contract_failures"] = failures
        results[name] = r
    return results
