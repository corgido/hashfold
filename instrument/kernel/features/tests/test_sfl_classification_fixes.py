"""CONTRACTS for SFL classification corrections.

1. Closed-class -ing/-ed grammatical words (indefinite pronouns,
   prepositions, adverbs, numerals) must NOT be swept into the
   material bucket by the morphology fallback. These are
   high-frequency in LLM prose ("something", "including",
   "according to", "indeed"), so the false positives systematically
   inflated material counts on exactly the instrument's target
   input class.

2. The `lexicon_copula_be` decision path must be reachable.
   COPULA_BE is a subset of the relational lexicon; with the
   relational check first, the per-token audit trace claimed a rule
   (`lexicon_relational`) different from the accounting path
   `sfl_compact` actually uses for the existential copula debit.
"""

from __future__ import annotations

from instrument.kernel.features.sfl import (
    classify_token_with_rule,
    compute_sfl_trace,
    sfl_compact,
)
from instrument.kernel.tokens import tokenise


def test_grammatical_ing_ed_words_are_not_material():
    # NB: "including" / "regarding" are lexicon-owned (relational) and
    # therefore not in this denylist — the lexicon check fires first.
    for tok in ("something", "anything", "everything", "nothing",
                "during", "according", "indeed", "hundred"):
        classification, rule = classify_token_with_rule(tok)
        assert classification == "none", (tok, classification, rule)
        assert rule == "denylist_non_process", (tok, rule)


def test_real_verbs_still_classify_material_by_morphology():
    # Not in any lexicon/denylist; should still fall through to
    # morphology.
    assert classify_token_with_rule("refactored") == ("material", "morphology_ed")
    assert classify_token_with_rule("deploying") == ("material", "morphology_ing")


def test_copula_rule_is_reachable_and_trace_matches_compact():
    classification, rule = classify_token_with_rule("is")
    assert classification == "relational"
    assert rule == "lexicon_copula_be"

    text = (
        "There is a problem. The system is slow because the cache is "
        "cold, and the operators believe the fix is simple. They said "
        "the deployment was delayed. "
    ) * 10
    tokens = tokenise(text)
    trace = compute_sfl_trace(tokens)
    compact = sfl_compact(tokens)

    # The trace's reconciled counts must reproduce the compact
    # entropy inputs: the copula/existential debit applies in both.
    counts = trace["summary"]["counts"]
    assert counts["existential"] > 0
    assert trace["summary"]["copula_existential_debit"] > 0
    assert compact["below_envelope"] is False

    copula_rules = {
        r["rule"] for r in trace["tokens"] if r["token"] == "is"
    }
    assert copula_rules == {"lexicon_copula_be"}
