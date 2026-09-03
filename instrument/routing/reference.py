"""Reference distribution loader.

Loads versioned reference JSONs bundled under
`instrument/routing/references/`, plus — when a deployment opts in
via `set_reference_dir()` — user references from an external
directory. Memoised via `@lru_cache` so repeated calls for the
same `(name, version)` return the same object.

User references are the supported path for the
baseline-and-deviation workflow (`docs/CALIBRATION.md`): build one
with `python -m tools.build_reference` from a corpus of your own
LLM outputs, mount the JSON in a directory, and point
`INSTRUMENT_REFERENCES_DIR` at it (the env var is read in
`instrument/config.py`; `serve()` and `run.py` call
`set_reference_dir` at boot — this module never touches env).
Precedence: a user file with the same `<name>_<version>.json`
stem REPLACES the bundled one; otherwise user references are
added alongside the bundled five. Ordering everywhere is sorted,
so distance records stay byte-stable.

This is the one place in the instrument tree that reads files at
runtime. The reads happen lazily on first demand, not at import,
so import cost stays minimal. The routing references are the
documented exception to the "no file I/O" rule.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from instrument.errors import ReferenceLoadError
from instrument.routing.types import ReferenceDistribution, reference_from_dict

_REFERENCES_DIR = Path(__file__).resolve().parent / "references"

# Optional user reference directory; set via set_reference_dir().
_EXTRA_DIR: Optional[Path] = None


class ReferenceNotFoundError(LookupError):
    """Raised when a named reference (or cohort) cannot be located."""


def set_reference_dir(path: "str | Path | None") -> list[tuple[str, str]]:
    """Register (or clear, with None) a user reference directory.

    Eagerly loads every `*_v*.json` in the directory so a malformed
    reference fails HERE — at boot — with `ReferenceLoadError`,
    rather than mid-request. Returns the (name, version) pairs found.
    Clears the load cache, since precedence may change.
    """
    global _EXTRA_DIR
    load_reference.cache_clear()
    if path is None:
        _EXTRA_DIR = None
        return []
    p = Path(path)
    if not p.is_dir():
        raise ReferenceLoadError(f"reference dir does not exist: {p}")
    _EXTRA_DIR = p
    found = [(n, v) for (n, v) in list_references()
             if (p / f"{n}_{v}.json").exists()]
    for name, version in found:
        load_reference(name, version)  # validate now, not at request time
    return found


def _path_for(name: str, version: str) -> Path:
    if _EXTRA_DIR is not None:
        candidate = _EXTRA_DIR / f"{name}_{version}.json"
        if candidate.exists():
            return candidate
    return _REFERENCES_DIR / f"{name}_{version}.json"


@lru_cache(maxsize=None)
def load_reference(name: str, version: str = "v2") -> ReferenceDistribution:
    """Return the named reference as a typed dataclass.

    Raises `ReferenceNotFoundError` if the file does not exist,
    `ReferenceLoadError` if it exists but cannot be parsed into a
    valid ReferenceDistribution.
    """
    path = _path_for(name, version)
    if not path.exists():
        raise ReferenceNotFoundError(
            f"reference not found: {name} version {version} at {path}"
        )
    try:
        with path.open("r", encoding="utf-8") as fh:
            return reference_from_dict(json.load(fh))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise ReferenceLoadError(f"invalid reference {path}: {e}") from e


def _scan(directory: Path) -> list[tuple[str, str]]:
    if not directory.exists():
        return []
    out: list[tuple[str, str]] = []
    for p in sorted(directory.glob("*.json")):
        stem = p.stem
        if "_v" not in stem:
            continue
        name, _, version = stem.rpartition("_")
        out.append((name, version))
    return out


def list_references() -> list[tuple[str, str]]:
    """All references as sorted `(name, version)` pairs.

    Bundled set union the user directory (if registered);
    duplicates collapse (the user file wins at load time).
    """
    pairs = set(_scan(_REFERENCES_DIR))
    if _EXTRA_DIR is not None:
        pairs.update(_scan(_EXTRA_DIR))
    return sorted(pairs)


def list_cohorts() -> list[str]:
    """Distinct register cohorts covered by bundled references."""
    seen: set[str] = set()
    for name, version in list_references():
        seen.add(load_reference(name, version).register_cohort)
    return sorted(seen)


def references_for_cohort(cohort: str) -> list[ReferenceDistribution]:
    """Every reference whose register_cohort matches `cohort`.

    Production references first, then exploratory; within each
    reliability level, ascending version.
    """
    out: list[ReferenceDistribution] = []
    for name, version in list_references():
        ref = load_reference(name, version)
        if ref.register_cohort == cohort:
            out.append(ref)
    out.sort(key=lambda r: (r.reliability != "production", r.version))
    return out


