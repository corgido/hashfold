"""Behavioral tests for the distributional view."""
from __future__ import annotations

import math

from instrument.kernel.tokens import tokenise
from instrument.reading.distributional import (
    FEATURE_ORDER,
    _MATTR_WINDOW,
    _mattr,
    distributional_reading,
)


def _tok(text: str):
    return tokenise(text)


def _long(text: str, min_words: int = 160):
    words = text.split()
    reps = (min_words // len(words)) + 1
    return _tok((text + " ") * reps)


# ---- Shape ----

def test_feature_order_has_twelve_keys():
    assert len(FEATURE_ORDER) == 12


def test_distributional_reading_returns_all_keys():
    tokens = _long("The researcher studied the problem carefully and wrote a detailed report.")
    result = distributional_reading(tokens)
    assert set(result.keys()) == set(FEATURE_ORDER)


def test_below_envelope_returns_nan():
    tokens = _tok("Short text only.")
    result = distributional_reading(tokens)
    assert all(math.isnan(v) for v in result.values())


# ---- Hapax ratio ----

def test_hapax_ratio_all_unique():
    words = " ".join(f"xword{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(200))
    result = distributional_reading(_tok(words))
    assert result["hapax_ratio"] > 0.95


def test_hapax_ratio_all_repeated():
    result = distributional_reading(_tok("alpha beta gamma " * 60))
    assert result["hapax_ratio"] < 0.05


# ---- Yule's K ----

def test_yule_k_concentrated_higher_than_diverse():
    repetitive = distributional_reading(_tok("alpha beta " * 100))
    diverse = distributional_reading(
        _tok(" ".join(f"xword{chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(200)))
    )
    assert repetitive["yule_k"] > diverse["yule_k"]


# ---- Growth slope ----

def test_growth_slope_positive_for_varied_text():
    tokens = _long("Every sentence introduces new vocabulary that has not appeared before in this document.")
    result = distributional_reading(tokens)
    assert result["growth_slope"] > 0


# ---- Mean word length ----

def test_mean_word_length_technical_vs_simple():
    technical = distributional_reading(
        _long("The epistemological considerations underlying methodological frameworks "
              "necessitate comprehensive interdisciplinary collaboration.")
    )
    simple = distributional_reading(
        _long("The cat sat on the mat and the dog ran to the park.")
    )
    assert technical["mean_word_length"] > simple["mean_word_length"]


# ---- Compression ratio ----

def test_compression_ratio_repetitive_lower():
    repetitive = distributional_reading(_tok("hello world " * 100))
    diverse = distributional_reading(
        _tok(" ".join(f"word{i}" for i in range(200)))
    )
    assert repetitive["compression_ratio"] < diverse["compression_ratio"]


# ---- Bigram entropy ----

def test_bigram_entropy_varied_higher():
    monotone = distributional_reading(_tok("the cat the cat the cat " * 30))
    varied = distributional_reading(
        _long("She walked quickly. He ran slowly. They jumped high. We sat down.")
    )
    assert varied["bigram_entropy"] > monotone["bigram_entropy"]


# ---- Sentence length entropy ----

def test_sentence_length_entropy_uniform_lower():
    uniform = distributional_reading(
        _tok(("Five words in this one. " * 40))
    )
    varied = distributional_reading(
        _tok(("Short. " + "This sentence has exactly ten words in it now. " +
              "A medium length sentence with some variation included. " +
              "This is a significantly longer sentence that contains many more words than the others to create distributional variety. ") * 12)
    )
    assert varied["sentence_length_entropy"] > uniform["sentence_length_entropy"]


# ---- Burstiness ----

def test_burstiness_periodic_negative():
    periodic = " ".join(
        f"alpha filler padding extra words beta gamma delta "
        for _ in range(25)
    )
    result = distributional_reading(_tok(periodic))
    assert result["burstiness"] < 0.3


# ---- Entropy drift ----

def test_entropy_drift_uniform_near_zero():
    tokens = _long("The researcher studied the problem carefully and wrote a detailed report.")
    result = distributional_reading(tokens)
    assert result["entropy_drift"] < 0.5


def test_entropy_drift_shift_detectable():
    first_half = "The cat sat on the mat. " * 20
    second_half = "Epistemological frameworks necessitate comprehensive interdisciplinary collaboration. " * 20
    tokens = _tok(first_half + second_half)
    result = distributional_reading(tokens)
    assert result["entropy_drift"] > 0


# ---- Repetition halflife ----

def test_repetition_halflife_in_unit_interval():
    tokens = _long("The researcher studied the problem carefully and wrote a detailed report.")
    result = distributional_reading(tokens)
    assert 0.0 <= result["repetition_halflife"] <= 1.0


# ---- MATTR ----
#
# Vocabulary built from plain ASCII letter words ("cycaa", "cycab", ...)
# so `kernel/tokens.py word_tokens` ([A-Za-z]+ with internal
# apostrophes/hyphens, lowercased, digits dropped) maps each written
# word to exactly one token and the window arithmetic is transparent.

def _vocab(n: int, tag: str = "cyc") -> list[str]:
    assert n <= 26 * 26
    return [f"{tag}{chr(97 + i // 26)}{chr(97 + i % 26)}" for i in range(n)]


def test_mattr_known_answer_cyclic_vocabulary():
    # 50 distinct words repeated cyclically 4 times -> 200 tokens.
    # Every 100-word window covers exactly two full cycles, so every
    # window has exactly 50 distinct types: MATTR = 50/100 = 0.5.
    words = _vocab(50) * 4
    tokens = _tok(" ".join(words))
    assert tokens.n_words == 200
    result = distributional_reading(tokens)
    assert result["mattr"] == 0.5


def test_mattr_known_answer_nonconstant_window_profile():
    # First half: a 20-word vocabulary cycled (dense repetition).
    # Second half: 120 all-distinct words. Windows spanning the seam
    # have a distinct count that varies with position, so the window
    # profile is non-constant. Expected value computed exactly by an
    # independent brute-force O(n*W) reference, using the identical
    # final division so equality is exact, not approximate.
    words = _vocab(20, "rep") * 6 + _vocab(120, "uni")  # 240 tokens
    tokens = _tok(" ".join(words))
    assert tokens.n_words == 240

    w = _MATTR_WINDOW
    n = len(words)
    distinct_sum = sum(
        len(set(words[i:i + w])) for i in range(n - w + 1)
    )
    expected = distinct_sum / ((n - w + 1) * w)

    result = distributional_reading(tokens)
    assert result["mattr"] == expected
    # Sanity on the construction: the profile really is non-constant.
    window_counts = {len(set(words[i:i + w])) for i in range(n - w + 1)}
    assert len(window_counts) > 1


def test_mattr_below_envelope_nan():
    # 120 words >= _MATTR_WINDOW but < MIN_WORDS: the envelope gate
    # must cover mattr like every other distributional feature.
    words = _vocab(40) * 3  # 120 tokens
    result = distributional_reading(_tok(" ".join(words)))
    assert math.isnan(result["mattr"])


def test_mattr_deterministic():
    text = ("The researcher studied the problem carefully and wrote "
            "a detailed report about the findings. ") * 20
    a = distributional_reading(_tok(text))["mattr"]
    b = distributional_reading(_tok(text))["mattr"]
    assert a == b


def test_mattr_defensive_short_input_nan():
    # Direct call below the window width: defensive NaN. Unreachable
    # through distributional_reading (MIN_WORDS = 150 > window).
    assert math.isnan(_mattr(tuple(_vocab(30))))
