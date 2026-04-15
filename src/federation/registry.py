"""
PeerRegistry — local view of known peers and their attestations.

Persisted per machine. Other machines have their own registries with
potentially different records. Federation does not mandate a global
view; each agent's registry is a record of *its* observations.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ..identity.attestation import AttestationEnvelope, verify_envelope
from .peer import Peer


class FederationError(Exception):
    """Federation-level operation failed."""


@dataclass
class PeerRegistry:
    """Local-knowledge registry of remote peers."""

    _peers: dict[str, Peer] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, lct_id: str) -> Peer | None:
        return self._peers.get(lct_id)

    def known(self, lct_id: str) -> bool:
        return lct_id in self._peers

    def all(self) -> list[Peer]:
        return list(self._peers.values())

    def __len__(self) -> int:
        return len(self._peers)

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def observe(
        self, envelope: AttestationEnvelope, *, expected_nonce: str | None = None
    ) -> Peer:
        """Verify an envelope and update the peer record.

        - Envelope signature must verify.
        - If expected_nonce is given, envelope.nonce must match (replay defense).
        - Envelope must be fresh (within its own ttl).

        On success, the peer is created or updated and returned.
        """
        if not verify_envelope(envelope):
            raise FederationError(
                f"envelope from {envelope.lct_id!r} failed signature verification"
            )
        if expected_nonce is not None and envelope.nonce != expected_nonce:
            raise FederationError(
                f"nonce mismatch: expected {expected_nonce!r}, got {envelope.nonce!r}"
            )
        if not envelope.is_fresh():
            raise FederationError(
                f"envelope from {envelope.lct_id!r} is past its expiry"
            )

        peer = self._peers.get(envelope.lct_id)
        if peer is None:
            peer = Peer(
                lct_id=envelope.lct_id,
                anchor_type=envelope.anchor_type,
                last_envelope=envelope.to_dict(),
            )
            self._peers[envelope.lct_id] = peer
        else:
            peer.last_envelope = envelope.to_dict()
            peer.anchor_type = envelope.anchor_type
        peer.update_seen()
        return peer

    def forget(self, lct_id: str) -> bool:
        return self._peers.pop(lct_id, None) is not None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        data = {"peers": {lct: p.to_dict() for lct, p in self._peers.items()}}
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=False))

    @classmethod
    def load(cls, path: str | Path) -> PeerRegistry:
        with open(path) as f:
            data = json.load(f)
        reg = cls()
        for lct, pd in data.get("peers", {}).items():
            reg._peers[lct] = Peer.from_dict(pd)
        return reg
