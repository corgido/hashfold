"""CONTRACT: the version pins say what they mean (0.10.0).

- instrument_version is single-sourced from instrument.__version__.
- schema_version tracks instrument_version for 0.10.0 (the reading
  schema changed: dist.mattr joined the distributional view) — a
  regulator-facing reviewer must not find a schema pin trailing the
  code that emits it.
- pyproject.toml agrees.
- The catalog's embedded stamps name the version the catalog was last
  REGENERATED AND CHECKED against — 0.9.1 — not the current version.
  0.10.0 deliberately leaves every catalog byte unchanged
  (catalog_sha256 stable; the pre-calibration thresholds were
  sanity-checked against 0.9.1 and no re-check happened), so bumping
  the stamps would claim a verification that never ran. The stamp is
  catalog provenance, not a live version pin.
"""

from __future__ import annotations

import re
from pathlib import Path

import instrument
from instrument.config import Config
from instrument.emit import _INSTRUMENT_VERSION
from instrument.reading.joint import SCHEMA_VERSION

_PKG_ROOT = Path(__file__).resolve().parents[2]

EXPECTED = "0.10.0"

# The version the catalog was last regenerated from source and
# sanity-checked against. Moves only when the catalog itself is
# regenerated — see the module docstring.
CATALOG_STAMP = "0.9.1"


def test_instrument_version_single_sourced():
    assert instrument.__version__ == EXPECTED
    assert _INSTRUMENT_VERSION is instrument.__version__


def test_schema_version_aligned():
    assert SCHEMA_VERSION == EXPECTED
    assert Config().emit_schema_version == SCHEMA_VERSION


def test_pyproject_agrees():
    text = (_PKG_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert m and m.group(1) == EXPECTED


def test_catalog_stamps_agree():
    from instrument.emissions.catalog_v2 import CATALOG
    assert CATALOG.get("instrument_version") == CATALOG_STAMP
    assert CATALOG.get("schema_version") == CATALOG_STAMP
