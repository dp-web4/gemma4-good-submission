"""
Three-layer identity.

    Layer A — IdentityManifest      (public)
    Layer B — sealed secret         (hardware or software)
    Layer C — AttestationEnvelope   (proof of witnessing)

Bootstrap once, authorize each session, attest for peers.
"""

from .attestation import (
    AttestationEnvelope,
    attest,
    verify_envelope,
)
from .manifest import TRUST_CEILINGS, IdentityManifest
from .provider import IdentityError, IdentityProvider, make_lct_id, new_nonce
from .sealed import (
    SealError,
    generate_secret,
    seal_secret,
    unseal_secret,
)
from .signing import SigningContext, verify_with_pubkey

__all__ = [
    "IdentityProvider",
    "IdentityManifest",
    "IdentityError",
    "AttestationEnvelope",
    "SigningContext",
    "SealError",
    "TRUST_CEILINGS",
    "make_lct_id",
    "new_nonce",
    "attest",
    "verify_envelope",
    "seal_secret",
    "unseal_secret",
    "generate_secret",
    "verify_with_pubkey",
]
