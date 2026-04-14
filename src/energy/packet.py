"""
ATP / ADP packets — metabolic accountability.

ATP (Allocation Transfer Packet) — energy allocated from an issuer to an
  entity. Like a charged battery. Has an amount, an origin, a destination.

ADP (Allocation Discharge Packet) — same packet after its energy has been
  spent. Carries the action it was spent on and a V3 value assessment of
  what was produced. Like a discharged battery, returnable to the pool.

Conservation
------------

Total ATP in the system equals total ATP ever issued minus total ADP
settled back to the pool. Every packet's lifecycle is:

    CHARGED → DISCHARGED → SETTLED

- CHARGED: held by an entity, not yet spent.
- DISCHARGED: spent on a specific action; value-to-be-assessed.
- SETTLED: V3 assessment recorded, packet returned to pool as ADP.

Overdraft is impossible by construction: you cannot spend a packet you
don't hold. Ledger operations are rejected when the entity doesn't have
enough CHARGED packets to cover the requested discharge.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from ..r6.types import V3


class PacketState(str, Enum):
    CHARGED = "charged"  # held, unspent
    DISCHARGED = "discharged"  # spent, value not yet assessed
    SETTLED = "settled"  # spent + assessed + returnable


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_packet_id() -> str:
    return f"atp:{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:16]}"


@dataclass
class AtpPacket:
    """A unit of metabolic energy, transferable and conserved."""

    packet_id: str = field(default_factory=_new_packet_id)
    amount: float = 0.0
    holder_lct: str = ""  # current owner
    issuer_lct: str = ""  # who minted this packet
    state: PacketState = PacketState.CHARGED

    issued_at: str = field(default_factory=_now_iso)
    discharged_at: str = ""
    settled_at: str = ""

    spent_on: str = ""  # R6 action_id this was spent on
    v3_assessment: V3 | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AtpPacket:
        v3 = d.get("v3_assessment")
        return cls(
            packet_id=d["packet_id"],
            amount=float(d.get("amount", 0.0)),
            holder_lct=d.get("holder_lct", ""),
            issuer_lct=d.get("issuer_lct", ""),
            state=PacketState(d.get("state", "charged")),
            issued_at=d.get("issued_at", ""),
            discharged_at=d.get("discharged_at", ""),
            settled_at=d.get("settled_at", ""),
            spent_on=d.get("spent_on", ""),
            v3_assessment=V3(**v3) if isinstance(v3, dict) else None,
        )

    # --- state transitions ---

    def discharge(self, action_ref: str) -> None:
        """CHARGED → DISCHARGED. Records the action this was spent on."""
        if self.state != PacketState.CHARGED:
            raise EnergyError(
                f"packet {self.packet_id} is {self.state.value}, cannot discharge"
            )
        self.state = PacketState.DISCHARGED
        self.spent_on = action_ref
        self.discharged_at = _now_iso()

    def settle(self, v3: V3) -> None:
        """DISCHARGED → SETTLED. Records the value produced."""
        if self.state != PacketState.DISCHARGED:
            raise EnergyError(
                f"packet {self.packet_id} is {self.state.value}, cannot settle"
            )
        self.state = PacketState.SETTLED
        self.v3_assessment = v3
        self.settled_at = _now_iso()


class EnergyError(Exception):
    """An energy operation violated conservation or state."""
