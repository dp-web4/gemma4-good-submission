"""
EnergyLedger — holds all ATP/ADP packets, enforces conservation.

Pure bookkeeping over the packet lifecycle. No signing here; signing
happens at the boundary (issuance envelopes could be signed by the
issuer identity in a production deployment, but for the hackathon
submission the ledger is trust-internal and the boundaries are signed
via the surrounding identity + R6 audit records).

Invariant
---------

    total_issued == charged(lct) + discharged(*) + settled(*)

Overdrafts, double-spends, and settling-without-discharge all raise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from ..r6.types import V3
from .packet import AtpPacket, EnergyError, PacketState


@dataclass
class EnergyLedger:
    """Mutable registry of all packets, with transaction history."""

    _packets: dict[str, AtpPacket] = field(default_factory=dict)
    _events: list[dict] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Mint (issuance)
    # ------------------------------------------------------------------

    def issue(
        self, *, amount: float, to_lct: str, from_issuer: str
    ) -> AtpPacket:
        """Create a fresh CHARGED packet held by `to_lct`."""
        if amount <= 0:
            raise EnergyError(f"amount must be positive, got {amount}")
        packet = AtpPacket(
            amount=amount,
            holder_lct=to_lct,
            issuer_lct=from_issuer,
        )
        self._packets[packet.packet_id] = packet
        self._events.append(
            {
                "op": "issue",
                "packet_id": packet.packet_id,
                "amount": amount,
                "to": to_lct,
                "from": from_issuer,
            }
        )
        return packet

    # ------------------------------------------------------------------
    # Transfer (CHARGED packet changes hands)
    # ------------------------------------------------------------------

    def transfer(self, packet_id: str, to_lct: str) -> AtpPacket:
        packet = self._require(packet_id)
        if packet.state != PacketState.CHARGED:
            raise EnergyError(
                f"only CHARGED packets can transfer; {packet_id} is {packet.state.value}"
            )
        prior = packet.holder_lct
        packet.holder_lct = to_lct
        self._events.append(
            {
                "op": "transfer",
                "packet_id": packet_id,
                "from": prior,
                "to": to_lct,
            }
        )
        return packet

    # ------------------------------------------------------------------
    # Discharge — spend a packet on an R6 action
    # ------------------------------------------------------------------

    def discharge(
        self, packet_id: str, *, action_ref: str, holder_lct: str
    ) -> AtpPacket:
        """Mark packet as spent on `action_ref`. Caller must own the packet."""
        packet = self._require(packet_id)
        if packet.holder_lct != holder_lct:
            raise EnergyError(
                f"packet {packet_id} held by {packet.holder_lct!r}, "
                f"not {holder_lct!r}"
            )
        packet.discharge(action_ref)
        self._events.append(
            {
                "op": "discharge",
                "packet_id": packet_id,
                "action_ref": action_ref,
                "holder": holder_lct,
            }
        )
        return packet

    def spend(
        self,
        *,
        holder_lct: str,
        amount: float,
        action_ref: str,
    ) -> list[AtpPacket]:
        """Discharge enough CHARGED packets held by `holder_lct` to cover `amount`.

        Greedy: uses smallest-first packets to minimize overspend. Returns
        the discharged packets. Raises if the holder doesn't have enough
        CHARGED balance.
        """
        if amount <= 0:
            raise EnergyError(f"amount must be positive, got {amount}")
        charged = sorted(
            (p for p in self._packets.values()
             if p.state == PacketState.CHARGED and p.holder_lct == holder_lct),
            key=lambda p: p.amount,
        )
        total_available = sum(p.amount for p in charged)
        if total_available < amount:
            raise EnergyError(
                f"insufficient energy: need {amount}, have {total_available} for {holder_lct}"
            )

        used: list[AtpPacket] = []
        covered = 0.0
        for p in charged:
            if covered >= amount:
                break
            self.discharge(p.packet_id, action_ref=action_ref, holder_lct=holder_lct)
            used.append(p)
            covered += p.amount
        return used

    # ------------------------------------------------------------------
    # Settle — record the value produced, packet becomes ADP
    # ------------------------------------------------------------------

    def settle(self, packet_id: str, v3: V3) -> AtpPacket:
        packet = self._require(packet_id)
        packet.settle(v3)
        self._events.append(
            {
                "op": "settle",
                "packet_id": packet_id,
                "v3_composite": v3.composite(),
            }
        )
        return packet

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def balance(self, lct: str) -> float:
        """Sum of CHARGED packet amounts held by `lct`."""
        return sum(
            p.amount for p in self._packets.values()
            if p.holder_lct == lct and p.state == PacketState.CHARGED
        )

    def packets_held(self, lct: str) -> list[AtpPacket]:
        return [
            p for p in self._packets.values()
            if p.holder_lct == lct and p.state == PacketState.CHARGED
        ]

    def packets_discharged(self, lct: str) -> list[AtpPacket]:
        return [
            p for p in self._packets.values()
            if p.holder_lct == lct and p.state == PacketState.DISCHARGED
        ]

    def all_packets(self) -> list[AtpPacket]:
        return list(self._packets.values())

    def events(self) -> list[dict]:
        return list(self._events)

    # ------------------------------------------------------------------
    # Conservation check
    # ------------------------------------------------------------------

    def total_issued(self) -> float:
        return sum(e["amount"] for e in self._events if e["op"] == "issue")

    def total_outstanding(self) -> float:
        """Sum of amounts across all packets regardless of state."""
        return sum(p.amount for p in self._packets.values())

    def check_conservation(self) -> bool:
        """total_issued should equal total_outstanding (nothing minted out of band)."""
        return abs(self.total_issued() - self.total_outstanding()) < 1e-9

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        data = {
            "packets": {pid: p.to_dict() for pid, p in self._packets.items()},
            "events": list(self._events),
        }
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=False))

    @classmethod
    def load(cls, path: str | Path) -> EnergyLedger:
        with open(path) as f:
            data = json.load(f)
        ledger = cls()
        for pid, pd in data.get("packets", {}).items():
            ledger._packets[pid] = AtpPacket.from_dict(pd)
        ledger._events = list(data.get("events", []))
        return ledger

    # ------------------------------------------------------------------

    def _require(self, packet_id: str) -> AtpPacket:
        p = self._packets.get(packet_id)
        if p is None:
            raise EnergyError(f"unknown packet: {packet_id}")
        return p
