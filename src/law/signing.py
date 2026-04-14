"""
Signing and verification for LawBundles.

A bundle is signed by a Legislator (an Ed25519 key held in an identity).
Witnesses may countersign the same canonical payload. Verification only
needs the bundle itself — the legislator's public key is embedded.

Witness chain
-------------

Each witness produces their own signature over the same canonical payload.
The bundle carries `witnesses: list[WitnessSignature]` each with the
witness's public key and signature. A verifier iterates the witnesses and
accepts the bundle at the trust level appropriate for the witness quorum
they consider trustworthy.
"""

from __future__ import annotations

from cryptography.hazmat.primitives import serialization

from ..identity.signing import SigningContext, verify_with_pubkey
from .law import LawBundle, WitnessSignature, b64d, b64e


class LawSignatureError(Exception):
    """Signing or verification failed."""


def sign_bundle(bundle: LawBundle, legislator: SigningContext, legislator_lct: str) -> None:
    """Sign a bundle in place. Fills legislator_lct, pubkey, and signature.

    The legislator LCT and pubkey are set BEFORE computing the canonical
    payload so that verification (which also reads those fields) produces
    the identical byte sequence.
    """
    pub_bytes = legislator.public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    bundle.legislator_lct = legislator_lct
    bundle.legislator_pubkey_b64 = b64e(pub_bytes)
    payload = bundle.canonical_payload()  # now includes the fields we just set
    sig = legislator.sign(payload)
    bundle.signature_b64 = b64e(sig)


def verify_legislator(bundle: LawBundle) -> bool:
    """Verify the legislator's signature against the bundle's canonical payload."""
    if not bundle.signature_b64 or not bundle.legislator_pubkey_b64:
        return False
    try:
        pub_bytes = b64d(bundle.legislator_pubkey_b64)
        sig = b64d(bundle.signature_b64)
    except (ValueError, TypeError):
        return False
    return verify_with_pubkey(pub_bytes, bundle.canonical_payload(), sig)


def add_witness(
    bundle: LawBundle, witness: SigningContext, witness_lct: str
) -> WitnessSignature:
    """Append a witness countersignature. Returns the appended record."""
    payload = bundle.canonical_payload()
    sig = witness.sign(payload)
    pub_bytes = witness.public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    record = WitnessSignature(
        witness_lct=witness_lct,
        public_key_b64=b64e(pub_bytes),
        signature_b64=b64e(sig),
    )
    bundle.witnesses.append(record)
    return record


def verify_witness(bundle: LawBundle, witness: WitnessSignature) -> bool:
    """Verify a single witness signature against the bundle payload."""
    try:
        pub_bytes = b64d(witness.public_key_b64)
        sig = b64d(witness.signature_b64)
    except (ValueError, TypeError):
        return False
    return verify_with_pubkey(pub_bytes, bundle.canonical_payload(), sig)


def verify_bundle(
    bundle: LawBundle, *, required_witnesses: int = 0
) -> bool:
    """Full verification: legislator valid AND enough valid witness signatures."""
    if not verify_legislator(bundle):
        return False
    if required_witnesses == 0:
        return True
    valid = sum(1 for w in bundle.witnesses if verify_witness(bundle, w))
    return valid >= required_witnesses
