"""bootstrap — deterministic per-feature sentence-bootstrap CIs.

The instrument's per-feature views report point estimates with no
uncertainty. This module resamples SENTENCES with replacement,
recomputes every per-feature view on each resampled document, and
reports a percentile confidence interval per feature. Short documents
get honest, wide intervals — graded reliability instead of the binary
150-word `below_envelope` cliff. Descriptive only: no flags, no
thresholds, no verdicts.

Resampling scheme (`sentence_bootstrap_paragraph_shape_v1`): draw
n_sentences indices with replacement over the FLAT sentence list, then
reassemble a document that preserves the original paragraph shape —
same paragraph count, same sentences-per-paragraph, filled in drawn
order. Sentences join with a single space, paragraphs with a blank
line. Preserving the shape keeps paragraph-sensitive features (the
extended view segments by paragraph) measured on documents with the
same macro-structure as the original.

Determinism is the contract: the PRNG is
``instrument.kernel.detrandom.DetRandom`` (SHA-256/CTR) seeded from
the document's ``input_sha256``, so the same bytes yield the same
error bars on every conforming host. Stdlib only. No file I/O. No env
reads.
"""

from __future__ import annotations

import math

from instrument.kernel.detrandom import DetRandom
from instrument.kernel.features.stylometry import (
    FEATURE_ORDER as STYLOMETRY_FEATURE_ORDER,
    stylometry_compact,
)
from instrument.kernel.quantize import q
from instrument.kernel.stats import percentile_linear, pstdev
from instrument.kernel.tokens import tokenise
from instrument.reading.distributional import (
    FEATURE_ORDER as DISTRIBUTIONAL_FEATURE_ORDER,
    distributional_reading,
)
from instrument.reading.extended import F, ALL_FEATURE_KEYS as OTHER_FEATURE_ORDER
from instrument.reading.flat import FEATURE_ORDER as SHAPER_FEATURE_ORDER, flat_reading
from instrument.types import Tokens

DEFAULT_B = 200
SCHEME = "sentence_bootstrap_paragraph_shape_v1"

# Below this many sentences a resample is more echo than sample: the
# same handful of sentences reshuffled cannot say anything about
# sampling variability. Refuse honestly instead of quoting an interval.
MIN_SENTENCES = 8

_CI_LOW_PCT = 2.5
_CI_HIGH_PCT = 97.5


def _feature_views(tokens: Tokens) -> dict:
    """One flat per-feature dict across all four scalar views.

    Composes the compact (13), extended (37), stylometry (7), and
    distributional views over a pre-tokenised struct, keyed exactly as
    the joint reading keys them (`stylometry.` / `dist.` prefixes; the
    compact and extended views carry their own framework prefixes).
    Trajectory / convergence / coherence are deliberately absent —
    they are not per-feature scalars.
    """
    flat = flat_reading(tokens)
    other = F(
        tokens.text,
        text_id="bootstrap",
        cleaned=tokens.cleaned,
        sentences_by_paragraph=tokens.paragraph_sentences,
    ).to_dict()
    stylometry_flat = stylometry_compact(tokens)
    dist_flat = distributional_reading(tokens)

    out: dict = {}
    for k in SHAPER_FEATURE_ORDER:
        if k in flat:
            out[k] = flat[k]
    for k in OTHER_FEATURE_ORDER:
        if k in other:
            out[k] = other[k]
    for k in STYLOMETRY_FEATURE_ORDER:
        out[f"stylometry.{k}"] = stylometry_flat[k]
    for k in DISTRIBUTIONAL_FEATURE_ORDER:
        out[f"dist.{k}"] = dist_flat[k]
    return out


