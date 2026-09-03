"""CONTRACTS for SFL compact view:
- classify_token returns expected buckets for canonical probes
- sfl_compact returns NaN below 150-word envelope
- sfl_compact matches the legacy shaper.instruments.sfl.read output
"""
from __future__ import annotations
import math
from instrument.kernel.features.sfl import KNOWN_ADJECTIVAL_PARTICIPLES, KNOWN_PLURAL_NOUNS, classify_token, classify_token_with_rule, compute_sfl_trace, sfl_compact
from instrument.kernel.nanmath import is_nan
from instrument.kernel.tokens import tokenise
PROBES = [('think', 'mental', 'cognition verb'), ('believes', 'mental', 'cognition verb'), ('said', 'verbal', 'reporting verb'), ('argued', 'verbal', 'speech act verb'), ('is', 'relational', 'copula'), ('became', 'relational', 'change-of-state copula'), ('has', 'relational', 'possession'), ('laughed', 'behavioral', 'behavioral process'), ('breathed', 'behavioral', 'behavioral process'), ('tables', 'none', 'plural noun'), ('chairs', 'none', 'plural noun'), ('walks', 'material', 'material lexicon entry (0.9.1: lexicon beats the ambiguous--s refusal)'), ('running', 'material', 'material lexicon entry'), ('walked', 'material', 'material lexicon entry'), ('make', 'material', 'base-form material verb (0.9.1)'), ('build', 'material', 'base-form material verb (0.9.1)'), ('interesting', 'none', 'adjectival participle'), ('tired', 'none', 'adjectival participle'), ('data', 'none', 'not a verb'), ('system', 'none', 'not a verb')]

def test_classify_token_canonical_probes():
    failures = []
    for token, expected, reason in PROBES:
        got = classify_token(token)
        if got != expected:
            failures.append(f'{token!r} expected {expected} ({reason}), got {got}')
    assert not failures, failures

def test_guards_are_frozensets():
    assert isinstance(KNOWN_PLURAL_NOUNS, frozenset)
    assert isinstance(KNOWN_ADJECTIVAL_PARTICIPLES, frozenset)

def test_sfl_compact_below_envelope_returns_nan():
    short = 'hello world. ' * 5
    reading = sfl_compact(tokenise(short))
    assert reading['below_envelope'] is True
    assert is_nan(reading['process_proxy_entropy'])
    assert is_nan(reading['stative_active_ratio'])
    assert is_nan(reading['projection_frequency'])

def test_sfl_compact_above_envelope_returns_real_numbers():
    text = 'The researcher thought about the problem carefully. She believed that a solution existed. She said it would take time. She argued the evidence was strong. The results were published. ' * 10
    reading = sfl_compact(tokenise(text))
    assert reading['below_envelope'] is False
    assert reading['n_words'] >= 150
    assert reading['process_proxy_entropy'] >= 0.0
    assert reading['process_proxy_entropy'] < math.log2(6) + 0.01
    assert reading['stative_active_ratio'] >= 0.0
    assert reading['projection_frequency'] >= 0.0


def test_classify_token_with_rule_taxonomy():
    cases = [
        ('think', 'mental', 'lexicon_mental'),
        ('said', 'verbal', 'lexicon_verbal'),
        ('became', 'relational', 'lexicon_relational'),
        ('is', 'relational', 'lexicon_copula_be'),
        ('laughed', 'behavioral', 'lexicon_behavioral'),
        ('tables', 'none', 'denylist_plural_noun'),
        ('interesting', 'none', 'denylist_adjectival_participle'),
        ('running', 'material', 'lexicon_material'),
        ('walked', 'material', 'lexicon_material'),
        ('make', 'material', 'lexicon_material'),
        ('refactoring', 'material', 'morphology_ing'),
        ('whereupon', 'none', 'default'),
    ]
    failures = []
    for token, expected_class, expected_rule in cases:
        got_class, got_rule = classify_token_with_rule(token)
        if (got_class, got_rule) != (expected_class, expected_rule):
            failures.append(
                f'{token!r}: expected ({expected_class!r}, {expected_rule!r}), '
                f'got ({got_class!r}, {got_rule!r})'
            )
    assert not failures, failures


def test_compute_sfl_trace_counts_match_compact_aggregate():
    """Trace summary counts must reconcile with what sfl_compact aggregates.

    Auditor reads the trace, sums per-bucket counts, derives entropy
    independently, and confirms the headline number.
    """
    text = 'The researcher thought about the problem carefully. She believed that a solution existed. She said it would take time. She argued the evidence was strong. The results were published. ' * 10
    tokens = tokenise(text)
    trace = compute_sfl_trace(tokens)
    compact = sfl_compact(tokens)

    # Every word token in tokens.words has a record (1:1).
    assert len(trace['tokens']) == len(tokens.words)
    # Every record carries the four required keys.
    for rec in trace['tokens']:
        assert set(rec.keys()) == {'index', 'token', 'classification', 'rule'}

    # Trace summary entropy == compact process_proxy_entropy.
    counts = trace['summary']['counts']
    total = sum(counts.values())
    h = 0.0
    for c in counts.values():
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    assert abs(h - compact['process_proxy_entropy']) < 1e-9


def test_compute_sfl_trace_runs_below_envelope():
    """Below-envelope docs still get a complete trace; only sfl_compact NaNs."""
    short = 'The cat sat. The dog ran. '
    trace = compute_sfl_trace(tokenise(short))
    assert 'tokens' in trace
    assert 'summary' in trace
    assert len(trace['tokens']) > 0
