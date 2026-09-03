"""check_layers — enforce the one-way import DAG across instrument/.

Layers and their allowed import targets:

    L1  instrument.{kernel,lexicons,types,errors}     stdlib only
    L2  instrument.reading                             L1
    L3  instrument.{emissions,routing}                 L1, L2
    L4  instrument.{serve,emit,config}                 L1, L2, L3

Rules:
    - Every `from instrument.<x>...` or `import instrument.<x>...`
      inside instrument/ must target a module at the same or a
      strictly lower layer than the importer.
    - Tests are exempt (they need to import whatever they exercise).

Usage:
    python -m tools.check_layers
    # => exits 0 if the DAG holds; nonzero with file:line reports if not.

Pytest wraps this via instrument/tests/test_layering.py.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTRUMENT_ROOT = REPO_ROOT / "instrument"


# ---- Layer definitions ---------------------------------------------------
#
# Each entry maps a module name prefix (after the `instrument.` stem) to a
# layer ordinal. Higher ordinals may import from lower ordinals; same-
# ordinal peers may import from each other. The classification is
# longest-prefix-first (checked in declared order).

LAYERS: tuple[tuple[str, int], ...] = (
    # L1 — kernel primitives + lexicons + shared types
    ("kernel",     1),
    ("lexicons",   1),
    ("types",      1),
    ("errors",     1),
    # L2 — reading layer (composes kernel features)
    ("reading",    2),
    # L3 — emissions + routing (composes L1/L2)
    ("emissions",  3),
    ("routing",    3),
    # Offline SPC charts over the distance stream (single module,
    # instrument/spc.py). The L3 bound allows L1/L2; its imports are
    # kernel-only (L1) by construction.
    ("spc",        3),
    # L4 — serve layer + top-level emit + config
    ("serve",      4),
    ("emit",       4),
    ("config",     4),
    # Generated provenance constant (hash of the core source). Imports
    # nothing; consumed only at L4 (emit). Classified L4 so the core cannot
    # import its own hash (also enforced by test_core_hermetic).
    ("_core_provenance", 4),
)

# Modules that legitimately bridge layers (e.g. `instrument/__init__.py`
# may re-export from any layer for external callers). Add here if
# needed; today the top-level package init is empty beyond __version__.
EXEMPT_SOURCES: frozenset[str] = frozenset({
    "instrument",  # root __init__
})


class Violation:
    __slots__ = ("source_path", "line", "source_mod", "target_mod",
                 "source_layer", "target_layer")

    def __init__(self, source_path: Path, line: int,
                 source_mod: str, target_mod: str,
                 source_layer: int, target_layer: int) -> None:
        self.source_path = source_path
        self.line = line
        self.source_mod = source_mod
        self.target_mod = target_mod
        self.source_layer = source_layer
        self.target_layer = target_layer

    def __str__(self) -> str:
        rel = self.source_path.relative_to(REPO_ROOT)
        return (
            f"{rel}:{self.line}: L{self.source_layer} "
            f"`{self.source_mod}` may not import L{self.target_layer} "
            f"`{self.target_mod}`"
        )


def _module_layer(module: str) -> int:
    """Classify an `instrument....` dotted module into a layer ordinal.

    Returns `0` for unknown modules (stdlib, third-party, or paths we
    don't track); layer 0 matches anything (no constraint).
    """
    if not module.startswith("instrument."):
        return 0
    tail = module[len("instrument."):]
    for prefix, layer in LAYERS:
        if tail == prefix or tail.startswith(prefix + "."):
            return layer
    return 0


def _path_to_module(path: Path) -> str:
    """instrument/kernel/features/sfl.py  ->  instrument.kernel.features.sfl"""
    rel = path.relative_to(REPO_ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _iter_source_files() -> list[Path]:
    """Non-test `.py` files under instrument/."""
    out: list[Path] = []
    for p in INSTRUMENT_ROOT.rglob("*.py"):
        if "tests" in p.parts:
            continue
        out.append(p)
    return out


def _find_imports(path: Path) -> list[tuple[str, int]]:
    """Return `(target_module, line_number)` for every instrument.* import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("instrument"):
                out.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("instrument"):
                    out.append((alias.name, node.lineno))
    return out


def scan() -> list[Violation]:
    """Walk instrument/ (skipping tests); return layering violations."""
    violations: list[Violation] = []
    for path in _iter_source_files():
        source_mod = _path_to_module(path)
        if source_mod in EXEMPT_SOURCES:
            continue
        source_layer = _module_layer(source_mod)
        if source_layer == 0:
            continue  # not tracked
        for target, lineno in _find_imports(path):
            target_layer = _module_layer(target)
            if target_layer == 0:
                continue  # stdlib or exempt
            if target_layer > source_layer:
                violations.append(
                    Violation(path, lineno, source_mod, target,
                              source_layer, target_layer)
                )
    return violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    violations = scan()
    if violations:
        for v in violations:
            print(str(v), file=sys.stderr)
        print(
            f"\n{len(violations)} layering violation(s) found.",
            file=sys.stderr,
        )
        return 1
    if args.verbose:
        src_count = len(_iter_source_files())
        print(f"0 violations across {src_count} source files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
