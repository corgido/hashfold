"""CONTRACT: the measurement core is hermetic.

The core — `instrument.kernel`, `instrument.reading`, `instrument.lexicons`
— is the untouchable, byte-reproducible witness (the audit `reading`). For
`core_code_sha256` to mean anything, the core must be a pure function of
`(input bytes, lexicon)`: it must import nothing from the advisory layer
(`emissions` / `routing`) or the composition layer (`serve` / `emit` /
`config`), read no environment, and do no file I/O.

This is partly enforced elsewhere (the L1->L4 import DAG in
`test_layering`, the env firewall in `test_no_env_reads`); this test states
the *core-purity* property directly, as one named contract, and adds the
no-file-I/O assertion that nothing else covers.
"""
from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_PACKAGES = ("kernel", "reading", "lexicons")

FORBIDDEN_IMPORT_PREFIXES = (
    "instrument.emissions",
    "instrument.routing",
    "instrument.serve",
    "instrument.emit",
    "instrument.config",
    "instrument._core_provenance",  # core must not import its own hash
)

# Names whose use implies file I/O or environment access in the core.
FORBIDDEN_NAMES = frozenset({"open"})
FORBIDDEN_ATTRS = frozenset({
    "read_text", "read_bytes", "write_text", "write_bytes",
    "environ", "getenv",
})


def _core_files() -> list[Path]:
    files: list[Path] = []
    for pkg in CORE_PACKAGES:
        for p in (REPO_ROOT / "instrument" / pkg).rglob("*.py"):
            if "tests" in p.parts or "__pycache__" in p.parts:
                continue
            files.append(p)
    return files


def test_core_imports_no_advisory():
    offenders: list[str] = []
    for p in _core_files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                targets.append(node.module)
            elif isinstance(node, ast.Import):
                targets.extend(a.name for a in node.names)
            for t in targets:
                if any(t == pre or t.startswith(pre + ".")
                       for pre in FORBIDDEN_IMPORT_PREFIXES):
                    offenders.append(f"{p.relative_to(REPO_ROOT)}:{node.lineno} -> {t}")
    assert not offenders, "core imports advisory/composition layer:\n" + "\n".join(offenders)


def test_core_does_no_io_or_env():
    offenders: list[str] = []
    for p in _core_files():
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
                offenders.append(f"{p.relative_to(REPO_ROOT)}:{node.lineno} -> {node.id}")
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
                offenders.append(f"{p.relative_to(REPO_ROOT)}:{node.lineno} -> .{node.attr}")
    assert not offenders, "core performs file I/O or env access:\n" + "\n".join(offenders)
