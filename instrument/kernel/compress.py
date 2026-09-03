"""compress — deterministic, portable compressibility estimate.

Replaces ``len(gzip.compress(...)) / len(bytes)``. The gzip/DEFLATE output
length is a function of the linked zlib implementation's match-finding
heuristics (lazy matching, hash-chain depth, ``good_match`` / ``nice_match``
cutoffs), which differ across zlib versions and builds. ``mtime=0`` fixes
only the 10-byte gzip header timestamp, not the DEFLATE body — so the
compressed length is *not* byte-portable across hosts, and float
quantisation cannot fix it (the difference is whole bytes of length, not a
last-ULP wobble).

This estimator is **normalised Lempel-Ziv (LZ78) complexity**: greedily
parse the UTF-8 byte string into distinct phrases (each the shortest prefix
not yet seen), and report ``n_phrases / n_bytes``. It is computed in pure
integer arithmetic, so the result is bit-identical on every conforming
Python, and it is a recognised compressibility / redundancy measure.

Range ``(0, 1]``: ~1.0 for incompressible / highly varied text; lower as
repetition rises (repetitive text reuses phrases, so fewer, longer phrases
cover the same length). ``NaN`` on empty input.

Note: this is a *different measurement* from the former gzip ratio — the
absolute values differ (the discriminative ordering is preserved). Changing
it is a measurement-surface change: bump the instrument version, and treat
any reference calibration of ``compression_ratio`` as stale.
"""
from __future__ import annotations


def compressibility(text: str) -> float:
    """Normalised LZ78 complexity of ``text`` (UTF-8). ``NaN`` if empty."""
    data = text.encode("utf-8")
    n = len(data)
    if n == 0:
        return float("nan")

    seen: set[bytes] = set()
    phrases = 0
    i = 0
    while i < n:
        length = 1
        # shortest prefix starting at i that is not yet a known phrase
        while i + length <= n and data[i:i + length] in seen:
            length += 1
        seen.add(data[i:i + length])
        phrases += 1
        i += length
    return phrases / n
