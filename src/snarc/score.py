"""
SnarcScore — 5-dimensional salience.

    Surprise  — divergence from expectation
    Novelty   — divergence from memory
    Arousal   — urgency / intensity of the moment
    Reward    — movement toward a goal
    Conflict  — contradiction with world model / policy

Every dimension is in [0, 1]. Composite is a weighted mean. The weights
are configurable because different situations reward different dimensions
(e.g., consolidation favors novelty + reward; alerting favors arousal +
conflict).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Default weights (sum to 1.0). Reasonable starting point.
DEFAULT_WEIGHTS: dict[str, float] = {
    "surprise": 0.25,
    "novelty": 0.25,
    "arousal": 0.15,
    "reward": 0.20,
    "conflict": 0.15,
}


def _clip(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass
class SnarcScore:
    """A 5D salience vector."""

    surprise: float = 0.0
    novelty: float = 0.0
    arousal: float = 0.0
    reward: float = 0.0
    conflict: float = 0.0

    # Free-form tags kept alongside the score — useful for diagnostics
    # without polluting the numeric interface.
    tags: list[str] = field(default_factory=list)

    def composite(self, weights: dict[str, float] | None = None) -> float:
        """Weighted mean of the five dimensions, clipped to [0, 1]."""
        w = weights if weights is not None else DEFAULT_WEIGHTS
        total_weight = sum(w.values())
        if total_weight <= 0:
            return 0.0
        total = (
            w.get("surprise", 0) * self.surprise
            + w.get("novelty", 0) * self.novelty
            + w.get("arousal", 0) * self.arousal
            + w.get("reward", 0) * self.reward
            + w.get("conflict", 0) * self.conflict
        )
        return _clip(total / total_weight)

    def above(self, threshold: float, weights: dict[str, float] | None = None) -> bool:
        return self.composite(weights) >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "surprise": self.surprise,
            "novelty": self.novelty,
            "arousal": self.arousal,
            "reward": self.reward,
            "conflict": self.conflict,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SnarcScore:
        return cls(
            surprise=float(d.get("surprise", 0.0)),
            novelty=float(d.get("novelty", 0.0)),
            arousal=float(d.get("arousal", 0.0)),
            reward=float(d.get("reward", 0.0)),
            conflict=float(d.get("conflict", 0.0)),
            tags=list(d.get("tags", [])),
        )

    # --- arithmetic helpers ---

    @classmethod
    def clamped(
        cls,
        surprise: float = 0.0,
        novelty: float = 0.0,
        arousal: float = 0.0,
        reward: float = 0.0,
        conflict: float = 0.0,
        tags: list[str] | None = None,
    ) -> SnarcScore:
        """Construct with per-dimension clipping into [0, 1]."""
        return cls(
            surprise=_clip(surprise),
            novelty=_clip(novelty),
            arousal=_clip(arousal),
            reward=_clip(reward),
            conflict=_clip(conflict),
            tags=tags or [],
        )

    def max_dim(self) -> tuple[str, float]:
        """Return (dimension_name, value) of the highest-scoring dimension."""
        pairs = [
            ("surprise", self.surprise),
            ("novelty", self.novelty),
            ("arousal", self.arousal),
            ("reward", self.reward),
            ("conflict", self.conflict),
        ]
        return max(pairs, key=lambda p: p[1])
