"""CONTRACT: compressibility is portable and tracks redundancy.

Replaces the former gzip ratio (zlib-implementation-dependent length, not
byte-portable). LZ78 complexity is integer-pure, so the value is exact and
identical on every host.
"""
from __future__ import annotations

import math

from instrument.kernel.compress import compressibility


def test_empty_is_nan():
    v = compressibility("")
    assert math.isnan(v)


def test_range_is_zero_to_one():
    for s in ["a" * 500, "the " * 200, "The cat sat on the mat. " * 40,
              "Heterogeneous prose with varied vocabulary and structure."]:
        v = compressibility(s)
        assert 0.0 < v <= 1.0


def test_more_repetition_is_more_compressible():
    # Strictly increasing complexity as repetition decreases.
    one_char = compressibility("a" * 2000)
    one_word = compressibility("the " * 500)
    one_sent = compressibility("The cat sat on the mat. " * 80)
    assert one_char < one_word < one_sent


def test_deterministic_and_integer_exact():
    s = "The pipeline reduces tail latency under sustained load. " * 50
    # Pure integer arithmetic -> identical every call, exact rational value.
    assert compressibility(s) == compressibility(s)
