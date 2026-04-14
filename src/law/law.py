"""
Law and LawBundle — the signed substrate of policy evaluation.

A Law is a single rule with an id, version, scope, rule body, and validity
window. A LawBundle is a named, versioned collection of laws signed by a
Legislator and optionally countersigned by witnesses.

Bundles are the unit of deployment, versioning, and attestation. Every R6
audit bundle embeds a `LawRef` pointing to the exact bundle that governed
its evaluation.

Rule body language
------------------

Rules are expressed as small predicate dicts. The full set understood by
the included rule interpreter (see `src/policy/rules.py`):

    {"permit": ["tool:read", "tool:click"]}       allowlist
    {"deny":   ["tool:exec"]}                     explicit denials
    {"max_cost": 10.0}                            cost constraint
    {"max_rate_per_minute": 10}                   rate limit
    {"require_ceiling": 0.7}                      min identity ceiling
    {"require_t3_min": {"temperament": 0.6}}      per-dimension T3 mins
    {"require_witness": 1}                        min witness attestations

Multiple rules in a bundle ANDed for evaluation: all must pass.
"""

from __future__ import annotations

import base64
import calendar
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iso_to_epoch(ts: str) -> float:
    # calendar.timegm interprets the struct_time as UTC (matching _now_iso);
    # time.mktime interprets it as local time, which produces off-by-TZ bugs.
    return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))


class LawError(Exception):
    """Law construction / verification failed."""


# --------------------------------------------------------------------------
# Law
# --------------------------------------------------------------------------


RULE_TYPES = frozenset(
    {"permission", "constraint", "ceiling", "prohibition", "requirement"}
)


@dataclass
class Law:
    """A single rule within a bundle."""

    law_id: str
    version: int
    scope: str  # e.g., "arc-agi-3-player", "federation", "tool:*"
    rule_type: str  # one of RULE_TYPES
    rule: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    effective_at: str = field(default_factory=_now_iso)
    expires_at: str = ""  # empty = no expiry
    supersedes: str = ""  # law_id this replaces, if any

    def __post_init__(self) -> None:
        if self.rule_type not in RULE_TYPES:
            raise LawError(
                f"rule_type must be one of {sorted(RULE_TYPES)}, got {self.rule_type!r}"
            )

    def is_effective(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if now < _iso_to_epoch(self.effective_at):
            return False
        if self.expires_at and now >= _iso_to_epoch(self.expires_at):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Law:
        return cls(**d)


# --------------------------------------------------------------------------
# LawBundle
# --------------------------------------------------------------------------


@dataclass
class WitnessSignature:
    """A co-signer attesting that they have read and accept the bundle."""

    witness_lct: str
    public_key_b64: str
    signature_b64: str


@dataclass
class LawBundle:
    """A named, versioned, signed collection of laws.

    Legislator signs the bundle's canonical digest. Witnesses optionally
    countersign. Bundle is verifiable offline using only its contents.
    """

    bundle_id: str
    scope: str
    version: int
    laws: list[Law] = field(default_factory=list)
    legislator_lct: str = ""
    legislator_pubkey_b64: str = ""
    issued_at: str = field(default_factory=_now_iso)
    expires_at: str = ""
    supersedes_bundle: str = ""
    signature_b64: str = ""  # legislator signature
    witnesses: list[WitnessSignature] = field(default_factory=list)

    # ---- digest ----

    def canonical_payload(self) -> bytes:
        """The bytes that are signed. Stable across runs, sort_keys=True."""
        data = {
            "bundle_id": self.bundle_id,
            "scope": self.scope,
            "version": self.version,
            "laws": [law.to_dict() for law in self.laws],
            "legislator_lct": self.legislator_lct,
            "legislator_pubkey_b64": self.legislator_pubkey_b64,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "supersedes_bundle": self.supersedes_bundle,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_payload()).hexdigest()

    # ---- effective window ----

    def is_effective(self, now: float | None = None) -> bool:
        now = now if now is not None else time.time()
        if now < _iso_to_epoch(self.issued_at):
            return False
        if self.expires_at and now >= _iso_to_epoch(self.expires_at):
            return False
        return True

    def active_laws(self, now: float | None = None) -> list[Law]:
        """Laws that are within their individual effective window."""
        return [law for law in self.laws if law.is_effective(now)]

    def laws_for_scope(self, scope: str, now: float | None = None) -> list[Law]:
        """Laws whose scope matches the requested scope.

        Supports glob suffixes: bundle law scope `tool:*` matches request
        scope `tool:web_fetch`. Exact match is preferred.
        """
        active = self.active_laws(now)
        matches: list[Law] = []
        for law in active:
            if law.scope == scope:
                matches.append(law)
            elif law.scope.endswith("*"):
                prefix = law.scope[:-1]
                if scope.startswith(prefix):
                    matches.append(law)
        return matches

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LawBundle:
        laws = [Law.from_dict(lx) for lx in d.get("laws", [])]
        witnesses = [WitnessSignature(**w) for w in d.get("witnesses", [])]
        return cls(
            bundle_id=d["bundle_id"],
            scope=d["scope"],
            version=d["version"],
            laws=laws,
            legislator_lct=d.get("legislator_lct", ""),
            legislator_pubkey_b64=d.get("legislator_pubkey_b64", ""),
            issued_at=d.get("issued_at", _now_iso()),
            expires_at=d.get("expires_at", ""),
            supersedes_bundle=d.get("supersedes_bundle", ""),
            signature_b64=d.get("signature_b64", ""),
            witnesses=witnesses,
        )

    @classmethod
    def load(cls, path: str | Path) -> LawBundle:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())


# --------------------------------------------------------------------------
# LawRef — the pointer embedded in R6 audit records
# --------------------------------------------------------------------------


@dataclass
class LawRef:
    """Compact reference to the law bundle under which an action was evaluated.

    This is the audit anchor: the R6Action bundle cannot be verified
    without checking that the cited LawBundle existed, had this digest,
    and was properly signed.
    """

    bundle_id: str
    bundle_digest: str
    version: int
    law_ids_applied: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_bundle(
        cls, bundle: LawBundle, laws_applied: list[Law] | None = None
    ) -> LawRef:
        return cls(
            bundle_id=bundle.bundle_id,
            bundle_digest=bundle.digest(),
            version=bundle.version,
            law_ids_applied=[lw.law_id for lw in (laws_applied or bundle.laws)],
        )


# --------------------------------------------------------------------------
# Encoding helpers shared with signing module
# --------------------------------------------------------------------------


def b64e(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))
