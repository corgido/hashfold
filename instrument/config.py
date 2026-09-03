"""Config — the only module outside `serve/` allowed to read env.

The instrument's runtime is env-free: nothing at L1/L2/L3 reads
`os.environ`. Deployment parameters (port, max_words, default
response shape) live here. `serve/http.py` calls `from_env()` at
startup; everything else uses `DEFAULT_CONFIG`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Runtime configuration.

    Sensible defaults target a Railway-style container deploy.
    Override via env (see `from_env`) or pass a custom instance
    into `serve.http.serve()`.
    """
    host: str = "0.0.0.0"
    port: int = 8000
    response_shape: str = "audit"         # audit | full | flags_only | reading_only | compact
    max_words: int = 10_000              # edge input cap; 0 = unlimited
    max_body_bytes: int = 80_000         # reject before read; 0 = use max_words * 8
    catalog_version: str = "v2"
    references_dir: "str | None" = None  # user reference JSONs (see routing.reference)
    emit_schema_version: str = "0.10.0"  # informational; schema is stamped from the reading
    bootstrap_b: int = 200               # replicates for ?include=uncertainty (see reading.bootstrap)


DEFAULT_CONFIG = Config()


def from_env() -> Config:
    """Build a Config from environment variables.

    Recognised vars (all optional):
        INSTRUMENT_HOST              str  (default 0.0.0.0)
        INSTRUMENT_PORT              int  (default 8000)
        INSTRUMENT_RESPONSE_SHAPE    str  (default audit)
        INSTRUMENT_MAX_WORDS         int  (default 10000; 0 = unlimited)
        INSTRUMENT_MAX_BODY_BYTES    int  (default 80000; 0 = max_words * 8)
        INSTRUMENT_CATALOG_VERSION   str  (default v2)
        INSTRUMENT_REFERENCES_DIR    str  (default unset; directory of
                                          user reference JSONs,
                                          registered at server boot)
        INSTRUMENT_BOOTSTRAP_B       int  (default 200; bootstrap
                                          replicates for the opt-in
                                          `?include=uncertainty` block)
    """
    def _int(name: str, default: int) -> int:
        raw = os.environ.get(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    return Config(
        host=os.environ.get("INSTRUMENT_HOST", DEFAULT_CONFIG.host),
        port=_int("INSTRUMENT_PORT", DEFAULT_CONFIG.port),
        response_shape=os.environ.get(
            "INSTRUMENT_RESPONSE_SHAPE", DEFAULT_CONFIG.response_shape,
        ),
        max_words=_int("INSTRUMENT_MAX_WORDS", DEFAULT_CONFIG.max_words),
        max_body_bytes=_int("INSTRUMENT_MAX_BODY_BYTES", DEFAULT_CONFIG.max_body_bytes),
        catalog_version=os.environ.get(
            "INSTRUMENT_CATALOG_VERSION", DEFAULT_CONFIG.catalog_version,
        ),
        references_dir=os.environ.get("INSTRUMENT_REFERENCES_DIR") or None,
        emit_schema_version=DEFAULT_CONFIG.emit_schema_version,
        bootstrap_b=_int("INSTRUMENT_BOOTSTRAP_B", DEFAULT_CONFIG.bootstrap_b),
    )
