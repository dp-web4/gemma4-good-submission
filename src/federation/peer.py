"""
Peer — a remote agent we have observed and (optionally) trust.

A Peer record holds:
  - the peer's LCT id and last-known attestation envelope
  - the moment they were first and most recently seen
  - their declared anchor type → trust ceiling cap

Peer state is local. Two peers can hold disagreeing records about each
other (different observation histories, different trust outcomes).
That's expected — federated trust is subjective per peer.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from ..identity.attestation import AttestationEnvelope
from ..identity.manifest import TRUST_CEILINGS


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class Peer:
    """A peer observed by this agent."""

    lct_id: str
    anchor_type: str = "software"
    last_envelope: dict | None = None  # AttestationEnvelope.to_dict() most recent
    first_seen: str = field(default_factory=_now_iso)
    last_seen: str = field(default_factory=_now_iso)
    interactions: int = 0

    @property
    def trust_ceiling(self) -> float:
        return TRUST_CEILINGS.get(self.anchor_type, 0.4)

    @property
    def has_attestation(self) -> bool:
        return self.last_envelope is not None

    def update_seen(self) -> None:
        self.last_seen = _now_iso()
        self.interactions += 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> Peer:
        return cls(
            lct_id=d["lct_id"],
            anchor_type=d.get("anchor_type", "software"),
            last_envelope=d.get("last_envelope"),
            first_seen=d.get("first_seen", _now_iso()),
            last_seen=d.get("last_seen", _now_iso()),
            interactions=int(d.get("interactions", 0)),
        )

    def envelope(self) -> AttestationEnvelope | None:
        if self.last_envelope is None:
            return None
        return AttestationEnvelope.from_dict(self.last_envelope)
