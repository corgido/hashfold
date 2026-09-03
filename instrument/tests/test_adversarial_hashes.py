"""CONTRACT: the hashes survive adversarial testing (0.9.1).

The named suite whose explicit goal is to move a surfaced number
without moving its attesting hash — and fail. Two invariants:

1. NON-SEMANTIC formatting (newline convention, BOM, trailing
   horizontal whitespace, blank-line run length, U+2019 apostrophe
   form*) moves NO measurement hash — `reading_sha256` and
   `content_sha256` are byte-identical — while `input_sha256`
   honestly moves whenever the raw bytes differ.
2. Any perturbation that moves any surfaced number moves
   `content_sha256` (and `reading_sha256` when the number is in the
   reading) — i.e. there is no input change that shifts a feature,
   trajectory value, or distance while the attesting hashes stay
   fixed. (Stored-record tampering is covered separately by
   test_offline_rehash.)

*U+2019 normalisation changes the cleaned bytes, so byte-level
features (compression ratio) legitimately differ — the apostrophe
case asserts token-level features match, not hash equality
(consistent with the 0.9.0 curly_contractions golden precedent).
"""

from __future__ import annotations

from dataclasses import asdict

from instrument.emit import emit

_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)
_FENCE = "```python\nvalue = compute(1, 2)\n\nresult = value * 3\n```\n\n"
_BASE = _PARA * 4 + _FENCE + _PARA * 4


def _hashes(text: str, raw: bytes | None = None) -> tuple[str, str, str]:
    md = asdict(emit(text, input_bytes=raw))["metadata"]
    return md["input_sha256"], md["reading_sha256"], md["content_sha256"]


BASE_IN, BASE_READ, BASE_CONTENT = _hashes(_BASE, _BASE.encode("utf-8"))

_NON_SEMANTIC_VARIANTS = {
    "crlf": _BASE.replace("\n", "\r\n"),
    "cr_only": _BASE.replace("\n", "\r"),
    "bom": "﻿" + _BASE,
    "trailing_ws": _BASE.replace("\n", "   \n"),
    "blank_run_inflation": _BASE.replace("\n\n", "\n\n\n\n"),
}


def test_non_semantic_formatting_never_moves_measurement_hashes():
    for name, variant in _NON_SEMANTIC_VARIANTS.items():
        raw = variant.encode("utf-8")
        h_in, h_read, h_content = _hashes(variant, raw)
        assert h_read == BASE_READ, f"{name}: reading hash moved"
        assert h_content == BASE_CONTENT, f"{name}: content hash moved"
        # Raw bytes differ, so provenance honestly differs.
        assert h_in != BASE_IN, f"{name}: input hash should move"


def test_semantic_changes_always_move_the_content_hash():
    semantic_variants = {
        # One word changes a feature.
        "word_change": _BASE.replace("clear majority", "narrow majority"),
        # Marker injection moves rst.contrast_marker_density.
        "marker_injection": _BASE + "However, the outcome was contested. ",
        # A new paragraph moves slice boundaries -> trajectory numbers.
        "extra_paragraph": _BASE + _PARA,
        # Fence content change: interior is blanked (measurement
        # invariant) but byte position shifts nothing semantic — moving
        # the fence BOUNDARY however changes cleaned bytes:
        "fence_grows": _BASE.replace(
            _FENCE, "```python\nvalue = compute(1, 2)\n\nx = 9\n\nresult = value * 3\n```\n\n"
        ),
    }
    for name, variant in semantic_variants.items():
        h_in, h_read, h_content = _hashes(variant, variant.encode("utf-8"))
        assert h_content != BASE_CONTENT, f"{name}: content hash failed to move"
        assert h_read != BASE_READ, f"{name}: reading hash failed to move"


def test_fence_interior_edit_is_measurement_invariant_but_input_visible():
    # Editing INSIDE a fence changes what was submitted (input hash)
    # but not what was measured (interiors are blanked line-by-line,
    # line count preserved) — the honest split, stated in SCOPE.md.
    variant = _BASE.replace("result = value * 3", "result = value * 9")
    h_in, h_read, h_content = _hashes(variant, variant.encode("utf-8"))
    assert h_in != BASE_IN
    assert h_read == BASE_READ
    assert h_content == BASE_CONTENT


def test_apostrophe_form_is_token_invariant():
    text = _BASE.replace("the chair argued", "the chair didn't doubt")
    curly = text.replace("didn't", "didn’t")
    ra = asdict(emit(text))
    rb = asdict(emit(curly))
    # Token-level features identical (U+2019 normalised); byte-level
    # compression may differ (3-byte UTF-8), so compare the SFL/RST
    # feature dicts, not the hashes.
    # (Reading isn't returned by emit(); reuse register evidence n_words
    # and the arc values as the token-level witnesses.)
    assert ra["metadata"]["n_words"] == rb["metadata"]["n_words"]
    assert ra["arc"] == rb["arc"]


def test_reproducibility_hash_moves_iff_any_component_moves():
    variant = "﻿" + _BASE  # non-semantic; input bytes differ
    md_base = asdict(emit(_BASE, input_bytes=_BASE.encode()))["metadata"]
    md_var = asdict(
        emit(variant, input_bytes=variant.encode())
    )["metadata"]
    assert md_var["reading_sha256"] == md_base["reading_sha256"]
    # input_sha256 differs -> reproducibility_hash must differ too
    # (it folds the provenance identity).
    assert md_var["input_sha256"] != md_base["input_sha256"]
    assert md_var["reproducibility_hash"] != md_base["reproducibility_hash"]
