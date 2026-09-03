"""CONTRACTS for per-slice trajectory features."""
from __future__ import annotations
import math
from instrument.kernel.features.trajectory_features import TRAJECTORY_FEATURES, read_trajectory
from instrument.kernel.nanmath import is_nan
from instrument.kernel.tokens import tokenise

def test_trajectory_feature_names():
    assert TRAJECTORY_FEATURES == ('lexical_novelty', 'sentence_length_variance', 'modal_density', 'negation_density')

def test_slice_zero_novelty_is_nan():
    text = 'Paragraph one body text. ' * 30 + '\n\n' + 'Paragraph two body text. ' * 30
    t = tokenise(text)
    n = len(text)
    slices = [(0, n // 2), (n // 2, n)]
    traj = read_trajectory(t, slices)
    assert is_nan(traj['lexical_novelty'][0])
    assert 0.0 <= traj['lexical_novelty'][1] <= 1.0
