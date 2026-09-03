"""stylometry — deterministic surface features orthogonal to SFL/RST/
Cohesion.

Seven features, computed in a single pass over a pre-tokenised
Tokens struct:

    compression_ratio         normalised LZ78 complexity (kernel.compress)
    semicolon_per_1k_words    `;` count / n_words * 1000
    comma_per_sentence        `,` count / n_sentences
    question_rate             sentences ending in `?` / n_sentences
    exclamation_rate          sentences ending in `!` / n_sentences
    quotation_density         quote chars / chars(cleaned) * 1000
    subordination_density     subordinating-conjunction hits / n_words * 1000

Scope: English-only. Unicode quotation marks normalised alongside
ASCII. Does NOT measure actual syntactic depth (would need a
parser), prosody, author identity, or any semantic property.
"""

from __future__ import annotations

from instrument.kernel.compress import compressibility
from instrument.kernel.tokens import word_tokens
from instrument.types import Tokens

_SUBORDINATORS_SINGLE: frozenset[str] = frozenset({
    "although", "though", "because", "since", "unless", "until",
    "when", "whenever", "where", "wherever", "while", "whereas",
    "before", "after", "if", "once", "whether",
})
_SUBORDINATORS_MULTI: tuple[str, ...] = (
    "even though", "as long as", "as soon as", "so that",
    "in order that", "provided that", "given that",
)
# Token-sequence form, longest-first (with a stable lexical
# tiebreak), for the matcher below. Matching is done on word-token
# sequences, NOT substrings: the old `phrase in sentence.lower()`
# check counted "so that" inside "also that" / "it's also that",
# and counted each multi-word phrase at most once per sentence while
# single-word subordinators were counted per occurrence.
_SUBORDINATORS_MULTI_TOKENS: tuple[tuple[str, ...], ...] = tuple(
    sorted(
        (tuple(p.split()) for p in _SUBORDINATORS_MULTI),
        key=lambda pw: (-len(pw), pw),
    )
)

_QUOTE_CHARS: frozenset[str] = frozenset({
    '"', "'",
    "\u201C", "\u201D",
    "\u2018", "\u2019",
    "\u00AB", "\u00BB",
})

FEATURE_ORDER: tuple[str, ...] = (
    "compression_ratio",
    "semicolon_per_1k_words",
    "comma_per_sentence",
    "question_rate",
    "exclamation_rate",
    "quotation_density",
    "subordination_density",
)


def _compression_ratio(cleaned: str) -> float:
    """Portable compressibility proxy (normalised LZ78 complexity).

    Replaces the former ``len(gzip.compress(cleaned)) / len(bytes)``, whose
    length was zlib-implementation-dependent and not byte-portable across
    hosts. See ``kernel/compress.py``.
    """
    return compressibility(cleaned)


def _punctuation(cleaned: str, sentences, n_words: int) -> dict[str, float]:
    n_sentences = len(sentences)
    if n_sentences == 0 or n_words == 0:
        return {
            "semicolon_per_1k_words": float("nan"),
            "comma_per_sentence": float("nan"),
            "question_rate": float("nan"),
            "exclamation_rate": float("nan"),
            "quotation_density": float("nan"),
        }
    semicolons = cleaned.count(";")
    commas = cleaned.count(",")
    questions = sum(1 for s in sentences if s.rstrip().endswith("?"))
    exclamations = sum(1 for s in sentences if s.rstrip().endswith("!"))
    quote_chars = sum(1 for c in cleaned if c in _QUOTE_CHARS)
    return {
        "semicolon_per_1k_words": semicolons / n_words * 1000.0,
        "comma_per_sentence": commas / n_sentences,
        "question_rate": questions / n_sentences,
        "exclamation_rate": exclamations / n_sentences,
        "quotation_density": quote_chars / max(len(cleaned), 1) * 1000.0,
    }


def _subordination_density(sentences, n_words: int) -> float:
    """Subordinating-conjunction hits per 1000 words.

    Greedy left-to-right scan over each sentence's word tokens:
    multi-word phrases (longest first) consume their tokens; any
    remaining unconsumed token in the single-word set counts once
    per occurrence. Both phrase classes are therefore counted
    per occurrence, on token boundaries.
    """
    if n_words == 0:
        return float("nan")
    hits = 0
    for sent in sentences:
        tokens = word_tokens(sent)
        consumed: set[int] = set()
        n = len(tokens)
        i = 0
        while i < n:
            matched = False
            for pw in _SUBORDINATORS_MULTI_TOKENS:
                length = len(pw)
                if i + length <= n and tuple(tokens[i:i + length]) == pw:
                    hits += 1
                    consumed.update(range(i, i + length))
                    i += length
                    matched = True
                    break
            if not matched:
                i += 1
        for j, t in enumerate(tokens):
            if j not in consumed and t in _SUBORDINATORS_SINGLE:
                hits += 1
    return hits / n_words * 1000.0


def stylometry_compact(tokens: Tokens) -> dict[str, float]:
    """Seven stylometry features over a pre-tokenised Tokens struct.

    Returns a flat dict keyed by the short names in `FEATURE_ORDER`
    (no `stylometry.*` prefix — the joint-reading composer
    namespaces them at the output boundary).
    """
    features: dict[str, float] = {}
    features["compression_ratio"] = _compression_ratio(tokens.cleaned)
    features.update(
        _punctuation(tokens.cleaned, tokens.sentences, tokens.n_words)
    )
    features["subordination_density"] = _subordination_density(
        tokens.sentences, tokens.n_words
    )
    return features
