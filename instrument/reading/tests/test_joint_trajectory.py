"""CONTRACT: the per-slice trajectory is part of the attested reading
(A-prime, closed in 0.9.1).

SCOPE.md lists the per-slice trajectory streams as part of the
measurement surface, and METROLOGY §4 documents them — so they must be
covered by `reading_sha256` / `content_sha256` and carried by the audit
shape. The joint reading therefore computes and embeds the trajectory
(core-side, deterministic, total on degenerate inputs); the emissions
arc (deltas / per-dimension summaries / slice labels) is a derived
advisory view recomputable from these attested values.
"""

from __future__ import annotations

from instrument.kernel.features.trajectory_features import TRAJECTORY_FEATURES
from instrument.reading.joint import joint_reading

_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)
_DOC = _PARA * 8


def test_reading_carries_the_trajectory_block():
    jr = joint_reading(_DOC)
    traj = jr["trajectory"]
    assert traj["regime"] == "elegant"
    assert isinstance(traj["boundary_level"], str)
    assert traj["n_slices"] >= 1
    assert len(traj["slices"]) == traj["n_slices"]
    for k in TRAJECTORY_FEATURES:
        assert len(traj["features"][k]) == traj["n_slices"]


def test_slice_zero_novelty_serialises_as_null():
    jr = joint_reading(_DOC)
    # quantize() maps the by-design slice-0 NaN to None so the reading
    # remains strict-valid JSON and hashes canonically.
    assert jr["trajectory"]["features"]["lexical_novelty"][0] is None


def test_degenerate_inputs_are_total():
    for text in ("", "   \n\n  ", "one", "```\ncode only\n", "word " * 10):
        jr = joint_reading(text)
        traj = jr["trajectory"]
        assert traj["n_slices"] >= 1
        for k in TRAJECTORY_FEATURES:
            assert len(traj["features"][k]) == traj["n_slices"]


def test_trajectory_is_newline_convention_invariant():
    lf = joint_reading(_DOC)
    crlf = joint_reading(_DOC.replace("\n", "\r\n"))
    assert lf["trajectory"] == crlf["trajectory"]
