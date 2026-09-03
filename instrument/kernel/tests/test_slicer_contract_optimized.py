"""CONTRACT: the slicer contract is real validation, not asserts.

Before this contract the clauses raised AssertionError, which
`python -O` / PYTHONOPTIMIZE strips — silently approving invalid
slicings AND changing `resolve_elegant`'s chosen slicing (i.e.
emission output) on optimised interpreters, while the
reproducibility hash stayed identical. The clauses now collect
failures explicitly; this test runs the validator in a `-O`
subprocess to pin the behaviour.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_SNIPPET = """
from instrument.kernel.slicer import validate_slicing
text = "word " * 400
bad = [(0, 10), (10, len(text))]   # slice 0 ~2 words: must fail the envelope
ok, failures = validate_slicing(text, bad)
assert_count = len(failures)
print(f"{int(ok)} {assert_count}")
"""


def _run(optimized: bool) -> tuple[bool, int]:
    cmd = [sys.executable] + (["-O"] if optimized else []) + ["-c", _SNIPPET]
    out = subprocess.run(
        cmd, capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    ).stdout.strip()
    ok_s, n_s = out.split()
    return bool(int(ok_s)), int(n_s)


def test_contract_rejects_bad_slicing_normal_mode():
    ok, n_failures = _run(optimized=False)
    assert ok is False
    assert n_failures >= 1


def test_contract_rejects_bad_slicing_under_dash_O():
    ok, n_failures = _run(optimized=True)
    assert ok is False, (
        "contract silently passed an invalid slicing under python -O"
    )
    assert n_failures >= 1


def test_elegant_slicing_identical_under_dash_O():
    """resolve_elegant must pick the same slicing with and without -O."""
    snippet = (
        "from pathlib import Path\n"
        "from instrument.kernel.regimes import regime_elegant\n"
        "text = Path('fixtures/source/academic_long.md')"
        ".read_text(encoding='utf-8')\n"
        "r = regime_elegant(text)\n"
        "print(r['n_slices'], r['boundary_level'])\n"
    )
    normal = subprocess.run(
        [sys.executable, "-c", snippet],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    ).stdout.strip()
    optimized = subprocess.run(
        [sys.executable, "-O", "-c", snippet],
        capture_output=True, text=True, check=True, cwd=REPO_ROOT,
    ).stdout.strip()
    assert normal == optimized, (
        f"elegant slicing diverges under -O: {normal!r} vs {optimized!r}"
    )
