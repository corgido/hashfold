"""FlagContext + shared helpers for the flag detectors.

Each detector accepts a `FlagContext` + its catalog params dict
and returns either `None` (not firing) or a dict of evidence
fields (firing). Detectors consume only the context fields they
need; unused fields are tolerated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


def is_nan(v) -> bool:
    try:
        return math.isnan(v)
    except TypeError:
        return False


def finite(xs: list) -> list[float]:
    return [float(x) for x in xs if x is not None and not is_nan(x)]


@dataclass(frozen=True)
class FlagContext:
    """All inputs a flag detector might need."""
    traj: dict[str, list[Optional[float]]] = field(default_factory=dict)
    slice_mean: dict[str, Optional[float]] = field(default_factory=dict)
    features: dict[str, Optional[float]] = field(default_factory=dict)
    soft_flags: tuple[str, ...] = ()
    convergence: Optional[dict] = None
    n_slices: int = 0
    n_words: int = 0
    text: str = ""


FlagDetector = Callable[[FlagContext, dict], Optional[dict[str, Any]]]
