"""quantize — deterministic float canonicalisation for the record.

The measurement path uses libm-delegated transcendentals (``math.log2``,
``math.log1p``) whose last-ULP results are not guaranteed bit-identical
across C libraries / CPUs. IEEE-754 mandates correct rounding for ``+``,
``-``, ``*``, ``/`` and ``sqrt`` (those are portable), but not for ``log``
or ``pow``. Two conforming hosts can therefore differ in the 15th-16th
significant figure, which is enough to break a byte-for-byte record
comparison.

Quantising every emitted float to a fixed number of *significant figures*
collapses that sub-significance noise while preserving all real signal:
drift was observed at sig fig 15-16; 12 sig figs leaves several digits of
margin and is far below any measurement significance here (densities are
per-100/-1000; entropies < ~13). Significant figures (``g`` format), not
decimal places, because emitted magnitudes span ~0.01 to ~10000.

``canonical_json`` produces the byte-stable serialisation used both for the
golden comparison and for the content hash in
``emissions.assembler``: sorted keys, compact separators, quantised floats,
tuples normalised to lists.
"""
from __future__ import annotations

import json
import math
from typing import Any

SIG_FIGS = 12


def q(x: Any) -> Any:
    """Quantise a single value. Non-floats pass through unchanged."""
    if isinstance(x, bool) or not isinstance(x, float):
        return x  # ints, bools, None, str pass through untouched
    if x != x or math.isinf(x):
        return None  # non-finite (NaN/inf) -> JSON null; valid JSON, and the
        # "not measurable" meaning is carried by the below_envelope flag
    y = float(f"{x:.{SIG_FIGS}g}")
    return 0.0 if y == 0.0 else y  # normalise -0.0 -> 0.0


def quantize(obj: Any) -> Any:
    """Recursively quantise every float in a nested structure.

    dict / list / tuple are walked; tuples become lists so the result is
    JSON-canonical. Every other scalar is passed through ``q``.
    """
    if isinstance(obj, dict):
        return {k: quantize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [quantize(v) for v in obj]
    return q(obj)


def canonical_json(obj: Any) -> str:
    """Byte-stable JSON of an (already-quantised or to-be-quantised) object.

    Quantises first so the serialisation is portable, then dumps with sorted
    keys and compact separators. ``q`` maps non-finite floats (NaN/inf) to
    ``None`` so the output is always valid JSON; ``allow_nan=False`` then acts
    as a guard that raises if any non-finite value somehow survives.
    """
    return json.dumps(
        quantize(obj),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
