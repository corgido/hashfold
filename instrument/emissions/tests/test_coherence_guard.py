"""CONTRACT: the coherence band cannot contradict the register layer
(D2, closed in 0.9.1).

Degenerate input (e.g. one word repeated 2000 times) is unprojectable
for the register layer, yet its few measurable convergence axes can
trivially agree — before 0.9.1 the emission read `coherence: high`
next to `register: unprojectable`. The advisory band now degrades to
`unmeasurable` (with a `degraded_reason`) whenever the register
outcome is unprojectable/structural or the reading is below envelope;
the scalar — a true measurement of agreement among measurable axes —
is preserved.
"""

from __future__ import annotations

from dataclasses import asdict

from instrument.emissions.assembler import assemble
from instrument.emissions.catalog import load_catalog
from instrument.emit import emit

_EMPTY_TRAJ = {
    "lexical_novelty": [],
    "sentence_length_variance": [],
    "modal_density": [],
    "negation_density": [],
}


def _agreeing_convergence() -> dict:
    return {
        "axes": {
            "sfl_process_complexity": {"direction": "agree_mid"},
            "rst_contrast": {"direction": "agree_low"},
            "rst_elaboration": {"direction": "agree_mid"},
            "register_modality": {"direction": "agree_mid"},
        },
        "overall": "converge",
    }


def _assemble(register_label: str, *, below_envelope: bool = False):
    return assemble(
        catalog=load_catalog("v2"),
        register_label=register_label,
        register_cohort="whatever",
        register_distance=None,
        register_evidence={"_text": "x", "distances_to_all_references": []},
        trajectory=_EMPTY_TRAJ,
        features={},
        soft_flags=(),
        convergence=_agreeing_convergence(),
        n_words=2000,
        n_sentences=1,
        instrument_version="t",
        schema_version="t",
        reading_below_envelope=below_envelope,
    )


def test_unprojectable_register_degrades_the_band_but_keeps_the_scalar():
    em = _assemble("unprojectable")
    assert em.coherence.value == 1.0
    assert em.coherence.label == "unmeasurable"
    assert em.coherence.evidence["degraded_reason"] == "register_unprojectable"


def test_structural_register_degrades_too():
    em = _assemble("structural")
    assert em.coherence.label == "unmeasurable"
    assert em.coherence.evidence["degraded_reason"] == "register_structural"


def test_below_envelope_reading_degrades():
    em = _assemble("match", below_envelope=True)
    assert em.coherence.label == "unmeasurable"
    assert em.coherence.evidence["degraded_reason"] == "below_envelope"


def test_projectable_register_keeps_its_band():
    em = _assemble("match")
    assert em.coherence.label == "high"
    assert "degraded_reason" not in em.coherence.evidence


def test_end_to_end_degenerate_input_never_bands():
    d = asdict(emit(("spam " * 2000).strip()))
    assert d["register"]["label"] in ("unprojectable", "structural")
    assert d["coherence"]["label"] not in ("high", "moderate", "low")
