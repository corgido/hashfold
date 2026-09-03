"""distributional — 12-feature distributional view.

Measures vocabulary structure, predictability, and temporal texture
through distributional statistics. No lexicons, no classification
decisions — every feature is a count, a ratio, or an entropy
computed directly from the token stream.

Operates on the Tokens struct. Stdlib only (math, collections).
"""

from __future__ import annotations

import math
from collections import Counter

from instrument.kernel.compress import compressibility

from instrument.types import Tokens

FEATURE_ORDER: tuple[str, ...] = (
    "hapax_ratio",
    "yule_k",
    "growth_slope",
    "mean_word_length",
    "char_entropy",
    "bigram_entropy",
    "compression_ratio",
    "sentence_length_entropy",
    "burstiness",
    "repetition_halflife",
    "entropy_drift",
    "mattr",
)

MIN_WORDS = 150

# Sliding-window width for MATTR. Every window is W consecutive word
# tokens; MIN_WORDS = 150 > _MATTR_WINDOW guarantees at least 51
# windows for any document that clears the envelope gate, so the
# feature is total within the measurement envelope.
_MATTR_WINDOW = 100


def _shannon(counts) -> float:
    total = sum(counts)
    if total == 0:
        return 0.0
    return -sum(
        (c / total) * math.log2(c / total)
        for c in counts if c > 0
    )


def _char_entropy(text: str) -> float:
    counts = Counter(c for c in text.lower() if c.isalpha())
    return _shannon(counts.values())


def _hapax_ratio(words: tuple[str, ...]) -> float:
    freq = Counter(words)
    unique = len(freq)
    if unique == 0:
        return 0.0
    hapax = sum(1 for c in freq.values() if c == 1)
    return hapax / unique


def _yule_k(words: tuple[str, ...]) -> float:
    n = len(words)
    if n == 0:
        return 0.0
    freq = Counter(words)
    spectrum = Counter(freq.values())
    m2 = sum(i * i * vi for i, vi in spectrum.items())
    denom = n * n
    if denom == 0:
        return 0.0
    return 1e4 * (m2 - n) / denom


def _growth_slope(words: tuple[str, ...]) -> float:
    n = len(words)
    if n < 2:
        return 0.0
    seen: set[str] = set()
    curve: list[int] = []
    for w in words:
        seen.add(w)
        curve.append(len(seen))
    x_mean = (n - 1) / 2.0
    y_mean = sum(curve) / n
    cov_xy = sum((i - x_mean) * (curve[i] - y_mean) for i in range(n))
    var_x = n * (n * n - 1) / 12.0
    if var_x == 0:
        return 0.0
    return (cov_xy / var_x) / n


def _mean_word_length(words: tuple[str, ...]) -> float:
    if not words:
        return 0.0
    return sum(len(w) for w in words) / len(words)


def _bigram_entropy(words: tuple[str, ...]) -> float:
    if len(words) < 2:
        return 0.0
    bigrams = [(words[i], words[i + 1]) for i in range(len(words) - 1)]
    counts = Counter(bigrams)
    return _shannon(counts.values())


def _compression_ratio(cleaned: str) -> float:
    return compressibility(cleaned)


def _sentence_length_entropy(sentences: tuple[str, ...]) -> float:
    if not sentences:
        return 0.0
    bins = [0] * 6
    for s in sentences:
        wc = len(s.split())
        if wc <= 5:
            bins[0] += 1
        elif wc <= 10:
            bins[1] += 1
        elif wc <= 15:
            bins[2] += 1
        elif wc <= 20:
            bins[3] += 1
        elif wc <= 30:
            bins[4] += 1
        else:
            bins[5] += 1
    return _shannon(bins)


def _burstiness(words: tuple[str, ...]) -> float:
    if len(words) < 10:
        return 0.0
    freq = Counter(words)
    content = {w: c for w, c in freq.items() if len(w) >= 3}
    top = sorted(content, key=content.get, reverse=True)[:20]

    values: list[float] = []
    for word in top:
        positions = [i for i, w in enumerate(words) if w == word]
        if len(positions) < 3:
            continue
        intervals = [
            positions[i + 1] - positions[i]
            for i in range(len(positions) - 1)
        ]
        mu = sum(intervals) / len(intervals)
        sigma = math.sqrt(sum((x - mu) * (x - mu) for x in intervals) / len(intervals))
        denom = sigma + mu
        values.append((sigma - mu) / denom if denom > 0 else 0.0)

    return sum(values) / len(values) if values else 0.0


