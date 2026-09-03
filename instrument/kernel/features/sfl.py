"""sfl — Systemic-Functional Linguistics process-type proxy.

Three features in the compact view:

    process_proxy_entropy    Shannon entropy over {material, mental,
                             relational, verbal, behavioral,
                             existential} — how distributed the
                             process-type mix is.
    stative_active_ratio     (relational + existential) / (mental +
                             verbal + material). Low = active prose;
                             high = descriptive / stative. Behavioral
                             processes are not bucketed into this
                             ratio (they sit between active and
                             stative in transitivity).
    projection_frequency     (mental + verbal) per 100 words — how
                             often the text reports or cites.

The six-bucket entropy matches the extended SFL view's bucket count
(`reading/extended/sfl.py`), so the `sfl_process_complexity`
convergence axis compares like-for-like alphabets.

Implementation note: this approximates Halliday's transitivity
process types by lemma-level lookup. It does NOT measure
participant roles, circumstances, clause boundaries, voice, or
Halliday's register metafunctions. Treat the output as a
process-type density profile, not a full transitivity analysis.
"""

from __future__ import annotations

import math
import re

from instrument.lexicons import LEXICONS
from instrument.types import Tokens

MIN_WORDS = 150

MENTAL: frozenset[str] = LEXICONS["processes_mental"]
VERBAL: frozenset[str] = LEXICONS["processes_verbal"]
RELATIONAL: frozenset[str] = LEXICONS["processes_relational"]
BEHAVIORAL: frozenset[str] = LEXICONS["processes_behavioral"]
MATERIAL: frozenset[str] = LEXICONS["processes_material"]

# Structural guards. Not lexicons in the semantic sense — they
# encode algorithmic rules coupled to classify_token, so they stay
# inline rather than moving into the versioned lexicon tree.

COPULA_BE: frozenset[str] = frozenset({"is", "are", "was", "were"})

EXISTENTIAL_PATTERN = re.compile(
    r"\bthere\s+(is|are|was|were|exists?|existed)\b",
    re.IGNORECASE,
)

# Common plural nouns ending in -s that are never verbs. Defense
# against the plural-noun false-positive into MATERIAL.
KNOWN_PLURAL_NOUNS: frozenset[str] = frozenset({
    "tables", "chairs", "rooms", "houses", "windows", "doors", "walls",
    "floors", "ceilings", "roads", "streets", "buildings", "cars", "trucks",
    "books", "pages", "chapters", "sections", "sentences", "words",
    "lines", "paragraphs", "documents", "files", "folders", "images",
    "pictures", "photos", "colors", "shapes", "sizes", "numbers",
    "letters", "symbols", "figures", "charts", "graphs",
    "people", "persons", "humans", "children", "adults", "men", "women",
    "hands", "feet", "eyes", "ears", "mouths", "heads", "bodies",
    "days", "weeks", "months", "years", "hours", "minutes", "seconds",
    "ideas", "thoughts", "concepts", "theories", "facts", "data",
    "results", "findings", "observations", "conclusions", "arguments",
    "reasons", "causes", "effects", "consequences", "problems", "solutions",
    "questions", "answers", "methods", "approaches", "strategies", "techniques",
    "tools", "instruments", "devices", "machines", "computers", "systems",
    "programs", "applications", "features", "functions", "operations",
    "processes", "tasks", "jobs", "works", "projects", "plans",
    "things", "items", "objects", "elements", "parts", "pieces", "components",
    "cases", "instances", "examples", "samples", "types", "kinds",
    "groups", "teams", "organizations", "companies", "institutions",
    "countries", "cities", "towns", "places", "locations", "areas",
    "points", "dots", "marks", "spots",
})

# -ed / -ing forms that are adjectives in practice, not verbs.
KNOWN_ADJECTIVAL_PARTICIPLES: frozenset[str] = frozenset({
    "interesting", "exciting", "boring", "tiring", "confusing",
    "amazing", "surprising", "disappointing", "shocking",
    "interested", "excited", "bored", "tired", "confused",
    "amazed", "surprised", "disappointed", "shocked",
    "complicated", "detailed", "limited", "related", "dedicated",
    "advanced", "developed", "established", "documented",
    "following", "preceding", "corresponding", "existing",
})

