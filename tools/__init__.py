"""Build and verification tools.

User-relevant tools for regenerating compiled artifacts from the
source JSONs in `_data/` and verifying the integrity of the layered
DAG. All tools here are deterministic; running them on an unchanged
source produces byte-identical output.

User-facing entry points:

    python -m tools.build_lexicons   --version v1 [--check]
    python -m tools.build_catalog    --version v2 [--check]
    python -m tools.build_joint_golden            [--check]
    python -m tools.build_emit_golden             [--check]
    python -m tools.check_layers
"""
