"""CONTRACT: DetRandom is a bit-identical, auditable SHA-256/CTR stream.

The known-answer vectors below pin the construction itself; the
behavioural tests pin the derived draws (uniform01, randbelow,
indices_with_replacement) to that stream.
"""

from __future__ import annotations

import hashlib

import pytest

from instrument.kernel.detrandom import DetRandom

# These literals are the cross-platform reproducibility pin — if this
# test fails, the PRNG construction changed and every downstream
# bootstrap/study artifact is invalidated.
PIN_SEED = "the-instrument/detrandom/pin"
PIN_U64S = (
    7079523919582980364,
    9532552920833632094,
    5881873631418789854,
    16636436401495354896,
    9844018805995014286,
    12976154071932887969,
    16805457574269763481,
    3084272852147462033,
)
ALT_SEED = "alternate"
ALT_U64S = (
    17629167592125576133,
    14719287567456173103,
    3231650967745058967,
    6296840642611659453,
)


def _reference_u64s(seed: str, count: int) -> list[int]:
    """Independent reconstruction of the spec, bypassing DetRandom."""
    out: list[int] = []
    block_index = 0
    while len(out) < count:
        digest = hashlib.sha256(f"{seed}:{block_index}".encode("utf-8")).digest()
        block_index += 1
        for i in range(0, 32, 8):
            out.append(int.from_bytes(digest[i:i + 8], "big"))
    return out[:count]


def test_known_answer_pin_seed():
    rng = DetRandom(PIN_SEED)
    drawn = [rng.u64() for _ in range(8)]
    assert drawn == list(PIN_U64S)
    assert _reference_u64s(PIN_SEED, 8) == list(PIN_U64S)


def test_known_answer_alternate_seed():
    rng = DetRandom(ALT_SEED)
    drawn = [rng.u64() for _ in range(4)]
    assert drawn == list(ALT_U64S)
    assert _reference_u64s(ALT_SEED, 4) == list(ALT_U64S)


def test_u64_range():
    rng = DetRandom(PIN_SEED)
    for _ in range(100):
        v = rng.u64()
        assert 0 <= v < 2**64


def test_uniform01_in_unit_interval():
    rng = DetRandom(PIN_SEED)
    for _ in range(1000):
        u = rng.uniform01()
        assert 0.0 <= u < 1.0


def test_uniform01_mean_near_half():
    rng = DetRandom(PIN_SEED)
    draws = [rng.uniform01() for _ in range(10_000)]
    m = sum(draws) / len(draws)
    assert 0.45 < m < 0.55


def test_uniform01_matches_pin_construction():
    # uniform01 is (u64 >> 11) * 2**-53 on the same stream.
    rng = DetRandom(PIN_SEED)
    assert rng.uniform01() == (PIN_U64S[0] >> 11) * 2.0**-53


def test_randbelow_bounds():
    rng = DetRandom(PIN_SEED)
    for n in (1, 2, 7, 1000):
        for _ in range(50):
            v = rng.randbelow(n)
            assert 0 <= v < n


def test_randbelow_rejects_nonpositive():
    rng = DetRandom(PIN_SEED)
    with pytest.raises(ValueError):
        rng.randbelow(0)
    with pytest.raises(ValueError):
        rng.randbelow(-3)


def test_distinct_seeds_distinct_streams():
    a = [DetRandom(PIN_SEED).u64() for _ in range(4)]
    b = [DetRandom(ALT_SEED).u64() for _ in range(4)]
    assert a != b


def test_same_seed_identical_streams():
    a = DetRandom(PIN_SEED)
    b = DetRandom(PIN_SEED)
    assert [a.u64() for _ in range(64)] == [b.u64() for _ in range(64)]


def test_indices_with_replacement():
    rng = DetRandom(PIN_SEED)
    idx = rng.indices_with_replacement(10, 25)
    assert len(idx) == 25
    assert all(0 <= i < 10 for i in idx)
    # Deterministic: a fresh instance with the same seed reproduces it.
    assert DetRandom(PIN_SEED).indices_with_replacement(10, 25) == idx


def test_indices_with_replacement_rejects_bad_args():
    rng = DetRandom(PIN_SEED)
    with pytest.raises(ValueError):
        rng.indices_with_replacement(0, 5)
    with pytest.raises(ValueError):
        rng.indices_with_replacement(10, -1)