# Closed-class grammatical words that end in -ing / -ed but are never
# verbs in running text: indefinite pronouns, prepositions, adverbs,
# numerals. All of these are high-frequency in LLM-generated prose
# ("something", "including", "according to", "indeed"), so without
# this guard the -ing/-ed morphology fallback systematically inflates
# the MATERIAL bucket on exactly the input class the instrument is
# pointed at.
KNOWN_NON_PROCESS: frozenset[str] = frozenset({
    "something", "anything", "everything", "nothing",
    "during", "according", "notwithstanding", "indeed", "hundred",
})


def classify_token_with_rule(token: str) -> tuple[str, str]:
    """Return (classification, rule_id) for a single token.

    classification: one of mental | verbal | relational | behavioral
                    | material | none.
    rule_id:        the decision path that produced the result, one of
                    lexicon_mental | lexicon_verbal | lexicon_copula_be
                    | lexicon_relational | lexicon_behavioral
                    | lexicon_material
                    | denylist_plural_noun | denylist_adjectival_participle
                    | denylist_non_process
                    | morphology_ing | morphology_ed | default.

    `existential` is detected by pattern over the text, not here.

    Lexicon checks fire before morphology so that a token like
    `laughed` (in the behavioral lexicon) is not stolen by the `-ed`
    morphology heuristic into material — and, since 0.9.1, the
    MATERIAL lexicon itself fires before the deny-lists: the
    deny-lists exist to guard the morphology fallback, not to veto a
    curated lexicon entry. Base-form material verbs (make, run,
    build, ...) classify via `lexicon_material`; the -ing/-ed
    morphology remains the fallback for inflections outside the
    lexicon tree.

    COPULA_BE is checked before RELATIONAL (it is a subset of the
    relational lexicon) so the `lexicon_copula_be` decision path is
    actually reachable; this keeps the per-token trace's stated rule
    consistent with `sfl_compact`'s copula/existential-debit
    accounting.
    """
    t = token.lower()
    if t in MENTAL:
        return "mental", "lexicon_mental"
    if t in VERBAL:
        return "verbal", "lexicon_verbal"
    if t in COPULA_BE:
        return "relational", "lexicon_copula_be"
    if t in RELATIONAL:
        return "relational", "lexicon_relational"
    if t in BEHAVIORAL:
        return "behavioral", "lexicon_behavioral"
    if t in MATERIAL:
        return "material", "lexicon_material"
    if t in KNOWN_PLURAL_NOUNS:
        return "none", "denylist_plural_noun"
    if t in KNOWN_ADJECTIVAL_PARTICIPLES:
        return "none", "denylist_adjectival_participle"
    if t in KNOWN_NON_PROCESS:
        return "none", "denylist_non_process"
    if t.endswith("ing") and len(t) > 5:
        return "material", "morphology_ing"
    if t.endswith("ed") and len(t) > 4:
        return "material", "morphology_ed"
    # Bare -s endings are too ambiguous; refuse to claim as material.
    return "none", "default"


def classify_token(token: str) -> str:
    """Return the SFL bucket for a single token.

    Convenience wrapper over `classify_token_with_rule`; see that
    function for the full rule taxonomy.
    """
    classification, _ = classify_token_with_rule(token)
    return classification


def _shannon_entropy(counts: dict[str, int]) -> float:
    total = sum(counts.values())
    if total == 0:
        return 0.0
    probs = [c / total for c in counts.values() if c > 0]
    return -sum(p * math.log2(p) for p in probs)


