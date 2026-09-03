"""RST relation analysis via discourse-marker detection (extended view).

13 features:

    <relation>_density      for 9 relation types (contrast, concession,
                            cause, result, elaboration, sequence,
                            condition, purpose, summary)
    total_marker_density    all markers per sentence
    relation_diversity      normalised Shannon entropy of relation mix
    branching_score         switches in dominant relation across sentences
    max_depth_score         longest run of same dominant relation / n_sentences

This is not tree parsing. We measure relation DENSITY — how often
each relation type surfaces per sentence — which is the surface
signal a parser would also use as primary evidence.
"""

from __future__ import annotations

import re
from collections import Counter
from math import log

from instrument.reading.document import Document
from instrument.reading.extended.lexicons import (
    ELABORATION_BROAD_MARKERS,
    RST_MARKERS,
)

ELAB_BROAD_MIN_WORDS = 8

# Structural elaboration cues: em-dash parentheticals + intra-sentential
# colon-glosses. Halliday-IFG / PDTB-3 treat both as elaboration.
_EMDASH_ELAB_RE = re.compile(
    r"[A-Za-z][^\n]{1,120}?\s+(?:[\u2013\u2014]|--)\s+[A-Za-z]"
)
_COLON_ELAB_RE = re.compile(r"[A-Za-z]\s*:\s+[a-z][a-z]+")

# Explicit priority for the 41 markers that appear in multiple RST
# categories. Without this, dict iteration order (last-write-wins)
# silently assigns the wrong relation to high-frequency markers like
# "but", "however", "since", and "so".
_MARKER_PRIORITY: dict[str, str] = {
    "but": "contrast",
    "however": "contrast",
    "while": "contrast",
    "yet": "contrast",
    "nevertheless": "contrast",
    "nonetheless": "contrast",
    "notwithstanding": "contrast",
    "whereas": "contrast",
    "whilst": "contrast",
    "alternatively": "contrast",
    "otherwise": "contrast",
    "only": "contrast",
    "save": "contrast",
    "anyhow": "contrast",
    "anyway": "contrast",
    "though": "concession",
    "still": "concession",
    "even": "concession",
    "granted": "concession",
    "of": "concession",
    "since": "cause",
    "for": "cause",
    "now": "cause",
    "on": "condition",
    "if": "condition",
    "given": "condition",
    "when": "condition",
    "in": "condition",
    "lest": "purpose",
    "end": "purpose",
    "so": "result",
    "hence": "result",
    "thus": "result",
    "therefore": "result",
    "upshot": "result",
    "subsequently": "sequence",
    "then": "sequence",
    "finally": "sequence",
    "ultimately": "sequence",
    "that": "elaboration",
    "indeed": "elaboration",
}

# Marker lookup tables built once from RST_MARKERS.
_SINGLE_WORD_MARKERS: dict[str, str] = {}
_MULTI_WORD_MARKERS: list[tuple[str, str]] = []
for _relation, _markers in RST_MARKERS.items():
    for _m in _markers:
        if " " in _m:
            _MULTI_WORD_MARKERS.append((_m, _relation))
        else:
            if _m in _MARKER_PRIORITY:
                _SINGLE_WORD_MARKERS[_m] = _MARKER_PRIORITY[_m]
            elif _m not in _SINGLE_WORD_MARKERS:
                _SINGLE_WORD_MARKERS[_m] = _relation


