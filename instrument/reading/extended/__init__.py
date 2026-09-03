"""extended — 37-feature view over SFL + RST + cohesion.

Both views (compact 13d, extended 37d) use the same L1 primitives
after the 2026-04-15 unification; they differ in feature
taxonomy, not in measurement. The extended view is ported here
verbatim from the legacy `shaper.extended` package.
"""

from __future__ import annotations

from instrument.reading.extended.feature import (
    ALL_FEATURE_KEYS,
    F,
    F_from_doc,
    FeatureVector,
)

__all__ = ["F", "F_from_doc", "FeatureVector", "ALL_FEATURE_KEYS"]
