"""features — measurement primitives.

Every module here exposes one or more pure functions that take a
`Tokens` struct and return a dict of feature_name → float. NaN is
returned for any feature that cannot be measured (below envelope,
insufficient process tokens, etc.).

Still L1: features are measurement, not composition.
"""

from __future__ import annotations
