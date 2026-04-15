"""
DreamBundle — exported high-salience experience for consolidation.

A bundle holds R6 actions + their decisions + V3 outcomes + SNARC scores,
selected from a session because they exceeded a salience threshold.
Bundles become the input for fine-tuning, retrieval cartridges, and
cross-machine knowledge transfer.

The bundle shape IS the training-data shape. One file = one batch of
audit-grade examples ready for the next learning cycle.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..policy.decision import Decision
from ..r6.action import R6Action
from ..r6.serialize import to_dict as r6_to_dict
from ..snarc.score import SnarcScore


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_bundle_id() -> str:
    return f"dream:{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:16]}"


@dataclass
class DreamEntry:
    """One experience inside a bundle: action + decision + outcome + salience."""

    action: dict  # serialized R6Action.to_dict()
    decision: dict | None = None  # serialized Decision.to_dict(), if any
    snarc: dict | None = None  # serialized SnarcScore.to_dict(), if any
    notes: str = ""  # free-form annotation

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> DreamEntry:
        return cls(
            action=d.get("action", {}),
            decision=d.get("decision"),
            snarc=d.get("snarc"),
            notes=d.get("notes", ""),
        )


@dataclass
class DreamBundle:
    """Header + list of DreamEntries, addressable by bundle_id."""

    bundle_id: str = field(default_factory=_new_bundle_id)
    machine: str = ""
    instance_lct: str = ""
    model: str = ""
    session: str = ""
    created_at: str = field(default_factory=_now_iso)
    salience_threshold: float = 0.5
    selection_weights: dict[str, float] | None = None
    entries: list[DreamEntry] = field(default_factory=list)

    # ---- size / digest ----

    def __len__(self) -> int:
        return len(self.entries)

    def digest(self) -> str:
        """Stable digest over canonical bytes — survives roundtrip."""
        return hashlib.sha256(self._canonical_payload()).hexdigest()

    def _canonical_payload(self) -> bytes:
        data = {
            "bundle_id": self.bundle_id,
            "machine": self.machine,
            "instance_lct": self.instance_lct,
            "model": self.model,
            "session": self.session,
            "created_at": self.created_at,
            "salience_threshold": self.salience_threshold,
            "selection_weights": self.selection_weights,
            "entries": [e.to_dict() for e in self.entries],
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")

    # ---- mutation ----

    def add(
        self,
        action: R6Action,
        *,
        decision: Decision | None = None,
        snarc: SnarcScore | None = None,
        notes: str = "",
    ) -> DreamEntry:
        entry = DreamEntry(
            action=r6_to_dict(action)["r6_action"],
            decision=decision.to_dict() if decision is not None else None,
            snarc=snarc.to_dict() if snarc is not None else None,
            notes=notes,
        )
        self.entries.append(entry)
        return entry

    # ---- serialization ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "machine": self.machine,
            "instance_lct": self.instance_lct,
            "model": self.model,
            "session": self.session,
            "created_at": self.created_at,
            "salience_threshold": self.salience_threshold,
            "selection_weights": self.selection_weights,
            "entries": [e.to_dict() for e in self.entries],
        }

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DreamBundle:
        return cls(
            bundle_id=d.get("bundle_id", _new_bundle_id()),
            machine=d.get("machine", ""),
            instance_lct=d.get("instance_lct", ""),
            model=d.get("model", ""),
            session=d.get("session", ""),
            created_at=d.get("created_at", _now_iso()),
            salience_threshold=float(d.get("salience_threshold", 0.5)),
            selection_weights=d.get("selection_weights"),
            entries=[DreamEntry.from_dict(e) for e in d.get("entries", [])],
        )

    @classmethod
    def load(cls, path: str | Path) -> DreamBundle:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())
