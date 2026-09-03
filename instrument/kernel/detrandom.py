"""detrandom — deterministic counter-mode PRNG (SHA-256/CTR).

Why not ``random.Random``: CPython guarantees cross-version stream
reproducibility only for ``random()`` itself — the distribution and
sequence methods (``shuffle``, ``choices``, ``randrange``, ...) are
explicitly allowed to change between versions, and have. This
instrument's CI proves byte-identical output across 3 OSes x
CPython 3.11-3.14 x musl x locales, so any randomness feeding an
emitted artifact must come from a construction that is bit-identical
everywhere and auditable from first principles: SHA-256 in counter
mode. The stream is a pure function of the seed string, so any
bootstrap or study built on it can be replayed byte-for-byte on any
conforming host.

Construction: block ``i`` is ``sha256(f"{seed}:{i}")``; each 32-byte
block yields four big-endian u64s, consumed in order; blocks are
consumed in counter order starting at 0. Everything downstream of
``u64()`` is integer arithmetic (the one float, ``uniform01``, is an
exact IEEE-754 operation), so no libm variance can enter the stream.
"""

from __future__ import annotations

import hashlib

_U64_LIMIT = 2**64  # draws are uniform on [0, 2**64)


class DetRandom:
    """Deterministic PRNG: SHA-256 in counter mode over a seed string.

    Not cryptographically secure in the keyed sense (the seed is not
    secret) — the point is determinism and auditability, not secrecy.
    """

    def __init__(self, seed: str) -> None:
        self._seed = seed
        self._counter = 0          # next block index to hash
        self._block: tuple[int, ...] = ()  # u64s of the current block
        self._offset = 0           # next unconsumed u64 within _block

    def u64(self) -> int:
        """Next raw draw: uniform integer in [0, 2**64)."""
        if self._offset >= len(self._block):
            digest = hashlib.sha256(
                f"{self._seed}:{self._counter}".encode("utf-8")
            ).digest()
            self._counter += 1
            self._block = tuple(
                int.from_bytes(digest[i:i + 8], "big") for i in range(0, 32, 8)
            )
            self._offset = 0
        value = self._block[self._offset]
        self._offset += 1
        return value

    def uniform01(self) -> float:
        """Uniform float in [0, 1) with 53 random bits.

        ``(u64 >> 11) * 2.0**-53`` is exact in IEEE-754 (a 53-bit
        integer scaled by a power of two), so the result is
        bit-identical on every conforming host.
        """
        return (self.u64() >> 11) * 2.0**-53

    def randbelow(self, n: int) -> int:
        """Unbiased uniform integer in [0, n) via rejection sampling.

        Draws u64s until one falls below the largest multiple of ``n``
        that fits in 64 bits, then reduces mod ``n``. Rejection (not
        plain modulo) keeps the distribution exactly uniform; the
        rejection probability is < 2**-32 for any realistic ``n``, so
        the expected cost is one draw.
        """
        if n <= 0:
            raise ValueError(f"randbelow requires n >= 1, got {n}")
        limit = (_U64_LIMIT // n) * n
        while True:
            draw = self.u64()
            if draw < limit:
                return draw % n

    def indices_with_replacement(self, n: int, k: int) -> list[int]:
        """k independent uniform indices in [0, n) (bootstrap resample)."""
        if k < 0:
            raise ValueError(f"indices_with_replacement requires k >= 0, got {k}")
        if n <= 0:
            raise ValueError(f"indices_with_replacement requires n >= 1, got {n}")
        return [self.randbelow(n) for _ in range(k)]
