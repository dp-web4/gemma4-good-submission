"""Tests for the PolicyGate + Decision pair (law-in-the-loop evaluation)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.identity.sealed import generate_secret
from src.identity.signing import SigningContext
from src.law import (
    Law,
    LawBundle,
    LawRef,
    LawRegistry,
    add_witness,
    sign_bundle,
)
from src.policy import (
    Decision,
    PolicyGate,
    RateObserver,
    RuleFailure,
    RuleVerdict,
    Verdict,
    evaluate_law,
)
from src.r6 import (
    ActionType,
    R6Action,
    Reference,
    Request,
    Resource,
    Role,
    Rules,
    T3,
)


def _sign_ctx() -> SigningContext:
    return SigningContext.from_secret(generate_secret())


def _law(
    law_id: str = "law:a",
    version: int = 1,
    scope: str = "demo",
    rule_type: str = "permission",
    rule: dict | None = None,
) -> Law:
    return Law(
        law_id=law_id,
        version=version,
        scope=scope,
        rule_type=rule_type,
        rule=rule or {"permit": ["demo"]},
    )


def _signed_bundle(laws: list[Law], scope: str = "demo") -> LawBundle:
    b = LawBundle(bundle_id="b:1", scope=scope, version=1, laws=laws)
    sign_bundle(b, _sign_ctx(), "lct:legislator")
    return b


def _action(
    scope: str = "demo",
    action_type: ActionType = ActionType.ACT,
    estimated_cost: float = 0.0,
    t3: T3 | None = None,
) -> R6Action:
    return R6Action(
        rules=Rules(permission_scope=[scope]),
        role=Role(role_id="lct:agent", context="test", t3=t3 or T3()),
        request=Request(action_type=action_type, description="test"),
        resource=Resource(estimated_cost=estimated_cost),
    )


# --------------------------------------------------------------------------
# Rule interpreter
# --------------------------------------------------------------------------


class TestEvaluateLaw:
    def test_permit_allowed(self):
        law = _law(rule={"permit": ["demo"]})
        v = evaluate_law(law, _action())
        assert v.passed

    def test_permit_not_listed(self):
        law = _law(rule={"permit": ["other_scope"]})
        v = evaluate_law(law, _action())
        assert not v.passed
        assert "not_permitted" in v.reason

    def test_deny_blocks(self):
        law = _law(rule={"deny": ["demo"]})
        v = evaluate_law(law, _action())
        assert not v.passed
        assert "denied" in v.reason

    def test_max_cost_pass(self):
        law = _law(rule={"max_cost": 10.0})
        v = evaluate_law(law, _action(estimated_cost=5.0))
        assert v.passed

    def test_max_cost_fail(self):
        law = _law(rule={"max_cost": 1.0})
        v = evaluate_law(law, _action(estimated_cost=5.0))
        assert not v.passed
        assert "cost_exceeded" in v.reason

    def test_require_ceiling(self):
        law = _law(rule={"require_ceiling": 0.9})
        v_low = evaluate_law(law, _action(), identity_ceiling=0.4)
        v_high = evaluate_law(law, _action(), identity_ceiling=1.0)
        assert not v_low.passed
        assert v_high.passed

    def test_require_t3_min(self):
        law = _law(rule={"require_t3_min": {"temperament": 0.7}})
        low_t3 = T3(talent=0.9, training=0.9, temperament=0.3)
        high_t3 = T3(talent=0.5, training=0.5, temperament=0.9)
        assert not evaluate_law(law, _action(t3=low_t3)).passed
        assert evaluate_law(law, _action(t3=high_t3)).passed

    def test_unknown_key_fails_closed(self):
        law = _law(rule={"not_a_real_key": True})
        v = evaluate_law(law, _action())
        assert not v.passed
        assert "unknown_rule_key" in v.reason

    def test_rate_limit(self):
        law = _law(rule={"max_rate_per_minute": 2})
        rate = RateObserver()
        action = _action()
        # First two pass
        rate.record(f"{action.role.role_id}:{action.request.action_type.value}")
        rate.record(f"{action.role.role_id}:{action.request.action_type.value}")
        v = evaluate_law(law, action, rate_observer=rate)
        assert not v.passed
        assert "rate_exceeded" in v.reason


# --------------------------------------------------------------------------
# PolicyGate
# --------------------------------------------------------------------------


class TestPolicyGate:
    def test_allow_when_all_laws_pass(self):
        bundle = _signed_bundle([_law(rule={"permit": ["demo"]})])
        gate = PolicyGate()
        decision = gate.evaluate(_action(), bundle)
        assert decision.is_allow
        assert decision.law_ref.bundle_id == "b:1"
        assert decision.law_ref.bundle_digest == bundle.digest()

    def test_deny_records_failures(self):
        bundle = _signed_bundle(
            [
                _law("l:a", rule={"permit": ["demo"]}),
                _law("l:b", rule={"max_cost": 1.0}),
            ]
        )
        gate = PolicyGate()
        decision = gate.evaluate(_action(estimated_cost=10.0), bundle)
        assert decision.is_deny
        assert any(f.law_id == "l:b" for f in decision.failures)
        assert "cost_exceeded" in decision.failures[0].reason

    def test_no_applicable_laws_allows(self):
        """No laws match scope → allow (with a 'no applicable laws' note)."""
        bundle = _signed_bundle([_law(scope="unrelated")])
        gate = PolicyGate()
        decision = gate.evaluate(_action(scope="demo"), bundle)
        assert decision.is_allow
        assert decision.reason == "no applicable laws"

    def test_apply_denies_action(self):
        bundle = _signed_bundle([_law(rule={"deny": ["demo"]})])
        gate = PolicyGate()
        action = _action()
        decision = gate.evaluate(action, bundle)
        gate.apply(action, decision)
        from src.r6 import ActionStatus

        assert action.status == ActionStatus.DENIED

    def test_law_ref_embeds_applied_laws(self):
        applied_law = _law("l:a", rule={"permit": ["demo"]})
        other_law = _law("l:b", scope="other")
        bundle = _signed_bundle([applied_law, other_law])
        gate = PolicyGate()
        decision = gate.evaluate(_action(), bundle)
        assert "l:a" in decision.law_ref.law_ids_applied
        assert "l:b" not in decision.law_ref.law_ids_applied

    def test_defer_when_no_bundle_for_scope(self):
        reg = LawRegistry()
        gate = PolicyGate()
        decision = gate.evaluate_with_registry(_action(scope="unknown"), reg)
        assert decision.is_defer
        assert "no_law_for_scope" in decision.reason

    def test_signed_decision_verifies(self):
        bundle = _signed_bundle([_law(rule={"permit": ["demo"]})])
        evaluator = _sign_ctx()
        gate = PolicyGate(evaluator_lct="lct:judge", evaluator=evaluator)
        decision = gate.evaluate(_action(), bundle)
        assert decision.signature_b64  # signed
        assert decision.verify() is True

    def test_tampered_decision_fails_verify(self):
        bundle = _signed_bundle([_law(rule={"permit": ["demo"]})])
        gate = PolicyGate(evaluator_lct="lct:judge", evaluator=_sign_ctx())
        decision = gate.evaluate(_action(), bundle)
        # mutate the verdict
        decision.verdict = Verdict.DENY
        assert decision.verify() is False

    def test_rate_limit_across_evaluations(self):
        """max_rate_per_minute enforced across multiple gate.evaluate calls."""
        bundle = _signed_bundle(
            [_law(rule={"max_rate_per_minute": 2, "permit": ["demo"]})]
        )
        gate = PolicyGate()
        d1 = gate.evaluate(_action(), bundle)
        d2 = gate.evaluate(_action(), bundle)
        d3 = gate.evaluate(_action(), bundle)
        assert d1.is_allow
        assert d2.is_allow
        assert d3.is_deny
        assert "rate_exceeded" in d3.reason


# --------------------------------------------------------------------------
# Decision serialization + audit integration
# --------------------------------------------------------------------------


class TestDecision:
    def test_decision_roundtrip(self):
        ref = LawRef(bundle_id="b", bundle_digest="d", version=1, law_ids_applied=["l:a"])
        d = Decision(
            action_id="r6:x",
            verdict=Verdict.ALLOW,
            law_ref=ref,
            reason="ok",
        )
        d.sign(_sign_ctx(), "lct:judge")
        restored = Decision.from_dict(d.to_dict())
        assert restored.action_id == "r6:x"
        assert restored.verdict == Verdict.ALLOW
        assert restored.law_ref.bundle_id == "b"
        assert restored.verify() is True

    def test_decision_and_action_form_two_part_bundle(self):
        """Audit bundle = (R6Action, Decision). Both independently verifiable."""
        bundle = _signed_bundle([_law(rule={"permit": ["demo"]})])
        gate = PolicyGate(evaluator_lct="lct:judge", evaluator=_sign_ctx())
        action = _action()
        decision = gate.evaluate(action, bundle)

        # Audit bundle
        audit = {
            "action": action.action_id,
            "decision": decision.to_dict(),
            "law_bundle_digest": bundle.digest(),
        }
        # Each part stands on its own
        assert audit["decision"]["law_ref"]["bundle_digest"] == audit["law_bundle_digest"]
        assert decision.verify()


# --------------------------------------------------------------------------
# End-to-end integration
# --------------------------------------------------------------------------


class TestIntegration:
    def test_full_flow_allow(self):
        """Full flow: identity → signed bundle → gate evaluation → signed
        decision → action proceeds."""
        from src.identity.signing import SigningContext

        legislator = SigningContext.from_secret(generate_secret())
        evaluator = SigningContext.from_secret(generate_secret())

        # Legislator issues a bundle
        bundle = LawBundle(
            bundle_id="b:arc-agi-3", scope="arc-agi-3-player", version=1,
            laws=[
                Law(
                    law_id="law:no-risky-actions", version=1,
                    scope="arc-agi-3-player", rule_type="prohibition",
                    rule={"deny": ["delegate"]},
                ),
                Law(
                    law_id="law:cost-cap", version=1,
                    scope="arc-agi-3-player", rule_type="constraint",
                    rule={"max_cost": 5.0},
                ),
            ],
        )
        sign_bundle(bundle, legislator, "lct:legislator")

        # Witness countersigns
        witness = SigningContext.from_secret(generate_secret())
        add_witness(bundle, witness, "lct:witness:1")

        # Registry loads bundle with witness requirement
        registry = LawRegistry()
        registry.required_witnesses = 1
        registry.register(bundle)

        # Gate evaluates
        gate = PolicyGate(evaluator_lct="lct:evaluator", evaluator=evaluator)
        action = R6Action(
            rules=Rules(permission_scope=["arc-agi-3-player"]),
            role=Role(role_id="lct:nomad/agent", context="player"),
            request=Request(action_type=ActionType.ACT, description="click"),
            resource=Resource(estimated_cost=1.0),
        )
        decision = gate.evaluate_with_registry(action, registry)

        assert decision.is_allow
        assert decision.verify() is True
        assert decision.law_ref.bundle_digest == bundle.digest()
        assert set(decision.law_ref.law_ids_applied) == {
            "law:no-risky-actions", "law:cost-cap",
        }

    def test_full_flow_deny_with_audit_trail(self):
        """When action is denied, audit can trace exactly which law and why."""
        legislator = _sign_ctx()
        bundle = LawBundle(
            bundle_id="b:federation", scope="federation", version=1,
            laws=[
                Law(
                    law_id="law:require-hw-identity", version=1,
                    scope="federation", rule_type="requirement",
                    rule={"require_ceiling": 0.85},
                    rationale="Software-only identities cannot speak for the federation.",
                ),
            ],
        )
        sign_bundle(bundle, legislator, "lct:legislator")

        evaluator = _sign_ctx()
        gate = PolicyGate(evaluator_lct="lct:evaluator", evaluator=evaluator)
        action = R6Action(
            rules=Rules(permission_scope=["federation"]),
            role=Role(role_id="lct:sprout/agent", context="fed"),
            request=Request(
                action_type=ActionType.ACT, description="propose"
            ),
            resource=Resource(estimated_cost=0.0),
        )
        # Software-anchor ceiling 0.4
        decision = gate.evaluate(action, bundle, identity_ceiling=0.4)
        gate.apply(action, decision)

        assert decision.is_deny
        from src.r6 import ActionStatus

        assert action.status == ActionStatus.DENIED
        assert any("ceiling_too_low" in f.reason for f in decision.failures)
        # Audit trail survives tampering attempts
        assert decision.verify() is True
        assert decision.law_ref.bundle_id == "b:federation"
