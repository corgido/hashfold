"""length_invariance — per-feature length-invariance audit.

Several features are length-dependent by construction:
`cohesion.type_token_ratio`, `coh.type_token_ratio`, and
`register.lexical_novelty` are raw type/token quotients, which fall
mechanically as documents grow — a baseline built on 800-word
documents compared against 3,000-word documents "detects drift" that
is pure arithmetic artifact. This tool measures every feature's
actual response to document length so the compliance documentation
can say, per feature, whether cross-length comparison is valid.

Method
------
Each corpus document is prefix-truncated at the nearest sentence
boundary at or beyond each word target in STRATA (150, 300, 600,
1200, 2400). A document contributes the 150/300/600 strata only if
its own text can fill them. For the 1200/2400 strata, synthetic long
material is built by concatenating same-cohort fixture texts in
sorted filename order (cycling as needed), appended after the
document's own text so every stratum of a document is a prefix of
the same extended sentence stream.

Synthetic-length material is valid here because the audit measures
feature response to length — a property of the formulas — not
discourse quality. Caveat recorded in the generated outputs: cycling
fixture texts re-introduces every word type, so vocabulary-novelty
features (the TTR family, `dist.hapax_ratio`) see *exaggerated*
declines at the synthetic strata; the direction of the artifact is
the same as natural vocabulary saturation, so the length_sensitive
classification remains conservative and correct in sign.

Per (doc, stratum) the full feature set is computed: shaper +
other_shaper + stylometry + distributional blocks of
`joint_reading`, flattened. Per feature:

- Spearman rank correlation (average-rank ties) of value vs
  log(word count) over all finite (doc, stratum) points;
- median relative change from the 150-stratum baseline to the
  largest filled stratum (baseline |v| < 1e-9 -> None for that doc);
- monotone fraction: fraction of docs (with >= 3 finite points)
  whose value moves monotonically across their filled strata.

Classification (a documentation label, not runtime metadata):
`length_invariant` iff |median relative change| < 0.10 AND
|rho| < 0.3; else `length_sensitive`; `insufficient_range` when
fewer than 3 finite (doc, stratum) points exist. A None median
relative change (all baselines ~0) leaves the decision to rho: a
feature that is flat at ~0 shows |rho| < 0.3 and classifies
invariant; one that grows from ~0 is caught by rho. A constant
series has no rank response and reports rho = 0.0.

Outputs (byte-stable; regenerate with --write, verify with --check):
    fixtures/validation/length_response.json
    docs/LENGTH_RESPONSE.md

Usage:
    python -m tools.length_invariance --write    # regenerate outputs
    python -m tools.length_invariance --check    # verify no drift

Stdlib + instrument L1/L2 only. Deterministic: no randomness, no
wall-clock content, all floats through `instrument.kernel.quantize`.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from instrument.kernel.quantize import q, quantize
from instrument.kernel.stats import percentile_linear
from instrument.kernel.tokens import tokenise, word_tokens
from instrument.reading.joint import joint_reading

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CORPUS_DIR = REPO_ROOT / "fixtures" / "source"
JSON_PATH = REPO_ROOT / "fixtures" / "validation" / "length_response.json"
MD_PATH = REPO_ROOT / "docs" / "LENGTH_RESPONSE.md"

# Word-count targets. 150 is the shaper/distributional envelope floor.
STRATA: tuple[int, ...] = (150, 300, 600, 1200, 2400)
BASELINE_STRATUM = 150
# Strata a document may fill with synthetic same-cohort material.
SYNTHETIC_STRATA: frozenset[int] = frozenset({1200, 2400})

# The eight prose fixtures (edge-case fixtures — below_envelope,
# structural_table, malformed_fence, unicode_quotes, nonlatin_cyrillic —
# are excluded: they exercise degradation paths, not prose measurement).
DEFAULT_DOCS: tuple[str, ...] = (
    "academic_long",
    "academic_short",
    "journalism",
    "literary",
    "dialogue",
    "discourse_heavy",
    "llm_technical",
    "contraction_heavy",
)

# Cohort assignment for synthetic-length concatenation. The five
# reference-cohort fixtures keep their cohorts (fixtures/source/
# RATIONALE.md); the two adversarial fixtures are grouped with the
# register family they are written in: discourse_heavy is academic
# argumentation, contraction_heavy is dialogue-form prose.
DEFAULT_COHORTS: dict[str, str] = {
    "academic_long": "academic",
    "academic_short": "academic",
    "discourse_heavy": "academic",
    "dialogue": "dialogue",
    "contraction_heavy": "dialogue",
    "journalism": "journalism",
    "literary": "literary",
    "llm_technical": "llm_technical",
}

# Near-zero baseline guard for relative change.
_BASELINE_EPS = 1e-9

# Classification thresholds.
_REL_CHANGE_BOUND = 0.10
_RHO_BOUND = 0.3

# Presentation notes for the generated table. Documentation labels only.
_NOTES: dict[str, str] = {
    "cohesion.type_token_ratio": (
        "TTR family: raw type/token quotient, falls with n by construction"
    ),
    "coh.type_token_ratio": (
        "TTR family: content-stem type/token quotient, falls with n by construction"
    ),
    "register.lexical_novelty": (
        "TTR family: content-word type/token quotient, falls with n by construction"
    ),
    "dist.hapax_ratio": (
        "vocabulary-novelty measure; declines with n as types recur"
    ),
    "dist.mattr": (
        "windowed TTR (W=100): fixed-width windows remove the mechanical length term"
    ),
    "dist.yule_k": "designed length-robust repetition measure",
}


# ---- corpus assembly -------------------------------------------------------


def _load_corpus(corpus_dir: Path) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return (doc names, doc -> text, doc -> cohort).

    The default corpus is the hardcoded eight-prose-fixture list with
    the documented cohort map. A custom --corpus-dir audits every
    `*.md` file in it, each document forming its own single-member
    cohort (synthetic strata then cycle the document's own text).
    """
    if corpus_dir.resolve() == DEFAULT_CORPUS_DIR.resolve():
        names = list(DEFAULT_DOCS)
        cohorts = dict(DEFAULT_COHORTS)
    else:
        names = sorted(p.stem for p in corpus_dir.glob("*.md"))
        cohorts = {n: n for n in names}
    texts: dict[str, str] = {}
    for name in names:
        path = corpus_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"corpus document missing: {path}")
        texts[name] = path.read_text(encoding="utf-8")
    return names, texts, cohorts


