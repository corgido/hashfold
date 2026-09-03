"""CONTRACT: per-slice trajectory measures the same input class as the
document-level features (FENCE-LEAK, closed in 0.9.1).

Slices are cut from the document-level CLEANED text (fence interiors
already blanked, frontmatter already stripped), so no slice boundary
can ever fall "inside" a fence and resurrect its content as prose.
Before 0.9.1 the slicer cut the raw text and each slice was re-cleaned
independently: a fenced block spanning a slice boundary looked like an
unclosed fence in both halves and was restored as prose, contaminating
`variance_spike` / `novelty_reopen` and the per-slice densities.
"""

from __future__ import annotations

from instrument.kernel.features.trajectory_features import (
    TRAJECTORY_FEATURES,
    read_trajectory,
)
from instrument.kernel.regimes import regime_elegant
from instrument.kernel.tokens import tokenise, word_tokens

# Prose with ZERO modals and ZERO negations; the fence interior is
# stuffed with both plus blank lines, so under the pre-0.9.1 slicer a
# cut inside the fence leaks them into some slice's densities.
_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)
_FENCE_BODY = (
    "should_flag = must not never cannot wouldnt shouldnt\n"
    "\n"
    "must_check = should would could might never none nothing\n"
    "\n"
    "zqxvbank_identifier_alpha = anti_theme_token_omega\n"
    "\n"
) * 8
_DOC = (
    _PARA * 5
    + "```python\n" + _FENCE_BODY + "```\n\n"
    + _PARA * 5
)


def _trajectory(text: str):
    tokens = tokenise(text)
    elegant = regime_elegant(tokens.cleaned)
    return tokens, elegant, read_trajectory(tokens, elegant["slices"])


def test_fence_content_never_leaks_into_any_slice():
    tokens, elegant, traj = _trajectory(_DOC)
    assert elegant["n_slices"] >= 2, "document must actually slice"
    # The fence is the only source of modals/negations in the document.
    assert all(v == 0.0 for v in traj["modal_density"]), traj["modal_density"]
    assert all(v == 0.0 for v in traj["negation_density"]), (
        traj["negation_density"]
    )


def test_per_slice_streams_reassemble_the_document_cleaned_stream():
    tokens, elegant, _ = _trajectory(_DOC)
    reassembled: list[str] = []
    for start, end in elegant["slices"]:
        reassembled.extend(word_tokens(tokens.cleaned[start:end]))
    assert tuple(reassembled) == tokens.words


def test_slice_starting_at_thematic_break_is_not_frontmatter_stripped():
    # A mid-document thematic-break pair looks like YAML frontmatter to a
    # per-slice re-clean. The words between the breaks are real prose and
    # must be measured. (Latent bug in the pre-0.9.1 per-slice clean().)
    text = (
        _PARA
        + "---\nthe answer should never come easily\n---\n\n"
        + _PARA
    )
    tokens = tokenise(text)
    break_start = tokens.cleaned.index("---")
    slices = [(0, break_start), (break_start, len(tokens.cleaned))]
    traj = read_trajectory(tokens, slices)
    # "should" and "never" live only inside the thematic-break span.
    assert traj["modal_density"][1] > 0.0
    assert traj["negation_density"][1] > 0.0


def test_all_four_streams_have_one_value_per_slice():
    _, elegant, traj = _trajectory(_DOC)
    for k in TRAJECTORY_FEATURES:
        assert len(traj[k]) == len(elegant["slices"])
