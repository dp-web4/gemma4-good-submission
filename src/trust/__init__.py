"""
T3/V3 evolution — live trust and value tensors.

T3 (Talent/Training/Temperament) measures role capability.
V3 (Valuation/Veracity/Validity) measures result quality.

R6Action records carry *snapshots* of T3 at action time. The ledger here
holds *current* values and the append-only observation history.

    from src.trust import TrustLedger
    ledger = TrustLedger()
    ledger.observe_t3("lct:nomad/agent", training=1.0, action_ref="r6:abc")
    current = ledger.snapshot_t3("lct:nomad/agent")
"""

from ..r6.types import T3, V3
from .ledger import (
    BASE_RATE,
    DECAY,
    MIN_RATE,
    ObservationRecord,
    RoleTrust,
    TrustLedger,
    effective_rate,
    update_scalar,
)

__all__ = [
    "TrustLedger",
    "RoleTrust",
    "ObservationRecord",
    "T3",
    "V3",
    "update_scalar",
    "effective_rate",
    "BASE_RATE",
    "DECAY",
    "MIN_RATE",
]
