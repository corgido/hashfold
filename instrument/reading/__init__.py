"""reading — L2 composition layer.

Composes L1 kernel features into full readings. Two views live
here: the flat/compact view (13 features, Tokens-currency) and
the extended view (37 features, Document-currency). The joint
reading composes both plus stylometry plus convergence into one
schema-versioned dict.

Imports from: L1 kernel, L1b lexicons.
Never imports: L3 emissions, L4 serve, config.
"""

from __future__ import annotations
