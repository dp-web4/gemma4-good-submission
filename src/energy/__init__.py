"""
ATP/ADP — metabolic accountability.

Every action costs energy. Energy comes from an allocation signed by an
issuer. Discharged packets carry proof of value created. Overdrafts are
impossible by construction — you can't spend what you don't hold.

    from src.energy import EnergyLedger, AtpPacket, PacketState

    ledger = EnergyLedger()
    packet = ledger.issue(amount=10.0, to_lct="lct:agent", from_issuer="lct:mint")
    ledger.discharge(packet.packet_id, action_ref="r6:abc", holder_lct="lct:agent")
    ledger.settle(packet.packet_id, v3_assessment)
"""

from .ledger import EnergyLedger
from .packet import AtpPacket, EnergyError, PacketState

__all__ = [
    "EnergyLedger",
    "AtpPacket",
    "PacketState",
    "EnergyError",
]
