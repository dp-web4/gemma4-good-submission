"""
IdentityProvider — the three-layer orchestrator.

Holds the manifest (Layer A), can unseal the secret (Layer B → SigningContext),
and can produce or cache attestation envelopes (Layer C).

Lifecycle:
    provider = IdentityProvider(instance_dir)
    provider.bootstrap(name, machine, model, passphrase)  # first run only
    ctx = provider.authorize(passphrase)                  # every process start
    envelope = provider.attest(nonce)                     # for peers / audits

Instance directory layout:
    {instance_dir}/
      identity.json          (Layer A, public)
      identity.sealed        (Layer B, encrypted)
      identity.attest.json   (Layer C, last attestation)
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import serialization

from .attestation import (
    DEFAULT_TTL_SECONDS,
    AttestationEnvelope,
    attest,
    verify_envelope,
)
from .manifest import IdentityManifest
from .sealed import generate_secret, load_sealed, save_sealed, seal_secret, unseal_secret
from .signing import SigningContext


def _manifest_digest(manifest: IdentityManifest) -> str:
    """SHA-256 of the canonical manifest bytes (public fields only)."""
    import json

    data = manifest.to_dict()
    # trust_ceiling is derived; do not bake it into the digest
    data.pop("trust_ceiling", None)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def make_lct_id(name: str, machine: str = "") -> str:
    """Construct an LCT id from a name + optional machine. Not cryptographically unique
    on its own — the public key fingerprint provides identity binding."""
    tag = f"{machine}/{name}" if machine else name
    return f"lct:{tag}"


def new_nonce() -> str:
    return secrets.token_hex(16)


class IdentityError(Exception):
    """Identity operation failed."""


@dataclass
class IdentityProvider:
    """Three-layer identity orchestrator."""

    instance_dir: Path
    _manifest: IdentityManifest | None = None
    _context: SigningContext | None = None

    def __init__(self, instance_dir: str | Path) -> None:
        self.instance_dir = Path(instance_dir)
        self._manifest = None
        self._context = None

    @property
    def manifest_path(self) -> Path:
        return self.instance_dir / "identity.json"

    @property
    def sealed_path(self) -> Path:
        return self.instance_dir / "identity.sealed"

    @property
    def attest_path(self) -> Path:
        return self.instance_dir / "identity.attest.json"

    # ------------------------------------------------------------------
    # Bootstrap: first-run identity creation
    # ------------------------------------------------------------------

    def bootstrap(
        self,
        name: str,
        passphrase: str,
        *,
        machine: str = "",
        model: str = "",
        model_family: str = "",
        anchor_type: str = "software",
    ) -> IdentityManifest:
        """Create a new identity. Generates secret, seals it, writes manifest."""
        if self.manifest_path.exists():
            raise IdentityError(f"identity already exists at {self.manifest_path}")
        os.makedirs(self.instance_dir, exist_ok=True)

        secret = generate_secret()
        ctx = SigningContext.from_secret(secret, anchor_type=anchor_type)
        manifest = IdentityManifest(
            name=name,
            lct_id=make_lct_id(name, machine),
            public_key_fingerprint=ctx.fingerprint,
            anchor_type=anchor_type,
            machine=machine,
            model=model,
            model_family=model_family,
        )
        manifest.save(self.manifest_path)
        envelope = seal_secret(secret, passphrase, anchor_type=anchor_type)
        save_sealed(envelope, self.sealed_path)
        self._manifest = manifest
        self._context = ctx
        return manifest

    # ------------------------------------------------------------------
    # Loading / authorizing an existing identity
    # ------------------------------------------------------------------

    def load_manifest(self) -> IdentityManifest:
        if self._manifest is None:
            self._manifest = IdentityManifest.load(self.manifest_path)
        return self._manifest

    def authorize(self, passphrase: str) -> SigningContext:
        """Unseal the secret and establish an in-memory signing context."""
        manifest = self.load_manifest()
        if not self.sealed_path.exists():
            raise IdentityError(f"no sealed secret at {self.sealed_path}")
        envelope = load_sealed(self.sealed_path)
        secret = unseal_secret(envelope, passphrase)
        ctx = SigningContext.from_secret(secret, anchor_type=manifest.anchor_type)
        if ctx.fingerprint != manifest.public_key_fingerprint:
            raise IdentityError(
                "public key fingerprint mismatch — manifest and sealed secret disagree"
            )
        self._context = ctx
        return ctx

    @property
    def context(self) -> Optional[SigningContext]:
        """Current signing context, if authorized."""
        return self._context

    @property
    def is_authorized(self) -> bool:
        return self._context is not None

    # ------------------------------------------------------------------
    # Attestation (Layer C)
    # ------------------------------------------------------------------

    def attest(
        self, nonce: str | None = None, ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> AttestationEnvelope:
        """Produce a fresh attestation envelope. Requires authorization."""
        if self._context is None:
            raise IdentityError("not authorized — call authorize() first")
        manifest = self.load_manifest()
        env = attest(
            self._context,
            lct_id=manifest.lct_id,
            manifest_digest=_manifest_digest(manifest),
            nonce=nonce or new_nonce(),
            ttl_seconds=ttl_seconds,
        )
        env.save(self.attest_path)
        return env

    def load_attestation(self) -> AttestationEnvelope | None:
        """Load the cached attestation, if any."""
        if not self.attest_path.exists():
            return None
        return AttestationEnvelope.load(self.attest_path)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def sign(self, data: bytes) -> bytes:
        if self._context is None:
            raise IdentityError("not authorized — call authorize() first")
        return self._context.sign(data)

    def public_key_bytes(self) -> bytes:
        if self._context is not None:
            return self._context.public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw,
            )
        env = self.load_attestation()
        if env is not None:
            import base64

            return base64.b64decode(env.public_key_b64)
        raise IdentityError("cannot recover public key — not authorized and no attestation")
