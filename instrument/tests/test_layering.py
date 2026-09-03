"""CONTRACT: the L1 -> L4 one-way import DAG holds across instrument/.

Wraps `tools.check_layers.scan()` so a pytest run fails on any
layering violation. The list of allowed upper bounds per layer
lives in the checker; see its docstring.
"""

from __future__ import annotations

from pathlib import Path

from tools.check_layers import _module_layer, scan

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_no_layering_violations():
    violations = scan()
    assert not violations, (
        "layering DAG broken:\n  "
        + "\n  ".join(str(v) for v in violations)
    )


def test_every_instrument_module_has_a_layer():
    """Smoke: no un-classified modules under instrument/ except tests.

    An unclassified module has `_module_layer(...) == 0`, which
    means the checker won't enforce anything on it. That's only
    acceptable for the root `instrument.__init__`; any real code
    path must map to a layer.
    """
    from tools.check_layers import INSTRUMENT_ROOT, _path_to_module

    unclassified: list[str] = []
    for path in INSTRUMENT_ROOT.rglob("*.py"):
        if "tests" in path.parts:
            continue
        mod = _path_to_module(path)
        if mod == "instrument":
            continue
        if _module_layer(mod) == 0:
            unclassified.append(mod)
    assert not unclassified, (
        f"modules without a layer: {unclassified}. "
        "Add them to `tools/check_layers.LAYERS`."
    )


def test_checker_flags_a_fabricated_violation(tmp_path, monkeypatch):
    """Sanity: the checker actually fires on a planted upward import.

    Writes a fake `instrument.kernel.bad` module that imports from
    `instrument.serve`, points the checker at the sandbox, and
    asserts it reports one violation.
    """
    from tools import check_layers

    # Mirror enough of the instrument tree to fool the scanner.
    root = tmp_path / "repo"
    pkg = root / "instrument" / "kernel"
    pkg.mkdir(parents=True)
    (root / "instrument" / "__init__.py").write_text("", encoding="utf-8")
    (root / "instrument" / "kernel" / "__init__.py").write_text("", encoding="utf-8")
    (root / "instrument" / "kernel" / "bad.py").write_text(
        "from instrument.serve.shape import handle  # illegal upward import\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(check_layers, "REPO_ROOT", root)
    monkeypatch.setattr(check_layers, "INSTRUMENT_ROOT", root / "instrument")

    violations = check_layers.scan()
    assert len(violations) == 1
    v = violations[0]
    assert v.source_layer == 1
    assert v.target_layer == 4
    assert "kernel" in v.source_mod
    assert "serve" in v.target_mod
