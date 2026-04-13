"""Tests for the T3/V3 trust ledger."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.r6 import T3, V3
from src.trust import (
    BASE_RATE,
    MIN_RATE,
    ObservationRecord,
    TrustLedger,
    effective_rate,
    update_scalar,
)


class TestUpdateMath:
    def test_effective_rate_starts_at_base(self):
        assert effective_rate(0) == pytest.approx(BASE_RATE)

    def test_effective_rate_decays(self):
        assert effective_rate(1) < effective_rate(0)
        assert effective_rate(10) < effective_rate(1)

    def test_effective_rate_never_zero(self):
        assert effective_rate(10_000) >= MIN_RATE

    def test_update_moves_toward_observation(self):
        new = update_scalar(current=0.5, observation=1.0, observations_so_far=0)
        assert new > 0.5

    def test_update_respects_ceiling(self):
        # Even with observation = 1.0 repeatedly, ceiling clamps
        v = 0.0
        for i in range(100):
            v = update_scalar(v, 1.0, i, ceiling=0.4)
        assert v <= 0.4
        assert v == pytest.approx(0.4, abs=0.01)

    def test_update_respects_floor(self):
        v = 1.0
        for i in range(100):
            v = update_scalar(v, 0.0, i)
        assert v >= 0.0

    def test_diminishing_returns(self):
        """Early observations move the value further than late ones."""
        # Fresh: 1 observation of 1.0 on a 0.5 starting value
        early_delta = update_scalar(0.5, 1.0, 0) - 0.5
        # After many observations, the same 1.0 moves it less
        late_delta = update_scalar(0.5, 1.0, 50) - 0.5
        assert early_delta > late_delta


class TestTrustLedger:
    def test_new_role_starts_neutral(self):
        ledger = TrustLedger()
        t = ledger.snapshot_t3("lct:new")
        assert t.talent == pytest.approx(0.5)
        assert t.training == pytest.approx(0.5)
        assert t.temperament == pytest.approx(0.5)

    def test_observe_t3_updates_tensor(self):
        ledger = TrustLedger()
        ledger.observe_t3("lct:agent", training=1.0)
        t = ledger.snapshot_t3("lct:agent")
        assert t.training > 0.5
        assert t.talent == pytest.approx(0.5)  # untouched
        assert t.temperament == pytest.approx(0.5)

    def test_repeated_good_observations_converge_up(self):
        ledger = TrustLedger()
        for _ in range(50):
            ledger.observe_t3("lct:agent", training=1.0)
        t = ledger.snapshot_t3("lct:agent")
        assert t.training > 0.9

    def test_ceiling_caps_evolution(self):
        ledger = TrustLedger()
        ledger.role("lct:agent", ceiling=0.4)
        for _ in range(100):
            ledger.observe_t3("lct:agent", talent=1.0)
        t = ledger.snapshot_t3("lct:agent")
        assert t.talent <= 0.4

    def test_observe_v3_independent_from_t3(self):
        ledger = TrustLedger()
        ledger.observe_t3("lct:agent", talent=1.0)
        ledger.observe_v3("lct:agent", veracity=0.0)
        t = ledger.snapshot_t3("lct:agent")
        v = ledger.snapshot_v3("lct:agent")
        assert t.talent > 0.5
        assert v.veracity < 0.5

    def test_multiple_dimensions_in_one_call(self):
        ledger = TrustLedger()
        recs = ledger.observe_t3(
            "lct:agent", talent=1.0, training=1.0, temperament=0.5
        )
        assert len(recs) == 3
        dims = {r.dimension for r in recs}
        assert dims == {"talent", "training", "temperament"}

    def test_roles_are_isolated(self):
        ledger = TrustLedger()
        ledger.observe_t3("lct:a", training=1.0)
        ledger.observe_t3("lct:a", training=1.0)
        t_a = ledger.snapshot_t3("lct:a")
        t_b = ledger.snapshot_t3("lct:b")
        assert t_a.training > 0.5
        assert t_b.training == pytest.approx(0.5)

    def test_snapshot_returns_copy_not_reference(self):
        ledger = TrustLedger()
        ledger.observe_t3("lct:a", talent=0.8)
        snap = ledger.snapshot_t3("lct:a")
        snap.talent = 999.0
        later = ledger.snapshot_t3("lct:a")
        assert later.talent != 999.0


class TestObservationRecords:
    def test_record_contains_prior_and_posterior(self):
        ledger = TrustLedger()
        recs = ledger.observe_t3("lct:a", training=1.0)
        r = recs[0]
        assert r.dimension == "training"
        assert r.prior_value == pytest.approx(0.5)
        assert r.posterior_value > r.prior_value
        assert r.observation == pytest.approx(1.0)

    def test_action_ref_and_witness_propagate(self):
        ledger = TrustLedger()
        recs = ledger.observe_t3(
            "lct:a", talent=1.0, action_ref="r6:xyz", witness_id="lct:w"
        )
        assert recs[0].action_ref == "r6:xyz"
        assert recs[0].witness_id == "lct:w"

    def test_history_preserves_order(self):
        ledger = TrustLedger()
        ledger.observe_t3("lct:a", talent=0.1)
        ledger.observe_t3("lct:a", talent=0.9)
        hist = ledger.history("lct:a")
        assert len(hist) == 2
        assert hist[0].observation == pytest.approx(0.1)
        assert hist[1].observation == pytest.approx(0.9)
        # prior of the second = posterior of the first
        assert hist[1].prior_value == pytest.approx(hist[0].posterior_value)

    def test_filter_history_by_role(self):
        ledger = TrustLedger()
        ledger.observe_t3("lct:a", talent=1.0)
        ledger.observe_t3("lct:b", talent=1.0)
        a = ledger.history("lct:a")
        b = ledger.history("lct:b")
        all_ = ledger.history()
        assert len(a) == 1
        assert len(b) == 1
        assert len(all_) == 2


class TestPersistence:
    def test_save_load_roundtrip(self, tmp_path: Path):
        ledger = TrustLedger()
        ledger.role("lct:agent", ceiling=0.9)
        ledger.observe_t3(
            "lct:agent", talent=0.8, training=0.7, action_ref="r6:1"
        )
        ledger.observe_v3("lct:agent", veracity=0.9, action_ref="r6:2")

        p = tmp_path / "trust.json"
        ledger.save(p)

        loaded = TrustLedger.load(p)
        t = loaded.snapshot_t3("lct:agent")
        v = loaded.snapshot_v3("lct:agent")
        assert t.talent == pytest.approx(ledger.snapshot_t3("lct:agent").talent)
        assert v.veracity == pytest.approx(ledger.snapshot_v3("lct:agent").veracity)
        hist = loaded.history("lct:agent")
        assert len(hist) == 3  # talent + training + veracity

    def test_load_preserves_ceiling(self, tmp_path: Path):
        ledger = TrustLedger()
        ledger.role("lct:agent", ceiling=0.4)
        for _ in range(10):
            ledger.observe_t3("lct:agent", talent=1.0)

        p = tmp_path / "trust.json"
        ledger.save(p)
        loaded = TrustLedger.load(p)

        # Ceiling must be enforced on further updates after reload
        for _ in range(100):
            loaded.observe_t3("lct:agent", talent=1.0)
        t = loaded.snapshot_t3("lct:agent")
        assert t.talent <= 0.4


class TestIntegrationWithR6:
    def test_can_embed_ledger_snapshot_in_r6_role(self):
        """T3 snapshot produced by ledger is suitable for R6Action.Role."""
        from src.r6 import R6Action, Role

        ledger = TrustLedger()
        ledger.observe_t3("lct:agent", talent=0.8, training=0.9, temperament=0.7)

        snapshot = ledger.snapshot_t3("lct:agent")
        action = R6Action(role=Role(role_id="lct:agent", context="demo", t3=snapshot))

        assert action.role.t3.talent > 0.5
        c = action.calc_confidence()
        assert c.role_capability == pytest.approx(action.role.t3.composite())
