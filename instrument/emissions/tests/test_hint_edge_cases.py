"""CONTRACTS for hint-routed edge cases at the emit + serve surface.

Pins two previously-broken behaviours:

1. A reading routed by a VALID hint but not projectable (e.g. a
   below-envelope document → NaN features → distance None) must emit
   `register.label == "unmeasurable"`, not crash. Before the fix,
   `classify_by_max(None, ...)` raised TypeError and the HTTP layer
   returned an opaque 500.

2. An UNKNOWN hint cohort is a caller error: emit raises
   `UnknownRegisterHintError` (a ValueError) and the serve layer maps
   it to HTTP 400 with the list of available cohorts — instead of
   silently degrading the emission to "unprojectable".
"""

from __future__ import annotations

import pytest

from instrument.emissions.catalog import classify_by_max, classify_by_min, load_catalog
from instrument.emit import emit
from instrument.routing.router import (
    NoComparableReferenceError,
    UnknownRegisterHintError,
)
from instrument.serve.shape import handle

_SHORT = "This is a short paragraph about nothing in particular. " * 4
_PROSE = (
    "The committee reviewed the proposal carefully and concluded that "
    "the evidence was incomplete. They argued the costs were too high "
    "and said the decision would be deferred until further review. "
) * 12


def test_classify_by_max_none_returns_none():
    bands = load_catalog("v2").get("register", {}).get("bands", [])
    assert classify_by_max(None, bands) is None


def test_classify_by_min_none_returns_none():
    assert classify_by_min(None, [{"label": "high", "min": 0.8}]) is None


def test_emit_valid_hint_unprojectable_doc_is_unmeasurable():
    em = emit(_SHORT, register_hint="academic")
    assert em.register.label == "unmeasurable"
    assert em.register.distance is None
    assert em.register.evidence["router_match"] == "unmeasurable"


def test_http_valid_hint_unprojectable_doc_is_200():
    status, payload = handle(
        "POST", "/?shape=compact&register_hint=academic", _SHORT,
    )
    assert status == 200
    assert payload["register"] == "unmeasurable"


def test_emit_unknown_hint_raises_value_error():
    with pytest.raises(UnknownRegisterHintError):
        emit(_PROSE, register_hint="cohort_that_does_not_exist")
    # Back-compat: the new error is still a NoComparableReferenceError
    # and a ValueError.
    assert issubclass(UnknownRegisterHintError, NoComparableReferenceError)
    assert issubclass(UnknownRegisterHintError, ValueError)


def test_http_unknown_hint_is_400_with_cohort_list():
    status, payload = handle(
        "POST", "/?register_hint=cohort_that_does_not_exist", _PROSE,
    )
    assert status == 400
    assert "available cohorts" in payload["error"]
    assert "academic" in payload["error"]