def _sentence_stream(text: str) -> list[tuple[int, str, int]]:
    """(paragraph_index, sentence, word_count) triples, in document order.

    Uses the canonical tokeniser so sentence boundaries are exactly the
    instrument's own paragraph-first sentence stream.
    """
    tokens = tokenise(text)
    stream: list[tuple[int, str, int]] = []
    for p_idx, group in enumerate(tokens.paragraph_sentences):
        for sentence in group:
            stream.append((p_idx, sentence, len(word_tokens(sentence))))
    return stream


def _rebuild(prefix: list[tuple[int, str, int]]) -> str:
    """Reassemble a sentence-stream prefix into measurement text.

    Sentences sharing a paragraph index are joined with spaces;
    paragraphs with blank lines. Word tokens are preserved exactly
    (the token regex cannot merge across whitespace), so the rebuilt
    text's word count is the sum of the per-sentence counts.
    """
    paragraphs: list[str] = []
    current_idx: int | None = None
    current: list[str] = []
    for p_idx, sentence, _ in prefix:
        if p_idx != current_idx:
            if current:
                paragraphs.append(" ".join(current))
            current = [sentence]
            current_idx = p_idx
        else:
            current.append(sentence)
    if current:
        paragraphs.append(" ".join(current))
    return "\n\n".join(paragraphs)


