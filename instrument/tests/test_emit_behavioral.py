from __future__ import annotations

from instrument.emit import emit
from instrument.reading.joint import joint_reading
from instrument.kernel.tokens import tokenise


def _long_text() -> str:
    base = (
        "The first sentence is here. "
        "The second sentence follows. "
        "The third sentence completes it. "
    )
    repeats = 1
    while len(base.split()) * repeats < 160:
        repeats += 1
    return base * repeats


def test_emit_metadata_n_sentences_nonzero():
    text = _long_text()
    emission = emit(text)
    assert emission.metadata.n_sentences > 0


def test_joint_reading_n_sentences_matches_tokenise():
    text = _long_text()
    jr = joint_reading(text)
    tokens = tokenise(text)
    assert jr["n_sentences"] == len(tokens.sentences)


def test_emit_n_sentences_matches_tokenise():
    text = _long_text()
    tokens = tokenise(text)
    emission = emit(text)
    assert emission.metadata.n_sentences == len(tokens.sentences)
