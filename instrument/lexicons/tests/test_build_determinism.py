"""CONTRACT: re-running the builder yields byte-identical output.

Dev-only test. If it fails, the fix is to run:

    python -m tools.build_lexicons --version v1

and commit the regenerated `_v1.py`.
"""

from __future__ import annotations

from pathlib import Path

from tools.build_lexicons import build

REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATED = REPO_ROOT / "instrument" / "lexicons" / "_v1.py"


def test_generated_matches_rebuilt():
    rebuilt = build("v1")
    on_disk = GENERATED.read_text(encoding="utf-8")
    assert rebuilt == on_disk, (
        "lexicons/_v1.py is out of date with lexicons/v1/*.json — "
        "run `python -m tools.build_lexicons --version v1`"
    )
