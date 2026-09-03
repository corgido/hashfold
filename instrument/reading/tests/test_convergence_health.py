"""Behavioral: post-bugfix convergence on known-good prose."""
from __future__ import annotations

from pathlib import Path

from instrument.reading.joint import joint_reading

_FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "source"


def test_academic_prose_does_not_fully_diverge():
    text = (_FIXTURES / "academic_long.md").read_text()
    jr = joint_reading(text)
    conv = jr["convergence"]
    assert conv["overall"] != "diverge"
    assert conv["n_axes_agree"] >= 2


def test_discourse_heavy_produces_rst_agreement():
    text = (_FIXTURES / "discourse_heavy.md").read_text()
    jr = joint_reading(text)
    conv = jr["convergence"]
    assert conv["n_axes_agree"] >= 1
