"""build_sbom — emit a CycloneDX software bill of materials.

The instrument's strongest supply-chain property — zero runtime
dependencies — is only a procurement asset if it arrives as an
artifact a scanner can ingest, not a README sentence. This tool
produces that artifact from the source tree itself.

    python -m tools.build_sbom                 # writes sbom.cdx.json
    python -m tools.build_sbom --out dist/sbom.cdx.json

The components list is intentionally empty: the runtime imports
only the Python standard library (enforced by
`tools/check_layers.py` and the import discipline of L1). The
document still carries the package itself (name, version, license,
source hash) so the SBOM is non-trivial to verifiers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _version() -> str:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise SystemExit("version not found in pyproject.toml")
    return m.group(1)


def _source_sha256() -> str:
    """Stable hash over every shipped source file (sorted walk)."""
    h = hashlib.sha256()
    for p in sorted((REPO_ROOT / "instrument").rglob("*.py")):
        if "__pycache__" in p.parts or "/tests/" in str(p) or p.parts[-2] == "tests":
            continue
        h.update(str(p.relative_to(REPO_ROOT)).encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
    return h.hexdigest()


def build() -> dict:
    version = _version()
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid.uuid4()}",
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "component": {
                "type": "application",
                "name": "hashfold",
                "version": version,
                "description": (
                    "Deterministic surface-feature measurement of long-form "
                    "prose for regulated record-keeping of LLM outputs."),
                "licenses": [{"license": {"name": "Apache-2.0"}}],
                "hashes": [{"alg": "SHA-256", "content": _source_sha256()}],
                "properties": [
                    {"name": "runtime", "value": "Python >= 3.10, stdlib only"},
                    {"name": "runtime_dependencies", "value": "none"},
                    {"name": "network_calls_at_runtime", "value": "none"},
                ],
            },
        },
        # Zero entries by design: no third-party runtime components.
        "components": [],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(REPO_ROOT / "sbom.cdx.json"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