def _extended_text(
    doc: str,
    texts: dict[str, str],
    cohorts: dict[str, str],
    n_words: dict[str, int],
    target: int,
) -> str:
    """Document text plus same-cohort padding to at least `target` words.

    Padding texts are the cohort's fixtures in sorted filename order,
    cycled as many times as needed. The document's own text always
    comes first so every stratum of a document is a prefix of the
    same extended stream.
    """
    cohort_members = sorted(
        name for name, c in cohorts.items()
        if c == cohorts[doc] and name in texts
    )
    parts = [texts[doc]]
    total = n_words[doc]
    i = 0
    while total < target:
        member = cohort_members[i % len(cohort_members)]
        parts.append(texts[member])
        total += n_words[member]
        i += 1
    return "\n\n".join(parts)


def _truncate_at_boundary(
    stream: list[tuple[int, str, int]], target: int
) -> tuple[str, int]:
    """Prefix-truncate at the nearest sentence boundary >= target words.

    Returns (rebuilt text, actual word count). Raises if the stream is
    too short — callers guarantee eligibility before calling.
    """
    cumulative = 0
    for i, (_, _, wc) in enumerate(stream):
        cumulative += wc
        if cumulative >= target:
            return _rebuild(stream[: i + 1]), cumulative
    raise ValueError(f"stream has only {cumulative} words < target {target}")


def _flat_feature_blocks(jr: dict) -> dict:
    """Flatten shaper + other_shaper + stylometry + distributional."""
    out: dict = {}
    out.update(jr["shaper"]["features"])
    out.update(jr["other_shaper"]["features"])
    out.update(jr["stylometry"]["features"])
    out.update(jr["distributional"]["features"])
    return out


def _is_finite_number(v) -> bool:
    """True for real finite numbers. joint_reading quantises NaN/inf
    to None, so None is the non-finite marker here."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


# ---- statistics ------------------------------------------------------------


def _average_ranks(xs: list[float]) -> list[float]:
    """1-based ranks with average-rank tie handling."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> float:
    """Spearman rank correlation with average-rank ties.

    A constant series (zero rank variance on either side) has no rank
    response by definition and reports 0.0 — for this audit that is
    the honest reading: the value does not move with length.
    """
    n = len(xs)
    rx = _average_ranks(xs)
    ry = _average_ranks(ys)
    mean_x = sum(rx) / n
    mean_y = sum(ry) / n
    cov = sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry))
    var_x = sum((a - mean_x) ** 2 for a in rx)
    var_y = sum((b - mean_y) ** 2 for b in ry)
    if var_x == 0.0 or var_y == 0.0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


def _median(xs: list[float]) -> float:
    return percentile_linear(sorted(xs), 50.0)


# ---- the audit -------------------------------------------------------------


