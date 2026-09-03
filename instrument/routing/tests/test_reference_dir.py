"""CONTRACTS for user references — the supported calibration path.

Covers: registering an external reference directory, precedence
(user file with the same stem replaces the bundled one),
boot-time validation (`ReferenceLoadError` on malformed JSON), and
the builder tool producing a reference the runtime can route
against (hint routing + presence in the distance records).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from instrument.errors import ReferenceLoadError
from instrument.routing.reference import (
    list_references,
    load_reference,
    set_reference_dir,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
BUNDLED = REPO_ROOT / "instrument" / "routing" / "references"


@pytest.fixture(autouse=True)
def _clean_registry():
    """Every test starts and ends with no user directory."""
    set_reference_dir(None)
    yield
    set_reference_dir(None)


def _customer_ref(tmp_path: Path, name: str, version: str = "v1",
                  cohort: str | None = None) -> Path:
    """Derive a valid user reference from a bundled one."""
    src = json.loads(
        (BUNDLED / "llm_technical_prose_v2.json").read_text(encoding="utf-8"))
    src["name"] = name
    src["version"] = version
    src["register_cohort"] = cohort or name
    out = tmp_path / f"{name}_{version}.json"
    out.write_text(json.dumps(src), encoding="utf-8")
    return out


def test_set_reference_dir_adds_and_clears(tmp_path):
    base = set(list_references())
    _customer_ref(tmp_path, "acme_normal")
    found = set_reference_dir(tmp_path)
    assert ("acme_normal", "v1") in found
    assert set(list_references()) == base | {("acme_normal", "v1")}
    ref = load_reference("acme_normal", "v1")
    assert ref.register_cohort == "acme_normal"
    set_reference_dir(None)
    assert set(list_references()) == base


def test_customer_file_with_same_stem_overrides_bundled(tmp_path):
    path = _customer_ref(tmp_path, "llm_technical_prose", "v2",
                         cohort="llm_technical_prose")
    data = json.loads(path.read_text())
    data["corpus_description"] = "CUSTOMER OVERRIDE"
    path.write_text(json.dumps(data), encoding="utf-8")
    set_reference_dir(tmp_path)
    assert load_reference("llm_technical_prose", "v2").corpus_description\
        == "CUSTOMER OVERRIDE"
    set_reference_dir(None)
    assert load_reference("llm_technical_prose", "v2").corpus_description\
        != "CUSTOMER OVERRIDE"


def test_malformed_reference_fails_at_registration(tmp_path):
    (tmp_path / "broken_v1.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ReferenceLoadError):
        set_reference_dir(tmp_path)


def test_missing_required_field_fails_at_registration(tmp_path):
    path = _customer_ref(tmp_path, "incomplete")
    data = json.loads(path.read_text())
    del data["pc_loadings"]
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ReferenceLoadError):
        set_reference_dir(tmp_path)


def test_missing_directory_raises():
    with pytest.raises(ReferenceLoadError):
        set_reference_dir("/nonexistent/refs")


def test_builder_output_routes_end_to_end(tmp_path):
    """tools/build_reference on a small corpus -> register -> hint-route."""
    from tools.build_reference import main as build_main

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for name in ("academic_short.md", "dialogue.md", "journalism.md",
                 "literary.md", "llm_technical.md", "discourse_heavy.md",
                 "contraction_heavy.md", "academic_long.md"):
        shutil.copy(REPO_ROOT / "fixtures" / "source" / name, corpus / name)

    refs_dir = tmp_path / "refs"
    rc = build_main([
        "--corpus-dir", str(corpus),
        "--name", "test_customer_baseline",
        "--cohort", "test_customer_baseline",
        "--scope", "in-test corpus",
        "--collection-window", "repo fixtures (static)",
        "--out", str(refs_dir),
    ])
    assert rc == 0
    set_reference_dir(refs_dir)

    from instrument.emit import emit
    text = (REPO_ROOT / "fixtures" / "source" / "llm_technical.md").read_text()
    em = emit(text, register_hint="test_customer_baseline")
    assert em.register.cohort == "test_customer_baseline"
    assert em.register.distance is not None
    names = {r["name"]
             for r in em.register.evidence["distances_to_all_references"]}
    assert "test_customer_baseline" in names
    assert "llm_technical_prose" in names  # bundled set still present
