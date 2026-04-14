"""
Scorer — produce SNARC scores from observations.

The scorer holds a bounded memory ring. Each `score()` call:

  - computes novelty from similarity against the memory ring
  - computes surprise from divergence against a caller-supplied expectation
  - accepts arousal / reward / conflict as explicit signals from the caller
    (these come from policy evaluation, reward shaping, and world-model
    consistency checks elsewhere in the loop)
  - appends the observation to the memory ring after scoring

Observations can be strings, dicts, or any object convertible to a stable
string (used for similarity). For dicts we canonicalize (sorted JSON).

Similarity is character-level Jaccard on tokens. Simple, dependency-free,
deterministic. Good enough for novelty scoring at the hackathon scale;
production swaps in embeddings.
"""

from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from typing import Any

from .score import SnarcScore


def _canonicalize(obs: Any) -> str:
    if isinstance(obs, str):
        return obs
    if isinstance(obs, (dict, list)):
        return json.dumps(obs, sort_keys=True, default=str)
    return str(obs)


def _tokens(text: str) -> set[str]:
    """Simple whitespace-split tokens, lowercased."""
    return {t.lower() for t in text.split() if t}


def jaccard(a: str, b: str) -> float:
    """Jaccard similarity over whitespace-split token sets."""
    ta = _tokens(a)
    tb = _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def novelty_against_ring(canonical: str, ring: deque[str]) -> float:
    """Novelty = 1 - max similarity to any item in memory.

    Empty memory → fully novel (1.0).
    Exact repeat of any recent item → 0.0 novelty.
    """
    if not ring:
        return 1.0
    best = max(jaccard(canonical, past) for past in ring)
    return max(0.0, 1.0 - best)


def surprise_between(observation: Any, expectation: Any) -> float:
    """Surprise = 1 - similarity(observation, expectation).

    If no expectation is provided, surprise is zero (nothing to be
    surprised relative to)."""
    if expectation is None:
        return 0.0
    return max(0.0, 1.0 - jaccard(_canonicalize(observation), _canonicalize(expectation)))


@dataclass
class ScoredObservation:
    """An observation with its assigned SNARC score."""

    observation: Any
    score: SnarcScore


class Scorer:
    """SNARC scorer with bounded novelty memory."""

    def __init__(self, memory_size: int = 64) -> None:
        self._ring: deque[str] = deque(maxlen=memory_size)

    @property
    def memory(self) -> list[str]:
        return list(self._ring)

    def score(
        self,
        observation: Any,
        *,
        expectation: Any = None,
        arousal: float = 0.0,
        reward: float = 0.0,
        conflict: float = 0.0,
        tags: list[str] | None = None,
    ) -> SnarcScore:
        """Score an observation and append it to the memory ring."""
        canonical = _canonicalize(observation)
        novelty = novelty_against_ring(canonical, self._ring)
        surprise = surprise_between(observation, expectation)

        sc = SnarcScore.clamped(
            surprise=surprise,
            novelty=novelty,
            arousal=arousal,
            reward=reward,
            conflict=conflict,
            tags=tags,
        )

        self._ring.append(canonical)
        return sc

    def clear(self) -> None:
        """Empty the memory ring. Useful for test isolation and scope resets."""
        self._ring.clear()
