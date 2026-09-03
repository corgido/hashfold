"""CONTRACTS for the 0.10.0 reference builder — honest null + stability.

Exercises `tools.build_reference` end to end on a deterministic
synthetic mini-corpus (15 documents built from rotated fixture
sentences — big enough for the 10-fold cross-validated null, small
enough to keep the suite fast):

  * two builds with a pinned `--calibration-date` are byte-identical
    (the stamp is the only nondeterministic byte on a fixed host);
  * the persisted `self_distance` carries the full sorted null with
    `basis=cross_validated_10fold`, and median/p95 are computed from
    the pooled CV values (not the resubstitution ones);
  * stability / provenance / recalibration_policy / collection_window
    / per_feature_quantiles blocks are present and well-formed;
  * `--no-cv` and a sub-10-document corpus both fall back to
    `basis=resubstitution`;
  * the output round-trips through the runtime loader.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from instrument.kernel.tokens import tokenise, word_tokens
from instrument.routing.types import reference_from_dict
from tools.build_reference import main as build_main

REPO_ROOT = Path(__file__).resolve().parents[3]

_N_DOCS = 15
_MIN_DOC_WORDS = 170  # comfortably over the builder's 150-word floor


def _sentence_pools() -> list[list[str]]:
    journalism = list(
        tokenise((REPO_ROOT / "fixtures" / "source" / "journalism.md")
                 .read_text(encoding="utf-8")).sentences)
    literary = list(
        tokenise((REPO_ROOT / "fixtures" / "source" / "literary.md")
                 .read_text(encoding="utf-8")).sentences)
    mixed = [s for pair in zip(journalism, literary) for s in pair]
    return [journalism, literary, mixed]


def _synth_doc(i: int, pools: list[list[str]]) -> str:
    """Deterministic pseudo-document i: rotated fixture sentences.

    Pool choice (i mod 3) and rotation offset (7·i) vary the register
    mix and sentence order doc to doc, so the corpus has real
    feature variance while staying a pure function of the fixture
    bytes and i.
    """
    pool = pools[i % len(pools)]
    start = (7 * i) % len(pool)
    out: list[str] = []
    words = 0
    k = 0
    while words < _MIN_DOC_WORDS:
        s = pool[(start + k) % len(pool)]
        out.append(s)
        words += len(word_tokens(s))
        k += 1
    # Paragraph break every 4 sentences: the docs measure as prose.
    paras = [" ".join(out[j:j + 4]) for j in range(0, len(out), 4)]
    return "\n\n".join(paras)


@pytest.fixture(scope="module")
def mini_corpus(tmp_path_factory) -> Path:
    root = tmp_path_factory.mktemp("mini_corpus")
    pools = _sentence_pools()
    for i in range(_N_DOCS):
        (root / f"doc_{i:02d}.md").write_text(
            _synth_doc(i, pools) + "\n", encoding="utf-8")
    return root


def _build(corpus: Path, out_dir: Path, *extra: str) -> Path:
    rc = build_main([
        "--corpus-dir", str(corpus),
        "--name", "mini", "--version", "v1", "--cohort", "mini",
        "--scope", "in-test synthetic mini-corpus",
        "--collection-window", "synthetic (in-test)",
        "--calibration-date", "2026-07-09T00:00:00Z",
        "--out", str(out_dir),
        *extra,
    ])
    assert rc == 0
    return out_dir / "mini_v1.json"


def test_build_is_byte_identical_with_pinned_date(mini_corpus, tmp_path):
    a = _build(mini_corpus, tmp_path / "a")
    b = _build(mini_corpus, tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()


def test_null_is_cross_validated_sorted_and_self_consistent(
        mini_corpus, tmp_path):
    ref = json.loads(_build(mini_corpus, tmp_path / "out").read_text())
    sd = ref["self_distance"]
    assert sd["basis"] == "cross_validated_10fold"
    assert sd["n"] == _N_DOCS
    assert len(sd["values"]) == _N_DOCS
    assert sd["values"] == sorted(sd["values"])
    # median/p95 come from the pooled CV values (quantized after the
    # percentile, so compare in q-space via the persisted numbers).
    assert sd["values"][0] <= sd["median"] <= sd["values"][-1]
    assert sd["p95"] <= sd["values"][-1]
    assert all(v >= 0.0 for v in sd["values"])

    # Provenance blocks.
    assert ref["collection_window"] == "synthetic (in-test)"
    prov = ref["provenance"]
    assert prov["tool"] == "tools.build_reference"
    assert prov["n_files_measured"] == _N_DOCS
    assert prov["n_kept"] == _N_DOCS
    assert isinstance(prov["dropped_features"], list)
    policy = ref["recalibration_policy"]
    assert policy["max_age_days"] == 180
    assert "baseline_age_exceeds_max" in policy["triggers"]
    assert policy["policy_version"] == "1"

    # Stability block from the reused fold fits.
    st = ref["stability"]
    assert st["method"] == "delete_block_jackknife"
    assert st["d_fraction"] == 0.1
    assert 1 <= st["n_replicates"] <= 10
    for pc_stats in st["centroid_shift_std_units"].values():
        assert pc_stats["mean"] <= pc_stats["max"]
    for pc_stats in st["loading_alignment_abs_cos"].values():
        assert 0.0 <= pc_stats["min"] <= pc_stats["mean"] <= 1.0
    lo, hi = st["self_p95_replicate_range"]
    assert lo <= hi

    # Per-feature percentile grids: 101 monotone points per kept feature.
    grids = ref["per_feature_quantiles"]
    assert set(grids) == set(ref["per_feature"])
    for grid in grids.values():
        assert len(grid) == 101
        assert grid == sorted(grid)

    # And the whole thing round-trips through the runtime loader.
    typed = reference_from_dict(ref)
    assert typed.self_distance.values == tuple(sd["values"])
    assert typed.stability["n_replicates"] == st["n_replicates"]


def test_no_cv_forces_resubstitution(mini_corpus, tmp_path):
    ref = json.loads(
        _build(mini_corpus, tmp_path / "out", "--no-cv").read_text())
    assert ref["self_distance"]["basis"] == "resubstitution"
    assert len(ref["self_distance"]["values"]) == _N_DOCS
    # No fold fits -> no stability block.
    assert "stability" not in ref


def test_small_corpus_falls_back_to_resubstitution(mini_corpus, tmp_path):
    small = tmp_path / "small"
    small.mkdir()
    for i, src in enumerate(sorted(mini_corpus.glob("*.md"))[:8]):
        (small / src.name).write_text(
            src.read_text(encoding="utf-8"), encoding="utf-8")
    ref = json.loads(_build(small, tmp_path / "out").read_text())
    assert ref["self_distance"]["basis"] == "resubstitution"
    assert ref["self_distance"]["n"] == 8
    assert "stability" not in ref


def test_skip_flags_drop_their_blocks(mini_corpus, tmp_path):
    ref = json.loads(_build(
        mini_corpus, tmp_path / "out",
        "--no-stability", "--no-feature-quantiles").read_text())
    assert "stability" not in ref
    assert "per_feature_quantiles" not in ref
    assert ref["self_distance"]["basis"] == "cross_validated_10fold"
