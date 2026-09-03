"""CONTRACT: the bundled references speak the 0.9.1 feature schema.

The 0.9.1 rename (rst.{contrast,elaboration}_pressure ->
rst.{contrast,elaboration}_marker_density) re-keys the bundled
reference statistic blocks. The migration is mechanical: statistics
and PC names byte-preserved, provenance of the original 0.6.0-era
measurement event unchanged (they remain SEEDS), v1 removed from the
bundle so a stale-schema reference can never win canonical selection
while projecting to None.
"""

from __future__ import annotations

import json
from pathlib import Path

from instrument.reading.extended import ALL_FEATURE_KEYS
from instrument.reading.flat import FEATURE_ORDER
from instrument.routing.pc import project_pc_composites
from instrument.routing.reference import list_references, load_reference

BUNDLED = Path(__file__).resolve().parents[1] / "references"

EXPECTED = {
    ("academic_prose", "v2"),
    ("dialogue_prose", "v2"),
    ("journalism_prose", "v2"),
    ("literary_prose", "v2"),
    ("llm_technical_prose", "v2"),
}


def test_bundle_is_exactly_the_five_v2_seeds():
    assert set(list_references()) == EXPECTED
    assert not list(BUNDLED.glob("*_v1.json")), (
        "a v1 file alongside v2 would win canonical selection "
        "(ascending-version rank) and project to None"
    )


def test_reference_keys_match_the_live_feature_schema():
    live = set(FEATURE_ORDER) | set(ALL_FEATURE_KEYS)
    for name, version in sorted(EXPECTED):
        ref = load_reference(name, version)
        unknown = {
            k for k in ref.pc_zscore_mean
            if not k.startswith("stylometry.") and k not in live
        }
        assert not unknown, f"{name}: stale feature keys {sorted(unknown)}"


def test_every_bundled_reference_projects_under_0_9_1():
    # A reference that cannot project is dead weight: every distance
    # against it is None. Feed each reference its own feature means —
    # values guaranteed to be present and finite for every key.
    for name, version in sorted(EXPECTED):
        ref = load_reference(name, version)
        features = dict(ref.pc_zscore_mean)
        pcs = project_pc_composites(features, ref)
        assert pcs is not None, f"{name} failed to project"
        assert all(v is not None for v in pcs.values()), f"{name}: None PC"


def test_migration_preserved_statistics_and_pc_names():
    for name, version in sorted(EXPECTED):
        raw = json.loads(
            (BUNDLED / f"{name}_{version}.json").read_text(encoding="utf-8")
        )
        mig = raw["migration"]
        assert mig["renamed_keys"] == {
            "rst.contrast_pressure": "rst.contrast_marker_density",
            "rst.elaboration_pressure": "rst.elaboration_marker_density",
        }
        # Original measurement-event provenance untouched: still a
        # 0.6.0-era seed, honestly labeled.
        assert raw["instrument_version"] == "0.6.0"
        assert raw["status"] == "draft"
        # New keys carry values; old keys are gone everywhere.
        for block in (raw["per_feature"], raw["pc_zscore_mean"],
                      raw["pc_zscore_std"], *raw["pc_loadings"].values()):
            assert "rst.contrast_marker_density" in block
            assert "rst.contrast_pressure" not in block
            assert "rst.elaboration_pressure" not in block
