"""
Layer A — IdentityManifest.

Public identity information. Readable by anyone. The manifest names who
this agent is in the world: its LCT id, its public key fingerprint, the
anchor it binds to.

Never contains secrets. Safe to share, log, attest.

Canonical reference: sage/identity/README.md §Layer A,
                     web4-standard/core-spec/LCT-linked-context-token.md
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path


TRUST_CEILINGS: dict[str, float] = {
    "tpm2": 1.0,
    "fido2": 0.9,
    "tpm2_no_pcr": 0.85,
    "secure_enclave": 0.85,
    "software": 0.4,
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class IdentityManifest:
    """Public identity manifest. No secrets. Readable by anyone."""

    name: str
    lct_id: str
    public_key_fingerprint: str = ""
    anchor_type: str = "software"
    machine: str = ""
    model: str = ""
    model_family: str = ""
    created: str = field(default_factory=_now_iso)
    sealed_path: str = "identity.sealed"
    status: str = "active"

    @property
    def trust_ceiling(self) -> float:
        return TRUST_CEILINGS.get(self.anchor_type, 0.4)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trust_ceiling"] = self.trust_ceiling
        return d

    def to_json(self, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    @classmethod
    def from_dict(cls, data: dict) -> IdentityManifest:
        # trust_ceiling is a derived field — drop it on load
        data = {k: v for k, v in data.items() if k != "trust_ceiling"}
        return cls(**data)

    @classmethod
    def load(cls, path: str | Path) -> IdentityManifest:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())
