"""CONTRACTS for PC projection."""

from __future__ import annotations

from pathlib import Path

import pytest

from instrument.reading.joint import joint_reading
from instrument.routing.pc import project_pc_composites
from instrument.routing.reference import load_reference


REPO_ROOT = Path(__file__).resolve().parents[3]


def _features_from_joint(text: str) -> dict:
    """Flatten a joint reading's feature blocks into one dict."""
    jr = joint_reading(text)
    out: dict = {}
    out.update(jr["shaper"]["features"])
    out.update(jr["other_shaper"]["features"])
    out.update(jr.get("stylometry", {}).get("features", {}))
    return out


@pytest.fixture(scope="module")
def llm_ref():
    return load_reference("llm_technical_prose", "v2")


def test_project_pc_returns_all_pc_axes(llm_ref):
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text()
    features = _features_from_joint(text)
    pcs = project_pc_composites(features, llm_ref)
    assert set(pcs.keys()) == set(llm_ref.pc_loadings.keys())


def test_project_pc_nan_feature_contaminates(llm_ref):
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text()
    features = _features_from_joint(text)
    features["sfl.process_proxy_entropy"] = float("nan")
    pcs = project_pc_composites(features, llm_ref)
    assert all(v is None for v in pcs.values())
