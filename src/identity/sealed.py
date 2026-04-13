"""
Layer B — Sealed secret.

The root secret is the seed material from which the identity key pair
is derived. In a production deployment this file is sealed to hardware
(TPM2, FIDO2, Secure Enclave) and unsealing requires a challenge-
response cycle with the anchor device.

This module provides the software fallback path: passphrase-based AES-GCM
encryption. Trust ceiling for software-sealed identities is 0.4 (see
`manifest.py::TRUST_CEILINGS`). Sufficient for development and for the
hackathon demo; insufficient for production claims.

The file format:
  {
    "version": 1,
    "anchor_type": "software",
    "kdf": {"algorithm": "pbkdf2-sha256", "salt": "<b64>", "iterations": 200000},
    "cipher": {"algorithm": "aes-256-gcm", "nonce": "<b64>", "ciphertext": "<b64>"}
  }
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes


SEAL_VERSION = 1
KDF_ITERATIONS = 200_000
SECRET_BYTES = 32  # Ed25519 seed size


class SealError(Exception):
    """Sealing/unsealing failed."""


def generate_secret() -> bytes:
    """Generate a fresh 32-byte random identity secret."""
    return secrets.token_bytes(SECRET_BYTES)


def _b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(passphrase.encode("utf-8"))


def seal_secret(secret: bytes, passphrase: str, anchor_type: str = "software") -> dict:
    """Seal a secret under a passphrase. Returns the sealed envelope."""
    if len(secret) != SECRET_BYTES:
        raise SealError(f"secret must be {SECRET_BYTES} bytes, got {len(secret)}")
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = _derive_key(passphrase, salt)
    ciphertext = AESGCM(key).encrypt(nonce, secret, associated_data=None)
    return {
        "version": SEAL_VERSION,
        "anchor_type": anchor_type,
        "kdf": {
            "algorithm": "pbkdf2-sha256",
            "salt": _b64e(salt),
            "iterations": KDF_ITERATIONS,
        },
        "cipher": {
            "algorithm": "aes-256-gcm",
            "nonce": _b64e(nonce),
            "ciphertext": _b64e(ciphertext),
        },
    }


def unseal_secret(envelope: dict, passphrase: str) -> bytes:
    """Unseal a sealed envelope. Raises SealError on failure."""
    if envelope.get("version") != SEAL_VERSION:
        raise SealError(f"unsupported seal version: {envelope.get('version')}")
    try:
        salt = _b64d(envelope["kdf"]["salt"])
        nonce = _b64d(envelope["cipher"]["nonce"])
        ciphertext = _b64d(envelope["cipher"]["ciphertext"])
    except (KeyError, ValueError) as e:
        raise SealError(f"malformed envelope: {e}") from e

    key = _derive_key(passphrase, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data=None)
    except Exception as e:
        raise SealError("decryption failed (wrong passphrase?)") from e


def save_sealed(envelope: dict, path: str | Path) -> None:
    Path(path).write_text(json.dumps(envelope, indent=2, sort_keys=False))


def load_sealed(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)