def compute_audit(corpus_dir: Path) -> dict:
    """Run the full audit. Returns the (unquantised) result object."""
    names, texts, cohorts = _load_corpus(corpus_dir)
    native_words = {name: tokenise(text).n_words for name, text in texts.items()}

    # Per (doc, stratum): flattened features + actual word count.
    # points[doc] = list of (stratum, actual_n_words, features)
    points: dict[str, list[tuple[int, int, dict]]] = {}
    corpus_meta: dict[str, dict] = {}
    max_target = max(s for s in STRATA)
    for doc in names:
        material = _extended_text(doc, texts, cohorts, native_words, max_target)
        stream = _sentence_stream(material)
        doc_points: list[tuple[int, int, dict]] = []
        strata_meta: list[list[int]] = []
        for stratum in STRATA:
            if stratum not in SYNTHETIC_STRATA and native_words[doc] < stratum:
                continue  # a doc contributes only strata it can fill
            truncated, actual = _truncate_at_boundary(stream, stratum)
            jr = joint_reading(truncated)
            features = _flat_feature_blocks(jr)
            n_words_measured = jr["n_words"]["shaper"]
            doc_points.append((stratum, n_words_measured, features))
            strata_meta.append([stratum, n_words_measured])
        points[doc] = doc_points
        # First filled stratum whose cut needed synthetic padding: the
        # crossing sentence lies beyond the doc's own text iff the
        # target exceeds the native word count.
        padded = [s for s, _, _ in doc_points if s > native_words[doc]]
        corpus_meta[doc] = {
            "cohort": cohorts[doc],
            "native_n_words": native_words[doc],
            "synthetic_from_stratum": min(padded) if padded else None,
            "strata": strata_meta,  # [stratum_target, measured_n_words]
        }

    feature_names = sorted({
        k for doc_points in points.values()
        for _, _, features in doc_points
        for k in features
    })

    results: dict[str, dict] = {}
    for feature in feature_names:
        # All finite (doc, stratum) points.
        log_counts: list[float] = []
        values: list[float] = []
        rel_changes: list[float] = []
        monotone_eligible = 0
        monotone_hits = 0
        for doc in names:
            series: list[tuple[int, float]] = []  # (stratum, value), finite
            for stratum, n_words_measured, features in points[doc]:
                v = features.get(feature)
                if _is_finite_number(v):
                    series.append((stratum, float(v)))
                    log_counts.append(math.log(n_words_measured))
                    values.append(float(v))
            by_stratum = dict(series)
            baseline = by_stratum.get(BASELINE_STRATUM)
            if series and baseline is not None:
                largest = max(s for s, _ in series)
                if largest > BASELINE_STRATUM:
                    if abs(baseline) >= _BASELINE_EPS:
                        rel_changes.append(
                            (by_stratum[largest] - baseline) / abs(baseline)
                        )
                    # else: near-zero baseline -> None for this doc (dropped)
            if len(series) >= 3:
                monotone_eligible += 1
                ordered = [v for _, v in sorted(series)]
                deltas = [b - a for a, b in zip(ordered, ordered[1:])]
                if all(d >= 0 for d in deltas) or all(d <= 0 for d in deltas):
                    monotone_hits += 1

        n_points = len(values)
        if n_points < 3:
            results[feature] = {
                "spearman_rho": None,
                "median_rel_change_150_to_max": None,
                "monotone_fraction": None,
                "n_points": n_points,
                "classification": "insufficient_range",
            }
            continue

        rho = _spearman(log_counts, values)
        median_rel = _median(rel_changes) if rel_changes else None
        monotone_fraction = (
            monotone_hits / monotone_eligible if monotone_eligible else None
        )
        invariant = (
            (median_rel is None or abs(median_rel) < _REL_CHANGE_BOUND)
            and abs(rho) < _RHO_BOUND
        )
        results[feature] = {
            "spearman_rho": rho,
            "median_rel_change_150_to_max": median_rel,
            "monotone_fraction": monotone_fraction,
            "n_points": n_points,
            "classification": (
                "length_invariant" if invariant else "length_sensitive"
            ),
        }

    return {
        "audit": "length_invariance",
        "generated_by": "python -m tools.length_invariance --write",
        "classification_rule": {
            "length_invariant": (
                f"|median_rel_change| < {_REL_CHANGE_BOUND} and "
                f"|spearman_rho| < {_RHO_BOUND}"
            ),
            "insufficient_range": "fewer than 3 finite (doc, stratum) points",
        },
        "strata_word_targets": list(STRATA),
        "synthetic_strata": sorted(SYNTHETIC_STRATA),
        "synthetic_note": (
            "1200/2400 strata use same-cohort fixture concatenation in "
            "sorted filename order (cycled); valid for measuring feature "
            "response to length (a property of the formulas), not "
            "discourse quality. Vocabulary-novelty features see "
            "exaggerated declines at synthetic strata (cycling recurs "
            "every type); the artifact's sign matches natural "
            "vocabulary saturation."
        ),
        "corpus": corpus_meta,
        "features": results,
    }


# ---- rendering -------------------------------------------------------------


