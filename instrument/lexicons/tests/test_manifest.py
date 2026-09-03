"""CONTRACT: the generated MANIFEST mirrors LEXICONS and the source SHA-256s."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from instrument.lexicons import LEXICONS, MANIFEST

LEXICON_SOURCE = Path(__file__).resolve().parents[3] / "_data" / "lexicons" / "v1"


def test_manifest_keys_match_lexicons_keys():
    assert set(MANIFEST.keys()) == set(LEXICONS.keys())


def test_manifest_counts_match_lexicons_sizes():
    for key, entry in MANIFEST.items():
        assert entry["count"] == len(LEXICONS[key]), key


def test_manifest_sha_matches_source_json():
    for key, entry in MANIFEST.items():
        rel = key.replace("_", "/", 1) + ".json"
        src = LEXICON_SOURCE / rel
        assert src.exists(), f"source JSON missing for {key}: {src}"
        actual = hashlib.sha256(src.read_bytes()).hexdigest()
        assert actual == entry["sha256"], (
            f"{key}: sha drift — regenerate with build_lexicons --version v1"
        )


def test_manifest_counts_match_source_json():
    for key, entry in MANIFEST.items():
        rel = key.replace("_", "/", 1) + ".json"
        src = LEXICON_SOURCE / rel
        data = json.loads(src.read_text(encoding="utf-8"))
        assert entry["count"] == data["count"], key
