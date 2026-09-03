"""rst — rhetorical structure cue densities (compact view).

Three features:

    marker_density          all discourse-marker cues per sentence
    elaboration_marker_density    elaboration cues per sentence (lexical +
                            em-dash parentheticals + colon-glosses)
    contrast_marker_density       contrast cues per sentence

This is NOT a discourse parser. Cues are detected by lexical +
punctuation + sentence-position heuristics; output is a cue-density
profile, not RST relation counts. Cue polysemy, implicit relations,
and genre drift are all inherent to mechanical cue detection; the
instrument is conservative by choice (per-sentence dedup, broad-cue
register guard, sentence-initial-only guards).
"""

from __future__ import annotations

import re

from instrument.lexicons import LEXICONS
from instrument.types import Tokens

MIN_WORDS = 150

ELABORATION_MARKERS: frozenset[str] = LEXICONS["rst_elaboration"]
ELABORATION_BROAD_MARKERS: frozenset[str] = LEXICONS["rst_elaboration_broad"]
CONTRAST_MARKERS: frozenset[str] = LEXICONS["rst_contrast"]
CAUSE_MARKERS: frozenset[str] = LEXICONS["rst_cause"]
RESULT_MARKERS: frozenset[str] = LEXICONS["rst_result"]
CONDITION_MARKERS: frozenset[str] = LEXICONS["rst_condition"]
JOINT_MARKERS: frozenset[str] = LEXICONS["rst_sequence"]

# Structural guards — algorithmic rules, not semantic lexicons.
SENTENCE_INITIAL_ONLY: frozenset[str] = frozenset(
    {"for", "as", "still", "so", "yet"}
)
BUT_FOCUS_TRIGGERS: frozenset[str] = frozenset(
    {"nothing", "anything", "all", "everything", "none"}
)
ELAB_BROAD_MIN_WORDS = 8

ALL_MARKERS: dict[str, frozenset[str]] = {
    "elaboration": ELABORATION_MARKERS,
    "contrast": CONTRAST_MARKERS,
    "cause": CAUSE_MARKERS,
    "result": RESULT_MARKERS,
    "condition": CONDITION_MARKERS,
    "joint": JOINT_MARKERS,
}

_EMDASH_ELAB_RE = re.compile(
    r"[a-z]\w*[^\n]{0,80}?\s+(?:[\u2013\u2014]|--)\s+[A-Za-z]"
)
_COLON_ELAB_RE = re.compile(r"[a-z]{2,}:\s+[a-z]{3,}")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
_LIST_LINE_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")
_WHITESPACE_SPLIT = re.compile(r"\s+")
_WORD_RE = re.compile(r"\b\w+\b")

# Compile mid-sentence elaboration cue patterns once at import.
_ELAB_MID_PATTERNS_STRONG = [
    (cue, re.compile(r"\b" + re.escape(cue) + r"\b", re.IGNORECASE))
    for cue in ELABORATION_MARKERS if cue not in ELABORATION_BROAD_MARKERS
]
_ELAB_MID_PATTERNS_BROAD = [
    (cue, re.compile(r"\b" + re.escape(cue) + r"\b", re.IGNORECASE))
    for cue in ELABORATION_BROAD_MARKERS
]


def has_sentence_terminators(text: str) -> bool:
    """True if `text` contains any of `.!?`."""
    return any(c in text for c in ".!?")


