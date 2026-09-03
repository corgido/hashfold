"""Shared error types for the instrument package."""

from __future__ import annotations


class InstrumentError(RuntimeError):
    """Base class; every instrument-specific error derives from this."""


class ReferenceLoadError(InstrumentError):
    """A reference JSON exists but cannot be parsed into a valid
    ReferenceDistribution (malformed JSON, missing fields, wrong
    shapes). Raised by `routing.reference` — distinct from
    `ReferenceNotFoundError` (file absent) so a deployment with a
    corrupt user reference fails loudly at boot rather than
    silently routing without it."""
