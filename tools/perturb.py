"""perturb — deterministic mechanical text perturbations for validation.

Eight perturbations that inject KNOWN mechanical edits into prose so
`tools/validation_study.py` can publish detection-rate-versus-realized-
effect-size curves against the held-out fixture split. Each entry in
`PERTURBATIONS` has a stable id and an
`apply(text, intensity, rng) -> (perturbed_text, counts)` function,
where `counts` is always `{"sites": int, "edited": int}` — the number
of editable sites found and the number actually edited. These are
mechanical surface edits, not a model of LLM drift; what they
demonstrate is the detection METHOD, and the study documentation says
so.

Contracts (tested in instrument/tests/test_perturb.py):

  * intensity 0.0 returns the text byte-identical (as does any run
    that happens to select zero sites — no edits means no rewrite);
  * with a fixed rng seed, realized edits are non-decreasing in
    intensity: every perturbation draws its site-selection uniforms
    FIRST, one `uniform01()` per site in document order,
    unconditionally, and edits site i iff `u_i < intensity` — so the
    selected-site set at eps1 is a subset of the set at eps2 >= eps1
    for the same stream. Draws that parameterise the edits themselves
    (permutations, word choices, donor picks) come after the whole
    selection pass, so they never desynchronise site selection;
  * same seed -> byte-identical output and counts.

Randomness is exclusively `instrument.kernel.detrandom.DetRandom`
(SHA-256/CTR, bit-identical on every host); the study seeds one
stream per (document, perturbation, intensity) — see
`tools/validation_study.py` for the seed scheme. `truncate` draws
nothing (it is a pure function of the text and the intensity).

Sentence-level perturbations use the kernel tokeniser
(`instrument.kernel.tokens.tokenise`) so "sentence" and "paragraph"
mean exactly what the instrument measures; the rebuilt text joins
sentences with single spaces and paragraphs with blank lines, the
same convention as `tools/fixture_corpus.py`. Character-level
perturbations (contraction_swap, punctuation_shift) splice the raw
text and leave everything outside the edited spans untouched.

Stdlib + instrument L1 only. No wall clock, no `random`.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional

from instrument.kernel.detrandom import DetRandom
from instrument.kernel.tokens import tokenise, word_tokens

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = REPO_ROOT / "fixtures" / "source"


# ---- shared helpers --------------------------------------------------------


def _check_intensity(intensity: float) -> None:
    if not 0.0 <= intensity <= 1.0:
        raise ValueError(f"intensity must be in [0, 1], got {intensity}")


def _select(rng: DetRandom, n_sites: int, intensity: float) -> list[bool]:
    """One selection uniform per site, in site order, unconditionally.

    Site i is edited iff `u_i < intensity`; `uniform01()` lies in
    [0, 1), so intensity 1.0 selects every site and 0.0 selects none.
    Consuming exactly `n_sites` draws regardless of intensity is what
    makes realized edits monotone in intensity at a fixed seed.
    """
    return [rng.uniform01() < intensity for _ in range(n_sites)]


def _paragraph_sentences(text: str) -> list[list[str]]:
    """Paragraph -> sentence lists via the canonical kernel tokeniser."""
    return [list(group) for group in tokenise(text).paragraph_sentences if group]


def _rebuild(paragraphs: list[list[str]]) -> str:
    """Sentences joined with spaces, paragraphs with blank lines —
    the fixture_corpus convention, so rebuilt text measures as
    paragraphed prose."""
    return "\n\n".join(" ".join(sents) for sents in paragraphs if sents)


def _lower_first(sentence: str) -> str:
    """Lower the leading letter when it reads as ordinary sentence
    case (upper followed by lower) — leaves acronyms/proper-noun-ish
    openings like "LLM" or "I" alone. Mechanical heuristic."""
    if (
        len(sentence) >= 2
        and sentence[0].isupper()
        and sentence[1].islower()
    ):
        return sentence[0].lower() + sentence[1:]
    return sentence


# ---- 1. contraction_swap ---------------------------------------------------

# Bidirectional (expanded, contracted) pairs. Both directions are
# sites: an expanded form contracts, a contracted form expands, each
# at rate intensity — nudging the document's contraction density
# toward the table's other side wherever it currently sits.
_CONTRACTION_PAIRS: tuple[tuple[str, str], ...] = (
    ("are not", "aren't"),
    ("cannot", "can't"),
    ("could not", "couldn't"),
    ("did not", "didn't"),
    ("does not", "doesn't"),
    ("do not", "don't"),
    ("had not", "hadn't"),
    ("has not", "hasn't"),
    ("have not", "haven't"),
    ("is not", "isn't"),
    ("it is", "it's"),
    ("should not", "shouldn't"),
    ("that is", "that's"),
    ("there is", "there's"),
    ("was not", "wasn't"),
    ("were not", "weren't"),
    ("will not", "won't"),
    ("would not", "wouldn't"),
)

_SWAP: dict[str, str] = {}
for _a, _b in _CONTRACTION_PAIRS:
    _SWAP[_a] = _b
    _SWAP[_b] = _a

# Curly (U+2019) apostrophes match too; replacements emit the straight
# form (the kernel canonicaliser folds them anyway). Longest form
# first so the alternation prefers "it is" over any shorter overlap.
_CONTRACTION_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(form).replace("'", "['’]")
        for form in sorted(_SWAP, key=len, reverse=True)
    )
    + r")\b",
    re.IGNORECASE,
)


def _apply_contraction_swap(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    _check_intensity(intensity)
    matches = list(_CONTRACTION_RE.finditer(text))
    picks = _select(rng, len(matches), intensity)
    if not any(picks):
        return text, {"sites": len(matches), "edited": 0}
    out: list[str] = []
    last = 0
    edited = 0
    for m, take in zip(matches, picks):
        if not take:
            continue
        found = m.group(0)
        repl = _SWAP[found.replace("’", "'").lower()]
        if found[:1].isupper():
            repl = repl[:1].upper() + repl[1:]
        out.append(text[last:m.start()])
        out.append(repl)
        last = m.end()
        edited += 1
    out.append(text[last:])
    return "".join(out), {"sites": len(matches), "edited": edited}


# ---- 2. sentence_reorder ---------------------------------------------------


def _fisher_yates(rng: DetRandom, n: int) -> list[int]:
    """Deterministic Fisher-Yates permutation of range(n) via
    `rng.randbelow`."""
    order = list(range(n))
    for i in range(n - 1, 0, -1):
        j = rng.randbelow(i + 1)
        order[i], order[j] = order[j], order[i]
    return order


def _apply_sentence_reorder(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    _check_intensity(intensity)
    paragraphs = _paragraph_sentences(text)
    sites = [i for i, p in enumerate(paragraphs) if len(p) >= 2]
    picks = _select(rng, len(sites), intensity)
    selected = [i for i, take in zip(sites, picks) if take]
    if not selected:
        return text, {"sites": len(sites), "edited": 0}
    for i in selected:
        sentences = paragraphs[i]
        order = _fisher_yates(rng, len(sentences))
        if order == sorted(order):
            # Identity permutation drawn: rotate so a selected
            # paragraph always actually changes (edited == selected,
            # which keeps realized edits honest and monotone).
            order = order[1:] + order[:1]
        paragraphs[i] = [sentences[j] for j in order]
    return _rebuild(paragraphs), {"sites": len(sites), "edited": len(selected)}


# ---- 3. paragraph_merge ----------------------------------------------------


def _apply_paragraph_merge(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    """Sites are the gaps between adjacent paragraphs; a selected gap
    merges its two neighbours (consecutive selected gaps chain)."""
    _check_intensity(intensity)
    paragraphs = _paragraph_sentences(text)
    n_gaps = max(0, len(paragraphs) - 1)
    picks = _select(rng, n_gaps, intensity)
    if not any(picks):
        return text, {"sites": n_gaps, "edited": 0}
    merged: list[list[str]] = [list(paragraphs[0])]
    edited = 0
    for take, paragraph in zip(picks, paragraphs[1:]):
        if take:
            merged[-1].extend(paragraph)
            edited += 1
        else:
            merged.append(list(paragraph))
    return _rebuild(merged), {"sites": n_gaps, "edited": edited}


# ---- 4. hedge_modal_insert -------------------------------------------------

# Sentence-initial insertions built from the instrument's own stance
# lexicons: the adverbs are members of LEXICONS["stance_hedges"] and
# the modals of LEXICONS["stance_modal"] (asserted in
# instrument/tests/test_perturb.py), composed into insertable
# sentence openers. (prefix, joiner) — adverbs take a comma, the
# modal templates read straight into the lowered sentence.
_HEDGE_INSERTIONS: tuple[tuple[str, str], ...] = (
    ("Perhaps", ", "),
    ("Arguably", ", "),
    ("Apparently", ", "),
    ("Presumably", ", "),
    ("Conceivably", ", "),
    ("It might be that", " "),
    ("It could be that", " "),
    ("It may be that", " "),
)


def _apply_hedge_modal_insert(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    _check_intensity(intensity)
    paragraphs = _paragraph_sentences(text)
    n_sentences = sum(len(p) for p in paragraphs)
    picks = _select(rng, n_sentences, intensity)
    if not any(picks):
        return text, {"sites": n_sentences, "edited": 0}
    edited = 0
    it = iter(picks)
    for paragraph in paragraphs:
        for k, sentence in enumerate(paragraph):
            if not next(it):
                continue
            prefix, joiner = _HEDGE_INSERTIONS[
                rng.randbelow(len(_HEDGE_INSERTIONS))
            ]
            paragraph[k] = prefix + joiner + _lower_first(sentence)
            edited += 1
    return _rebuild(paragraphs), {"sites": n_sentences, "edited": edited}


# ---- 5. truncate -----------------------------------------------------------


def _apply_truncate(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    """Keep the first (1 - 0.4 * intensity) fraction of sentences
    (intensity 1.0 keeps 60%). Draws nothing from `rng`; sites are
    sentences, edited counts the dropped tail."""
    _check_intensity(intensity)
    paragraphs = _paragraph_sentences(text)
    n_sentences = sum(len(p) for p in paragraphs)
    keep = max(1, math.floor((1.0 - 0.4 * intensity) * n_sentences))
    dropped = max(0, n_sentences - keep)
    if dropped == 0:
        return text, {"sites": n_sentences, "edited": 0}
    kept: list[list[str]] = []
    remaining = keep
    for paragraph in paragraphs:
        if remaining <= 0:
            break
        kept.append(paragraph[:remaining])
        remaining -= len(paragraph)
    return _rebuild(kept), {"sites": n_sentences, "edited": dropped}


# ---- 6. register_mix -------------------------------------------------------

# Fixtures written in the academic register per the documented cohort
# map (fixtures/source/RATIONALE.md; echoed in
# tools/length_invariance.DEFAULT_COHORTS — discourse_heavy is
# academic argumentation). Academic documents take the literary
# donor; everything else takes academic_long, so the splice is
# cross-register by construction.
_ACADEMIC_FIXTURES: tuple[str, ...] = (
    "academic_long", "academic_short", "discourse_heavy",
)
_MIN_DONOR_SENTENCE_WORDS = 4


def donor_fixture_for(doc_id: str) -> str:
    """Donor fixture name for `register_mix` on the named document."""
    if any(doc_id.startswith(prefix) for prefix in _ACADEMIC_FIXTURES):
        return "literary"
    return "academic_long"


@lru_cache(maxsize=None)
def donor_sentences(fixture_name: str) -> tuple[str, ...]:
    """Donor sentence pool: the named prose fixture's sentences (via
    the kernel tokeniser), dropping fragments shorter than
    _MIN_DONOR_SENTENCE_WORDS words. Deterministic per fixture bytes."""
    text = (SOURCE_DIR / f"{fixture_name}.md").read_text(encoding="utf-8")
    pool = tuple(
        sentence
        for group in tokenise(text).paragraph_sentences
        for sentence in group
        if len(word_tokens(sentence)) >= _MIN_DONOR_SENTENCE_WORDS
    )
    if not pool:
        raise ValueError(f"donor fixture {fixture_name!r} has no usable sentences")
    return pool


def _apply_register_mix(
    text: str,
    intensity: float,
    rng: DetRandom,
    donor: Optional[tuple[str, ...]] = None,
) -> tuple[str, dict]:
    """Replace `intensity` of the sentences with rng-drawn sentences
    from a different-register donor pool. `donor` defaults to the
    academic_long pool; the study passes
    `donor_sentences(donor_fixture_for(doc_id))` so academic documents
    get the literary donor instead."""
    _check_intensity(intensity)
    pool = donor if donor is not None else donor_sentences("academic_long")
    paragraphs = _paragraph_sentences(text)
    n_sentences = sum(len(p) for p in paragraphs)
    picks = _select(rng, n_sentences, intensity)
    if not any(picks):
        return text, {"sites": n_sentences, "edited": 0}
    edited = 0
    it = iter(picks)
    for paragraph in paragraphs:
        for k in range(len(paragraph)):
            if not next(it):
                continue
            paragraph[k] = pool[rng.randbelow(len(pool))]
            edited += 1
    return _rebuild(paragraphs), {"sites": n_sentences, "edited": edited}


# ---- 7. punctuation_shift --------------------------------------------------

# Em/en-dashes (with any horizontal whitespace around them) -> ", ";
# "!" and ";" -> ".". Horizontal-only whitespace so a dash at a line
# edge cannot swallow a newline and merge paragraphs.
_PUNCT_RE = re.compile(r"[ \t]*[—–][ \t]*|[!;]")


def _apply_punctuation_shift(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    _check_intensity(intensity)
    matches = list(_PUNCT_RE.finditer(text))
    picks = _select(rng, len(matches), intensity)
    if not any(picks):
        return text, {"sites": len(matches), "edited": 0}
    out: list[str] = []
    last = 0
    edited = 0
    for m, take in zip(matches, picks):
        if not take:
            continue
        out.append(text[last:m.start()])
        out.append(", " if m.group(0) not in ("!", ";") else ".")
        last = m.end()
        edited += 1
    out.append(text[last:])
    return "".join(out), {"sites": len(matches), "edited": edited}


# ---- 8. sentence_duplicate -------------------------------------------------


def _apply_sentence_duplicate(
    text: str, intensity: float, rng: DetRandom
) -> tuple[str, dict]:
    """Duplicate `intensity` of the sentences in place (the copy
    immediately follows the original within its paragraph) — a
    burstiness/compression signature."""
    _check_intensity(intensity)
    paragraphs = _paragraph_sentences(text)
    n_sentences = sum(len(p) for p in paragraphs)
    picks = _select(rng, n_sentences, intensity)
    if not any(picks):
        return text, {"sites": n_sentences, "edited": 0}
    edited = 0
    it = iter(picks)
    rebuilt: list[list[str]] = []
    for paragraph in paragraphs:
        block: list[str] = []
        for sentence in paragraph:
            block.append(sentence)
            if next(it):
                block.append(sentence)
                edited += 1
        rebuilt.append(block)
    return _rebuild(rebuilt), {"sites": n_sentences, "edited": edited}


# ---- registry --------------------------------------------------------------


@dataclass(frozen=True)
class Perturbation:
    """One mechanical perturbation: stable id, one-line description,
    and `apply(text, intensity, rng, **kwargs) -> (text, counts)`."""
    id: str
    description: str
    apply: Callable[..., tuple[str, dict]]


PERTURBATIONS: dict[str, Perturbation] = {
    p.id: p
    for p in (
        Perturbation(
            "contraction_swap",
            "expand contractions / contract expandable pairs "
            "(bidirectional table) at rate eps over found sites",
            _apply_contraction_swap,
        ),
        Perturbation(
            "sentence_reorder",
            "within-paragraph sentence permutation (deterministic "
            "Fisher-Yates) on eps of multi-sentence paragraphs",
            _apply_sentence_reorder,
        ),
        Perturbation(
            "paragraph_merge",
            "merge adjacent paragraph pairs at rate eps over "
            "paragraph gaps",
            _apply_paragraph_merge,
        ),
        Perturbation(
            "hedge_modal_insert",
            "insert hedge/modal sentence openers (from the stance "
            "lexicons) at eps of sentence starts",
            _apply_hedge_modal_insert,
        ),
        Perturbation(
            "truncate",
            "keep the first (1 - 0.4*eps) fraction of sentences "
            "(eps=1 keeps 60%)",
            _apply_truncate,
        ),
        Perturbation(
            "register_mix",
            "replace eps of sentences with rng-drawn sentences from a "
            "different-register donor fixture",
            _apply_register_mix,
        ),
        Perturbation(
            "punctuation_shift",
            "em/en-dashes -> commas, exclamations/semicolons -> "
            "periods, at rate eps over sites",
            _apply_punctuation_shift,
        ),
        Perturbation(
            "sentence_duplicate",
            "duplicate eps of sentences in place "
            "(burstiness/compression signature)",
            _apply_sentence_duplicate,
        ),
    )
}
