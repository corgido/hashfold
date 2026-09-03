"""Flag detectors — registry of 12 document-internal event detectors.

Each detector is a small module with a `detect(ctx, params)`
function. The registry wires them by the catalog's `id` field so
that `catalog.yaml` → detector lookup is a dict read, not an
import.

ADVISORY: every flag in this package converts raw measurements into
a discrete event by crossing a catalog-defined threshold. Flags are
the inference layer of the instrument; they are not the canonical
record. Compliance pipelines should consume the underlying
measurements (per-slice trajectory values, deltas, distances, axis
agreement values) from the audit shape and apply their own
thresholds against their own baselines. Catalog v2 thresholds are
documented as pre-calibration placeholders in
`instrument/emissions/catalog_v2.py`.
"""

from __future__ import annotations

from instrument.emissions.flags import (
    below_envelope_shaper,
    cross_view_diverge,
    feature_unmeasurable_cluster,
    malformed_fence_recovered,
    modal_pivot,
    negation_cluster,
    novelty_collapse,
    novelty_reopen,
    register_shift,
    trajectory_unmeasurable,
    unbalanced_quotation,
    variance_spike,
)
from instrument.emissions.flags._common import FlagContext, FlagDetector

FLAG_DETECTORS: dict[str, FlagDetector] = {
    # Trajectory events
    "novelty_reopen":    novelty_reopen.detect,
    "novelty_collapse":  novelty_collapse.detect,
    "variance_spike":    variance_spike.detect,
    "modal_pivot":       modal_pivot.detect,
    "negation_cluster":  negation_cluster.detect,
    "register_shift":    register_shift.detect,
    # Structural events
    "malformed_fence_recovered": malformed_fence_recovered.detect,
    "unbalanced_quotation":      unbalanced_quotation.detect,
    "below_envelope_shaper":     below_envelope_shaper.detect,
    "trajectory_unmeasurable":   trajectory_unmeasurable.detect,
    # Measurement-reliability events
    "cross_view_diverge":            cross_view_diverge.detect,
    "feature_unmeasurable_cluster":  feature_unmeasurable_cluster.detect,
}


def get_flag_detector(detector_id: str) -> FlagDetector:
    fn = FLAG_DETECTORS.get(detector_id)
    if fn is None:
        raise KeyError(
            f"unknown flag detector {detector_id!r}; "
            f"available: {sorted(FLAG_DETECTORS)}"
        )
    return fn


__all__ = ["FLAG_DETECTORS", "FlagContext", "FlagDetector", "get_flag_detector"]
