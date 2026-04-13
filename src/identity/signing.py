"""
SigningContext — in-memory authorized signing key.

Once an identity is authorized (unsealed with the correct passphrase,
or challenge-responded with hardware in production), a SigningContext
is materialized from the secret seed. The context holds the derived
Ed25519 key pair and provides sign/verify.

The context is never persisted. It lives only in memory for the
duration of the authorized session. Re-authorization is required
after process restart.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.exceptions import InvalidSignature


def _derive_keypair(secret: bytes) -> Ed25519PrivateKey:
    """Derive an Ed25519 private key from a 32-byte seed."""
    if len(secret) != 32:
        raise ValueError(f"Ed25519 seed must be 32 bytes, got {len(secret)}")
    return Ed25519PrivateKey.from_private_bytes(secret)


def fingerprint(pubkey: Ed25519PublicKey) -> str:
    """Short, stable fingerprint for the public key (first 16 hex chars of SHA-256)."""
    from cryptography.hazmat.primitives import serialization

    raw = pubkey.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class SigningContext:
    """Authorized signing context. Lives in memory only."""

    _private: Ed25519PrivateKey
    anchor_type: str = "software"
    authorized_at: float = field(default_factory=time.time)

    @classmethod
    def from_secret(
        cls, secret: bytes, anchor_type: str = "software"
    ) -> SigningContext:
        return cls(_private=_derive_keypair(secret), anchor_type=anchor_type)

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._private.public_key()

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.public_key)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.authorized_at

    def sign(self, data: bytes) -> bytes:
        return self._private.sign(data)

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Verify a signature against this context's public key."""
        try:
            self.public_key.verify(signature, data)
            return True
        except InvalidSignature:
            return False


def verify_with_pubkey(
    pubkey_bytes: bytes, data: bytes, signature: bytes
) -> bool:
    """Verify a signature using a raw Ed25519 public key (32 bytes)."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(pubkey_bytes)
        pub.verify(signature, data)
        return True
    except (InvalidSignature, ValueError):
        return False