def _detect_markers_in_sentence(sent_text: str, tokens) -> list[str]:
    """Detect discourse-marker relations in a sentence (per-sentence dedup).

    Each relation is counted at most ONCE per sentence regardless
    of how many cues of that relation appear, matching the compact
    view's dedup policy so the joint rst_* axes compare like with
    like.
    """
    seen: set[str] = set()
    found: list[str] = []
    text_lower = sent_text.lower()

    def _note(relation: str) -> None:
        if relation not in seen:
            seen.add(relation)
            found.append(relation)

    # Multi-word markers via substring search with word-boundary checks.
    for marker_text, relation in _MULTI_WORD_MARKERS:
        if relation in seen:
            continue
        idx = 0
        while True:
            i = text_lower.find(marker_text, idx)
            if i == -1:
                break
            left_ok = (i == 0) or (not text_lower[i - 1].isalnum())
            right = i + len(marker_text)
            right_ok = (right == len(text_lower)) or (
                not text_lower[right].isalnum()
            )
            if left_ok and right_ok:
                _note(relation)
                break
            idx = i + 1

    # Single-word markers via token lookup. Register-sensitive
    # elaboration cues require the sentence to clear ELAB_BROAD_MIN_WORDS.
    sent_wc = sum(1 for t in tokens if t.is_word)
    for tok in tokens:
        t_lower = tok.lower
        if t_lower in _SINGLE_WORD_MARKERS:
            relation = _SINGLE_WORD_MARKERS[t_lower]
            if (relation == "elaboration"
                    and t_lower in ELABORATION_BROAD_MARKERS
                    and sent_wc < ELAB_BROAD_MIN_WORDS):
                continue
            _note(relation)

    # Structural elaboration cues (em-dash / colon).
    if "elaboration" not in seen:
        if _EMDASH_ELAB_RE.search(sent_text) or _COLON_ELAB_RE.search(sent_text):
            _note("elaboration")

    return found


def _zero_features() -> dict:
    f = {f"{r}_density": 0.0 for r in RST_MARKERS}
    f.update({
        "total_marker_density": 0.0,
        "relation_diversity": 0.0,
        "branching_score": 0.0,
        "max_depth_score": 0.0,
    })
    return f


def analyse(doc: Document) -> dict:
    """Compute 13 RST features over a `Document`."""
    if doc.n_sentences == 0:
        return _zero_features()

    sentence_relations: list[list[str]] = []
    relation_totals: Counter = Counter()
    for sent in doc.sentences:
        rels = _detect_markers_in_sentence(sent.text, sent.tokens)
        sentence_relations.append(rels)
        for r in rels:
            relation_totals[r] += 1

    n_sent = doc.n_sentences
    features: dict[str, float] = {}

    for relation in RST_MARKERS:
        features[f"{relation}_density"] = relation_totals[relation] / n_sent

    total_markers = sum(relation_totals.values())
    features["total_marker_density"] = total_markers / n_sent

    if total_markers > 0:
        entropy = 0.0
        for c in relation_totals.values():
            if c > 0:
                p = c / total_markers
                entropy -= p * log(p, 2)
        max_entropy = log(len(RST_MARKERS), 2)
        features["relation_diversity"] = (
            entropy / max_entropy if max_entropy > 0 else 0.0
        )
    else:
        features["relation_diversity"] = 0.0

    sentence_dominant: list = []
    for rels in sentence_relations:
        if rels:
            sentence_dominant.append(Counter(rels).most_common(1)[0][0])
        else:
            sentence_dominant.append(None)

    if len(sentence_dominant) > 1:
        switches = 0
        comparisons = 0
        for a, b in zip(sentence_dominant, sentence_dominant[1:]):
            if a is not None and b is not None:
                comparisons += 1
                if a != b:
                    switches += 1
        features["branching_score"] = (
            switches / comparisons if comparisons > 0 else 0.0
        )
    else:
        features["branching_score"] = 0.0

    if sentence_dominant:
        max_run = 0
        cur_run = 0
        cur_label: object = object()
        for d in sentence_dominant:
            if d is not None and d == cur_label:
                cur_run += 1
            else:
                cur_run = 1 if d is not None else 0
                cur_label = d
            if cur_run > max_run:
                max_run = cur_run
        features["max_depth_score"] = max_run / n_sent
    else:
        features["max_depth_score"] = 0.0

    return features
