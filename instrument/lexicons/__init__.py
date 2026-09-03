"""Pre-compiled lexicons — no file I/O, no env reads.

Version is pinned at import time by the module we re-export from.
To ship a new version, generate ``_v<N>.py`` with
``tools/build_lexicons.py`` and change the two lines below
(import path + ``LEXICON_VERSION``).
"""

from __future__ import annotations

from ._v1 import BODY_SHA256, LEXICONS, MANIFEST

LEXICON_VERSION: str = "v1"

__all__ = ["LEXICONS", "LEXICON_VERSION", "MANIFEST", "BODY_SHA256"]
