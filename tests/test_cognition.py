"""Tests for the integration cognition loop."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.cognition import CognitionLoop, Outcome, StubExecutor, TickReport
from src.dreamcycle.consolidator import Consolidator
from src.energy.ledger import EnergyLedger
from src.identity import IdentityProvider
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import Law, LawBundle, LawRegistry, sign_bundle
from src.policy.decision import Verdict
from src.policy.gate import PolicyGate
from src.r6 import ActionType, R6Action, V3
from src.snarc.scorer import Scorer
from src.trust.ledger import TrustLedger


@pytest.fixture
def setup(tmp_path: Path):
    """Build a fully-wired cognition loop for tests."""
    # Identity — authorized
    identity = IdentityProvider(tmp_path / "agent")
    identity.bootstrap(name="agent", passphrase="pp", machine="legion")

    # Law — a permissive bundle for scope "demo"
    legislator = SigningContext.from_secret(generate_secret())
    bundle = LawBundle(
        bundle_id="b:demo",
        scope="demo",
        version=1,
        laws=[
            Law(
                law_id="law:permit-act",
                version=1,
                scope="demo",
                rule_type="permission",
                rule={"permit": ["demo", "act"]},
            ),
            Law(
                law_id="law:cost-cap",
                version=1,
                scope="demo",
                rule_type="constraint",
                rule={"max_cost": 10.0},
            ),
        ],
    )
    sign_bundle(bundle, legislator, "lct:legislator")

    laws = LawRegistry()
    laws.register(bundle)

    # Energy — issue 10 packets of 1.0 each
    energy = EnergyLedger()
    for _ in range(10):
        energy.issue(
            amount=1.0,
            to_lct=identity.load_manifest().lct_id,
            from_issuer="lct:mint",
        )

    # Trust / SNARC / Consolidator / Gate
    trust = TrustLedger()
    snarc = Scorer()
    consolidator = Consolidator(
        machine="legion",
        instance_lct=identity.load_manifest().lct_id,
        model="stub",
        session="test",
        salience_threshold=0.2,
    )
    evaluator = SigningContext.from_secret(generate_secret())
    gate = PolicyGate(evaluator_lct="lct:evaluator", evaluator=evaluator)

    loop = CognitionLoop(
        identity=identity,
        role_id="lct:role/player",
        role_context="demo-player",
        scope="demo",
        laws=laws,
        energy=energy,
        trust=trust,
        snarc=snarc,
        consolidator=consolidator,
        gate=gate,
    )
    return {
        "loop": loop,
        "identity": identity,
        "energy": energy,
        "trust": trust,
        "consolidator": consolidator,
        "laws": laws,
        "bundle": bundle,
    }


# --------------------------------------------------------------------------
# Basic tick
# --------------------------------------------------------------------------


class TestTickBasic:
    def test_allowed_tick_completes(self, setup):
        loop = setup["loop"]
        report = loop.tick(
            observation="frame:1",
            request_description="click at (1,2)",
        )
        assert report.decision.is_allow
        assert report.executed
        assert report.outcome is not None
        from src.r6 import ActionStatus

        assert report.action.status == ActionStatus.COMPLETED

    def test_action_embeds_initiator(self, setup):
        loop = setup["loop"]
        identity = setup["identity"]
        report = loop.tick(
            observation="frame",
            request_description="test",
        )
        assert report.action.initiator_id == identity.load_manifest().lct_id

    def test_decision_references_law(self, setup):
        loop, bundle = setup["loop"], setup["bundle"]
        report = loop.tick(observation="x", request_description="test")
        assert report.decision.law_ref.bundle_id == bundle.bundle_id
        assert report.decision.law_ref.bundle_digest == bundle.digest()

    def test_decision_is_signed(self, setup):
        loop = setup["loop"]
        report = loop.tick(observation="x", request_description="test")
        assert report.decision.verify()

    def test_unauthorized_identity_rejected(self, tmp_path: Path):
        """CognitionLoop requires an authorized identity."""
        identity = IdentityProvider(tmp_path / "agent")
        identity.bootstrap(name="a", passphrase="pp")
        # Fresh provider that loads but doesn't authorize
        fresh = IdentityProvider(tmp_path / "agent")

        with pytest.raises(RuntimeError, match="authorized"):
            CognitionLoop(
                identity=fresh, role_id="r", role_context="c", scope="demo",
                laws=LawRegistry(), energy=EnergyLedger(),
                trust=TrustLedger(), snarc=Scorer(),
                consolidator=Consolidator(), gate=PolicyGate(),
            )


# --------------------------------------------------------------------------
# Energy accounting
# --------------------------------------------------------------------------


class TestEnergyAccounting:
    def test_tick_spends_energy(self, setup):
        loop, energy = setup["loop"], setup["energy"]
        identity = setup["identity"]
        before = energy.balance(identity.load_manifest().lct_id)
        report = loop.tick(
            observation="x", request_description="test", estimated_cost=3.0
        )
        after = energy.balance(identity.load_manifest().lct_id)
        assert before - after == pytest.approx(3.0)
        assert report.energy_spent == pytest.approx(3.0)
        assert len(report.energy_packets) == 3  # 3 × 1.0 packets

    def test_energy_packets_settled(self, setup):
        loop, energy = setup["loop"], setup["energy"]
        report = loop.tick(
            observation="x", request_description="test", estimated_cost=2.0
        )
        from src.energy.packet import PacketState

        for pid in report.energy_packets:
            assert energy._packets[pid].state == PacketState.SETTLED

    def test_conservation_holds(self, setup):
        loop, energy = setup["loop"], setup["energy"]
        for _ in range(3):
            loop.tick(observation="x", request_description="t", estimated_cost=1.0)
        assert energy.check_conservation()

    def test_out_of_energy_records_failure(self, setup):
        loop = setup["loop"]
        # Exhaust energy
        for _ in range(10):
            loop.tick(observation="x", request_description="t", estimated_cost=1.0)
        # Next tick should fail with no energy
        report = loop.tick(
            observation="x", request_description="t", estimated_cost=1.0
        )
        from src.r6 import ActionStatus

        assert report.action.status == ActionStatus.FAILED
        assert "no energy" in report.reason.lower()


# --------------------------------------------------------------------------
# Policy enforcement
# --------------------------------------------------------------------------


class TestPolicyEnforcement:
    def test_denied_action_not_executed(self, setup):
        loop = setup["loop"]
        # Request that exceeds the cost-cap law
        report = loop.tick(
            observation="x", request_description="t", estimated_cost=100.0
        )
        assert report.decision.is_deny
        assert not report.executed
        from src.r6 import ActionStatus

        assert report.action.status == ActionStatus.DENIED

    def test_denied_action_spends_no_energy(self, setup):
        loop, energy = setup["loop"], setup["energy"]
        identity = setup["identity"]
        before = energy.balance(identity.load_manifest().lct_id)
        loop.tick(
            observation="x", request_description="t", estimated_cost=100.0
        )
        after = energy.balance(identity.load_manifest().lct_id)
        assert before == after  # no spend on denied

    def test_no_bundle_for_scope_defers(self, tmp_path, setup):
        """A scope with no registered bundle → DEFER, not ALLOW."""
        loop = setup["loop"]
        loop.scope = "unknown_scope"
        report = loop.tick(observation="x", request_description="t")
        assert report.decision.is_defer
        assert not report.executed


# --------------------------------------------------------------------------
# Trust evolution
# --------------------------------------------------------------------------


class TestTrustEvolution:
    def test_trust_updates_after_completion(self, setup):
        """With a software anchor (ceiling 0.4), trust is clipped to the
        ceiling regardless of observed quality. Demonstrates ceiling
        enforcement through the loop."""
        loop, trust = setup["loop"], setup["trust"]
        for _ in range(5):
            loop.tick(observation="x", request_description="t", estimated_cost=1.0)
        after = trust.snapshot_t3("lct:role/player")
        # Software anchor caps T3 at 0.4; StubExecutor quality averages ~0.75
        # → clipped to ceiling
        assert after.training == pytest.approx(0.4)
        # And observations were actually recorded
        history = trust.history("lct:role/player")
        assert any(r.tensor == "t3" and r.dimension == "training" for r in history)

    def test_v3_updates_after_completion(self, setup):
        """V3 starts at 0.0 (below ceiling), so it should rise toward
        the ceiling from outcome observations."""
        loop, trust = setup["loop"], setup["trust"]
        before = trust.snapshot_v3("lct:role/player")
        for _ in range(5):
            loop.tick(observation="x", request_description="t", estimated_cost=1.0)
        after = trust.snapshot_v3("lct:role/player")
        assert after.validity > before.validity

    def test_denied_actions_dont_update_trust(self, setup):
        loop, trust = setup["loop"], setup["trust"]
        before = trust.snapshot_t3("lct:role/player")
        for _ in range(3):
            loop.tick(
                observation="x", request_description="t", estimated_cost=100.0
            )
        after = trust.snapshot_t3("lct:role/player")
        assert after.training == before.training  # unchanged


# --------------------------------------------------------------------------
# Consolidation
# --------------------------------------------------------------------------


class TestConsolidation:
    def test_ticks_record_into_consolidator(self, setup):
        loop, cons = setup["loop"], setup["consolidator"]
        loop.tick(observation="novel frame 1", request_description="t")
        loop.tick(observation="novel frame 2", request_description="t")
        assert cons.buffer_len == 2

    def test_consolidate_after_session(self, setup):
        loop, cons = setup["loop"], setup["consolidator"]
        # First observation is novel; subsequent similar ones decrease novelty.
        loop.tick(observation="totally unique signal xyz", request_description="t")
        bundle = cons.consolidate()
        # Depending on threshold and weights, at least the highly-novel
        # first tick should be retained
        assert len(bundle) >= 1


# --------------------------------------------------------------------------
# Custom executor
# --------------------------------------------------------------------------


class AlwaysFailingExecutor:
    def execute(self, action, context=None):
        raise RuntimeError("boom")


class TestExecutorFailure:
    def test_executor_failure_is_recorded(self, setup):
        loop = setup["loop"]
        loop.executor = AlwaysFailingExecutor()
        report = loop.tick(
            observation="x", request_description="t", estimated_cost=1.0
        )
        from src.r6 import ActionStatus

        assert report.action.status == ActionStatus.FAILED
        assert "boom" in report.reason


# --------------------------------------------------------------------------
# End-to-end
# --------------------------------------------------------------------------


class TestEndToEnd:
    def test_full_loop_produces_audit_bundle(self, setup):
        loop = setup["loop"]
        report = loop.tick(
            observation={"frame": 1, "objects": ["green_block"]},
            request_description="click green block",
            action_type=ActionType.ACT,
            estimated_cost=1.0,
            expectation={"frame": 0, "objects": []},
            arousal=0.3, reward=0.5, conflict=0.1,
        )
        assert report.decision.is_allow
        assert report.executed
        d = report.to_dict()
        # Report shape carries the full audit story
        assert "action_id" in d
        assert "decision" in d
        assert d["decision"]["verdict"] == "allow"
        assert "snarc" in d
        assert "outcome" in d
        assert d["outcome"]["quality"] > 0
        assert d["energy_spent"] == pytest.approx(1.0)
        assert len(d["energy_packets"]) == 1

    def test_multi_tick_session(self, setup):
        loop, cons = setup["loop"], setup["consolidator"]
        reports = []
        for i in range(5):
            reports.append(
                loop.tick(
                    observation=f"unique observation number {i}",
                    request_description=f"action {i}",
                    estimated_cost=1.0,
                )
            )
        # All allowed (cost within cap)
        assert all(r.decision.is_allow for r in reports)
        assert all(r.executed for r in reports)
        # Consolidator has 5 records
        assert cons.buffer_len == 5
        # Conservation
        assert setup["energy"].check_conservation()