def count_sentence_initial_markers(sentences) -> dict[str, int]:
    """Count per-category cue hits across `sentences`.

    Each sentence contributes at most once per category (per-sentence
    dedup). Sentence-initial, mid-"but", and elaboration-structural
    passes are applied in order.
    """
    counts = {cat: 0 for cat in ALL_MARKERS}
    elaboration_seen: set[int] = set()
    contrast_seen: set[int] = set()

    # Pass 1: sentence-initial markers.
    for idx, sent in enumerate(sentences):
        lower = sent.lower().lstrip(" ,;:—-")
        first_word_raw = _WHITESPACE_SPLIT.split(lower)[0] if lower else ""
        first_word = first_word_raw.rstrip(",.;:!?")
        sent_wc = len(sent.split())
        for category, markers in ALL_MARKERS.items():
            hit = False
            for marker in markers:
                if lower.startswith(marker + " ") or lower.startswith(marker + ","):
                    if marker in SENTENCE_INITIAL_ONLY and first_word != marker:
                        continue
                    if (category == "elaboration"
                            and marker in ELABORATION_BROAD_MARKERS
                            and sent_wc < ELAB_BROAD_MIN_WORDS):
                        continue
                    counts[category] += 1
                    hit = True
                    break
            if hit:
                if category == "elaboration":
                    elaboration_seen.add(idx)
                elif category == "contrast":
                    contrast_seen.add(idx)

    # Pass 2: mid-sentence "but" (unless preceded by a focus trigger).
    for idx, sent in enumerate(sentences):
        if idx in contrast_seen:
            continue
        tokens = _WORD_RE.findall(sent.lower())
        for i, tok in enumerate(tokens):
            if tok == "but" and i > 0:
                prev = tokens[i - 1]
                if prev not in BUT_FOCUS_TRIGGERS:
                    counts["contrast"] += 1
                    contrast_seen.add(idx)
                    break

    # Pass 3: mid-sentence + structural elaboration on prose-only lines.
    for idx, sent in enumerate(sentences):
        if idx in elaboration_seen:
            continue
        prose_lines: list[str] = []
        for ln in sent.split("\n"):
            stripped = ln.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            if "|" in ln:
                continue
            if _LIST_LINE_RE.match(ln):
                continue
            if set(stripped) <= set("-*_= "):
                continue
            prose_lines.append(ln)
        if not prose_lines:
            continue
        scrubbed = _INLINE_CODE_RE.sub(" ", "\n".join(prose_lines))
        scrubbed_wc = len(scrubbed.split())
        hit = False
        for _cue, pat in _ELAB_MID_PATTERNS_STRONG:
            if pat.search(scrubbed):
                hit = True
                break
        if not hit and scrubbed_wc >= ELAB_BROAD_MIN_WORDS:
            for _cue, pat in _ELAB_MID_PATTERNS_BROAD:
                if pat.search(scrubbed):
                    hit = True
                    break
        if not hit and _EMDASH_ELAB_RE.search(scrubbed):
            hit = True
        if not hit and _COLON_ELAB_RE.search(scrubbed):
            hit = True
        if hit:
            counts["elaboration"] += 1
            elaboration_seen.add(idx)

    return counts


def rst_compact(tokens: Tokens) -> dict[str, float]:
    """Three-feature RST read over a pre-tokenised Tokens struct."""
    n_words = tokens.n_words
    if n_words < MIN_WORDS:
        return {
            "marker_density": float("nan"),
            "elaboration_marker_density": float("nan"),
            "contrast_marker_density": float("nan"),
            "n_words": n_words,
            "below_envelope": True,
        }
    if not has_sentence_terminators(tokens.cleaned):
        return {
            "marker_density": float("nan"),
            "elaboration_marker_density": float("nan"),
            "contrast_marker_density": float("nan"),
            "n_words": n_words,
            "below_envelope": True,
        }
    sentences = tokens.sentences
    n_sentences = len(sentences)
    if n_sentences == 0:
        return {
            "marker_density": float("nan"),
            "elaboration_marker_density": float("nan"),
            "contrast_marker_density": float("nan"),
            "n_words": n_words,
            "below_envelope": True,
        }

    counts = count_sentence_initial_markers(list(sentences))
    total_markers = sum(counts.values())
    return {
        "marker_density": total_markers / n_sentences,
        "elaboration_marker_density": counts["elaboration"] / n_sentences,
        "contrast_marker_density": counts["contrast"] / n_sentences,
        "n_words": n_words,
        "below_envelope": False,
    }
