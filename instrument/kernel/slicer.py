"""slicer — propose and validate document slicings.

Slices a document along its own structural grain, preferring
larger structural units (sections, paragraphs, sentences) over
smaller ones. Only breaks mid-unit when no larger boundary admits
a valid slicing under the contract.

The slicer PROPOSES. The contract VALIDATES. A slicing is
admissible only if every clause holds.

Clamps:
- WORD_ENVELOPE      every slice must have >= MIN_WORDS_PER_SLICE words.
- SFL_LOAD           every slice must carry >= MIN_PROCESS_TOKENS verb-ish
                     tokens (mental + verbal + relational + existential).
- COHESION_LOAD      every slice must carry >= MIN_CONTENT_TYPES unique
                     content-word types.

RST has no structural clamp: a marker density of zero is a
legitimate reading.
"""

from __future__ import annotations

import re

from instrument.kernel.features.cohesion import STOPWORDS
from instrument.kernel.features.sfl import (
    COPULA_BE,
    EXISTENTIAL_PATTERN,
    MENTAL,
    RELATIONAL,
    VERBAL,
)
from instrument.kernel.tokens import word_tokens

MIN_WORDS_PER_SLICE = 150
MIN_PROCESS_TOKENS = 5
MIN_CONTENT_TYPES = 10
MAX_SLICES = 20

_SECTION_PATTERN = re.compile(r"\n\s*#{1,6}\s+[^\n]+\n", re.MULTILINE)
_PARAGRAPH_PATTERN = re.compile(r"\n\s*\n")
_SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_WHITESPACE_PATTERN = re.compile(r"\s+")


# ---- boundary finders ------------------------------------------------------

def find_section_breaks(text: str) -> list[int]:
    return [m.start() for m in _SECTION_PATTERN.finditer(text) if m.start() > 0]


def find_paragraph_breaks(text: str) -> list[int]:
    return [m.end() for m in _PARAGRAPH_PATTERN.finditer(text)]


def find_sentence_breaks(text: str) -> list[int]:
    return [m.end() for m in _SENTENCE_PATTERN.finditer(text)]


def find_word_breaks(text: str) -> list[int]:
    return [m.end() for m in _WHITESPACE_PATTERN.finditer(text)]


BOUNDARY_FINDERS = [
    ("section", find_section_breaks),
    ("paragraph", find_paragraph_breaks),
    ("sentence", find_sentence_breaks),
    ("word", find_word_breaks),
]


# ---- clamps (apply to a slice text) ---------------------------------------

def check_word_envelope(tokens: list[str]) -> tuple[bool, int]:
    n = len(tokens)
    return n >= MIN_WORDS_PER_SLICE, n


def check_sfl_load(tokens: list[str], slice_text: str) -> tuple[bool, int]:
    mental = sum(1 for t in tokens if t in MENTAL)
    verbal = sum(1 for t in tokens if t in VERBAL)
    relational = sum(
        1 for t in tokens if t in RELATIONAL or t in COPULA_BE
    )
    existential = len(EXISTENTIAL_PATTERN.findall(slice_text))
    total = mental + verbal + relational + existential
    return total >= MIN_PROCESS_TOKENS, total


def check_cohesion_load(tokens: list[str]) -> tuple[bool, int]:
    types = {t for t in tokens if t not in STOPWORDS}
    return len(types) >= MIN_CONTENT_TYPES, len(types)


# ---- slice proposal -------------------------------------------------------

def propose_slices_at_level(
    text: str, finder, n_slices: int
) -> list[tuple[int, int]]:
    """Propose `n_slices` slices by greedy-nearest to equal-char cuts."""
    candidates = [c for c in finder(text) if 0 < c < len(text)]
    if len(candidates) < n_slices - 1:
        return []
    total_len = len(text)
    target_len = total_len / n_slices
    cuts: list[int] = []
    used: set[int] = set()
    for i in range(1, n_slices):
        target = int(i * target_len)
        best: int | None = None
        best_dist: int | None = None
        for c in candidates:
            if c in used:
                continue
            d = abs(c - target)
            if best_dist is None or d < best_dist:
                best = c
                best_dist = d
        if best is None:
            return []
        cuts.append(best)
        used.add(best)
    cuts.sort()
    out: list[tuple[int, int]] = []
    prev = 0
    for c in cuts:
        out.append((prev, c))
        prev = c
    out.append((prev, total_len))
    return out


# ---- contract clauses -----------------------------------------------------
#
# Each clause returns a list of failure messages (empty = clause holds).
# Deliberately NOT implemented with `assert`: `python -O` /
# PYTHONOPTIMIZE strips asserts, which would silently approve invalid
# slicings and change `resolve_elegant`'s chosen slicing — i.e. change
# emission output — on an optimised interpreter. The contract is
# runtime validation, not a debug check.

def _clause_coverage(text: str, slices: list[tuple[int, int]]) -> list[str]:
    if not slices:
        return ["no slices"]
    failures: list[str] = []
    if slices[0][0] != 0:
        failures.append(f"first slice must start at 0, got {slices[0][0]}")
    if slices[-1][1] != len(text):
        failures.append(
            f"last slice must end at {len(text)}, got {slices[-1][1]}"
        )
    for i in range(len(slices) - 1):
        if slices[i][1] != slices[i + 1][0]:
            failures.append(
                f"slice {i} ends at {slices[i][1]} but slice {i+1} starts at "
                f"{slices[i+1][0]}"
            )
    return failures


