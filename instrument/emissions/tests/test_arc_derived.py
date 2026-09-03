"""CONTRACT: the arc emission is a derived-advisory view, recomputable
from the attested reading.trajectory (0.9.1, A-prime).

`reading.trajectory.features` is hash-attested (content/reading sha).
The arc's per-slice values, deltas, and per-dimension summaries are
pure arithmetic over those attested values — so an input perturbation
cannot move any arc number without moving the attesting hashes, and an
auditor can recompute the arc offline from the audit record.
"""

from __future__ import annotations

from dataclasses import asdict

from instrument.emissions.assembler import _assemble_arc
from instrument.emissions.catalog import load_catalog
from instrument.emit import emit_with_reading
from instrument.kernel.quantize import q, quantize

_PARA = (
    "The committee reviewed the proposal in detail during the spring "
    "session. Several members raised concerns about the timeline and "
    "the chair argued that the schedule was achievable within budget. "
    "After a long discussion the vote passed with a clear majority.\n\n"
)
_DOC = _PARA * 8


def test_arc_recomputable_from_attested_trajectory():
    emission, jr = emit_with_reading(_DOC)
    catalog = load_catalog("v2")
    rebuilt = _assemble_arc(quantize(jr["trajectory"]["features"]), catalog)
    assert asdict(rebuilt) == asdict(emission.arc)


def test_quantize_is_idempotent_on_emitted_values():
    emission, jr = emit_with_reading(_DOC)
    feats = jr["trajectory"]["features"]
    for series in feats.values():
        for v in series:
            assert q(q(v)) == q(v)
    # The whole reading is stable under a second quantize pass (the
    # assembler re-quantizes the trajectory it receives).
    assert quantize(jr) == jr
