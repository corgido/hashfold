"""Catalog loader — dispatches to the generated catalog_v<N> module.

The catalog JSON at `_data/emissions_catalog/v2.json` is compiled
to `instrument/emissions/catalog_v2.py` by
`tools/build_catalog.py`. Consumers call `load_catalog("v2")`
and get a dict — same schema, same thresholds, zero runtime file
I/O.

ADVISORY: every threshold in the catalog (flag firing conditions,
register match/drift/break bands, coherence high/moderate/low
bands) is the inference layer of the instrument. Catalog v2
thresholds are explicitly pre-calibration placeholders. Compliance
pipelines should consume the underlying measurements (in the audit
shape) and apply their own thresholds; the catalog labels are
convenience.
"""

from __future__ import annotations

from instrument.emissions.catalog_v2 import CATALOG as _CATALOG_V2


class CatalogError(RuntimeError):
    """Raised when an unknown catalog version is requested."""


_REGISTRY: dict[str, dict] = {
    "v2": _CATALOG_V2,
}


def load_catalog(version: str = "v2") -> dict:
    """Return the catalog dict for the requested version."""
    if version not in _REGISTRY:
        raise CatalogError(
            f"unknown catalog version: {version!r}; "
            f"available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[version]


def classify_by_max(value: float | None, bands: list[dict]) -> str | None:
    """Return the band label whose `max` threshold contains `value`.

    `bands` is a list of `{"label": str, "max": number | None}`
    dicts ordered from strictest to loosest. `"max": null` means
    the final catchall band — matches any value. Returns `None` if
    no band matches (only possible when the catchall is missing)
    or if `value` is None (unmeasurable — e.g. a hint-routed
    reading that could not be projected; callers map None to their
    own "unmeasurable" label).
    """
    if value is None:
        return None
    for band in bands:
        threshold = band.get("max")
        if threshold is None or value <= threshold:
            return band["label"]
    return None


def classify_by_min(value: float | None, bands: list[dict]) -> str | None:
    """Counterpart to `classify_by_max` for coherence-style bands.

    `bands` is a list of `{"label": str, "min": number | None}`
    ordered from highest threshold to lowest. `"min": null` is the
    catchall. Returns `None` when `value` is None (unmeasurable).
    """
    if value is None:
        return None
    for band in bands:
        threshold = band.get("min")
        if threshold is None or value >= threshold:
            return band["label"]
    return None
