"""Tests for the dreamcycle (consolidator + bundle)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.dreamcycle import Consolidator, DreamBundle, DreamEntry, WakeRecord
from src.law import Law, LawBundle, LawRef, sign_bundle
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.policy import Decision, PolicyGate, Verdict
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
from src.snarc import SnarcScore


def _action(scope: str = "demo") -> R6Action:
    return R6Action(
        rules=Rules(permission_scope=[scope]),
        role=Role(role_id="lct:agent", context="test"),
        request=Request(action_type=ActionType.ACT, description="test"),
        resource=Resource(estimated_cost=1.0),
    )


def _signed_bundle() -> LawBundle:
    b = LawBundle(
        bundle_id="b:1", scope="demo", version=1,
        laws=[Law(law_id="l:a", version=1, scope="demo",
                  rule_type="permission", rule={"permit": ["demo"]})],
    )
    sign_bundle(b, SigningContext.from_secret(generate_secret()), "lct:leg")
    return b


# --------------------------------------------------------------------------
# DreamBundle
# --------------------------------------------------------------------------


class TestDreamBundle:
    def test_empty_bundle(self):
        b = DreamBundle()
        assert len(b) == 0
        assert b.bundle_id.startswith("dream:")

    def test_add_action(self):
        b = DreamBundle()
        b.add(_action(), snarc=SnarcScore(novelty=0.9))
        assert len(b) == 1
        assert b.entries[0].snarc["novelty"] == pytest.approx(0.9)

    def test_add_with_decision(self):
        b = DreamBundle()
        ref = LawRef(bundle_id="b", bundle_digest="d", version=1, law_ids_applied=[])
        decision = Decision(
            action_id="r6:x", verdict=Verdict.ALLOW, law_ref=ref, reason="ok"
        )
        b.add(_action(), decision=decision, snarc=SnarcScore(novelty=1.0))
        assert b.entries[0].decision["verdict"] == "allow"
        assert b.entries[0].decision["law_ref"]["bundle_id"] == "b"

    def test_digest_stable(self):
        b = DreamBundle(bundle_id="dream:fixed", machine="nomad")
        b.add(_action(), snarc=SnarcScore(novelty=0.7))
        d1 = b.digest()
        d2 = b.digest()
        assert d1 == d2

    def test_digest_changes_with_content(self):
        b1 = DreamBundle(bundle_id="dream:fixed")
        b1.add(_action(), snarc=SnarcScore(novelty=0.5))
        d1 = b1.digest()
        b1.add(_action(), snarc=SnarcScore(novelty=0.6))
        d2 = b1.digest()
        assert d1 != d2

    def test_roundtrip_file(self, tmp_path: Path):
        b = DreamBundle(machine="nomad", instance_lct="lct:nomad/agent",
                        model="gemma-4-e4b", session="s1")
        b.add(_action(), snarc=SnarcScore(novelty=0.9, reward=0.7))
        b.add(_action(), snarc=SnarcScore(surprise=0.5))

        p = tmp_path / "bundle.json"
        b.save(p)
        loaded = DreamBundle.load(p)
        assert len(loaded) == 2
        assert loaded.machine == "nomad"
        assert loaded.entries[0].snarc["novelty"] == pytest.approx(0.9)
        # Digest survives roundtrip
        assert loaded.digest() == b.digest()


# --------------------------------------------------------------------------
# Consolidator — wake-time recording
# --------------------------------------------------------------------------


class TestConsolidatorRecording:
    def test_record_appends_to_buffer(self):
        c = Consolidator()
        c.record(_action(), snarc=SnarcScore(novelty=0.9))
        assert c.buffer_len == 1

    def test_buffer_bounded(self):
        c = Consolidator(buffer_size=3)
        for _ in range(10):
            c.record(_action(), snarc=SnarcScore(novelty=0.5))
        assert c.buffer_len == 3

    def test_clear_buffer(self):
        c = Consolidator()
        c.record(_action(), snarc=SnarcScore(novelty=0.9))
        c.record(_action(), snarc=SnarcScore(novelty=0.8))
        c.clear_buffer()
        assert c.buffer_len == 0


# --------------------------------------------------------------------------
# Consolidator — sleep-time selection
# --------------------------------------------------------------------------


class TestConsolidatorSelection:
    def test_selects_above_threshold(self):
        c = Consolidator(salience_threshold=0.5)
        # High-salience: broad signal across dimensions
        c.record(
            _action(),
            snarc=SnarcScore(surprise=0.8, novelty=0.8, arousal=0.5,
                             reward=0.7, conflict=0.4),
        )
        c.record(_action(), snarc=SnarcScore(novelty=0.1))  # low
        kept = c.select()
        assert len(kept) == 1
        assert kept[0].snarc.novelty == pytest.approx(0.8)

    def test_records_without_snarc_excluded(self):
        c = Consolidator(salience_threshold=0.0)
        c.record(_action())  # no snarc
        c.record(_action(), snarc=SnarcScore(novelty=1.0))
        kept = c.select()
        # Even at threshold 0, the un-scored one is excluded
        assert len(kept) == 1

    def test_threshold_override(self):
        c = Consolidator(salience_threshold=0.5)
        c.record(_action(), snarc=SnarcScore(novelty=0.3))
        # Default threshold rejects it
        assert c.select() == []
        # Override accepts it
        kept = c.select(threshold=0.0)
        assert len(kept) == 1

    def test_custom_weights_change_selection(self):
        """Selection respects the consolidator's selection_weights."""
        # Reward-only weights: only reward counts
        c = Consolidator(
            salience_threshold=0.5,
            selection_weights={
                "surprise": 0.0, "novelty": 0.0, "arousal": 0.0,
                "reward": 1.0, "conflict": 0.0,
            },
        )
        c.record(_action(), snarc=SnarcScore(novelty=1.0, reward=0.0))  # excluded
        c.record(_action(), snarc=SnarcScore(novelty=0.0, reward=1.0))  # included
        kept = c.select()
        assert len(kept) == 1
        assert kept[0].snarc.reward == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Consolidator — emit bundle
