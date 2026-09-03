"""CONTRACT: the MATERIAL process bucket is lexicon-driven (0.9.1).

SCOPE.md claims six process buckets classified via the pinned lexicon
tree. Before 0.9.1 the shaper never consulted the 656-word
`processes_material` lexicon — material was detected purely by
`-ing`/`-ed` morphology, so 41 of the 77 most common English verbs
(make, run, build, ...) went unclassified and the deny-lists existed
to patch morphology noise. The classifier now consults the MATERIAL
lexicon after BEHAVIORAL and before the deny-lists (rule id
`lexicon_material`); morphology remains the fallback for inflected
forms outside the lexicons.
"""

from __future__ import annotations

from instrument.kernel.features.sfl import (
    classify_token_with_rule,
    compute_sfl_trace,
    sfl_compact,
)
from instrument.kernel.tokens import tokenise


def test_base_form_material_verbs_classify_via_lexicon():
    for tok in ("make", "run", "build", "take", "give", "create",
                "alter", "bake", "arrive"):
        assert classify_token_with_rule(tok) == ("material", "lexicon_material"), tok


def test_earlier_buckets_keep_precedence_over_material():
    # Overlap tokens stay with their semantically-primary bucket.
    assert classify_token_with_rule("read") == ("verbal", "lexicon_verbal")
    assert classify_token_with_rule("carry") == ("relational", "lexicon_relational")
    assert classify_token_with_rule("shake") == ("behavioral", "lexicon_behavioral")


def test_lexicon_wins_over_denylists_for_the_three_flips():
    # The deny-lists guard the morphology fallback, not the lexicon.
    # Exactly these three tokens flip from denylist-none to material
    # (documented in CHANGES-0.9.1.md).
    for tok in ("works", "developed", "following"):
        assert classify_token_with_rule(tok) == ("material", "lexicon_material"), tok


def test_denylists_still_guard_morphology():
    # Not in any lexicon; the deny-lists must still stop the -s/-ing/-ed
    # morphology noise.
    assert classify_token_with_rule("ceilings") == ("none", "denylist_plural_noun")
    assert classify_token_with_rule("interesting") == (
        "none", "denylist_adjectival_participle"
    )
    assert classify_token_with_rule("something") == ("none", "denylist_non_process")


def test_morphology_fallback_survives_for_unlexiconed_inflections():
    # Not in the material lexicon (inflected/derived form) -> morphology.
    cls, rule = classify_token_with_rule("refactoring")
    assert cls == "material" and rule == "morphology_ing"


def test_aggregate_and_trace_reconcile():
    text = (
        "Engineers build bridges and create tools. They make plans and "
        "run tests. The team said the results were good and believed "
        "the design would hold. Workers take measurements and give "
        "reports while the manager watches quietly. "
    ) * 8
    tokens = tokenise(text)
    trace = compute_sfl_trace(tokens)
    compact = sfl_compact(tokens)
    assert compact["below_envelope"] is False
    # The trace's per-token records must agree with the classifier.
    for rec in trace["tokens"]:
        assert (rec["classification"], rec["rule"]) == classify_token_with_rule(
            rec["token"]
        )
    # And the reconciliation property SCOPE.md promises the auditor:
    # trace summary counts equal the counts sfl_compact feeds entropy.
    from instrument.kernel.features.sfl import _shannon_entropy
    assert abs(
        _shannon_entropy(trace["summary"]["counts"])
        - compact["process_proxy_entropy"]
    ) < 1e-12
