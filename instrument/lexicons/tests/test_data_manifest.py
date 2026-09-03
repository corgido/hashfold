"""CONTRACT: the standalone `_data/lexicons/v<N>/manifest.json` matches the
shipped source JSONs.

SECURITY.md directs auditors to this manifest for provenance. It is a
separate artifact from the MANIFEST embedded in the compiled module, so it
can silently drift when a source JSON is edited without regenerating the
manifest. This test makes that drift a CI failure.

If it fails, recompute the per-file `sha256` / `count` and `total_entries`
from the current files and commit the corrected manifest.
"""
from __future__ import annotations

from tools.build_lexicons import check_data_manifest


def test_data_manifest_matches_files() -> None:
    assert check_data_manifest("v1") == 0, (
        "standalone _data manifest drifted from the source JSONs — see "
        "stderr for the mismatching files"
    )
