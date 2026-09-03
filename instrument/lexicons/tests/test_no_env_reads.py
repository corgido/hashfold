"""CONTRACT: no module inside L1-L3 of `instrument/` reads os.environ.

The production instrument must be import-safe on a read-only
filesystem with no environment variables set. The ONLY allowed
env readers are `instrument.config` (reads env in `from_env()` on
demand) and anything under `instrument.serve` (deployment-adapter
layer).
"""

from __future__ import annotations

import ast
from pathlib import Path

INSTRUMENT_ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {
    INSTRUMENT_ROOT / "config.py",
}
ALLOWED_ROOTS = {
    INSTRUMENT_ROOT / "serve",
}


def _allowed(path: Path) -> bool:
    if path in ALLOWED:
        return True
    for root in ALLOWED_ROOTS:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _reads_os_environ(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                if node.attr == "environ":
                    return True
            if isinstance(node.value, ast.Attribute):
                if node.value.attr == "os" and node.attr == "environ":
                    return True
    return False


def test_no_env_reads_in_forbidden_modules():
    offenders = []
    for path in INSTRUMENT_ROOT.rglob("*.py"):
        if _allowed(path):
            continue
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _reads_os_environ(tree):
            offenders.append(path.relative_to(INSTRUMENT_ROOT))
    assert not offenders, (
        f"env reads found outside allowed layer: {offenders}"
    )
