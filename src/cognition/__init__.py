"""
Cognition — the integration loop.

    loop = CognitionLoop(
        identity=provider, role_id="lct:agent/player", role_context="game",
        scope="arc-agi-3-player", laws=law_registry, energy=energy_ledger,
        trust=trust_ledger, snarc=Scorer(), consolidator=Consolidator(...),
        gate=PolicyGate(evaluator_lct="lct:judge", evaluator=evaluator_id),
        executor=StubExecutor(),   # or your Gemma 4 adapter
    )

    report = loop.tick(observation, request_description="click at (12,34)",
                      estimated_cost=1.0)
    # TickReport carries: signed Action + signed Decision + SNARC score +
    # Outcome + energy accounting. One tick = one full audit bundle.
"""

from .executor import Executor, Outcome, StubExecutor
from .loop import CognitionLoop, TickReport

__all__ = [
    "CognitionLoop",
    "TickReport",
    "Executor",
    "Outcome",
    "StubExecutor",
]
