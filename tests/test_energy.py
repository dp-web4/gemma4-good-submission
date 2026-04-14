"""Tests for ATP/ADP energy ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.energy import AtpPacket, EnergyError, EnergyLedger, PacketState
from src.r6.types import V3


class TestPacketLifecycle:
    def test_default_state_charged(self):
        p = AtpPacket(amount=1.0, holder_lct="lct:a", issuer_lct="lct:mint")
        assert p.state == PacketState.CHARGED
        assert p.packet_id.startswith("atp:")

    def test_unique_ids(self):
        a = AtpPacket(amount=1.0)
        b = AtpPacket(amount=1.0)
        assert a.packet_id != b.packet_id

    def test_discharge_transition(self):
        p = AtpPacket(amount=1.0, holder_lct="lct:a")
        p.discharge("r6:x")
        assert p.state == PacketState.DISCHARGED
        assert p.spent_on == "r6:x"

    def test_settle_transition(self):
        p = AtpPacket(amount=1.0, holder_lct="lct:a")
        p.discharge("r6:x")
        p.settle(V3(0.5, 0.6, 0.7))
        assert p.state == PacketState.SETTLED
        assert p.v3_assessment is not None

    def test_cannot_discharge_twice(self):
        p = AtpPacket(amount=1.0, holder_lct="lct:a")
        p.discharge("r6:x")
        with pytest.raises(EnergyError):
            p.discharge("r6:y")

    def test_cannot_settle_before_discharge(self):
        p = AtpPacket(amount=1.0, holder_lct="lct:a")
        with pytest.raises(EnergyError):
            p.settle(V3())

    def test_cannot_discharge_settled(self):
        p = AtpPacket(amount=1.0, holder_lct="lct:a")
        p.discharge("r6:x")
        p.settle(V3())
        with pytest.raises(EnergyError):
            p.discharge("r6:y")

    def test_packet_roundtrip(self):
        p = AtpPacket(amount=2.5, holder_lct="lct:a", issuer_lct="lct:m")
        p.discharge("r6:x")
        p.settle(V3(0.1, 0.2, 0.3))
        restored = AtpPacket.from_dict(p.to_dict())
        assert restored.packet_id == p.packet_id
        assert restored.state == PacketState.SETTLED
        assert restored.v3_assessment.valuation == pytest.approx(0.1)


class TestIssuance:
    def test_issue_increases_balance(self):
        ledger = EnergyLedger()
        ledger.issue(amount=10.0, to_lct="lct:a", from_issuer="lct:mint")
        assert ledger.balance("lct:a") == pytest.approx(10.0)

    def test_issue_multiple_packets(self):
        ledger = EnergyLedger()
        ledger.issue(amount=3.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.issue(amount=7.0, to_lct="lct:a", from_issuer="lct:m")
        assert ledger.balance("lct:a") == pytest.approx(10.0)
        assert len(ledger.packets_held("lct:a")) == 2

    def test_issue_negative_rejected(self):
        ledger = EnergyLedger()
        with pytest.raises(EnergyError):
            ledger.issue(amount=-1.0, to_lct="lct:a", from_issuer="lct:m")

    def test_issue_zero_rejected(self):
        ledger = EnergyLedger()
        with pytest.raises(EnergyError):
            ledger.issue(amount=0.0, to_lct="lct:a", from_issuer="lct:m")

    def test_balance_excludes_others(self):
        ledger = EnergyLedger()
        ledger.issue(amount=10.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.issue(amount=5.0, to_lct="lct:b", from_issuer="lct:m")
        assert ledger.balance("lct:a") == pytest.approx(10.0)
        assert ledger.balance("lct:b") == pytest.approx(5.0)


class TestTransfer:
    def test_transfer_moves_balance(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=5.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.transfer(p.packet_id, "lct:b")
        assert ledger.balance("lct:a") == pytest.approx(0.0)
        assert ledger.balance("lct:b") == pytest.approx(5.0)

    def test_cannot_transfer_discharged(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:a")
        with pytest.raises(EnergyError):
            ledger.transfer(p.packet_id, "lct:b")


class TestDischarge:
    def test_discharge_by_holder(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:a")
        assert ledger.balance("lct:a") == pytest.approx(0.0)
        assert len(ledger.packets_discharged("lct:a")) == 1

    def test_wrong_holder_rejected(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        with pytest.raises(EnergyError, match="held by"):
            ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:b")

    def test_unknown_packet_rejected(self):
        ledger = EnergyLedger()
        with pytest.raises(EnergyError, match="unknown"):
            ledger.discharge("atp:fake", action_ref="r6:x", holder_lct="lct:a")


class TestSpend:
    def test_spend_exact_amount(self):
        ledger = EnergyLedger()
        ledger.issue(amount=5.0, to_lct="lct:a", from_issuer="lct:m")
        used = ledger.spend(holder_lct="lct:a", amount=5.0, action_ref="r6:x")
        assert len(used) == 1
        assert ledger.balance("lct:a") == pytest.approx(0.0)

    def test_spend_across_multiple_packets(self):
        ledger = EnergyLedger()
        ledger.issue(amount=2.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.issue(amount=3.0, to_lct="lct:a", from_issuer="lct:m")
        used = ledger.spend(holder_lct="lct:a", amount=4.0, action_ref="r6:x")
        assert len(used) >= 2  # at least 2 packets consumed to cover 4.0
        assert ledger.balance("lct:a") < 1.0  # some overspend possible

    def test_spend_uses_smallest_first(self):
        ledger = EnergyLedger()
        ledger.issue(amount=10.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        used = ledger.spend(holder_lct="lct:a", amount=1.0, action_ref="r6:x")
        # Should prefer the 1.0 packet (smallest first)
        assert len(used) == 1
        assert used[0].amount == pytest.approx(1.0)

    def test_overdraft_rejected(self):
        ledger = EnergyLedger()
        ledger.issue(amount=5.0, to_lct="lct:a", from_issuer="lct:m")
        with pytest.raises(EnergyError, match="insufficient"):
            ledger.spend(holder_lct="lct:a", amount=10.0, action_ref="r6:x")

    def test_overdraft_doesnt_partial_spend(self):
        """If spend raises, no packets should have been discharged."""
        ledger = EnergyLedger()
        ledger.issue(amount=5.0, to_lct="lct:a", from_issuer="lct:m")
        with pytest.raises(EnergyError):
            ledger.spend(holder_lct="lct:a", amount=10.0, action_ref="r6:x")
        assert ledger.balance("lct:a") == pytest.approx(5.0)


class TestSettle:
    def test_settle_after_discharge(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:a")
        ledger.settle(p.packet_id, V3(0.8, 0.9, 0.7))
        assert ledger._packets[p.packet_id].state == PacketState.SETTLED

    def test_settle_without_discharge_fails(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        with pytest.raises(EnergyError):
            ledger.settle(p.packet_id, V3())


class TestConservation:
    def test_issued_equals_outstanding(self):
        ledger = EnergyLedger()
        ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.issue(amount=2.5, to_lct="lct:b", from_issuer="lct:m")
        assert ledger.total_issued() == pytest.approx(3.5)
        assert ledger.total_outstanding() == pytest.approx(3.5)
        assert ledger.check_conservation()

    def test_conservation_holds_through_lifecycle(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=10.0, to_lct="lct:a", from_issuer="lct:m")
        assert ledger.check_conservation()
        ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:a")
        assert ledger.check_conservation()
        ledger.settle(p.packet_id, V3(0.5, 0.5, 0.5))
        assert ledger.check_conservation()

    def test_events_log_complete(self):
        ledger = EnergyLedger()
        p = ledger.issue(amount=1.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.transfer(p.packet_id, "lct:b")
        ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:b")
        ledger.settle(p.packet_id, V3())
        ops = [e["op"] for e in ledger.events()]
        assert ops == ["issue", "transfer", "discharge", "settle"]


class TestPersistence:
    def test_roundtrip(self, tmp_path: Path):
        ledger = EnergyLedger()
        p = ledger.issue(amount=5.0, to_lct="lct:a", from_issuer="lct:m")
        ledger.discharge(p.packet_id, action_ref="r6:x", holder_lct="lct:a")
        ledger.settle(p.packet_id, V3(0.9, 0.8, 0.7))

        path = tmp_path / "energy.json"
        ledger.save(path)
        loaded = EnergyLedger.load(path)
        assert loaded.total_issued() == pytest.approx(5.0)
        assert loaded.check_conservation()
        restored = loaded._packets[p.packet_id]
        assert restored.state == PacketState.SETTLED
        assert restored.v3_assessment.valuation == pytest.approx(0.9)


class TestR6Integration:
    def test_spend_for_r6_action(self):
        """Standard flow: R6 action wants to spend → ledger.spend → discharge records.

        Packets are indivisible, so the caller issues denominations
        appropriate for expected action costs. Here we issue 10 packets
        of 1.0 each to support fine-grained spending.
        """
        from src.r6 import R6Action, Resource

        ledger = EnergyLedger()
        for _ in range(10):
            ledger.issue(amount=1.0, to_lct="lct:agent", from_issuer="lct:mint")
        assert ledger.balance("lct:agent") == pytest.approx(10.0)

        action = R6Action(resource=Resource(estimated_cost=3.0))
        action.mark_executing()
        used = ledger.spend(
            holder_lct="lct:agent",
            amount=action.resource.estimated_cost,
            action_ref=action.action_id,
        )
        assert ledger.balance("lct:agent") == pytest.approx(7.0)
        # action's resource can be updated with actual consumption
        action.resource.cost_consumed = sum(p.amount for p in used)

        # After action completes, settle with a V3 assessment
        for p in used:
            ledger.settle(p.packet_id, V3(0.7, 0.8, 0.9))
        assert ledger.check_conservation()

    def test_packet_indivisibility_is_principled(self):
        """Packets are atomic units — issuing one 10.0 packet means you
        can't spend 3.0 without discharging the whole 10.0. Production
        would 'mint change' (discharge + re-issue smaller denominations);
        the hackathon submission keeps it simple."""
        ledger = EnergyLedger()
        ledger.issue(amount=10.0, to_lct="lct:a", from_issuer="lct:m")
        used = ledger.spend(holder_lct="lct:a", amount=3.0, action_ref="r6:x")
        # The single 10.0 packet is fully discharged to cover 3.0
        assert len(used) == 1
        assert used[0].amount == pytest.approx(10.0)
        assert ledger.balance("lct:a") == pytest.approx(0.0)
