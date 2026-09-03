"""Lexicons for the extended structural view.

Semantic word lists come from `instrument.lexicons.LEXICONS`
(frozensets compiled at build time from lexicons/v1/*.json).
Structural guards (pronouns, demonstratives, definite article,
stopwords) stay inline — they encode closed-class function words,
not semantic lists.

Source provenance:
- SFL processes:  Halliday & Matthiessen IFG 4e, ch.5
- RST relations:  Mann & Thompson (1988) + PDTB-3
- Cohesion:       Halliday & Hasan (1976)
"""

from __future__ import annotations

from instrument.lexicons import LEXICONS

# ---------- SFL: process types ---------------------------------------------

MATERIAL_VERBS:   frozenset[str] = LEXICONS["processes_material"]
MENTAL_VERBS:     frozenset[str] = LEXICONS["processes_mental"]
RELATIONAL_VERBS: frozenset[str] = LEXICONS["processes_relational"]
VERBAL_VERBS:     frozenset[str] = LEXICONS["processes_verbal"]
BEHAVIORAL_VERBS: frozenset[str] = LEXICONS["processes_behavioral"]

EXISTENTIAL_TRIGGERS: frozenset[str] = LEXICONS["existential_triggers"]

# ---------- Modality and stance --------------------------------------------

MODAL_VERBS: frozenset[str] = LEXICONS["stance_modal"]
HEDGES:      frozenset[str] = LEXICONS["stance_hedges"]
BOOSTERS:    frozenset[str] = LEXICONS["stance_boosters"]

# ---------- RST discourse relations ----------------------------------------
# Values are sorted lists because the extended RST scanner iterates them
# as ordered sequences; sorting preserves determinism.

RST_MARKERS: dict[str, list[str]] = {
    "contrast":    sorted(LEXICONS["rst_contrast"]),
    "concession":  sorted(LEXICONS["rst_concession"]),
    "cause":       sorted(LEXICONS["rst_cause"]),
    "result":      sorted(LEXICONS["rst_result"]),
    "elaboration": sorted(LEXICONS["rst_elaboration"]),
    "sequence":    sorted(LEXICONS["rst_sequence"]),
    "condition":   sorted(LEXICONS["rst_condition"]),
    "purpose":     sorted(LEXICONS["rst_purpose"]),
    "summary":     sorted(LEXICONS["rst_summary"]),
}

ELABORATION_BROAD_MARKERS: frozenset[str] = LEXICONS["rst_elaboration_broad"]

# ---------- Cohesion -------------------------------------------------------

PERSONAL_PRONOUNS: frozenset[str] = frozenset({
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
})

DEMONSTRATIVES: frozenset[str] = frozenset({"this", "that", "these", "those"})

DEFINITE_ARTICLE: frozenset[str] = frozenset({"the"})

ADDITIVE_CONJUNCTIONS:    frozenset[str] = LEXICONS["cohesion_additive"]
ADVERSATIVE_CONJUNCTIONS: frozenset[str] = LEXICONS["cohesion_adversative"]
CAUSAL_CONJUNCTIONS:      frozenset[str] = LEXICONS["cohesion_causal"]
TEMPORAL_CONJUNCTIONS:    frozenset[str] = LEXICONS["cohesion_temporal"]

from instrument.kernel.features.cohesion import STOPWORDS as STOPWORDS  # noqa: F811
