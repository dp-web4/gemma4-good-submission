"""
Federation — peer authentication and law-state convergence.

Peer authentication uses challenge-response over attestation envelopes.
Law-state convergence compares per-scope active bundle versions; higher
version wins; superseded bundles re-evaluate pending work.

Federation is local: each agent's PeerRegistry is *its* observations.
There is no global view, by design.

    from src.federation import (
        PeerRegistry, AuthChallenge, mutual_auth,
        LawStateAdvert, diff_law_state, reconcile_law,
    )
"""

from .exchange import (
    AuthChallenge,
    LawStateAdvert,
    LawStateDelta,
    diff_law_state,
    mutual_auth,
    reconcile_law,
    respond_to_challenge,
    verify_response,
)
from .peer import Peer
from .registry import FederationError, PeerRegistry

__all__ = [
    "Peer",
    "PeerRegistry",
    "FederationError",
    "AuthChallenge",
    "respond_to_challenge",
    "verify_response",
    "mutual_auth",
    "LawStateAdvert",
    "LawStateDelta",
    "diff_law_state",
    "reconcile_law",
]