def _clause_non_empty(text: str, slices: list[tuple[int, int]]) -> list[str]:
    return [
        f"slice {i} is empty ({s}, {e})"
        for i, (s, e) in enumerate(slices) if e <= s
    ]


def _clause_word_envelope(text: str, slices: list[tuple[int, int]]) -> list[str]:
    failures: list[str] = []
    for i, (s, e) in enumerate(slices):
        tokens = word_tokens(text[s:e])
        ok, n = check_word_envelope(tokens)
        if not ok:
            failures.append(
                f"slice {i} has {n} words, below word envelope "
                f"{MIN_WORDS_PER_SLICE}"
            )
    return failures


def _clause_sfl_load(text: str, slices: list[tuple[int, int]]) -> list[str]:
    failures: list[str] = []
    for i, (s, e) in enumerate(slices):
        slice_text = text[s:e]
        tokens = word_tokens(slice_text)
        ok, n = check_sfl_load(tokens, slice_text)
        if not ok:
            failures.append(
                f"slice {i} has {n} process tokens, below SFL load "
                f"{MIN_PROCESS_TOKENS}"
            )
    return failures


def _clause_cohesion_load(text: str, slices: list[tuple[int, int]]) -> list[str]:
    failures: list[str] = []
    for i, (s, e) in enumerate(slices):
        tokens = word_tokens(text[s:e])
        ok, n = check_cohesion_load(tokens)
        if not ok:
            failures.append(
                f"slice {i} has {n} content types, below cohesion load "
                f"{MIN_CONTENT_TYPES}"
            )
    return failures


CONTRACT = (
    _clause_coverage,
    _clause_non_empty,
    _clause_word_envelope,
    _clause_sfl_load,
    _clause_cohesion_load,
)


def validate_slicing(
    text: str, slices: list[tuple[int, int]]
) -> tuple[bool, list[str]]:
    """Run every contract clause. Return (ok, failure_messages)."""
    failures: list[str] = []
    for clause in CONTRACT:
        for msg in clause(text, slices):
            failures.append(f"{clause.__name__}: {msg}")
    return (not failures, failures)


# ---- resolver -------------------------------------------------------------

def resolve_elegant(text: str, max_slices: int = MAX_SLICES) -> dict:
    """Find the coarsest-level, largest-N slicing that passes the contract.

    If the best result collapses to N=1 but the word envelope would
    allow more, a relaxed contract (word envelope + cohesion load,
    skipping SFL load) is tried — handles code-heavy / list-dominant /
    nominal documents. The relaxed boundary level is suffixed
    ``-relaxed``.
    """
    word_count = len(text.split())
    hard_ceiling = max(1, min(max_slices, word_count // MIN_WORDS_PER_SLICE))

    trace: list[dict] = []
    for level_name, finder in BOUNDARY_FINDERS:
        for n in range(hard_ceiling, 0, -1):
            slices = propose_slices_at_level(text, finder, n)
            if not slices:
                trace.append(
                    {"level": level_name, "n": n, "ok": False,
                     "reason": "insufficient boundaries"}
                )
                continue
            ok, failures = validate_slicing(text, slices)
            trace.append(
                {"level": level_name, "n": n, "ok": ok,
                 "failures": failures if not ok else []}
            )
            if ok:
                if n == 1 and hard_ceiling > 1:
                    relaxed = _try_relaxed(text, hard_ceiling, trace)
                    if relaxed:
                        return relaxed
                return {
                    "word_count": word_count,
                    "hard_ceiling": hard_ceiling,
                    "full_resolution": n,
                    "boundary_level": level_name,
                    "slices": slices,
                    "trace": trace,
                }

    relaxed = _try_relaxed(text, hard_ceiling, trace)
    if relaxed:
        return relaxed
    return {
        "word_count": word_count,
        "hard_ceiling": hard_ceiling,
        "full_resolution": 1,
        "boundary_level": "document",
        "slices": [(0, len(text))],
        "trace": trace,
    }


def _try_relaxed(text: str, hard_ceiling: int, trace: list) -> dict | None:
    """Relaxed contract: word envelope + cohesion load only, no SFL load."""
    def _validate(text, slices):
        failures = []
        for i, (s, e) in enumerate(slices):
            tokens = word_tokens(text[s:e])
            we_ok, we_val = check_word_envelope(tokens)
            if not we_ok:
                failures.append(f"word_envelope: slice {i} = {we_val}w")
            coh_ok, coh_val = check_cohesion_load(tokens)
            if not coh_ok:
                failures.append(f"cohesion_load: slice {i} = {coh_val} types")
        return not failures, failures

    word_count = len(text.split())
    relaxed_trace: list[dict] = []
    for level_name, finder in BOUNDARY_FINDERS:
        for n in range(hard_ceiling, 1, -1):
            slices = propose_slices_at_level(text, finder, n)
            if not slices:
                continue
            ok, _ = _validate(text, slices)
            relaxed_trace.append(
                {"level": level_name, "n": n, "ok": ok, "relaxed": True}
            )
            if ok:
                return {
                    "word_count": word_count,
                    "hard_ceiling": hard_ceiling,
                    "full_resolution": n,
                    "boundary_level": level_name + "-relaxed",
                    "slices": slices,
                    "trace": trace + relaxed_trace,
                }
    return None
