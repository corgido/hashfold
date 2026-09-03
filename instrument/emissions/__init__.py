"""emissions — L3 composition of the four-part DocumentEmission.

Takes pre-computed reading outputs (joint reading + trajectory +
router match) and assembles `register`, `arc`, `flags`,
`coherence`, and metadata into the canonical emission surface.

Imports from: L1 kernel, L2 reading.
Never imports: L4 serve, config.
"""

from __future__ import annotations

from instrument.emissions.types import (
    ArcEmission,
    CoherenceEmission,
    CorpusEmissionReport,
    DeviationOverlay,
    DimensionSummary,
    DocumentEmission,
    EmissionMetadata,
    Flag,
    PairOverlay,
    RegisterEmission,
    SliceEmission,
)

__all__ = [
    "ArcEmission", "CoherenceEmission", "CorpusEmissionReport",
    "DeviationOverlay", "DimensionSummary", "DocumentEmission",
    "EmissionMetadata", "Flag", "PairOverlay",
    "RegisterEmission", "SliceEmission",
]
