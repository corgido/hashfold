"""coherence — fraction of measurable axes where the two views agree.

Turns a joint reading's convergence block into a
`CoherenceEmission` with a scalar in [0, 1] and (optionally) a
catalog-driven label ("high" / "moderate" / "low").

The scalar is `n_axes_agree / n_axes_measurable`. Incomparable
axes (where the shaper value is NaN) are excluded from both
numerator and denominator. Diverging axes are in the denominator
but not the numerator. Axes named in
`reading.convergence.COHERENCE_EXCLUDED_AXES` (0.9.1:
`cohesion_repetition`, a duplicate computation whose agreement is
structurally guaranteed) are excluded from both numerator and
denominator — internal consistency across substantially shared
computation must not read as corroboration.

ADVISORY: the scalar (n_agree / n_measurable) is pure measurement.
The `label` field ("high"/"moderate"/"low") is inference — a
catalog-driven banding of the scalar. Compliance pipelines
should record the scalar; the label is convenience.
"""

from __future__ import annotations

from typing import Optional

from instrument.emissions.catalog import classify_by_min
from instrument.emissions.types import CoherenceEmission
from instrument.reading.convergence import COHERENCE_EXCLUDED_AXES

# Minimum measurable axes (of the 4 coherence-eligible axes) for the
# advisory label to band.
# A VALIDITY floor — refusing to label a vacuous sample — not a
# calibrated threshold; see the gate comment in compute_coherence.
MIN_MEASURABLE_AXES = 3


def compute_coherence(
    convergence: Optional[dict],
    bands: Optional[list] = None,
) -> CoherenceEmission:
    """Derive the CoherenceEmission from a convergence block.

    `bands` is optional; when provided (from the catalog) the
    emission carries a human-readable label alongside the scalar.
    """
    if not convergence:
        return CoherenceEmission(
            value=None,
            label=None,
            n_axes_measurable=0,
            n_axes_agree=0,
            diverging_axes=(),
            incomparable_axes=(),
            evidence={"reason": "no convergence signal"},
        )

    axes = convergence.get("axes") or {}
    diverging: list[str] = []
    incomparable: list[str] = []
    excluded: list[str] = []
    agree_labels: dict[str, str] = {}
    for name, spec in axes.items():
        if name in COHERENCE_EXCLUDED_AXES:
            excluded.append(name)
            continue
        direction = spec.get("direction") if isinstance(spec, dict) else None
        if direction == "diverge":
            diverging.append(name)
        elif direction == "incomparable":
            incomparable.append(name)
        elif direction and direction.startswith("agree_"):
            agree_labels[name] = direction
        else:
            incomparable.append(name)

    n_measurable = len(agree_labels) + len(diverging)
    n_agree = len(agree_labels)
    value = (n_agree / n_measurable) if n_measurable > 0 else None

    # Validity gate, not calibration: with fewer than a majority of
    # the five axes measurable, the agree-fraction is statistically
    # vacuous (a below-envelope or non-English document can score
    # 1/1 = "high" because two zeros agree). The scalar is still
    # emitted — it is a true measurement of agreement among the
    # measurable axes — but banding it would assert a confidence the
    # sample size cannot carry, so the advisory label degrades to
    # "unmeasurable", matching the register layer's convention.
    if n_measurable < MIN_MEASURABLE_AXES:
        label = "unmeasurable" if value is not None else None
    else:
        label = classify_by_min(value, bands) if (value is not None and bands) else None

    return CoherenceEmission(
        value=value,
        label=label,
        n_axes_measurable=n_measurable,
        n_axes_agree=n_agree,
        diverging_axes=tuple(diverging),
        incomparable_axes=tuple(incomparable),
        evidence={
            "axis_directions": {
                name: (spec.get("direction") if isinstance(spec, dict) else None)
                for name, spec in axes.items()
            },
            "excluded_axes": excluded,
            "overall": convergence.get("overall"),
        },
    )
