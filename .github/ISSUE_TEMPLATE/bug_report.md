---
name: Bug report
about: A number, hash, crash, or gate that does not behave as documented
labels: bug
---

**What happened**

**What you expected**

**Reproducer**
The exact input bytes (attach the file, or a minimised version), and
the command or request that triggered it.

**Pins** (from the emission's `metadata` block, if you got one)
- `instrument_version`:
- `lexicon_version`:
- `catalog_sha256`:
- `distance_method`:
- `reproducibility_hash`:

**Environment**
- OS / libc:
- Python version:
- Output of `python -m pytest instrument/ -q` and the `--check` gates
  (`CONTRIBUTING.md`), if relevant:
