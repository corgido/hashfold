"""cohesion — surface cohesion signals (compact view).

Three features:

    type_token_ratio      |unique word types| / n_words
    pronoun_density       pronouns per 100 words
    lexical_repetition    content-word types appearing in >= 2
                          distinct sentences, as a rate in [0, 1]

Implementation scope: exact lemma matches only. Does NOT do
coreference resolution, substitution, ellipsis, or synonym /
hypernym chains. Treat as a surface-repetition signal, not a full
Halliday & Hasan cohesion analysis.
"""

from __future__ import annotations

from instrument.kernel.tokens import word_tokens
from instrument.types import Tokens

MIN_WORDS = 150

PRONOUNS: frozenset[str] = frozenset({
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "this", "that", "these", "those",
})

# Stopwords = closed-class words we exclude from lexical-repetition
# counting. Pronouns are included so pronoun_density is the
# canonical place pronouns enter the signal.
STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "if", "then", "else",
    "of", "in", "on", "at", "to", "for", "with", "by", "from",
    "as", "is", "are", "was", "were", "be", "been", "being", "am",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "can", "could", "should", "may", "might", "must", "shall",
    "not", "no", "yes", "so", "too", "very", "just", "only",
    "also", "than", "which", "who", "whom", "whose", "what",
    "when", "where", "why", "how", "all", "some", "any", "each",
    "every", "both", "few", "more", "most", "other", "such",
    "because", "through", "between", "above", "below", "after",
    "before", "during", "while", "without", "within", "against",
    "toward", "towards", "into", "onto", "upon", "about", "around",
    "across", "along", "among", "over", "under", "up", "down",
    "again", "doing", "further", "having", "here", "there", "now",
    "nor", "off", "out", "own", "same", "well",
}) | PRONOUNS


def content_words(words) -> set[str]:
    """Return the set of content-word types in `words`.

    A content word is a token longer than 2 characters that is not
    in `STOPWORDS`. Used by register.lexical_novelty and by the
    trajectory novelty detector.
    """
    return {t for t in words if t not in STOPWORDS and len(t) > 2}


def cohesion_compact(tokens: Tokens) -> dict[str, float]:
    """Three-feature cohesion read over a pre-tokenised Tokens struct."""
    n_words = tokens.n_words
    if n_words < MIN_WORDS:
        return {
            "type_token_ratio": float("nan"),
            "pronoun_density": float("nan"),
            "lexical_repetition": float("nan"),
            "n_words": n_words,
            "below_envelope": True,
        }

    types = set(tokens.words)
    ttr = len(types) / n_words

    pronoun_count = sum(1 for t in tokens.words if t in PRONOUNS)
    pronoun_density = pronoun_count / n_words * 100.0

    # Cross-sentence lexical-repetition rate: content-word types
    # appearing in >= 2 distinct sentences, divided by total unique
    # content types. Matches shaper.extended.coh.lexical_repetition_rate
    # so the joint cohesion_repetition axis compares like with like.
    stem_to_sents: dict[str, set[int]] = {}
    for idx, sent in enumerate(tokens.sentences):
        for t in word_tokens(sent):
            if t in STOPWORDS or len(t) <= 2:
                continue
            stem_to_sents.setdefault(t, set()).add(idx)
    unique_types = len(stem_to_sents)
    if unique_types:
        repeated_types = sum(
            1 for sent_set in stem_to_sents.values() if len(sent_set) >= 2
        )
        lexical_repetition = repeated_types / unique_types
    else:
        lexical_repetition = 0.0

    return {
        "type_token_ratio": ttr,
        "pronoun_density": pronoun_density,
        "lexical_repetition": lexical_repetition,
        "n_words": n_words,
        "below_envelope": False,
    }
