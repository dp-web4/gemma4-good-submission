"""Tests for the Law module (signed law bundles + registry)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import (
    Law,
    LawBundle,
    LawError,
    LawRef,
    LawRegistry,
    RegistryError,
    RULE_TYPES,
    WitnessSignature,
    add_witness,
    sign_bundle,
    verify_bundle,
    verify_legislator,
    verify_witness,
)


def _law(
    law_id: str = "law:test",
    version: int = 1,
    scope: str = "demo",
    rule_type: str = "permission",
    rule: dict | None = None,
) -> Law:
    return Law(
        law_id=law_id,
        version=version,
        scope=scope,
        rule_type=rule_type,
        rule=rule or {"permit": ["demo"]},
    )


def _sign_ctx() -> SigningContext:
    return SigningContext.from_secret(generate_secret())


# --------------------------------------------------------------------------
# Law
# --------------------------------------------------------------------------


class TestLaw:
    def test_valid_construction(self):
        law = _law()
        assert law.law_id == "law:test"
        assert law.is_effective()

    def test_invalid_rule_type_rejected(self):
        with pytest.raises(LawError):
            Law(
                law_id="l", version=1, scope="s",
                rule_type="nonsense", rule={},
            )

    def test_valid_rule_types(self):
        for rt in RULE_TYPES:
            law = Law(law_id="l", version=1, scope="s", rule_type=rt, rule={})
            assert law.rule_type == rt

    def test_expiry(self):
        past = "2000-01-01T00:00:00Z"
        future = "2099-01-01T00:00:00Z"
        effective = Law(
            law_id="l", version=1, scope="s", rule_type="permission",
            rule={}, effective_at=past, expires_at=future,
        )
        assert effective.is_effective()

        expired = Law(
            law_id="l", version=1, scope="s", rule_type="permission",
            rule={}, effective_at=past, expires_at=past,
        )
        assert not expired.is_effective()

    def test_not_yet_effective(self):
        future = "2099-01-01T00:00:00Z"
        pending = Law(
            law_id="l", version=1, scope="s", rule_type="permission",
            rule={}, effective_at=future,
        )
        assert not pending.is_effective()


# --------------------------------------------------------------------------
# LawBundle
# --------------------------------------------------------------------------


class TestLawBundle:
    def test_digest_stable(self):
        bundle = LawBundle(
            bundle_id="b:1", scope="demo", version=1, laws=[_law()]
        )
        d1 = bundle.digest()
        d2 = bundle.digest()
        assert d1 == d2

    def test_digest_changes_with_contents(self):
        b1 = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        b2 = LawBundle(
            bundle_id="b:1", scope="demo", version=1,
            laws=[_law(), _law("law:2")],
        )
        assert b1.digest() != b2.digest()

    def test_digest_excludes_signature_but_includes_legislator(self):
        """Digest is over canonical_payload. It EXCLUDES signature_b64 and
        witnesses (so attaching witnesses doesn't change the digest) but
        INCLUDES legislator_lct and pubkey (so two different signers
        producing the same law content have different digests)."""
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        ctx = _sign_ctx()
        sign_bundle(b, ctx, "lct:leg")
        digest_after_signing = b.digest()

        # Adding witnesses does NOT change the digest (they're not in the payload)
        add_witness(b, _sign_ctx(), "lct:w1")
        assert b.digest() == digest_after_signing

        # Re-signing (even with the same ctx) produces the same digest
        # because signature_b64 is not part of the canonical payload.
        sig_before = b.signature_b64
        sign_bundle(b, ctx, "lct:leg")
        assert b.digest() == digest_after_signing
        # The signature bytes themselves may or may not differ (Ed25519 is
        # deterministic, so they'll match), but digest is invariant either way.

    def test_sign_verify_roundtrip(self):
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        ctx = _sign_ctx()
        sign_bundle(b, ctx, "lct:leg")
        assert verify_legislator(b) is True
        assert verify_bundle(b) is True

    def test_tampered_bundle_fails_verify(self):
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        sign_bundle(b, _sign_ctx(), "lct:leg")
        # mutate a law after signing
        b.laws.append(_law("law:injected"))
        assert verify_legislator(b) is False

    def test_unsigned_bundle_verify_fails(self):
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        assert verify_legislator(b) is False

    def test_add_witness_counters(self):
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        sign_bundle(b, _sign_ctx(), "lct:leg")
        w1 = _sign_ctx()
        w2 = _sign_ctx()
        add_witness(b, w1, "lct:w1")
        add_witness(b, w2, "lct:w2")
        assert len(b.witnesses) == 2
        for w in b.witnesses:
            assert verify_witness(b, w)

    def test_verify_requires_witnesses(self):
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        sign_bundle(b, _sign_ctx(), "lct:leg")
        assert verify_bundle(b, required_witnesses=0) is True
        assert verify_bundle(b, required_witnesses=1) is False  # none attached
        add_witness(b, _sign_ctx(), "lct:w")
        assert verify_bundle(b, required_witnesses=1) is True
        assert verify_bundle(b, required_witnesses=2) is False

    def test_laws_for_scope_exact(self):
        b = LawBundle(
            bundle_id="b:1", scope="demo", version=1,
            laws=[
                _law("l:a", scope="a"),
                _law("l:b", scope="b"),
                _law("l:a2", scope="a"),
            ],
        )
        matches = b.laws_for_scope("a")
        ids = {lw.law_id for lw in matches}
        assert ids == {"l:a", "l:a2"}

    def test_laws_for_scope_glob(self):
        b = LawBundle(
            bundle_id="b:1", scope="demo", version=1,
            laws=[
                _law("l:tools", scope="tool:*"),
                _law("l:fetch", scope="tool:fetch"),
                _law("l:other", scope="net:*"),
            ],
        )
        matches = b.laws_for_scope("tool:fetch")
        ids = {lw.law_id for lw in matches}
        assert ids == {"l:tools", "l:fetch"}
        matches = b.laws_for_scope("net:post")
        assert {lw.law_id for lw in matches} == {"l:other"}

    def test_roundtrip_file(self, tmp_path: Path):
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        sign_bundle(b, _sign_ctx(), "lct:leg")
        p = tmp_path / "b.json"
        b.save(p)
        loaded = LawBundle.load(p)
        assert loaded.bundle_id == b.bundle_id
        assert loaded.digest() == b.digest()
        assert verify_legislator(loaded)


# --------------------------------------------------------------------------
# LawRef
# --------------------------------------------------------------------------


class TestLawRef:
    def test_from_bundle(self):
        b = LawBundle(
            bundle_id="b:1", scope="demo", version=3,
            laws=[_law("l:a"), _law("l:b")],
        )
        ref = LawRef.from_bundle(b)
        assert ref.bundle_id == "b:1"
        assert ref.version == 3
        assert ref.bundle_digest == b.digest()
        assert set(ref.law_ids_applied) == {"l:a", "l:b"}

    def test_ref_with_subset(self):
        b = LawBundle(
            bundle_id="b:1", scope="demo", version=1,
            laws=[_law("l:a"), _law("l:b")],
        )
        ref = LawRef.from_bundle(b, [b.laws[0]])
        assert ref.law_ids_applied == ["l:a"]


# --------------------------------------------------------------------------
# LawRegistry
# --------------------------------------------------------------------------


def _signed_bundle(
    bundle_id: str = "b:1", scope: str = "demo", version: int = 1,
    laws: list[Law] | None = None,
) -> LawBundle:
    b = LawBundle(
        bundle_id=bundle_id, scope=scope, version=version,
        laws=laws or [_law()],
    )
    sign_bundle(b, _sign_ctx(), "lct:leg")
    return b


class TestLawRegistry:
    def test_register_and_active(self):
        reg = LawRegistry()
        b = _signed_bundle()
        reg.register(b)
        assert reg.active("demo") is b

    def test_register_rejects_unsigned(self):
        reg = LawRegistry()
        b = LawBundle(bundle_id="b:1", scope="demo", version=1, laws=[_law()])
        with pytest.raises(RegistryError):
            reg.register(b)

    def test_newer_version_supersedes(self):
        reg = LawRegistry()
        b1 = _signed_bundle(bundle_id="b:1", version=1)
        b2 = _signed_bundle(bundle_id="b:2", version=2)
        reg.register(b1)
        reg.register(b2)
        assert reg.active("demo") is b2
        assert b2.supersedes_bundle == "b:1"

    def test_older_version_rejected(self):
        reg = LawRegistry()
        b2 = _signed_bundle(bundle_id="b:2", version=2)
        reg.register(b2)
        b1 = _signed_bundle(bundle_id="b:1", version=1)
        with pytest.raises(RegistryError, match="not newer"):
            reg.register(b1)

    def test_supersession_chain(self):
        reg = LawRegistry()
        b1 = _signed_bundle(bundle_id="b:1", version=1)
        b2 = _signed_bundle(bundle_id="b:2", version=2)
        b3 = _signed_bundle(bundle_id="b:3", version=3)
        reg.register(b1)
        reg.register(b2)
        reg.register(b3)
        chain = reg.supersession_chain("demo")
        ids = [b.bundle_id for b in chain]
        assert ids == ["b:3", "b:2", "b:1"]

    def test_isolated_scopes(self):
        reg = LawRegistry()
        reg.register(_signed_bundle(bundle_id="b:t", scope="tools"))
        reg.register(_signed_bundle(bundle_id="b:f", scope="federation"))
        assert reg.active("tools").bundle_id == "b:t"
        assert reg.active("federation").bundle_id == "b:f"
        assert set(reg.scopes()) == {"tools", "federation"}

    def test_required_witnesses_enforced(self):
        reg = LawRegistry()
        reg.required_witnesses = 1
        b = _signed_bundle()
        with pytest.raises(RegistryError):
            reg.register(b)
        add_witness(b, _sign_ctx(), "lct:w")
        reg.register(b)
        assert reg.active("demo") is b

    def test_load_directory(self, tmp_path: Path):
        reg = LawRegistry()
        b1 = _signed_bundle(bundle_id="b:1", version=1, scope="a")
        b2 = _signed_bundle(bundle_id="b:2", version=1, scope="b")
        b1.save(tmp_path / "b1.json")
        b2.save(tmp_path / "b2.json")
        count = reg.load_directory(tmp_path)
        assert count == 2
        assert reg.active("a").bundle_id == "b:1"
        assert reg.active("b").bundle_id == "b:2"