def _repetition_halflife(words: tuple[str, ...]) -> float:
    if len(words) < 2:
        return 0.5
    bigrams = [(words[i], words[i + 1]) for i in range(len(words) - 1)]
    first_repeat: dict[tuple[str, str], int] = {}
    seen: set[tuple[str, str]] = set()
    for i, bg in enumerate(bigrams):
        if bg in seen and bg not in first_repeat:
            first_repeat[bg] = i
        seen.add(bg)

    total_repeaters = len(first_repeat)
    if total_repeaters == 0:
        return 0.5

    sorted_positions = sorted(first_repeat.values())
    half_target = total_repeaters / 2.0
    for count, pos in enumerate(sorted_positions, 1):
        if count >= half_target:
            return pos / len(bigrams)
    return 0.5


def _entropy_drift(cleaned: str) -> float:
    if len(cleaned) < 20:
        return 0.0
    mid = len(cleaned) // 2
    return abs(_char_entropy(cleaned[:mid]) - _char_entropy(cleaned[mid:]))


def _mattr(words: tuple[str, ...], window: int = _MATTR_WINDOW) -> float:
    """Moving-Average Type-Token Ratio over sliding windows of `window` words.

    MATTR = mean over all `n - window + 1` sliding windows of
    (distinct types in window) / window. Because every window has the
    same width, the value does not fall mechanically as the document
    grows — it is the length-robust alternative to
    `cohesion.type_token_ratio` / `coh.type_token_ratio` /
    `register.lexical_novelty`, whose raw type/token quotients decline
    with n by construction. A reported measurement and an
    invariance-audit instrument (see docs/LENGTH_RESPONSE.md), not a
    routing coordinate: the distributional view does not feed routing.

    Total within the measurement envelope: `MIN_WORDS = 150 >
    _MATTR_WINDOW = 100`, so any document that clears the envelope
    gate has at least one full window. The `n < window` branch below
    returns NaN defensively but is unreachable through the public path
    (`distributional_reading` gates on MIN_WORDS first).

    O(n): one Counter over the current window, incremented at the
    leading edge and decremented at the trailing edge, with the
    distinct-type count tracked as an integer. The mean is computed as
    (sum of per-window distinct counts) / (n_windows * window) — pure
    integer arithmetic until the single final division.
    """
    n = len(words)
    if n < window:
        return float("nan")  # unreachable via distributional_reading
    counts: Counter[str] = Counter(words[:window])
    distinct = len(counts)
    distinct_sum = distinct
    for i in range(window, n):
        incoming = words[i]
        outgoing = words[i - window]
        if incoming != outgoing:
            counts[incoming] += 1
            if counts[incoming] == 1:
                distinct += 1
            counts[outgoing] -= 1
            if counts[outgoing] == 0:
                del counts[outgoing]
                distinct -= 1
        distinct_sum += distinct
    return distinct_sum / ((n - window + 1) * window)


def _nan_features() -> dict[str, float]:
    return {k: float("nan") for k in FEATURE_ORDER}


def distributional_reading(tokens: Tokens) -> dict[str, float]:
    """12-feature distributional view over a pre-tokenised Tokens struct."""
    if tokens.n_words < MIN_WORDS:
        return _nan_features()

    return {
        "hapax_ratio": _hapax_ratio(tokens.words),
        "yule_k": _yule_k(tokens.words),
        "growth_slope": _growth_slope(tokens.words),
        "mean_word_length": _mean_word_length(tokens.words),
        "char_entropy": _char_entropy(tokens.cleaned),
        "bigram_entropy": _bigram_entropy(tokens.words),
        "compression_ratio": _compression_ratio(tokens.cleaned),
        "sentence_length_entropy": _sentence_length_entropy(tokens.sentences),
        "burstiness": _burstiness(tokens.words),
        "repetition_halflife": _repetition_halflife(tokens.words),
        "entropy_drift": _entropy_drift(tokens.cleaned),
        "mattr": _mattr(tokens.words),
    }
