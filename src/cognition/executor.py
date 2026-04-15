"""
Executor — pluggable interface between the cognition loop and an actual model.

The executor takes an R6Action in EXECUTING state plus a context blob and
produces an outcome: text output, estimated quality score, and a V3 value
assessment. The cognition loop doesn't care whether the implementation is
a deterministic stub, a local Gemma 4 runtime, or a remote API call — the
interface is the same.

This file ships a single implementation: `StubExecutor`, deterministic,
no dependencies, no network. Good enough for the demo and for tests that
need a predictable outcome.

Plugging in Gemma 4
-------------------

A Gemma 4 adapter lives outside this file (future work). It would:

  1. Translate the R6Action.request into a chat-format prompt, with
     Reference entries as context
  2. Call the model (via transformers or mlx-lm)
  3. Map the model output into a text `output` plus a heuristic quality
     estimate
  4. Return an Outcome with a V3 assessment derived from the model's
     confidence and any post-hoc validation
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from ..r6.action import R6Action
from ..r6.types import V3


@dataclass
class Outcome:
    """Result of running one action. Consumed by the cognition loop to
    populate R6Action.result and to feed back into trust/salience."""

    output: Any
    quality: float  # [0, 1] — how well the action met acceptance criteria
    value: V3  # what was produced, in the value tensor
    notes: str = ""


class Executor(Protocol):
    """Minimal interface a cognition loop needs from an execution backend."""

    def execute(self, action: R6Action, context: dict | None = None) -> Outcome:
        """Run the action's request and return an outcome."""
        ...


# --------------------------------------------------------------------------
# StubExecutor — deterministic, dependency-free, demo-ready
# --------------------------------------------------------------------------


class StubExecutor:
    """A deterministic stand-in for a real model backend.

    Outcomes are derived from the action's hash so behavior is repeatable
    across runs (required for demo and test stability). Quality and value
    are drawn from the hash in [0, 1], but biased up to simulate a
    generally-competent agent.
    """

    def execute(self, action: R6Action, context: dict | None = None) -> Outcome:
        seed = int(hashlib.sha256(action.action_id.encode()).hexdigest()[:8], 16)

        def pick(offset: int, *, lo: float = 0.0, hi: float = 1.0) -> float:
            base = ((seed >> (offset * 8)) & 0xFF) / 255.0
            return lo + (hi - lo) * base

        # Bias upward: competent-but-imperfect agent
        quality = pick(0, lo=0.55, hi=0.95)
        val = V3(
            valuation=pick(1, lo=0.4, hi=0.9),
            veracity=pick(2, lo=0.5, hi=0.95),
            validity=pick(3, lo=0.6, hi=0.98),
        )
        description = action.request.description or "(no description)"
        return Outcome(
            output={
                "stub": True,
                "for": description,
                "action_id": action.action_id,
            },
            quality=quality,
            value=val,
            notes="produced by StubExecutor (deterministic)",
        )
