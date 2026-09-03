"""FeatureVector composition for the extended view.

`F(text)` returns a fixed-length feature vector combining SFL
(11) + RST (13) + cohesion (13) — 37 features in positional order.
The order is stable across calls; appending a feature requires
bumping `SCHEMA_VERSION` in `reading.joint`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from instrument.reading.document import Document, parse
from instrument.reading.extended import cohesion, rst, sfl

SFL_FEATURE_KEYS: list[str] = [
    "pct_material", "pct_mental", "pct_relational",
    "pct_verbal", "pct_behavioral", "pct_existential",
    "process_density", "modal_density",
    "hedge_density", "booster_density", "modality_balance",
]

RST_FEATURE_KEYS: list[str] = [
    "contrast_density", "concession_density",
    "cause_density", "result_density",
    "elaboration_density", "sequence_density",
    "condition_density", "purpose_density", "summary_density",
    "total_marker_density", "relation_diversity",
    "branching_score", "max_depth_score",
]

COHESION_FEATURE_KEYS: list[str] = [
    "pronoun_density", "demonstrative_density",
    "definite_article_density", "reference_density",
    "additive_density", "adversative_density",
    "causal_density", "temporal_density",
    "conjunction_balance", "type_token_ratio",
    "lexical_repetition_rate", "lexical_chain_count",
    "lexical_chain_span",
]

ALL_FEATURE_KEYS: list[str] = (
    [f"sfl.{k}" for k in SFL_FEATURE_KEYS]
    + [f"rst.{k}" for k in RST_FEATURE_KEYS]
    + [f"coh.{k}" for k in COHESION_FEATURE_KEYS]
)


@dataclass
class FeatureVector:
    text_id: str
    n_words: int
    n_sentences: int
    n_paragraphs: int
    sfl: dict = field(default_factory=dict)
    rst: dict = field(default_factory=dict)
    cohesion: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        out: dict = {
            "text_id": self.text_id,
            "n_words": self.n_words,
            "n_sentences": self.n_sentences,
            "n_paragraphs": self.n_paragraphs,
        }
        for k in SFL_FEATURE_KEYS:
            out[f"sfl.{k}"] = self.sfl.get(k, 0.0)
        for k in RST_FEATURE_KEYS:
            out[f"rst.{k}"] = self.rst.get(k, 0.0)
        for k in COHESION_FEATURE_KEYS:
            out[f"coh.{k}"] = self.cohesion.get(k, 0.0)
        return out

    def to_vector(self) -> list[float]:
        """Return the 37-dim numeric vector in canonical order."""
        v: list[float] = []
        for k in SFL_FEATURE_KEYS:
            v.append(self.sfl.get(k, 0.0))
        for k in RST_FEATURE_KEYS:
            v.append(self.rst.get(k, 0.0))
        for k in COHESION_FEATURE_KEYS:
            v.append(self.cohesion.get(k, 0.0))
        return v


def F(
    text: str,
    text_id: str = "anon",
    *,
    cleaned: str | None = None,
    sentences_by_paragraph: tuple[tuple[str, ...], ...] | None = None,
) -> FeatureVector:
    """Compute the joint feature vector for a text."""
    doc = parse(
        text, cleaned=cleaned, sentences_by_paragraph=sentences_by_paragraph,
    )
    return F_from_doc(doc, text_id)


def F_from_doc(doc: Document, text_id: str = "anon") -> FeatureVector:
    """Compute the joint feature vector from a pre-parsed Document."""
    return FeatureVector(
        text_id=text_id,
        n_words=doc.n_words,
        n_sentences=doc.n_sentences,
        n_paragraphs=doc.n_paragraphs,
        sfl=sfl.analyse(doc),
        rst=rst.analyse(doc),
        cohesion=cohesion.analyse(doc),
    )
