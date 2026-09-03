"""instrument — production variant of the shape-of-language measurer.

Public surface (stable across minor versions):

    from instrument.reading.joint import joint_reading
    from instrument.emissions import emit

The import path is deliberately flat: layer entry points are
re-exported from their layer's __init__.py, not from the top.
Callers that want a single dependency line still go through the
layer packages so layering is visible in the import text.
"""

from __future__ import annotations

__version__ = "0.10.0"
