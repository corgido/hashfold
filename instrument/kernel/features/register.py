"""register — document-level stylistic features.

Four features; historical name is `register` but this is NOT
Halliday's register (field / tenor / mode). Treat these as
trajectory-adjacent stylistic measures:

    lexical_novelty             content types / content tokens
    sentence_length_variance    variance of sentence word counts
    modal_density               modals per 100 words
    negation_density            negation markers per 100 words

Bucket name is preserved for output-schema stability.
"""

from __future__ import annotations

from instrument.kernel.features.cohesion import STOPWORDS, content_words
from instrument.types import Tokens

MODALS: frozenset[str] = frozenset({
    "can", "could", "may", "might", "must", "shall", "should",
    "will", "would", "ought",
})

# Apostrophe forms ("don't") match when input has ASCII apostrophes.
# Bare forms ("dont") cover apostrophe-free input (informal text, OCR).
NEGATIONS: frozenset[str] = frozenset({
    "not", "no", "never", "nothing", "nobody", "none", "neither", "nor",
    "cannot",
    "cant", "wont", "dont", "doesnt", "didnt", "isnt", "arent",
    "wasnt", "werent", "hasnt", "havent", "hadnt", "wouldnt", "couldnt",
    "shouldnt",
    "don't", "won't", "can't", "doesn't", "didn't", "isn't", "aren't",
    "wasn't", "weren't", "hasn't", "haven't", "hadn't", "wouldn't",
    "couldn't", "shouldn't",
})


def lexical_novelty(tokens: Tokens) -> float:
    """Unique content-word types / total content-word tokens."""
    cw = content_words(tokens.words)
    total_content = sum(
        1 for t in tokens.words if t not in STOPWORDS and len(t) > 2
    )
    return len(cw) / max(total_content, 1)


def sentence_length_variance(tokens: Tokens) -> float:
    """Variance (population, ddof=0) of sentence word counts.

    Uses the canonical paragraph-first sentence stream (`tokens.sentences`)
    so every consumer of "sentence" in the instrument sees the same
    segmentation. Matches the segmentation used by RST, the extended view,
    and per-slice trajectory features.

    0.0 when fewer than two sentences.
    """
    sents = tokens.sentences
    if len(sents) < 2:
        return 0.0
    lengths = [len(s.split()) for s in sents]
    mean = sum(lengths) / len(lengths)
    return sum((l - mean) * (l - mean) for l in lengths) / len(lengths)


def modal_density(tokens: Tokens) -> float:
    """Modal auxiliaries per 100 words. 0.0 on empty text."""
    if not tokens.words:
        return 0.0
    return sum(1 for t in tokens.words if t in MODALS) / len(tokens.words) * 100.0


def negation_density(tokens: Tokens) -> float:
    """Negation markers per 100 words. 0.0 on empty text."""
    if not tokens.words:
        return 0.0
    return sum(1 for t in tokens.words if t in NEGATIONS) / len(tokens.words) * 100.0


def register_read(tokens: Tokens) -> dict[str, float]:
    """All four register features as a dict."""
    return {
        "lexical_novelty": lexical_novelty(tokens),
        "sentence_length_variance": sentence_length_variance(tokens),
        "modal_density": modal_density(tokens),
        "negation_density": negation_density(tokens),
    }