def _reassemble(
    paragraph_shape: tuple[int, ...],
    sentences: tuple[str, ...],
    indices: list[int],
) -> str:
    """Rebuild a document from drawn sentence indices, preserving shape.

    ``paragraph_shape`` is the original sentences-per-paragraph counts;
    ``indices`` (``len == sum(paragraph_shape)``) index into the flat
    ``sentences`` tuple and are consumed in drawn order, chunked into
    paragraphs of the original sizes. Sentences join with a single
    space, paragraphs with a blank line. A zero-count paragraph (an
    original paragraph that contributed no sentences) is omitted — the
    paragraph splitter would drop the empty string anyway.
    """
    paragraphs: list[str] = []
    pos = 0
    for count in paragraph_shape:
        chunk = indices[pos:pos + count]
        pos += count
        if chunk:
            paragraphs.append(" ".join(sentences[i] for i in chunk))
    return "\n\n".join(paragraphs)


def _is_finite_number(v: object) -> bool:
    """True for int/float values that are finite (bools excluded)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    return math.isfinite(v)


def bootstrap_uncertainty(text: str, *, seed: str, b: int = DEFAULT_B) -> dict:
    """Per-feature bootstrap confidence intervals for a document.

    Resamples sentences with replacement ``b`` times (scheme: see
    module docstring and ``SCHEME``), recomputes the per-feature views
    on each replicate, and summarises each feature's replicate
    distribution.

    REPRODUCIBILITY CONTRACT — the PRNG seed string is constructed as
    ``f"{SCHEME}:{seed}"`` and fed to ``DetRandom``, i.e. the scheme
    name, one ASCII colon, then the caller's ``seed`` verbatim.
    ``seed`` is the document's ``input_sha256`` (the SHA-256 of the raw
    transport bytes), so the resample plan — and therefore every
    interval — is a pure function of the input bytes and ``b``. Same
    bytes in, same error bars out, on any conforming host.

    Returns (all floats quantised through ``kernel.quantize.q``):

        {"method": SCHEME, "b": b, "seed": seed,
         "n_sentences": n, "features": {key: {...}}}

    where each feature summary is either

        {"point", "ci_low", "ci_high", "se", "n_finite"}

    (``point`` = the unresampled value; ``ci_low`` / ``ci_high`` = the
    2.5th / 97.5th linear-interpolation percentiles of the finite
    replicate values; ``se`` = their population standard deviation), or

        {"status": "unstable_under_resampling", "n_finite": ...}

    when fewer than half the replicates produced a finite value.
    Documents with fewer than ``MIN_SENTENCES`` sentences return
    ``{"status": "too_few_sentences_for_bootstrap", ...}`` instead —
    a refusal, not an interval.
    """
    if b < 1:
        raise ValueError(f"bootstrap_uncertainty requires b >= 1, got {b}")

    tokens = tokenise(text)
    paragraph_shape = tuple(len(g) for g in tokens.paragraph_sentences)
    sentences = tokens.sentences
    n = len(sentences)
    if n < MIN_SENTENCES:
        return {
            "status": "too_few_sentences_for_bootstrap",
            "n_sentences": n,
            "method": SCHEME,
        }

    point = _feature_views(tokens)
    feature_keys = list(point)
    replicates: dict[str, list] = {k: [] for k in feature_keys}

    rng = DetRandom(f"{SCHEME}:{seed}")
    for _ in range(b):
        indices = rng.indices_with_replacement(n, n)
        rep_views = _feature_views(
            tokenise(_reassemble(paragraph_shape, sentences, indices))
        )
        for k in feature_keys:
            replicates[k].append(rep_views.get(k))

    features: dict[str, dict] = {}
    for k in feature_keys:
        # Replicate order is deterministic, so the summation order in
        # pstdev (and the sort below) is too.
        finite = [float(v) for v in replicates[k] if _is_finite_number(v)]
        n_finite = len(finite)
        if 2 * n_finite < b:
            features[k] = {
                "status": "unstable_under_resampling",
                "n_finite": n_finite,
            }
            continue
        se = pstdev(finite)
        finite.sort()
        features[k] = {
            "point": q(point[k]),
            "ci_low": q(percentile_linear(finite, _CI_LOW_PCT)),
            "ci_high": q(percentile_linear(finite, _CI_HIGH_PCT)),
            "se": q(se),
            "n_finite": n_finite,
        }

    return {
        "method": SCHEME,
        "b": b,
        "seed": seed,
        "n_sentences": n,
        "features": features,
    }
