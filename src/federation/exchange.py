"""
Federation exchange protocols.

This module implements protocol *shape*, not transport. The functions
here take Python objects across "the wire" — in production these would
be JSON over TLS, gRPC, or a federation message bus. The protocol is
the same regardless.

Two protocols implemented:

  1. Peer authentication — challenge-response attestation exchange.
     A → B: nonce; B → A: signed envelope; A verifies → adds B to registry.

  2. Law-state convergence — peers compare active law-bundle digests
     per scope. Higher version wins. Records are exchanged and registered.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from ..identity.attestation import AttestationEnvelope
from ..identity.provider import IdentityProvider, new_nonce
from ..law.law import LawBundle
from ..law.registry import LawRegistry, RegistryError
from ..law.signing import verify_bundle
from .peer import Peer
from .registry import FederationError, PeerRegistry


# --------------------------------------------------------------------------
# Peer authentication
# --------------------------------------------------------------------------


@dataclass
class AuthChallenge:
    """The challenge a verifier sends to a prover."""

    challenger_lct: str
    nonce: str

    @classmethod
    def fresh(cls, challenger_lct: str) -> AuthChallenge:
        return cls(challenger_lct=challenger_lct, nonce=new_nonce())


def respond_to_challenge(
    prover: IdentityProvider, challenge: AuthChallenge
) -> AttestationEnvelope:
    """Prover side: produce an attestation envelope using the challenge nonce."""
    if not prover.is_authorized:
        raise FederationError(
            "prover identity is not authorized; cannot respond to challenge"
        )
    return prover.attest(nonce=challenge.nonce)


def verify_response(
    registry: PeerRegistry,
    challenge: AuthChallenge,
    envelope: AttestationEnvelope,
) -> Peer:
    """Verifier side: register the peer if their envelope checks out."""
    return registry.observe(envelope, expected_nonce=challenge.nonce)


def mutual_auth(
    alice: IdentityProvider,
    alice_registry: PeerRegistry,
    alice_lct: str,
    bob: IdentityProvider,
    bob_registry: PeerRegistry,
    bob_lct: str,
) -> tuple[Peer, Peer]:
    """Run the full two-sided challenge-response.

    Returns (alice_view_of_bob, bob_view_of_alice).
    """
    # Alice challenges Bob
    a_chal = AuthChallenge.fresh(alice_lct)
    b_envelope = respond_to_challenge(bob, a_chal)
    bob_in_alices_registry = verify_response(alice_registry, a_chal, b_envelope)

    # Bob challenges Alice
    b_chal = AuthChallenge.fresh(bob_lct)
    a_envelope = respond_to_challenge(alice, b_chal)
    alice_in_bobs_registry = verify_response(bob_registry, b_chal, a_envelope)

    return bob_in_alices_registry, alice_in_bobs_registry


# --------------------------------------------------------------------------
# Law-state convergence
# --------------------------------------------------------------------------


@dataclass
class LawStateAdvert:
    """A peer's advertisement of its currently-active law bundles per scope."""

    advertiser_lct: str
    bundles_by_scope: dict[str, dict]  # scope → {bundle_id, version, digest}

    @classmethod
    def from_registry(cls, advertiser_lct: str, registry: LawRegistry) -> LawStateAdvert:
        bundles_by_scope: dict[str, dict] = {}
        for scope in registry.scopes():
            b = registry.active(scope)
            if b is None:
                continue
            bundles_by_scope[scope] = {
                "bundle_id": b.bundle_id,
                "version": b.version,
                "digest": b.digest(),
            }
        return cls(advertiser_lct=advertiser_lct, bundles_by_scope=bundles_by_scope)


@dataclass
class LawStateDelta:
    """Per-scope verdicts from comparing two adverts."""

    same_or_newer: list[str]  # scopes where local >= peer
    peer_newer: list[str]  # scopes where peer should send their bundle to us
    peer_unknown: list[str]  # scopes peer knows about, we don't


def diff_law_state(
    local: LawStateAdvert, peer: LawStateAdvert
) -> LawStateDelta:
    """Compute per-scope differences. No bundles transferred yet — just a
    map of who holds what version per scope."""
    same_or_newer: list[str] = []
    peer_newer: list[str] = []
    peer_unknown: list[str] = []

    local_scopes = set(local.bundles_by_scope.keys())
    peer_scopes = set(peer.bundles_by_scope.keys())

    for scope in local_scopes & peer_scopes:
        local_v = local.bundles_by_scope[scope]["version"]
        peer_v = peer.bundles_by_scope[scope]["version"]
        if local_v >= peer_v:
            same_or_newer.append(scope)
        else:
            peer_newer.append(scope)

    for scope in peer_scopes - local_scopes:
        peer_unknown.append(scope)

    return LawStateDelta(
        same_or_newer=same_or_newer,
        peer_newer=peer_newer,
        peer_unknown=peer_unknown,
    )


def reconcile_law(
    local_registry: LawRegistry,
    incoming: list[LawBundle],
) -> tuple[list[LawBundle], list[tuple[LawBundle, str]]]:
    """Apply incoming bundles to the local registry where they are newer.

    Returns (accepted, rejected_with_reason).
    """
    accepted: list[LawBundle] = []
    rejected: list[tuple[LawBundle, str]] = []

    for bundle in incoming:
        if not verify_bundle(
            bundle, required_witnesses=local_registry.required_witnesses
        ):
            rejected.append((bundle, "verification_failed"))
            continue
        try:
            local_registry.register(bundle)
            accepted.append(bundle)
        except RegistryError as e:
            rejected.append((bundle, str(e)))

    return accepted, rejected