def sfl_compact(tokens: Tokens) -> dict[str, float]:
    """Three-feature SFL read over a pre-tokenised Tokens struct.

    Returns NaN for every feature when below the 150-word envelope.
    `n_words` and `below_envelope` are always populated.
    """
    n_words = tokens.n_words
    if n_words < MIN_WORDS:
        return {
            "process_proxy_entropy": float("nan"),
            "stative_active_ratio": float("nan"),
            "projection_frequency": float("nan"),
            "n_words": n_words,
            "below_envelope": True,
        }

    # Existential matches over the cleaned text, not the original.
    existential_matches = EXISTENTIAL_PATTERN.findall(tokens.cleaned)
    existential_count = len(existential_matches)
    # Debit copula-BE hits absorbed by the existential pattern so we
    # don't double-count "there is" as relational + existential.
    existential_copula_debits = sum(
        1 for m in existential_matches if m.lower() in COPULA_BE
    )

    mental = verbal = relational_other = relational_copula_be = 0
    behavioral = material = 0
    for tok in tokens.words:
        if tok in MENTAL:
            mental += 1
        elif tok in VERBAL:
            verbal += 1
        elif tok in COPULA_BE:
            relational_copula_be += 1
        elif tok in RELATIONAL:
            relational_other += 1
        elif tok in BEHAVIORAL:
            behavioral += 1
        elif tok in MATERIAL:
            material += 1
        elif (tok in KNOWN_PLURAL_NOUNS
                or tok in KNOWN_ADJECTIVAL_PARTICIPLES
                or tok in KNOWN_NON_PROCESS):
            continue
        elif tok.endswith("ing") and len(tok) > 5:
            material += 1
        elif tok.endswith("ed") and len(tok) > 4:
            material += 1

    relational_copula_adjusted = max(
        0, relational_copula_be - existential_copula_debits
    )
    relational_total = relational_other + relational_copula_adjusted

    counts = {
        "mental": mental,
        "verbal": verbal,
        "relational": relational_total,
        "behavioral": behavioral,
        "existential": existential_count,
        "material": material,
    }
    entropy = _shannon_entropy(counts)
    stative = relational_total + existential_count
    active = mental + verbal + material
    stative_active_ratio = stative / max(active, 1)
    projection_frequency = (mental + verbal) / n_words * 100.0

    return {
        "process_proxy_entropy": entropy,
        "stative_active_ratio": stative_active_ratio,
        "projection_frequency": projection_frequency,
        "n_words": n_words,
        "below_envelope": False,
    }


def compute_sfl_trace(tokens: Tokens) -> dict:
    """Per-token SFL classification trace, plus existential matches.

    Compliance-grade audit trail: every token in `tokens.words` gets
    a record of its classification and the rule that fired. Existential
    pattern matches over the cleaned text are reported separately.
    `summary.counts` is the same six-bucket count `sfl_compact` feeds
    into entropy (with the copula-debit applied to relational so the
    auditor can reconcile counts → entropy without re-deriving).

    Trace shape:

        {"tokens":     [{"index", "token", "classification", "rule"}, ...],
         "existential": [{"match", "verb"}, ...],
         "summary":    {"counts": {<bucket>: int, ...},
                        "copula_existential_debit": int}}

    Below-envelope documents (n_words < 150) still get a complete
    trace; only the aggregate `sfl_compact` features are NaN.
    """
    token_records: list[dict] = []
    counts = {
        "mental": 0, "verbal": 0, "relational": 0,
        "behavioral": 0, "material": 0, "none": 0,
    }
    for i, tok in enumerate(tokens.words):
        classification, rule = classify_token_with_rule(tok)
        token_records.append({
            "index": i,
            "token": tok,
            "classification": classification,
            "rule": rule,
        })
        counts[classification] += 1

    existential_records: list[dict] = []
    for m in EXISTENTIAL_PATTERN.finditer(tokens.cleaned):
        existential_records.append({
            "match": m.group(0),
            "verb": m.group(1),
        })

    debit = sum(
        1 for r in existential_records if r["verb"].lower() in COPULA_BE
    )
    counts["relational"] = max(0, counts["relational"] - debit)
    summary_counts = {
        "mental": counts["mental"],
        "verbal": counts["verbal"],
        "relational": counts["relational"],
        "behavioral": counts["behavioral"],
        "existential": len(existential_records),
        "material": counts["material"],
    }

    return {
        "tokens": token_records,
        "existential": existential_records,
        "summary": {
            "counts": summary_counts,
            "copula_existential_debit": debit,
        },
    }
