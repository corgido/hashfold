"""trajectory_features — per-slice feature curves.

Takes a whole-document Tokens plus an ordered list of (start, end)
character-offset slices *into the document-level cleaned text*
(`Tokens.cleaned`) and returns the four register features as
per-slice lists. Slice 0 novelty is NaN (no prior comparison
point; returning 1.0 would artificially anchor every document's
trajectory at the ceiling).

Per-slice measurements run on substrings of the ONE document-level
cleaning (frontmatter stripped, fenced-code interiors blanked,
apostrophes normalised). Cleaning happens once, before slicing, so
"modal density in slice 4" and "modal density of the document"
measure the same kind of input by construction — a fence spanning
a slice boundary cannot be resurrected as prose, and a slice that
happens to start at a mid-document thematic break cannot be
mistaken for YAML frontmatter. (Both were real failure modes of the
pre-0.9.1 slice-then-reclean order.)
"""

from __future__ import annotations

from instrument.kernel.features.cohesion import STOPWORDS, content_words
from instrument.kernel.features.register import MODALS, NEGATIONS
from instrument.kernel.sentences import split_sentences
from instrument.kernel.tokens import word_tokens

TRAJECTORY_FEATURES: tuple[str, ...] = (
    "lexical_novelty",
    "sentence_length_variance",
    "modal_density",
    "negation_density",
)


def _content_words(tokens: list[str]) -> set[str]:
    """Content words over the pre-tokenized list.

    Filtered by STOPWORDS and len(t) > 2.
    Caller is responsible for cleaning the slice substring before
    tokenizing (so frontmatter and fenced-code content do not
    contribute).
    """
    return {
        t for t in tokens
        if t not in STOPWORDS and len(t) > 2
    }


def _slice_novelty(tokens: list[str], prior_seen: set[str]) -> float:
    slice_content = _content_words(tokens)
    if not slice_content:
        return 0.0
    novel = slice_content - prior_seen
    return len(novel) / len(slice_content)


def _slice_variance(slice_text: str) -> float:
    # Whole-slice sentence split; matches legacy
    # trajectory_features.sentence_length_variance.
    sents = split_sentences(slice_text)
    if len(sents) < 2:
        return 0.0
    lengths = [len(s.split()) for s in sents]
    mean = sum(lengths) / len(lengths)
    return sum((l - mean) * (l - mean) for l in lengths) / len(lengths)


def _slice_modal(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in MODALS) / len(tokens) * 100.0


def _slice_negation(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if t in NEGATIONS) / len(tokens) * 100.0


def read_trajectory(
    tokens, slices: list[tuple[int, int]]
) -> dict[str, list[float]]:
    """Read the four trajectory features across the given slices.

    `tokens` is an `instrument.types.Tokens` struct (or anything
    with a `.cleaned` attribute); slices index into the document-level
    CLEANED text (`Tokens.cleaned`). Callers produce them by slicing
    the cleaned text (e.g. `regime_elegant(tokens.cleaned)`).

    Each slice's features are computed on the cleaned substring as-is
    — no per-slice re-cleaning (see the module docstring); the
    prior_seen novelty set is updated from the same tokens.
    """
    result: dict[str, list[float]] = {f: [] for f in TRAJECTORY_FEATURES}
    prior_seen: set[str] = set()

    for i, (start, end) in enumerate(slices):
        slice_text = tokens.cleaned[start:end]
        wt = word_tokens(slice_text)
        if i == 0:
            result["lexical_novelty"].append(float("nan"))
        else:
            result["lexical_novelty"].append(
                _slice_novelty(wt, prior_seen)
            )
        result["sentence_length_variance"].append(_slice_variance(slice_text))
        result["modal_density"].append(_slice_modal(wt))
        result["negation_density"].append(_slice_negation(wt))
        prior_seen |= _content_words(wt)

    return result