# --------------------------------------------------------------------------


class TestConsolidate:
    def test_emits_bundle_with_metadata(self):
        c = Consolidator(
            machine="nomad", instance_lct="lct:nomad/agent",
            model="gemma-4-e4b", session="2026-04-14",
            salience_threshold=0.4,
        )
        c.record(
            _action(),
            snarc=SnarcScore(surprise=0.7, novelty=0.9, arousal=0.5,
                             reward=0.8, conflict=0.3),
        )
        bundle = c.consolidate()
        assert bundle.machine == "nomad"
        assert bundle.instance_lct == "lct:nomad/agent"
        assert bundle.model == "gemma-4-e4b"
        assert bundle.session == "2026-04-14"
        assert bundle.salience_threshold == pytest.approx(0.4)
        assert len(bundle) == 1

    def test_clears_buffer_by_default(self):
        c = Consolidator(salience_threshold=0.0)
        c.record(_action(), snarc=SnarcScore(novelty=0.9))
        c.consolidate()
        assert c.buffer_len == 0

    def test_can_consolidate_without_clearing(self):
        c = Consolidator(salience_threshold=0.0)
        c.record(_action(), snarc=SnarcScore(novelty=0.9))
        c.consolidate(clear_buffer=False)
        assert c.buffer_len == 1

    def test_consolidate_zero_threshold_takes_everything_scored(self):
        c = Consolidator(salience_threshold=0.5)
        c.record(_action(), snarc=SnarcScore(novelty=0.0))
        c.record(_action(), snarc=SnarcScore(novelty=1.0))
        c.record(_action())  # un-scored — excluded
        bundle = c.consolidate(threshold=0.0)
        assert len(bundle) == 2

    def test_consolidate_preserves_decision_and_snarc(self):
        c = Consolidator(salience_threshold=0.0)
        ref = LawRef(bundle_id="b", bundle_digest="d", version=1, law_ids_applied=[])
        decision = Decision(
            action_id="r6:x", verdict=Verdict.ALLOW, law_ref=ref, reason="ok"
        )
        c.record(
            _action(),
            decision=decision,
            snarc=SnarcScore(novelty=0.9),
            notes="first action",
        )
        bundle = c.consolidate()
        e = bundle.entries[0]
        assert e.decision["verdict"] == "allow"
        assert e.snarc["novelty"] == pytest.approx(0.9)
        assert e.notes == "first action"


# --------------------------------------------------------------------------
# Replay — closing the loop
# --------------------------------------------------------------------------


class TestReplay:
    def test_replay_yields_entries(self):
        c = Consolidator(salience_threshold=0.0)
        c.record(_action(), snarc=SnarcScore(novelty=1.0))
        c.record(_action(), snarc=SnarcScore(novelty=0.8))
        bundle = c.consolidate()

        replayed = list(Consolidator.replay_priors(bundle))
        assert len(replayed) == 2
        # Each entry is a DreamEntry with action+snarc preserved
        for e in replayed:
            assert "action" in e.to_dict()
            assert e.snarc is not None


# --------------------------------------------------------------------------
# End-to-end: record → policy → snarc → consolidate → save → load
# --------------------------------------------------------------------------


class TestEndToEnd:
    def test_full_loop(self, tmp_path: Path):
        # Set up: legislator signs bundle, policy gate evaluates
        bundle_law = _signed_bundle()
        gate = PolicyGate(evaluator_lct="lct:judge",
                          evaluator=SigningContext.from_secret(generate_secret()))

        # Wake: agent acts, gate evaluates, snarc scored
        c = Consolidator(
            machine="nomad", instance_lct="lct:nomad/agent",
            model="gemma-4-e4b", session="s1", salience_threshold=0.4,
        )
        # Pairs of (novelty, arousal) — broader signal so composite >= threshold
        # for the high ones. With default weights, ~3 dimensions at >=0.6 reach 0.4.
        signals = [
            (0.9, 0.7),  # high — broad signal, will be kept
            (0.1, 0.0),  # low
            (0.8, 0.6),  # high
            (0.0, 0.0),  # low
        ]
        for novelty, arousal in signals:
            action = _action()
            decision = gate.evaluate(action, bundle_law)
            snarc = SnarcScore(
                surprise=novelty * 0.8, novelty=novelty,
                arousal=arousal, reward=0.5, conflict=0.2,
            )
            c.record(action, decision=decision, snarc=snarc)

        # Sleep: consolidate
        bundle = c.consolidate()
        assert len(bundle) >= 2  # the high-novelty ones survive

        # Persist
        path = tmp_path / "dreams" / "today.json"
        path.parent.mkdir()
        bundle.save(path)

        # Wake tomorrow: load priors back as context
        loaded = DreamBundle.load(path)
        assert loaded.digest() == bundle.digest()
        priors = list(Consolidator.replay_priors(loaded))
        assert len(priors) == len(bundle)

        # Each prior carries the full audit shape
        for p in priors:
            assert "action_id" in p.action
            assert p.decision is not None
            assert "verdict" in p.decision
            assert p.snarc is not None
