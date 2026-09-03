"""CONTRACTS for tools.fixture_corpus — the deterministic fixture split.

The even split calibrates the committed validation reference
(`fixtures/references/fixture_prose_v1.json`); the odd split is the
held-out set for emit-level tests and the validation study. Both
depend on the segmentation being a pure function of the fixture
bytes: same ids, same text, on every host.
"""

from __future__ import annotations

import pytest

from instrument.kernel.tokens import word_tokens
from tools.fixture_corpus import PROSE_FIXTURES, iter_segments, write_split


def test_segments_are_deterministic_and_sorted():
    first = iter_segments()
    second = iter_segments()
    assert first == second
    ids = [sid for sid, _ in first]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids))
    assert {sid.rsplit("_", 1)[0] for sid in ids} == set(PROSE_FIXTURES)


def test_segments_are_around_200_words():
    for sid, text in iter_segments():
        n = len(word_tokens(text))
        # Flush-at-200 with a <100-word tail merged into its
        # predecessor: every segment lands in [100, 400).
        assert 100 <= n < 400, f"{sid}: {n} words"


def test_write_split_partitions_by_parity(tmp_path):
    even = {p.stem for p in write_split(tmp_path / "even", "even")}
    odd = {p.stem for p in write_split(tmp_path / "odd", "odd")}
    assert even.isdisjoint(odd)
    assert even | odd == {sid for sid, _ in iter_segments()}
    assert all(int(s.rsplit("_", 1)[1]) % 2 == 0 for s in even)
    assert all(int(s.rsplit("_", 1)[1]) % 2 == 1 for s in odd)


def test_write_split_rejects_bad_parity(tmp_path):
    with pytest.raises(ValueError):
        write_split(tmp_path, "both")
