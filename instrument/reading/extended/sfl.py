"""SFL transitivity + interpersonal analysis (extended view).

Eleven features: six process-type proportions (material / mental /
relational / verbal / behavioral / existential) plus process
density, modal density, hedge density, booster density, and
modality balance.

Approximation: process types are inferred from verb-lemma lookup.
No POS tagger; any token whose lowercased form appears in a
process-verb set is treated as a candidate verb. False positives
(e.g. "look" as noun) apply uniformly across texts, so the
distributional signal survives comparison.
"""

from __future__ import annotations

from collections import Counter

from instrument.reading.document import Document
from instrument.reading.extended.lexicons import (
    BEHAVIORAL_VERBS,
    BOOSTERS,
    EXISTENTIAL_TRIGGERS,
    HEDGES,
    MATERIAL_VERBS,
    MENTAL_VERBS,
    MODAL_VERBS,
    RELATIONAL_VERBS,
    VERBAL_VERBS,
)

PROCESS_LEXICONS: dict[str, frozenset[str]] = {
    "material": MATERIAL_VERBS,
    "mental": MENTAL_VERBS,
    "relational": RELATIONAL_VERBS,
    "verbal": VERBAL_VERBS,
    "behavioral": BEHAVIORAL_VERBS,
    "existential": EXISTENTIAL_TRIGGERS,
}


def classify_token(lower: str) -> str | None:
    """Return process type for a token, or None if no match."""
    for ptype, lex in PROCESS_LEXICONS.items():
        if lower in lex:
            return ptype
    return None


def _zero_features() -> dict:
    f = {f"pct_{p}": 0.0 for p in PROCESS_LEXICONS}
    f.update({
        "process_density": 0.0,
        "modal_density": 0.0,
        "hedge_density": 0.0,
        "booster_density": 0.0,
        "modality_balance": 0.0,
    })
    return f


def analyse(doc: Document) -> dict:
    """Compute 11 SFL features over a `Document`."""
    if doc.n_words == 0:
        return _zero_features()

    process_counts: Counter = Counter()
    modal_count = hedge_count = booster_count = 0

    for sent in doc.sentences:
        for tok in sent.tokens:
            if not tok.is_word:
                continue
            lower = tok.lower
            ptype = classify_token(lower)
            if ptype:
                process_counts[ptype] += 1
            if lower in MODAL_VERBS:
                modal_count += 1
            if lower in HEDGES:
                hedge_count += 1
            if lower in BOOSTERS:
                booster_count += 1

    total_classified = sum(process_counts.values())
    total_words = doc.n_words

    features: dict[str, float] = {}
    for ptype in PROCESS_LEXICONS:
        features[f"pct_{ptype}"] = (
            process_counts[ptype] / total_classified
            if total_classified > 0 else 0.0
        )
    features["process_density"] = total_classified / total_words * 100.0
    features["modal_density"] = modal_count / total_words * 100.0
    features["hedge_density"] = hedge_count / total_words * 100.0
    features["booster_density"] = booster_count / total_words * 100.0
    features["modality_balance"] = (
        (booster_count - hedge_count) / (booster_count + hedge_count)
        if (booster_count + hedge_count) > 0 else 0.0
    )
    return features
