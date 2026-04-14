"""
Decision — the signed outcome of a policy evaluation.

A Decision is produced by PolicyGate when evaluating an R6Action against
a LawBundle. It carries the verdict (allow | deny | defer), the LawRef
that identifies the exact bundle consulted, and — when signed — the
evaluator's signature over a canonical payload.

Pair with the R6Action to form a complete two-part audit bundle.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from cryptography.hazmat.primitives import serialization

from ..identity.signing import SigningContext, verify_with_pubkey
from ..law.law import LawRef


class Verdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    DEFER = "defer"  # requires human review / additional context


@dataclass
class RuleFailure:
    """Per-law verdict captured when a rule fails."""

    law_id: str
    reason: str


@dataclass
class Decision:
    """The signed outcome of policy evaluation."""

    action_id: str  # R6 action this decision applies to
    verdict: Verdict
    law_ref: LawRef
    reason: str = ""  # top-level human-readable summary
    failures: list[RuleFailure] = field(default_factory=list)
    evaluator_lct: str = ""
    evaluator_pubkey_b64: str = ""
    evaluated_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    signature_b64: str = ""

    # --- canonical payload ---

    def canonical_payload(self) -> bytes:
        data = {
            "action_id": self.action_id,
            "verdict": self.verdict.value,
            "law_ref": self.law_ref.to_dict(),
            "reason": self.reason,
            "failures": [asdict(f) for f in self.failures],
            "evaluator_lct": self.evaluator_lct,
            "evaluator_pubkey_b64": self.evaluator_pubkey_b64,
            "evaluated_at": self.evaluated_at,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_payload()).hexdigest()

    # --- signing ---

    def sign(self, evaluator: SigningContext, evaluator_lct: str) -> None:
        """Sign this decision in place."""
        pub_bytes = evaluator.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.evaluator_lct = evaluator_lct
        self.evaluator_pubkey_b64 = base64.b64encode(pub_bytes).decode("ascii")
        sig = evaluator.sign(self.canonical_payload())
        self.signature_b64 = base64.b64encode(sig).decode("ascii")

    def verify(self) -> bool:
        if not self.signature_b64 or not self.evaluator_pubkey_b64:
            return False
        try:
            pub = base64.b64decode(self.evaluator_pubkey_b64)
            sig = base64.b64decode(self.signature_b64)
        except (ValueError, TypeError):
            return False
        return verify_with_pubkey(pub, self.canonical_payload(), sig)

    # --- serialization ---

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Decision:
        return cls(
            action_id=d["action_id"],
            verdict=Verdict(d["verdict"]),
            law_ref=LawRef(**d["law_ref"]),
            reason=d.get("reason", ""),
            failures=[RuleFailure(**f) for f in d.get("failures", [])],
            evaluator_lct=d.get("evaluator_lct", ""),
            evaluator_pubkey_b64=d.get("evaluator_pubkey_b64", ""),
            evaluated_at=d.get("evaluated_at", ""),
            signature_b64=d.get("signature_b64", ""),
        )

    # --- convenience ---

    @property
    def is_allow(self) -> bool:
        return self.verdict == Verdict.ALLOW

    @property
    def is_deny(self) -> bool:
        return self.verdict == Verdict.DENY

    @property
    def is_defer(self) -> bool:
        return self.verdict == Verdict.DEFER
