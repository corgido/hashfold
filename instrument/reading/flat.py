"""flat — the 13-feature compact view.

Composes kernel features into the canonical 13-feature reading
used by the embedder and the joint composer. Tokenises the text
ONCE and threads the same `Tokens` struct through every feature
module — no re-tokenisation in the hot path (§5.1 of the plan).

The output schema mirrors the legacy `shaper.instruments.flat_reading`:

    {
      "sfl.process_proxy_entropy": float,
      "sfl.stative_active_ratio":  float,
      "sfl.projection_frequency":  float,
      "rst.marker_density":        float,
      "rst.elaboration_marker_density":  float,
      "rst.contrast_marker_density":     float,
      "cohesion.type_token_ratio":  float,
      "cohesion.pronoun_density":   float,
      "cohesion.lexical_repetition": float,
      "register.lexical_novelty":            float,
      "register.sentence_length_variance":   float,
      "register.modal_density":              float,
      "register.negation_density":           float,
      "n_words":        int,
      "below_envelope": bool,
    }
"""

from __future__ import annotations

from instrument.kernel.features import cohesion, register, rst, sfl
from instrument.kernel.tokens import tokenise
from instrument.types import Tokens

FEATURE_ORDER: tuple[str, ...] = (
    "sfl.process_proxy_entropy",
    "sfl.stative_active_ratio",
    "sfl.projection_frequency",
    "rst.marker_density",
    "rst.elaboration_marker_density",
    "rst.contrast_marker_density",
    "cohesion.type_token_ratio",
    "cohesion.pronoun_density",
    "cohesion.lexical_repetition",
    "register.lexical_novelty",
    "register.sentence_length_variance",
    "register.modal_density",
    "register.negation_density",
)


def read(tokens: Tokens) -> dict:
    """Return the four-bucket reading over a pre-tokenised struct."""
    return {
        "sfl": sfl.sfl_compact(tokens),
        "rst": rst.rst_compact(tokens),
        "cohesion": cohesion.cohesion_compact(tokens),
        "register": register.register_read(tokens),
    }


def flat_reading(tokens: Tokens) -> dict:
    """Return the 13-feature flat dict + `n_words` + `below_envelope`.

    Composition matches legacy `shaper.instruments.flat_reading`
    exactly: four buckets → flattened with `<framework>.<feature>`
    keys; `n_words` and `below_envelope` propagated from the SFL
    reading (which is the canonical gate).
    """
    r = read(tokens)
    out: dict = {}
    for framework, features in r.items():
        for k, v in features.items():
            if k in ("n_words", "below_envelope"):
                continue
            out[f"{framework}.{k}"] = v
    out["n_words"] = r["sfl"]["n_words"]
    out["below_envelope"] = r["sfl"]["below_envelope"]
    return out


def flat_reading_from_text(text: str) -> dict:
    """Entry point from raw text. Tokenises once, then reads.

    Legacy callers that pass `text` hit this; new callers that
    already have a `Tokens` struct call `flat_reading(tokens)`
    directly, saving the tokenisation cost.
    """
    return flat_reading(tokenise(text))
