"""Tests for the three-layer identity module."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.identity import (
    AttestationEnvelope,
    IdentityError,
    IdentityManifest,
    IdentityProvider,
    SealError,
    SigningContext,
    TRUST_CEILINGS,
    attest,
    generate_secret,
    make_lct_id,
    new_nonce,
    seal_secret,
    unseal_secret,
    verify_envelope,
    verify_with_pubkey,
)
from src.identity.provider import _manifest_digest


# --------------------------------------------------------------------------
# Layer A — manifest
# --------------------------------------------------------------------------


class TestManifest:
    def test_default_trust_ceiling(self):
        m = IdentityManifest(name="nomad", lct_id="lct:nomad/test")
        assert m.anchor_type == "software"
        assert m.trust_ceiling == 0.4

    def test_hardware_trust_ceilings(self):
        assert TRUST_CEILINGS["tpm2"] == 1.0
        assert TRUST_CEILINGS["fido2"] == 0.9
        assert TRUST_CEILINGS["secure_enclave"] == 0.85
        assert TRUST_CEILINGS["software"] == 0.4

    def test_roundtrip(self, tmp_path: Path):
        m = IdentityManifest(
            name="agent",
            lct_id="lct:test/agent",
            public_key_fingerprint="abc123",
            anchor_type="fido2",
            machine="thor",
            model="gemma4-e4b",
        )
        p = tmp_path / "identity.json"
        m.save(p)
        loaded = IdentityManifest.load(p)
        assert loaded.name == m.name
        assert loaded.anchor_type == m.anchor_type
        assert loaded.trust_ceiling == 0.9
        assert loaded.public_key_fingerprint == "abc123"

    def test_trust_ceiling_not_persisted_as_authority(self, tmp_path: Path):
        """trust_ceiling is derived, not stored — loading tolerates its presence."""
        p = tmp_path / "id.json"
        raw = {
            "name": "n",
            "lct_id": "lct:x",
            "anchor_type": "tpm2",
            "trust_ceiling": 999.0,  # attacker-injected
        }
        p.write_text(json.dumps(raw))
        m = IdentityManifest.load(p)
        assert m.trust_ceiling == 1.0  # derived from anchor_type, not loaded


# --------------------------------------------------------------------------
# Layer B — sealed
# --------------------------------------------------------------------------


class TestSealed:
    def test_seal_unseal_roundtrip(self):
        secret = generate_secret()
        envelope = seal_secret(secret, "correct horse battery staple")
        recovered = unseal_secret(envelope, "correct horse battery staple")
        assert recovered == secret

    def test_wrong_passphrase_fails(self):
        secret = generate_secret()
        envelope = seal_secret(secret, "correct")
        with pytest.raises(SealError):
            unseal_secret(envelope, "wrong")

    def test_envelope_has_no_plaintext(self):
        secret = generate_secret()
        envelope = seal_secret(secret, "pp")
        blob = json.dumps(envelope).encode()
        assert secret not in blob  # raw bytes not present
        # and the ciphertext is not trivially the secret
        import base64

        ct = base64.b64decode(envelope["cipher"]["ciphertext"])
        assert ct != secret

    def test_secret_length(self):
        secret = generate_secret()
        assert len(secret) == 32

    def test_each_seal_is_fresh(self):
        """Same secret + passphrase → different envelope (fresh salt + nonce)."""
        secret = generate_secret()
        e1 = seal_secret(secret, "pp")
        e2 = seal_secret(secret, "pp")
        assert e1["kdf"]["salt"] != e2["kdf"]["salt"]
        assert e1["cipher"]["nonce"] != e2["cipher"]["nonce"]
        assert e1["cipher"]["ciphertext"] != e2["cipher"]["ciphertext"]


# --------------------------------------------------------------------------
# SigningContext
# --------------------------------------------------------------------------


class TestSigning:
    def test_sign_verify_roundtrip(self):
        secret = generate_secret()
        ctx = SigningContext.from_secret(secret)
        data = b"hello world"
        sig = ctx.sign(data)
        assert ctx.verify(data, sig) is True

    def test_verify_fails_on_tampered_data(self):
        ctx = SigningContext.from_secret(generate_secret())
        sig = ctx.sign(b"original")
        assert ctx.verify(b"tampered", sig) is False

    def test_fingerprint_stable(self):
        secret = generate_secret()
        ctx1 = SigningContext.from_secret(secret)
        ctx2 = SigningContext.from_secret(secret)
        assert ctx1.fingerprint == ctx2.fingerprint

    def test_fingerprint_different_secrets(self):
        ctx1 = SigningContext.from_secret(generate_secret())
        ctx2 = SigningContext.from_secret(generate_secret())
        assert ctx1.fingerprint != ctx2.fingerprint

    def test_verify_with_pubkey_standalone(self):
        from cryptography.hazmat.primitives import serialization

        ctx = SigningContext.from_secret(generate_secret())
        sig = ctx.sign(b"msg")
        pub_bytes = ctx.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        assert verify_with_pubkey(pub_bytes, b"msg", sig) is True
        assert verify_with_pubkey(pub_bytes, b"other", sig) is False

    def test_invalid_seed_length(self):
        with pytest.raises(ValueError):
            SigningContext.from_secret(b"too short")


# --------------------------------------------------------------------------
# Layer C — attestation
# --------------------------------------------------------------------------


class TestAttestation:
    def test_attest_verify_roundtrip(self):
        ctx = SigningContext.from_secret(generate_secret())
        env = attest(ctx, "lct:test", "digest123", new_nonce())
        assert verify_envelope(env) is True

    def test_tampered_envelope_fails(self):
        ctx = SigningContext.from_secret(generate_secret())
        env = attest(ctx, "lct:test", "digest", new_nonce())
        # mutate the lct_id — signature should no longer verify
        env.lct_id = "lct:attacker"
        assert verify_envelope(env) is False

    def test_freshness(self):
        ctx = SigningContext.from_secret(generate_secret())
        env = attest(ctx, "lct:test", "digest", new_nonce(), ttl_seconds=3600)
        assert env.is_fresh() is True
        # fake a future clock
        future = time.mktime(time.strptime(env.expires_at, "%Y-%m-%dT%H:%M:%SZ")) + 10
        assert env.is_fresh(now=future) is False

    def test_envelope_roundtrip(self, tmp_path: Path):
        ctx = SigningContext.from_secret(generate_secret())
        env = attest(ctx, "lct:test", "digest", new_nonce())
        p = tmp_path / "att.json"
        env.save(p)
        loaded = AttestationEnvelope.load(p)
        assert verify_envelope(loaded) is True
        assert loaded.lct_id == env.lct_id


# --------------------------------------------------------------------------
# IdentityProvider — the whole flow
# --------------------------------------------------------------------------


class TestProvider:
    def test_bootstrap_then_authorize(self, tmp_path: Path):
        provider = IdentityProvider(tmp_path)
        manifest = provider.bootstrap(
            name="agent1",
            passphrase="pp",
            machine="thor",
            model="gemma4-e4b",
        )
        assert manifest.lct_id == "lct:thor/agent1"
        assert manifest.public_key_fingerprint  # non-empty
        assert manifest.trust_ceiling == 0.4  # software default

        # files on disk
        assert (tmp_path / "identity.json").exists()
        assert (tmp_path / "identity.sealed").exists()

        # new provider instance can authorize from disk
        other = IdentityProvider(tmp_path)
        ctx = other.authorize("pp")
        assert ctx.fingerprint == manifest.public_key_fingerprint
        assert other.is_authorized

    def test_double_bootstrap_rejected(self, tmp_path: Path):
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="pp")
        with pytest.raises(IdentityError):
            p.bootstrap(name="b", passphrase="pp")

    def test_wrong_passphrase_fails_authorization(self, tmp_path: Path):
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="good")
        other = IdentityProvider(tmp_path)
        with pytest.raises(SealError):
            other.authorize("bad")

    def test_attest_requires_authorization(self, tmp_path: Path):
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="pp")
        other = IdentityProvider(tmp_path)  # loaded but not authorized
        with pytest.raises(IdentityError):
            other.attest()

    def test_attest_produces_verifiable_envelope(self, tmp_path: Path):
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="pp", machine="thor")
        p.authorize("pp")
        env = p.attest()
        assert verify_envelope(env)
        assert env.lct_id == "lct:thor/a"
        # digest in envelope should match a fresh manifest digest
        assert env.manifest_digest == _manifest_digest(p.load_manifest())

    def test_attestation_cached_on_disk(self, tmp_path: Path):
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="pp")
        p.authorize("pp")
        p.attest()
        loaded = p.load_attestation()
        assert loaded is not None
        assert verify_envelope(loaded)

    def test_sign_requires_authorization(self, tmp_path: Path):
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="pp")
        other = IdentityProvider(tmp_path)
        with pytest.raises(IdentityError):
            other.sign(b"x")

    def test_manifest_fingerprint_binds_to_sealed_secret(self, tmp_path: Path):
        """If someone swaps identity.sealed, authorization fails."""
        p1 = IdentityProvider(tmp_path)
        p1.bootstrap(name="a", passphrase="pp")

        # create a second identity in a different directory, then swap its sealed file in
        other_dir = tmp_path / "other"
        p2 = IdentityProvider(other_dir)
        p2.bootstrap(name="b", passphrase="pp")

        # overwrite p1's sealed file with p2's — fingerprints will disagree
        import shutil

        shutil.copy(p2.sealed_path, p1.sealed_path)

        p3 = IdentityProvider(tmp_path)
        with pytest.raises(IdentityError, match="fingerprint mismatch"):
            p3.authorize("pp")


# --------------------------------------------------------------------------
# End-to-end: two-party attestation exchange
# --------------------------------------------------------------------------


class TestPeerExchange:
    def test_alice_attests_bob_verifies(self, tmp_path: Path):
        """Alice and Bob run independent providers. Alice attests; Bob verifies using
        nothing but the envelope itself (public key is embedded)."""
        alice_dir = tmp_path / "alice"
        bob_dir = tmp_path / "bob"

        alice = IdentityProvider(alice_dir)
        alice.bootstrap(name="alice", passphrase="a-pp", machine="legion")
        alice.authorize("a-pp")

        bob = IdentityProvider(bob_dir)
        bob.bootstrap(name="bob", passphrase="b-pp", machine="mcnugget")
        bob.authorize("b-pp")

        # Alice produces an attestation
        envelope = alice.attest(nonce="bob-challenge-42")

        # Bob receives the envelope and verifies — he needs nothing from Alice
        # except the envelope itself.
        assert verify_envelope(envelope)
        assert envelope.nonce == "bob-challenge-42"
        assert envelope.lct_id == "lct:legion/alice"
        assert envelope.is_fresh()

    def test_replay_protection_via_nonce(self, tmp_path: Path):
        """A verifier should check that the nonce matches what it issued.
        verify_envelope only proves authenticity — nonce checking is the
        consumer's job."""
        p = IdentityProvider(tmp_path)
        p.bootstrap(name="a", passphrase="pp")
        p.authorize("pp")
        env = p.attest(nonce="challenge-1")
        # attempted replay with a different challenge
        assert env.nonce == "challenge-1"
        assert env.nonce != "challenge-2"  # consumer would reject
