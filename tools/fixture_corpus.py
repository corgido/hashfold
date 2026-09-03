"""fixture_corpus — deterministic segmentation of the prose fixtures.

Slices the eight prose fixtures under `fixtures/source/` into
~200-word sentence-boundary pseudo-documents, giving the repository an
in-tree corpus large enough to calibrate and validate against without
shipping any external data. Segmentation is a pure function of the
fixture bytes — the kernel tokeniser, paragraph splitter, and sentence
splitter, no randomness — so every host sees the same segment ids and
the same segment text.

Two consumers, kept strictly apart:

  * the EVEN split (segment indices 0, 2, 4, ... per fixture)
    calibrates `fixtures/references/fixture_prose_v1.json`, the
    committed validation reference;
  * the ODD split is the held-out set for emit-level tests and the
    in-repo validation study. It must never feed a build that odd
    segments are later scored against — that would reintroduce the
    resubstitution optimism the 0.10.0 null distribution removes.

API:

    iter_segments() -> list[tuple[str, str]]
        (seg_id, text) pairs, e.g. ("journalism_003", "..."), sorted
        by seg_id; deterministic across hosts.

    write_split(dest_dir, parity) -> list[Path]
        Write `<seg_id>.md` for the "even" or "odd" segment indices
        (parity is per fixture) into dest_dir; returns written paths.

CLI (convenience for the calibration recipe):

    python -m tools.fixture_corpus --dest /tmp/even_split --parity even
"""

from __future__ import annotations

import argparse
from pathlib import Path

from instrument.kernel.tokens import tokenise, word_tokens

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "fixtures" / "source"

# The eight prose fixtures (the remaining files under source/ are
# adversarial/degenerate inputs — below-envelope, non-Latin, tables —
# not prose to calibrate on). Kept sorted, so iter_segments output is
# sorted by construction.
PROSE_FIXTURES: tuple[str, ...] = (
    "academic_long",
    "academic_short",
    "contraction_heavy",
    "dialogue",
    "discourse_heavy",
    "journalism",
    "literary",
    "llm_technical",
)

# Segments flush at the first sentence boundary at or past this many
# words, so real segments run slightly over.
TARGET_WORDS = 200

# A trailing remainder shorter than this merges into the fixture's
# last segment instead of becoming a fragment that the reference
# builder's word floor (--min-words, default 150) would silently drop.
_MIN_TAIL_WORDS = 100


def _segment_fixture(text: str) -> list[str]:
    """Split one fixture's text into ~TARGET_WORDS pseudo-documents.

    Boundaries fall only between sentences (kernel sentence splitter,
    via `tokenise`, which also canonicalises and strips fenced code —
    segments are prose, never half a code fence). Paragraph structure
    is preserved: sentences from one source paragraph are joined with
    spaces, paragraphs with blank lines, so the pseudo-documents still
    read (and measure) as paragraphed prose.
    """
    toks = tokenise(text)
    # segment -> paragraph-block -> sentences; a source paragraph that
    # straddles a flush contributes a block to each side.
    segments: list[list[list[str]]] = []
    cur_blocks: list[list[str]] = []
    cur_words = 0
    for para_sentences in toks.paragraph_sentences:
        start_block = True
        for sentence in para_sentences:
            if start_block or not cur_blocks:
                cur_blocks.append([])
                start_block = False
            cur_blocks[-1].append(sentence)
            cur_words += len(word_tokens(sentence))
            if cur_words >= TARGET_WORDS:
                segments.append(cur_blocks)
                cur_blocks = []
                cur_words = 0
                start_block = True  # rest of this paragraph opens the next segment
    if cur_blocks:
        if segments and cur_words < _MIN_TAIL_WORDS:
            segments[-1].extend(cur_blocks)
        else:
            segments.append(cur_blocks)
    return [
        "\n\n".join(" ".join(block) for block in seg_blocks)
        for seg_blocks in segments
    ]


def iter_segments() -> list[tuple[str, str]]:
    """All pseudo-documents as sorted, deterministic (seg_id, text).

    seg_id is `<fixture>_<index>` with a three-digit zero-padded
    per-fixture index starting at 000.
    """
    out: list[tuple[str, str]] = []
    for fixture in PROSE_FIXTURES:
        text = (SOURCE_DIR / f"{fixture}.md").read_text(encoding="utf-8")
        for i, segment in enumerate(_segment_fixture(text)):
            out.append((f"{fixture}_{i:03d}", segment))
    return out


def write_split(dest_dir: "str | Path", parity: str) -> list[Path]:
    """Write one parity class of segments as `<seg_id>.md` files.

    `parity` is "even" or "odd", applied to each fixture's own segment
    indices (so both splits cover every fixture). Returns the written
    paths, sorted. The directory is created if needed; existing files
    with the same names are overwritten (the content is deterministic,
    so a rewrite is byte-identical).
    """
    if parity not in ("even", "odd"):
        raise ValueError(f"parity must be 'even' or 'odd', got {parity!r}")
    want = 0 if parity == "even" else 1
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for seg_id, text in iter_segments():
        index = int(seg_id.rsplit("_", 1)[1])
        if index % 2 != want:
            continue
        path = dest / f"{seg_id}.md"
        path.write_text(text + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(
        description="Write the even or odd fixture-segment split "
                    "(deterministic pseudo-corpus for calibration/validation).")
    ap.add_argument("--dest", required=True, help="output directory")
    ap.add_argument("--parity", required=True, choices=["even", "odd"])
    args = ap.parse_args(argv)
    written = write_split(args.dest, args.parity)
    total = len(iter_segments())
    print(f"wrote {len(written)} of {total} segments ({args.parity}) "
          f"to {args.dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