def render_json(audit: dict) -> str:
    """Byte-stable JSON: sorted keys, q()-quantised floats, indent=2,
    trailing newline."""
    return json.dumps(
        quantize(audit),
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _fmt_signed(v) -> str:
    return "—" if v is None else f"{q(float(v)):+.3f}"


def _fmt_frac(v) -> str:
    return "—" if v is None else f"{q(float(v)):.2f}"


def render_md(audit: dict) -> str:
    """Generated documentation table. Derived entirely from the audit
    object, so the two outputs cannot disagree."""
    features = audit["features"]
    lines: list[str] = []
    lines.append("# LENGTH_RESPONSE — per-feature response to document length")
    lines.append("")
    lines.append(
        "> Generated by `python -m tools.length_invariance --write`. Do not"
    )
    lines.append(
        "> edit by hand — regenerate with that command; verify drift with"
    )
    lines.append("> `python -m tools.length_invariance --check`.")
    lines.append("")
    lines.append(
        "Every feature of the joint reading (shaper + extended + stylometry"
    )
    lines.append(
        "+ distributional), measured on prefix-truncations of the eight"
    )
    lines.append(
        f"prose fixtures at word targets {list(audit['strata_word_targets'])}."
    )
    lines.append(
        "Truncation is at the nearest sentence boundary at or past the"
    )
    lines.append(
        "target; a document contributes 150/300/600 only if its own text"
    )
    lines.append(
        "fills them, while the 1200/2400 strata use synthetic long material"
    )
    lines.append(
        "(same-cohort fixtures concatenated in sorted filename order,"
    )
    lines.append(
        "cycled). Synthetic-length material is valid for measuring feature"
    )
    lines.append(
        "response to length — a property of the formulas — not discourse"
    )
    lines.append(
        "quality; cycling recurs every word type, so vocabulary-novelty"
    )
    lines.append(
        "features see exaggerated (same-sign) declines at those strata."
    )
    lines.append("")
    lines.append(
        "`length_invariant` iff |median rel change| < "
        f"{_REL_CHANGE_BOUND} and |ρ| < {_RHO_BOUND}; fewer than 3 finite"
    )
    lines.append(
        "points → `insufficient_range`. These are documentation labels for"
    )
    lines.append(
        "baseline construction (compare like lengths with like), not"
    )
    lines.append("runtime metadata.")
    lines.append("")
    lines.append(
        "| feature | ρ (value vs log n) | median rel change (150→max) "
        "| monotone fraction | classification | note |"
    )
    lines.append("|---|---|---|---|---|---|")
    for name in sorted(features):
        r = features[name]
        lines.append(
            f"| `{name}` "
            f"| {_fmt_signed(r['spearman_rho'])} "
            f"| {_fmt_signed(r['median_rel_change_150_to_max'])} "
            f"| {_fmt_frac(r['monotone_fraction'])} "
            f"| {r['classification']} "
            f"| {_NOTES.get(name, '')} |"
        )
    lines.append("")
    lines.append("## The TTR family and `dist.mattr`")
    lines.append("")

    def _row(name: str) -> dict:
        return features.get(name, {})

    ttr = _row("cohesion.type_token_ratio")
    coh_ttr = _row("coh.type_token_ratio")
    novelty = _row("register.lexical_novelty")
    mattr = _row("dist.mattr")
    yule = _row("dist.yule_k")
    lines.append(
        "Raw type/token quotients fall mechanically as documents grow —"
    )
    lines.append(
        "the denominator (tokens) outruns the numerator (types) in any"
    )
    lines.append(
        "natural text, so a baseline built on short documents compared"
    )
    lines.append(
        "against long ones \"detects drift\" that is pure arithmetic"
    )
    lines.append("artifact. Measured here:")
    lines.append("")
    lines.append(
        f"- `cohesion.type_token_ratio`: ρ = "
        f"{_fmt_signed(ttr.get('spearman_rho'))}, median rel change "
        f"{_fmt_signed(ttr.get('median_rel_change_150_to_max'))} — "
        f"{ttr.get('classification', 'n/a')}."
    )
    lines.append(
        f"- `coh.type_token_ratio`: ρ = "
        f"{_fmt_signed(coh_ttr.get('spearman_rho'))}, median rel change "
        f"{_fmt_signed(coh_ttr.get('median_rel_change_150_to_max'))} — "
        f"{coh_ttr.get('classification', 'n/a')}."
    )
    lines.append(
        f"- `register.lexical_novelty`: ρ = "
        f"{_fmt_signed(novelty.get('spearman_rho'))}, median rel change "
        f"{_fmt_signed(novelty.get('median_rel_change_150_to_max'))} — "
        f"{novelty.get('classification', 'n/a')}."
    )
    lines.append("")
    lines.append(
        "`dist.mattr` (Moving-Average TTR, window 100) replaces the"
    )
    lines.append(
        "mechanical length term with a fixed-width window. Measured: ρ ="
    )
    lines.append(
        f"{_fmt_signed(mattr.get('spearman_rho'))}, median rel change "
        f"{_fmt_signed(mattr.get('median_rel_change_150_to_max'))} — "
        f"{mattr.get('classification', 'n/a')} under the strict rule."
    )
    lines.append(
        "Read that classification with its magnitudes: the raw TTR family"
    )
    lines.append(
        "loses roughly three quarters of its value from 150 to 2400 words"
    )
    lines.append(
        "purely by construction, while `dist.mattr` moves a few percent —"
    )
    lines.append(
        "rank correlation is magnitude-blind, so a consistent few-percent"
    )
    lines.append(
        "drift (part corpus composition at the synthetic strata, part the"
    )
    lines.append(
        "higher local diversity of document openings) ranks like a"
    )
    lines.append(
        "collapse. `dist.mattr` is the length-corrected alternative for"
    )
    lines.append(
        "cross-length vocabulary-richness comparison; the existing"
    )
    lines.append(
        f"length-robust contrast `dist.yule_k` measured ρ = "
        f"{_fmt_signed(yule.get('spearman_rho'))}, median rel change "
        f"{_fmt_signed(yule.get('median_rel_change_150_to_max'))} "
        f"({yule.get('classification', 'n/a')}) — only approximately"
    )
    lines.append(
        "length-invariant on real prose. Compare TTR-family values only"
    )
    lines.append(
        "within a length cohort; see docs/METROLOGY.md §2.3/§2.4/§6."
    )
    lines.append("")
    return "\n".join(lines)


# ---- entry points ----------------------------------------------------------


def write(corpus_dir: Path) -> int:
    audit = compute_audit(corpus_dir)
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(render_json(audit), encoding="utf-8")
    print(f"wrote {JSON_PATH.relative_to(REPO_ROOT)}")
    MD_PATH.write_text(render_md(audit), encoding="utf-8")
    print(f"wrote {MD_PATH.relative_to(REPO_ROOT)}")
    return 0


def check(corpus_dir: Path) -> int:
    audit = compute_audit(corpus_dir)
    drifted: list[str] = []
    for path, regenerated in (
        (JSON_PATH, render_json(audit)),
        (MD_PATH, render_md(audit)),
    ):
        if not path.exists():
            print(f"MISSING: {path}", file=sys.stderr)
            return 1
        committed = path.read_text(encoding="utf-8")
        if regenerated != committed:
            drifted.append(str(path.relative_to(REPO_ROOT)))
            print(f"DRIFT: {path.relative_to(REPO_ROOT)}", file=sys.stderr)
    if drifted:
        print(
            f"{len(drifted)} output(s) drifted — regenerate with "
            "`python -m tools.length_invariance --write`",
            file=sys.stderr,
        )
        return 1
    print("2 outputs ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Per-feature length-invariance audit."
    )
    ap.add_argument(
        "--corpus-dir",
        type=Path,
        default=DEFAULT_CORPUS_DIR,
        help=(
            "Corpus directory. Default: fixtures/source (the eight prose "
            "fixtures with the documented cohort map); a custom directory "
            "audits every *.md file in it, one single-member cohort each."
        ),
    )
    ap.add_argument(
        "--write", action="store_true", help="regenerate committed outputs"
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="regenerate to memory, byte-compare against committed outputs",
    )
    args = ap.parse_args(argv)
    if args.write == args.check:
        ap.error("pass exactly one of --write / --check")
    return write(args.corpus_dir) if args.write else check(args.corpus_dir)


if __name__ == "__main__":
    raise SystemExit(main())
