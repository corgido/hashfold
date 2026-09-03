"""CONTRACT: every float in a DocumentEmission is quantised.

P0-1 makes the record portable by quantising emitted floats to 12 sig figs.
This guards *coverage*: not just the reading, but the arc (derived slopes /
ranges / deltas) and flag evidence — anything that ends up in a response
shape. A future detector that emits a raw float will trip this.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from pathlib import Path

from instrument.emit import emit
from instrument.kernel.quantize import q

_FIXTURES = sorted((Path(__file__).resolve().parents[3] / "fixtures" / "source").glob("*.md"))


def _floats(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _floats(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from _floats(v, f"{path}[{i}]")
    elif isinstance(obj, float) and not math.isnan(obj):
        yield path, obj


def test_every_emission_float_is_quantized():
    offenders: list[str] = []
    for f in _FIXTURES:
        em = asdict(emit(f.read_text(encoding="utf-8")))
        for path, v in _floats(em):
            if q(v) != v:
                offenders.append(f"{f.name}{path} = {v!r}")
    assert not offenders, "unquantised emitted floats:\n" + "\n".join(offenders[:20])
