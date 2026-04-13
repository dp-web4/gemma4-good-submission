"""
Layer C — AttestationEnvelope.

A cached proof that some authority has witnessed and verified the
identity. In production this is the output of a hardware attestation
handshake (TPM2 quote, FIDO2 attestation statement, SE attestation).

For the software path this module produces a self-attestation: the
agent signs its own manifest with its authorized signing key. It's a
weaker claim — it proves the agent holds the private key, not that the
agent ran on a trusted platform — but it's a valid structural element
that federation peers can exchange and verify.

Envelopes expire: freshness is part of the trust signal.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from .signing import SigningContext, verify_with_pubkey


DEFAULT_TTL_SECONDS = 3600  # 1 hour


def _now() -> float:
    return time.time()


def _iso(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


@dataclass
class AttestationEnvelope:
    """Signed claim: at `issued_at`, this key attested to this manifest."""

    lct_id: str
    anchor_type: str
    public_key_b64: str  # raw Ed25519 public key, base64
    manifest_digest: str  # sha256 of canonical manifest JSON
    nonce: str  # challenge nonce for replay protection
    issued_at: str
    expires_at: str
    signature_b64: str = ""

    def signing_payload(self) -> bytes:
        """Canonical payload that was/will-be signed. Signature field excluded."""
        d = asdict(self)
        d.pop("signature_b64", None)
        return json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @property
    def expires_epoch(self) -> float:
        return time.mktime(time.strptime(self.expires_at, "%Y-%m-%dT%H:%M:%SZ"))

    def is_fresh(self, now: float | None = None) -> bool:
        now = now if now is not None else _now()
        return now < self.expires_epoch

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, d: dict) -> AttestationEnvelope:
        return cls(**d)

    @classmethod
    def load(cls, path: str | Path) -> AttestationEnvelope:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())


def attest(
    context: SigningContext,
    lct_id: str,
    manifest_digest: str,
    nonce: str,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> AttestationEnvelope:
    """Produce a signed attestation envelope.

    In the software path, the agent self-attests: it signs a payload
    containing its own public key + manifest digest + nonce + timestamps.
    A peer who trusts the public key can verify the signature and accept
    the envelope.
    """
    pub_bytes = context.public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    import base64

    now = _now()
    env = AttestationEnvelope(
        lct_id=lct_id,
        anchor_type=context.anchor_type,
        public_key_b64=base64.b64encode(pub_bytes).decode("ascii"),
        manifest_digest=manifest_digest,
        nonce=nonce,
        issued_at=_iso(now),
        expires_at=_iso(now + ttl_seconds),
    )
    sig = context.sign(env.signing_payload())
    env.signature_b64 = base64.b64encode(sig).decode("ascii")
    return env


def verify_envelope(env: AttestationEnvelope) -> bool:
    """Verify the envelope's signature against its embedded public key."""
    import base64

    try:
        pub_bytes = base64.b64decode(env.public_key_b64)
        sig = base64.b64decode(env.signature_b64)
    except (ValueError, TypeError):
        return False
    return verify_with_pubkey(pub_bytes, env.signing_payload(), sig)
