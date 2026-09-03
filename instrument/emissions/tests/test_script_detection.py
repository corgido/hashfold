"""CONTRACT: non-Latin input fails loudly, never silently (D5, 0.9.1).

The instrument measures Latin-script prose ([A-Za-z] tokeniser). A
substantively non-Latin document must say so — `unsupported_script`
as the unprojectable subtype with script counts in evidence — instead
of masquerading as `insufficient_prose`. A mixed document that still
projects carries a `substantive_non_latin_content` soft flag in the
reading so the measured-on-Latin-residue caveat is visible.
"""

from __future__ import annotations

from dataclasses import asdict

from instrument.emit import emit
from instrument.emissions.structural_profile import profile
from instrument.reading.joint import joint_reading

_CYRILLIC_PARA = (
    "Комитет подробно рассмотрел предложение на весенней сессии. "
    "Несколько участников высказали замечания по срокам работы, но "
    "председатель заявил, что план выполним в рамках бюджета. После "
    "долгого обсуждения предложение было принято большинством голосов.\n\n"
)
_ENGLISH_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)


def test_cyrillic_document_profiles_as_unsupported_script():
    prof = profile(_CYRILLIC_PARA * 8)
    assert prof.subtype == "unsupported_script"
    assert prof.n_nonlatin_letters > prof.n_latin_letters


def test_cyrillic_document_emits_loud_unprojectable():
    d = asdict(emit(_CYRILLIC_PARA * 8))
    assert d["register"]["label"] == "unprojectable"
    ev = d["register"]["evidence"]
    assert ev["unprojectable_subtype"] == "unsupported_script"
    sp = ev["structural_profile"]
    assert sp["n_nonlatin_letters"] > 0
    assert sp["nonlatin_ratio"] > 0.5


def test_mixed_document_that_projects_carries_soft_flag():
    text = _ENGLISH_PARA * 8 + _CYRILLIC_PARA * 2
    jr = joint_reading(text)
    assert "substantive_non_latin_content" in jr["soft_flags"]
    # It still measures (the Latin residue clears the envelope).
    assert jr["n_words"]["shaper"] >= 150


def test_pure_english_has_no_script_flag():
    jr = joint_reading(_ENGLISH_PARA * 8)
    assert "substantive_non_latin_content" not in jr["soft_flags"]


def test_short_gibberish_is_still_insufficient_prose():
    # No substantive non-Latin content -> the old subtype taxonomy holds.
    prof = profile("just a few words")
    assert prof.subtype == "insufficient_prose"
