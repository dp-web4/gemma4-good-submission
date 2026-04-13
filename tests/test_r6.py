"""Tests for the R6 action grammar."""

from __future__ import annotations

import json

import pytest

from src.r6 import (
    ActionStatus,
    ActionType,
    Priority,
    R6Action,
    Reference,
    Request,
    Resource,
    Result,
    Role,
    Rules,
    T3,
    V3,
    WitnessAttestation,
    from_dict,
    from_json,
    to_dict,
    to_json,
)


class TestTypes:
    def test_t3_composite(self):
        t = T3(talent=0.4, training=0.6, temperament=0.8)
        assert t.composite() == pytest.approx(0.6)

    def test_v3_composite(self):
        v = V3(valuation=0.1, veracity=0.2, validity=0.3)
        assert v.composite() == pytest.approx(0.2)

    def test_rules_permits(self):
        r = Rules(permission_scope=["read", "write"])
        assert r.permits("read") is True
        assert r.permits("delete") is False

    def test_rules_budget(self):
        r = Rules(constraints={"max_cost": 10.0})
        assert r.within_budget(5.0) is True
        assert r.within_budget(15.0) is False

    def test_rules_timeout(self):
        r = Rules(constraints={"timeout_s": 30.0})
        assert r.within_timeout(20.0) is True
        assert r.within_timeout(60.0) is False

    def test_role_has_permission(self):
        r = Role(role_id="r:1", context="test", delegated_permissions=["a"])
        assert r.has_permission("a") is True
        assert r.has_permission("b") is False

    def test_resource_can_afford(self):
        r = Resource(cost_allocated=10.0, estimated_cost=5.0)
        assert r.can_afford() is True
        r2 = Resource(cost_allocated=3.0, estimated_cost=5.0)
        assert r2.can_afford() is False

    def test_resource_remaining(self):
        r = Resource(cost_allocated=10.0, cost_consumed=3.0)
        assert r.remaining() == pytest.approx(7.0)


class TestR6Action:
    def test_defaults(self):
        a = R6Action()
        assert a.status == ActionStatus.PENDING
        assert a.action_id.startswith("r6:")
        assert a.timestamp  # non-empty iso
        assert a.result.output is None

    def test_unique_ids(self):
        a, b = R6Action(), R6Action()
        assert a.action_id != b.action_id

    def test_confidence_calculation(self):
        a = R6Action(
            role=Role(role_id="r", context="c", t3=T3(0.6, 0.6, 0.6)),
            resource=Resource(cost_allocated=10.0, estimated_cost=5.0),
        )
        c = a.calc_confidence(risk_factor=0.8)
        assert c.role_capability == pytest.approx(0.6)
        assert c.resource_availability == pytest.approx(1.0)
        assert c.risk_assessment == pytest.approx(0.8)
        assert 0 < c.overall() < 1

    def test_confidence_no_reference(self):
        a = R6Action()
        c = a.calc_confidence()
        # neutral historical prior when no similar_actions
        assert c.historical_success == pytest.approx(0.5)

    def test_confidence_with_reference(self):
        a = R6Action(reference=Reference(similar_actions=["x", "y", "z"]))
        c = a.calc_confidence()
        assert c.historical_success > 0.5
        assert c.historical_success <= 1.0

    def test_lifecycle(self):
        a = R6Action()
        assert a.status == ActionStatus.PENDING
        a.mark_executing()
        assert a.status == ActionStatus.EXECUTING
        a.mark_completed(Result(output="ok"))
        assert a.status == ActionStatus.COMPLETED
        assert a.result.output == "ok"

    def test_failure_records_side_effect(self):
        a = R6Action()
        a.mark_failed("network timeout")
        assert a.status == ActionStatus.FAILED
        assert "network timeout" in a.result.side_effects

    def test_denied_records_reason(self):
        a = R6Action()
        a.mark_denied("permission")
        assert a.status == ActionStatus.DENIED
        assert any("permission" in s for s in a.result.side_effects)


class TestSerialization:
    def _make_rich_action(self) -> R6Action:
        return R6Action(
            rules=Rules(
                governing_contracts=["web4:core"],
                permission_scope=["tool:read", "tool:compute"],
                constraints={"max_cost": 100.0, "timeout_s": 30.0},
            ),
            role=Role(
                role_id="lct:agent:42",
                context="game-player",
                delegated_permissions=["play"],
                t3=T3(0.7, 0.8, 0.6),
            ),
            request=Request(
                action_type=ActionType.ACT,
                description="click at (12, 34)",
                acceptance_criteria=["frame changes"],
                priority=Priority.HIGH,
                deadline="2026-05-18T00:00:00Z",
            ),
            reference=Reference(
                current_observation={"grid_w": 64, "grid_h": 64},
                similar_actions=["r6:abc", "r6:def"],
                relevant_memory=["saw_this_before"],
                horizon_depth=3,
            ),
            resource=Resource(
                cost_allocated=10.0,
                cost_consumed=2.5,
                compute_units=1,
                data_access=["frame_buffer"],
                estimated_cost=1.0,
            ),
            initiator_id="lct:nomad:gemma4-e4b",
        )

    def test_roundtrip_dict(self):
        a = self._make_rich_action()
        d = to_dict(a)
        b = from_dict(d)
        assert b.action_id == a.action_id
        assert b.initiator_id == a.initiator_id
        assert b.request.action_type == ActionType.ACT
        assert b.request.priority == Priority.HIGH
        assert b.role.t3.talent == pytest.approx(0.7)
        assert b.rules.constraints == {"max_cost": 100.0, "timeout_s": 30.0}
        assert b.reference.similar_actions == ["r6:abc", "r6:def"]
        assert b.resource.cost_allocated == pytest.approx(10.0)

    def test_roundtrip_json(self):
        a = self._make_rich_action()
        a.mark_completed(
            Result(
                output={"clicked": True},
                witnesses=[
                    WitnessAttestation(
                        witness_id="lct:witness",
                        attestation_type="quality",
                        signature="abc",
                    )
                ],
            )
        )
        text = to_json(a)
        # valid JSON
        json.loads(text)
        b = from_json(text)
        assert b.status == ActionStatus.COMPLETED
        assert b.result.output == {"clicked": True}
        assert len(b.result.witnesses) == 1
        assert b.result.witnesses[0].attestation_type == "quality"

    def test_enum_values_in_json(self):
        a = R6Action()
        text = to_json(a)
        # enums serialize as their string value, not "ActionStatus.PENDING"
        assert "pending" in text
        assert "ActionStatus" not in text

    def test_minimal_roundtrip(self):
        a = R6Action()
        b = from_dict(to_dict(a))
        assert b.status == ActionStatus.PENDING
        assert b.role.role_id == ""


class TestAuditBundleShape:
    """The R6 shape IS the audit bundle shape. Verify the contract."""

    def test_bundle_has_all_six_inputs_plus_result(self):
        a = R6Action()
        d = to_dict(a)["r6_action"]
        for key in ("rules", "role", "request", "reference", "resource", "result"):
            assert key in d, f"audit bundle missing {key}"

    def test_bundle_has_provenance(self):
        a = R6Action(initiator_id="lct:some:agent")
        d = to_dict(a)["r6_action"]
        # provenance fields that make this auditable
        assert "action_id" in d
        assert "initiator_id" in d
        assert "timestamp" in d
        assert "status" in d
