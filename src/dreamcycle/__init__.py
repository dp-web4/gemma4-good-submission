"""
Dreamcycle — sleep/wake consolidation that turns experience into training data.

    cons = Consolidator(machine="nomad", instance_lct="lct:nomad/agent",
                        model="gemma-4-e4b-it", session="2026-04-14",
                        salience_threshold=0.5)
    cons.record(action, decision=decision, snarc=snarc)
    bundle = cons.consolidate()        # filters by salience, exports
    bundle.save("dreams/today.json")

The exported DreamBundle is the audit-grade training example shape.
Reloading the bundle in tomorrow's session injects today's salient
experience as priors — closing the loop.
"""

from .bundle import DreamBundle, DreamEntry
from .consolidator import Consolidator, WakeRecord

__all__ = [
    "Consolidator",
    "WakeRecord",
    "DreamBundle",
    "DreamEntry",
]
