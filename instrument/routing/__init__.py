"""routing — cohort-aware reference selection for emissions.

Takes a reading's flat feature dict and picks the nearest
reference cohort by standardised PC-centroid distance, or
validates a caller-declared hint. The selected reference carries
the PC distance used by the emissions register label.

Peer of `instrument/emissions/` in the dependency graph: both
consume L2 reading outputs; `instrument/emit.py` at L4 composes
both.
"""

from __future__ import annotations

from instrument.routing.reference import (
    ReferenceNotFoundError,
    list_cohorts,
    list_references,
    load_reference,
    references_for_cohort,
)
from instrument.routing.reference import set_reference_dir
from instrument.routing.router import (
    DEFAULT_DISTANCE_THRESHOLD,
    NoComparableReferenceError,
    UnknownRegisterHintError,
    route,
)
from instrument.routing.types import (
    CompositeStats,
    FeatureStats,
    LengthCohort,
    ReferenceDistribution,
    RegisterMatch,
    classify_length_cohort,
    reference_from_dict,
    reference_to_dict,
)

__all__ = [
    "CompositeStats", "FeatureStats", "LengthCohort",
    "ReferenceDistribution", "RegisterMatch",
    "classify_length_cohort", "reference_from_dict", "reference_to_dict",
    "load_reference", "list_references", "list_cohorts",
    "references_for_cohort", "ReferenceNotFoundError",
    "route", "NoComparableReferenceError", "UnknownRegisterHintError",
    "DEFAULT_DISTANCE_THRESHOLD", "set_reference_dir",
]
