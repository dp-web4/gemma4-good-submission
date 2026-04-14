"""
SNARC — 5D salience scoring.

    Surprise + Novelty + Arousal + Reward + Conflict → composite
    score used for memory retention, policy escalation, and
    dream-consolidation selection.

    from src.snarc import Scorer, SnarcScore
    scorer = Scorer(memory_size=64)
    score = scorer.score(observation, expectation=prior_frame,
                         arousal=0.3, reward=0.8)
    if score.composite() > 0.6:
        keep_for_consolidation(observation, score)
"""

from .score import DEFAULT_WEIGHTS, SnarcScore
from .scorer import (
    ScoredObservation,
    Scorer,
    jaccard,
    novelty_against_ring,
    surprise_between,
)

__all__ = [
    "Scorer",
    "SnarcScore",
    "ScoredObservation",
    "DEFAULT_WEIGHTS",
    "jaccard",
    "novelty_against_ring",
    "surprise_between",
]
