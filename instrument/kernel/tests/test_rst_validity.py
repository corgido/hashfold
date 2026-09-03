"""CONTRACT: monotonic-perturbation validity for the renamed RST
marker-density features (0.9.1).

The discriminant study showed these features measure sentence-initial
*marker density*, not rhetorical structure — hence the 0.9.1 rename.
The validity bar that matters for a relative-to-baseline instrument is
sensitivity: injecting contrast/elaboration markers into a text must
move the corresponding density monotonically up; removing them moves
it down. (Criterion validity against human RST annotation is
explicitly out of scope — see SCOPE.md.)
"""

from __future__ import annotations

from instrument.kernel.features.rst import rst_compact
from instrument.kernel.tokens import tokenise

_PLAIN = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members studied the timeline carefully. The "
    "chair explained the schedule to the group. The vote took place "
    "after a long discussion. The proposal passed with a clear "
    "majority. The working group started the project immediately. "
)


def _densities(text: str) -> dict:
    return rst_compact(tokenise(text))


def _with_contrast_markers(n: int) -> str:
    base = _PLAIN * 6
    injected = "However, the results were mixed. " * n
    return base + injected


def _with_elaboration_markers(n: int) -> str:
    base = _PLAIN * 6
    injected = "Specifically, the plan named three separate milestones for the team. " * n
    return base + injected


def test_contrast_marker_density_responds_monotonically():
    values = [
        _densities(_with_contrast_markers(n))["contrast_marker_density"]
        for n in (0, 2, 4, 8)
    ]
    assert all(b > a for a, b in zip(values, values[1:])), values


def test_elaboration_marker_density_responds_monotonically():
    values = [
        _densities(_with_elaboration_markers(n))["elaboration_marker_density"]
        for n in (0, 2, 4, 8)
    ]
    assert all(b > a for a, b in zip(values, values[1:])), values


def test_removing_markers_lowers_the_density():
    with_markers = _with_contrast_markers(6)
    without = with_markers.replace("However, the results were mixed. ", "")
    d_with = _densities(with_markers)["contrast_marker_density"]
    d_without = _densities(without)["contrast_marker_density"]
    assert d_with > d_without


def test_renamed_keys_are_the_only_rst_compact_keys():
    d = _densities(_PLAIN * 6)
    assert "contrast_marker_density" in d
    assert "elaboration_marker_density" in d
    assert "contrast_pressure" not in d
    assert "elaboration_pressure" not in d
