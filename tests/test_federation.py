"""Tests for federation: peer auth + law-state convergence."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.federation import (
    AuthChallenge,
    FederationError,
    LawStateAdvert,
    Peer,
    PeerRegistry,
    diff_law_state,
    mutual_auth,
    reconcile_law,
    respond_to_challenge,
    verify_response,
)
from src.identity import IdentityProvider
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import (
    Law,
    LawBundle,
    LawRegistry,
    sign_bundle,
)


def _identity(tmp_path: Path, name: str, machine: str = "") -> IdentityProvider:
    p = IdentityProvider(tmp_path / name)
    p.bootstrap(name=name, passphrase="pp", machine=machine)
    p.authorize("pp")
    return p


def _signed_bundle(
    bundle_id: str = "b:1",
    scope: str = "demo",
    version: int = 1,
) -> LawBundle:
    b = LawBundle(
        bundle_id=bundle_id, scope=scope, version=version,
        laws=[Law(law_id="l:a", version=1, scope=scope,
                  rule_type="permission", rule={"permit": ["demo"]})],
    )
    sign_bundle(b, SigningContext.from_secret(generate_secret()), "lct:leg")
    return b


# --------------------------------------------------------------------------
# Peer + Registry basics
# --------------------------------------------------------------------------


class TestPeer:
    def test_default_software_ceiling(self):
        p = Peer(lct_id="lct:a")
        assert p.anchor_type == "software"
        assert p.trust_ceiling == 0.4

    def test_hardware_ceiling(self):
        p = Peer(lct_id="lct:a", anchor_type="tpm2")
        assert p.trust_ceiling == 1.0

    def test_update_seen_increments(self):
        p = Peer(lct_id="lct:a")
        assert p.interactions == 0
        p.update_seen()
        p.update_seen()
        assert p.interactions == 2


class TestPeerRegistry:
    def test_empty_registry(self):
        r = PeerRegistry()
        assert len(r) == 0
        assert not r.known("lct:nobody")
        assert r.get("lct:nobody") is None

    def test_observe_creates_peer(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        envelope = alice.attest(nonce="n1")

        registry = PeerRegistry()
        peer = registry.observe(envelope, expected_nonce="n1")
        assert peer.lct_id == alice.load_manifest().lct_id
        assert peer.has_attestation
        assert registry.known(peer.lct_id)

    def test_observe_updates_existing(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        registry = PeerRegistry()

        e1 = alice.attest(nonce="n1")
        peer1 = registry.observe(e1, expected_nonce="n1")
        assert peer1.interactions == 1

        e2 = alice.attest(nonce="n2")
        peer2 = registry.observe(e2, expected_nonce="n2")
        assert peer2.interactions == 2
        assert peer1 is peer2  # same record, mutated in place

    def test_observe_rejects_bad_nonce(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        envelope = alice.attest(nonce="actual")
        registry = PeerRegistry()
        with pytest.raises(FederationError, match="nonce mismatch"):
            registry.observe(envelope, expected_nonce="expected_different")

    def test_observe_rejects_tampered_envelope(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        envelope = alice.attest(nonce="n1")
        envelope.lct_id = "lct:attacker"
        registry = PeerRegistry()
        with pytest.raises(FederationError, match="signature verification"):
            registry.observe(envelope, expected_nonce="n1")

    def test_forget(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        envelope = alice.attest(nonce="n1")
        registry = PeerRegistry()
        registry.observe(envelope, expected_nonce="n1")
        assert registry.forget(envelope.lct_id)
        assert not registry.known(envelope.lct_id)

    def test_persistence_roundtrip(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        envelope = alice.attest(nonce="n1")
        registry = PeerRegistry()
        registry.observe(envelope, expected_nonce="n1")

        path = tmp_path / "peers.json"
        registry.save(path)
        loaded = PeerRegistry.load(path)
        assert len(loaded) == 1
        assert loaded.known(envelope.lct_id)


# --------------------------------------------------------------------------
# Challenge-response auth
# --------------------------------------------------------------------------


class TestAuth:
    def test_respond_returns_signed_envelope(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        challenge = AuthChallenge.fresh("lct:bob")
        envelope = respond_to_challenge(alice, challenge)
        assert envelope.nonce == challenge.nonce

    def test_respond_requires_authorization(self, tmp_path: Path):
        # Bootstrap on one provider (auto-authorizes); load on a fresh
        # provider that has not called authorize().
        p1 = IdentityProvider(tmp_path / "agent")
        p1.bootstrap(name="agent", passphrase="pp")
        p2 = IdentityProvider(tmp_path / "agent")  # loads from disk, no auth
        assert not p2.is_authorized

        challenge = AuthChallenge.fresh("lct:other")
        with pytest.raises(FederationError, match="not authorized"):
            respond_to_challenge(p2, challenge)

    def test_verify_response_registers_peer(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice")
        bob_registry = PeerRegistry()

        challenge = AuthChallenge.fresh("lct:bob")
        envelope = respond_to_challenge(alice, challenge)
        peer = verify_response(bob_registry, challenge, envelope)
        assert bob_registry.known(peer.lct_id)

    def test_mutual_auth_registers_both_sides(self, tmp_path: Path):
        alice = _identity(tmp_path, "alice", machine="legion")
        bob = _identity(tmp_path, "bob", machine="thor")
        alice_reg = PeerRegistry()
        bob_reg = PeerRegistry()

        # mutual_auth returns (bob_in_alices_registry, alice_in_bobs_registry)
        bob_seen_by_alice, alice_seen_by_bob = mutual_auth(
            alice, alice_reg, "lct:legion/alice",
            bob, bob_reg, "lct:thor/bob",
        )
        assert alice_reg.known(bob_seen_by_alice.lct_id)
        assert bob_reg.known(alice_seen_by_bob.lct_id)

        # Each side has their own view of the relationship — different
        # interaction counts (1 each), but identical peer identities.
        assert alice_reg.get("lct:thor/bob").interactions == 1
        assert bob_reg.get("lct:legion/alice").interactions == 1


# --------------------------------------------------------------------------
# Law-state convergence
# --------------------------------------------------------------------------


class TestLawStateAdvert:
    def test_advert_from_registry(self):
        reg = LawRegistry()
        reg.register(_signed_bundle(bundle_id="b:tools", scope="tools", version=1))
        reg.register(_signed_bundle(bundle_id="b:fed", scope="federation", version=2))

        advert = LawStateAdvert.from_registry("lct:me", reg)
        assert "tools" in advert.bundles_by_scope
        assert advert.bundles_by_scope["tools"]["version"] == 1
        assert advert.bundles_by_scope["federation"]["version"] == 2


class TestDiffLawState:
    def test_identical_state(self):
        reg = LawRegistry()
        reg.register(_signed_bundle(version=1))
        a = LawStateAdvert.from_registry("lct:a", reg)
        b = LawStateAdvert.from_registry("lct:b", reg)
        delta = diff_law_state(a, b)
        assert delta.same_or_newer == ["demo"]
        assert delta.peer_newer == []
        assert delta.peer_unknown == []

    def test_peer_has_newer_version(self):
        a_reg = LawRegistry()
        a_reg.register(_signed_bundle(bundle_id="b:1", version=1))
        b_reg = LawRegistry()
        b_reg.register(_signed_bundle(bundle_id="b:2", version=2))

        a = LawStateAdvert.from_registry("lct:a", a_reg)
        b = LawStateAdvert.from_registry("lct:b", b_reg)
        delta = diff_law_state(a, b)
        assert delta.peer_newer == ["demo"]

    def test_peer_knows_unknown_scope(self):
        a_reg = LawRegistry()
        b_reg = LawRegistry()
        b_reg.register(_signed_bundle(scope="federation", version=1))

        a = LawStateAdvert.from_registry("lct:a", a_reg)
        b = LawStateAdvert.from_registry("lct:b", b_reg)
        delta = diff_law_state(a, b)
        assert delta.peer_unknown == ["federation"]


class TestReconcileLaw:
    def test_accept_new_bundle(self):
        local = LawRegistry()
        accepted, rejected = reconcile_law(local, [_signed_bundle()])
        assert len(accepted) == 1
        assert len(rejected) == 0
        assert local.active("demo") is not None

    def test_reject_unsigned_bundle(self):
        local = LawRegistry()
        unsigned = LawBundle(
            bundle_id="b:bad", scope="demo", version=1,
            laws=[Law(law_id="l:a", version=1, scope="demo",
                      rule_type="permission", rule={})],
        )
        accepted, rejected = reconcile_law(local, [unsigned])
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert rejected[0][1] == "verification_failed"

    def test_accept_newer_supersedes(self):
        local = LawRegistry()
        local.register(_signed_bundle(bundle_id="b:old", version=1))
        accepted, _ = reconcile_law(
            local, [_signed_bundle(bundle_id="b:new", version=2)]
        )
        assert len(accepted) == 1
        assert local.active("demo").version == 2

    def test_reject_older(self):
        local = LawRegistry()
        local.register(_signed_bundle(bundle_id="b:current", version=2))
        accepted, rejected = reconcile_law(
            local, [_signed_bundle(bundle_id="b:stale", version=1)]
        )
        assert len(accepted) == 0
        assert len(rejected) == 1
        assert "not newer" in rejected[0][1]


# --------------------------------------------------------------------------
# End-to-end federation scenarios
# --------------------------------------------------------------------------


class TestEndToEnd:
    def test_partition_recovery(self, tmp_path: Path):
        """Two agents go offline with diverged law state. On reconnect:
        1) authenticate, 2) advert + diff, 3) request newer bundles,
        4) reconcile."""
        # Setup: alice and bob both running, both authorized
        alice = _identity(tmp_path, "alice", machine="legion")
        bob = _identity(tmp_path, "bob", machine="thor")
        alice_reg = PeerRegistry()
        bob_reg = PeerRegistry()

        # Both have law v1 at start
        alice_law = LawRegistry()
        bob_law = LawRegistry()
        v1 = _signed_bundle(bundle_id="b:v1", version=1)
        alice_law.register(_signed_bundle(bundle_id="b:v1-a", version=1))
        bob_law.register(_signed_bundle(bundle_id="b:v1-b", version=1))

        # Partition: alice gets v2 from her legislator
        alice_law.register(_signed_bundle(bundle_id="b:v2", version=2))

        # Reconnect: mutual auth
        mutual_auth(
            alice, alice_reg, "lct:legion/alice",
            bob, bob_reg, "lct:thor/bob",
        )

        # Adverts
        a_advert = LawStateAdvert.from_registry("lct:legion/alice", alice_law)
        b_advert = LawStateAdvert.from_registry("lct:thor/bob", bob_law)

        # Bob diffs against alice → discovers alice has newer
        delta_for_bob = diff_law_state(b_advert, a_advert)
        assert "demo" in delta_for_bob.peer_newer

        # Alice ships her newer bundle to bob; bob reconciles
        newer = alice_law.active("demo")
        accepted, rejected = reconcile_law(bob_law, [newer])
        assert len(accepted) == 1
        assert bob_law.active("demo").version == 2

        # Both now agree
        a2 = LawStateAdvert.from_registry("lct:legion/alice", alice_law)
        b2 = LawStateAdvert.from_registry("lct:thor/bob", bob_law)
        delta = diff_law_state(a2, b2)
        assert delta.peer_newer == []
        assert delta.peer_unknown == []
