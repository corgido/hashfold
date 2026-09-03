"""CONTRACTS for the deterministic sentence bootstrap.

Pins: byte-identical output on repeated calls (the reproducibility
contract), seed-sensitivity (a different seed draws a different
resample plan), the honest refusal below MIN_SENTENCES, CI-contains-
point sanity, and the paragraph-shape-preserving reassembly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from instrument.kernel.quantize import canonical_json
from instrument.reading.bootstrap import (
    DEFAULT_B,
    MIN_SENTENCES,
    SCHEME,
    _reassemble,
    bootstrap_uncertainty,
)

REPO_ROOT = Path(__file__).resolve().parents[3]

_SEED = "a" * 64  # stand-in input_sha256; any string is a valid seed


@pytest.fixture(scope="module")
def journalism_text() -> str:
    return (REPO_ROOT / "fixtures" / "source" / "journalism.md").read_text(
        encoding="utf-8"
    )


@pytest.fixture(scope="module")
def journalism_block(journalism_text: str) -> dict:
    return bootstrap_uncertainty(journalism_text, seed=_SEED, b=25)


def test_deterministic_across_calls(journalism_text, journalism_block):
    again = bootstrap_uncertainty(journalism_text, seed=_SEED, b=25)
    assert canonical_json(journalism_block) == canonical_json(again)


def test_different_seed_different_resample(journalism_text, journalism_block):
    other = bootstrap_uncertainty(journalism_text, seed="b" * 64, b=25)
    # Same document, same b -> same points; a different seed must draw
    # a different resample plan, so some feature's CI differs.
    assert other["seed"] != journalism_block["seed"]
    differing = [
        k for k, v in journalism_block["features"].items()
        if "ci_low" in v and "ci_low" in other["features"][k]
        and (v["ci_low"], v["ci_high"])
        != (other["features"][k]["ci_low"], other["features"][k]["ci_high"])
    ]
    assert differing, "different seed produced an identical resample"


def test_envelope_fields(journalism_block):
    assert journalism_block["method"] == SCHEME
    assert journalism_block["b"] == 25
    assert journalism_block["seed"] == _SEED
    assert journalism_block["n_sentences"] >= MIN_SENTENCES
    assert journalism_block["features"]


def test_feature_summary_shape(journalism_block):
    for key, summary in journalism_block["features"].items():
        if "status" in summary:
            assert summary["status"] == "unstable_under_resampling"
            assert set(summary) == {"status", "n_finite"}
            continue
        assert set(summary) == {"point", "ci_low", "ci_high", "se", "n_finite"}
        assert summary["ci_low"] <= summary["ci_high"], key
        assert summary["se"] >= 0.0, key
        assert 0 <= summary["n_finite"] <= 25, key


def test_too_few_sentences_refuses():
    out = bootstrap_uncertainty(
        "One sentence here. Then a second one. Finally a third.",
        seed=_SEED,
    )
    assert out == {
        "status": "too_few_sentences_for_bootstrap",
        "n_sentences": 3,
        "method": SCHEME,
    }


def test_ci_contains_point_for_most_features(journalism_block):
    """Sanity, not a theorem: the percentile CI of a sentence bootstrap
    should bracket the unresampled point for the large majority of
    features (skewed small-sample features may legitimately miss)."""
    contained = 0
    total = 0
    for summary in journalism_block["features"].values():
        if "point" not in summary or summary["point"] is None:
            continue
        total += 1
        if summary["ci_low"] <= summary["point"] <= summary["ci_high"]:
            contained += 1
    assert total > 0
    assert contained / total > 0.8, f"{contained}/{total} contained"


def test_default_b_is_200():
    assert DEFAULT_B == 200


def test_bad_b_raises(journalism_text):
    with pytest.raises(ValueError):
        bootstrap_uncertainty(journalism_text, seed=_SEED, b=0)


# ---- _reassemble: the paragraph-shape-preserving rebuild ------------------

def test_reassemble_preserves_paragraph_shape():
    sentences = ("S0.", "S1.", "S2.", "S3.", "S4.")
    # Original shape: paragraph of 2 sentences, then paragraph of 3.
    rebuilt = _reassemble((2, 3), sentences, [4, 4, 0, 2, 1])
    assert rebuilt == "S4. S4.\n\nS0. S2. S1."


def test_reassemble_identity_draw_reproduces_layout():
    sentences = ("A one.", "B two.", "C three.")
    rebuilt = _reassemble((1, 2), sentences, [0, 1, 2])
    assert rebuilt == "A one.\n\nB two. C three."


def test_reassemble_skips_empty_paragraphs():
    rebuilt = _reassemble((2, 0, 1), ("X.", "Y."), [1, 0, 1])
    assert rebuilt == "Y. X.\n\nY."


def test_two_paragraph_text_end_to_end():
    """A real 2-paragraph document: every replicate keeps the original
    paragraph count and sizes, so n_sentences is invariant."""
    para1 = " ".join(f"Alpha sentence number {w} runs here." for w in
                     ("one", "two", "three", "four", "five"))
    para2 = " ".join(f"Beta sentence number {w} follows on." for w in
                     ("six", "seven", "eight", "nine"))
    out = bootstrap_uncertainty(f"{para1}\n\n{para2}\n", seed=_SEED, b=10)
    assert out["n_sentences"] == 9
    assert out["method"] == SCHEME
    assert out["features"]
