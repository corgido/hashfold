"""Cohesion analysis (Halliday & Hasan 1976; extended view).

13 features across three sub-systems:

    Reference        pronoun / demonstrative / definite-article /
                     reference densities per 100 words
    Lexical          type_token_ratio, lexical_repetition_rate,
                     lexical_chain_count (>=3 sentences, normalised by
                     n_sentences), lexical_chain_span (avg span, norm.)
    Conjunction      additive / adversative / causal / temporal
                     densities + conjunction_balance (adversative /
                     (additive + adversative) ∈ [0, 1])

Approximation: lexical chains require thesaural relations to detect
synonymy. We approximate by exact-stem repetition (crude suffix
stripping, not Porter). Underestimates cohesion in texts with rich
vocabulary variation; conservative measure.
"""

from __future__ import annotations

from collections import defaultdict

from instrument.reading.document import Document
from instrument.reading.extended.lexicons import (
    ADDITIVE_CONJUNCTIONS,
    ADVERSATIVE_CONJUNCTIONS,
    CAUSAL_CONJUNCTIONS,
    DEFINITE_ARTICLE,
    DEMONSTRATIVES,
    PERSONAL_PRONOUNS,
    STOPWORDS,
    TEMPORAL_CONJUNCTIONS,
)


def _is_content_word(lower: str) -> bool:
    if len(lower) < 3:
        return False
    if lower in STOPWORDS:
        return False
    if not lower[0].isalpha():
        return False
    return True


def _stem(word: str) -> str:
    """Crude suffix stripping. Conservative: if in doubt, leave alone."""
    w = word.lower()
    if len(w) < 5:
        return w
    for suf in ("ingly", "ation", "ions", "ing", "ies", "ied",
                "ed", "es", "s", "ly"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _zero_features() -> dict:
    return {
        "pronoun_density": 0.0,
        "demonstrative_density": 0.0,
        "definite_article_density": 0.0,
        "reference_density": 0.0,
        "additive_density": 0.0,
        "adversative_density": 0.0,
        "causal_density": 0.0,
        "temporal_density": 0.0,
        "conjunction_balance": 0.0,
        "type_token_ratio": 0.0,
        "lexical_repetition_rate": 0.0,
        "lexical_chain_count": 0.0,
        "lexical_chain_span": 0.0,
    }


def analyse(doc: Document) -> dict:
    """Compute 13 cohesion features over a `Document`."""
    if doc.n_words == 0 or doc.n_sentences == 0:
        return _zero_features()

    pronouns = demonstratives = definite_articles = 0
    additive = adversative = causal = temporal = 0
    stem_to_sents: dict = defaultdict(set)
    content_words: list[str] = []

    for s_idx, sent in enumerate(doc.sentences):
        for tok in sent.tokens:
            if not tok.is_word:
                continue
            lower = tok.lower
            if lower in PERSONAL_PRONOUNS:
                pronouns += 1
            if lower in DEMONSTRATIVES:
                demonstratives += 1
            if lower in DEFINITE_ARTICLE:
                definite_articles += 1
            if lower in ADDITIVE_CONJUNCTIONS:
                additive += 1
            if lower in ADVERSATIVE_CONJUNCTIONS:
                adversative += 1
            if lower in CAUSAL_CONJUNCTIONS:
                causal += 1
            if lower in TEMPORAL_CONJUNCTIONS:
                temporal += 1
            if _is_content_word(lower):
                stem = _stem(lower)
                stem_to_sents[stem].add(s_idx)
                content_words.append(stem)

    n_words = doc.n_words
    n_sent = doc.n_sentences

    features: dict = {
        "pronoun_density": pronouns / n_words * 100.0,
        "demonstrative_density": demonstratives / n_words * 100.0,
        "definite_article_density": definite_articles / n_words * 100.0,
        "reference_density": (
            (pronouns + demonstratives + definite_articles) / n_words * 100.0
        ),
        "additive_density": additive / n_words * 100.0,
        "adversative_density": adversative / n_words * 100.0,
        "causal_density": causal / n_words * 100.0,
        "temporal_density": temporal / n_words * 100.0,
    }

    features["conjunction_balance"] = (
        adversative / (additive + adversative)
        if (additive + adversative) > 0 else 0.0
    )

    if content_words:
        unique_stems = set(content_words)
        features["type_token_ratio"] = len(unique_stems) / len(content_words)
        repeated_stems = [
            s for s, sents in stem_to_sents.items() if len(sents) >= 2
        ]
        features["lexical_repetition_rate"] = (
            len(repeated_stems) / len(unique_stems)
        )
        chains = [
            (s, sents) for s, sents in stem_to_sents.items()
            if len(sents) >= 3
        ]
        features["lexical_chain_count"] = len(chains) / n_sent
        if chains:
            spans = [
                (max(sents) - min(sents)) / max(1, n_sent - 1)
                for _, sents in chains
            ]
            features["lexical_chain_span"] = sum(spans) / len(spans)
        else:
            features["lexical_chain_span"] = 0.0
    else:
        features["type_token_ratio"] = 0.0
        features["lexical_repetition_rate"] = 0.0
        features["lexical_chain_count"] = 0.0
        features["lexical_chain_span"] = 0.0

    return features
