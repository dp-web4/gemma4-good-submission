"""
T3/V3 trust and value tensor evolution.

T3 (Talent / Training / Temperament) — how capable the role is.
V3 (Valuation / Veracity / Validity) — how good the result was.

The R6Action record carries a *snapshot* of T3 in its Role — the trust the
role held at action time. The ledger in this module is the live, evolving
state: every new observation updates the current T3/V3 for that role.

Update model
------------

Each dimension of T3 or V3 evolves under an exponential moving average with
diminishing returns, bounded by the role's trust ceiling (from identity):

    t_new = clip(t_old + lr(n) * (observation - t_old), 0, ceiling)

where lr(n) = base_rate * decay^n, n = prior observations in that dimension.
Early observations move trust quickly; once established, updates are small.
Ceiling prevents a software-anchored identity from ever accruing trust
beyond 0.4 regardless of track record.

Every update produces an ObservationRecord appended to the ledger. That
record is the audit proof of how the current T3/V3 got to where it is.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..r6.types import T3, V3


# --------------------------------------------------------------------------
# Update math
# --------------------------------------------------------------------------


BASE_RATE = 0.10  # initial learning rate
DECAY = 0.95  # per-observation decay of learning rate (diminishing returns)
MIN_RATE = 0.01  # floor — trust never stops updating entirely


def effective_rate(observations: int, base: float = BASE_RATE) -> float:
    """Learning rate that decays with observation count but doesn't reach zero."""
    rate = base * (DECAY**observations)
    return max(rate, MIN_RATE)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def update_scalar(
    current: float,
    observation: float,
    observations_so_far: int,
    ceiling: float = 1.0,
) -> float:
    """Evolve a single trust dimension."""
    lr = effective_rate(observations_so_far)
    proposed = current + lr * (observation - current)
    return _clip(proposed, 0.0, ceiling)


# --------------------------------------------------------------------------
# Observation — the audit record of every update
# --------------------------------------------------------------------------


@dataclass
class ObservationRecord:
    """Why a T3 or V3 value changed.

    Immutable. Appended to the ledger. Signed when authorized.
    """

    role_id: str
    tensor: str  # "t3" | "v3"
    dimension: str  # "talent"|"training"|"temperament"|"valuation"|"veracity"|"validity"
    observation: float  # raw observation in [0, 1]
    prior_value: float
    posterior_value: float
    action_ref: str = ""  # R6 action id that produced this observation, if any
    witness_id: str = ""  # who attested to the observation
    timestamp: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    signature_b64: str = ""  # optional — signed by witness

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------


@dataclass
class RoleTrust:
    """Current T3/V3 + observation counts for one role."""

    role_id: str
    ceiling: float = 1.0  # from identity trust_ceiling
    t3: T3 = field(default_factory=T3)
    v3: V3 = field(default_factory=V3)
    t3_counts: dict[str, int] = field(
        default_factory=lambda: {"talent": 0, "training": 0, "temperament": 0}
    )
    v3_counts: dict[str, int] = field(
        default_factory=lambda: {"valuation": 0, "veracity": 0, "validity": 0}
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TrustLedger:
    """Holds current T3/V3 per role + the append-only history of updates."""

    def __init__(self) -> None:
        self._roles: dict[str, RoleTrust] = {}
        self._history: list[ObservationRecord] = []

    # --- role lookup ---

    def role(self, role_id: str, ceiling: float = 1.0) -> RoleTrust:
        """Get or create the trust record for a role."""
        if role_id not in self._roles:
            self._roles[role_id] = RoleTrust(role_id=role_id, ceiling=ceiling)
        return self._roles[role_id]

    def snapshot_t3(self, role_id: str) -> T3:
        """Current T3 snapshot for a role. Suitable for embedding in an R6Action."""
        r = self._roles.get(role_id)
        return T3(r.t3.talent, r.t3.training, r.t3.temperament) if r else T3()

    def snapshot_v3(self, role_id: str) -> V3:
        r = self._roles.get(role_id)
        return V3(r.v3.valuation, r.v3.veracity, r.v3.validity) if r else V3()

    # --- updates ---

    def observe_t3(
        self,
        role_id: str,
        *,
        talent: float | None = None,
        training: float | None = None,
        temperament: float | None = None,
        action_ref: str = "",
        witness_id: str = "",
    ) -> list[ObservationRecord]:
        """Apply one or more T3 observations for a role.

        Each supplied dimension is updated independently. Returns the
        records appended for this call.
        """
        role = self.role(role_id)
        records: list[ObservationRecord] = []
        for dim, value in (
            ("talent", talent),
            ("training", training),
            ("temperament", temperament),
        ):
            if value is None:
                continue
            prior = getattr(role.t3, dim)
            post = update_scalar(prior, value, role.t3_counts[dim], role.ceiling)
            setattr(role.t3, dim, post)
            role.t3_counts[dim] += 1
            rec = ObservationRecord(
                role_id=role_id,
                tensor="t3",
                dimension=dim,
                observation=value,
                prior_value=prior,
                posterior_value=post,
                action_ref=action_ref,
                witness_id=witness_id,
            )
            records.append(rec)
            self._history.append(rec)
        return records

    def observe_v3(
        self,
        role_id: str,
        *,
        valuation: float | None = None,
        veracity: float | None = None,
        validity: float | None = None,
        action_ref: str = "",
        witness_id: str = "",
    ) -> list[ObservationRecord]:
        """Apply one or more V3 observations for a role."""
        role = self.role(role_id)
        records: list[ObservationRecord] = []
        for dim, value in (
            ("valuation", valuation),
            ("veracity", veracity),
            ("validity", validity),
        ):
            if value is None:
                continue
            prior = getattr(role.v3, dim)
            post = update_scalar(prior, value, role.v3_counts[dim], role.ceiling)
            setattr(role.v3, dim, post)
            role.v3_counts[dim] += 1
            rec = ObservationRecord(
                role_id=role_id,
                tensor="v3",
                dimension=dim,
                observation=value,
                prior_value=prior,
                posterior_value=post,
                action_ref=action_ref,
                witness_id=witness_id,
            )
            records.append(rec)
            self._history.append(rec)
        return records

    # --- audit / persistence ---

    def history(self, role_id: str | None = None) -> list[ObservationRecord]:
        if role_id is None:
            return list(self._history)
        return [r for r in self._history if r.role_id == role_id]

    def save(self, path: str | Path) -> None:
        """Persist ledger state + history to a JSON file."""
        data = {
            "roles": {rid: r.to_dict() for rid, r in self._roles.items()},
            "history": [r.to_dict() for r in self._history],
        }
        Path(path).write_text(json.dumps(data, indent=2, sort_keys=False))

    @classmethod
    def load(cls, path: str | Path) -> TrustLedger:
        """Load ledger state from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        ledger = cls()
        for rid, r in data.get("roles", {}).items():
            role = RoleTrust(
                role_id=r["role_id"],
                ceiling=r.get("ceiling", 1.0),
                t3=T3(**r["t3"]),
                v3=V3(**r["v3"]),
                t3_counts=dict(r.get("t3_counts", {})),
                v3_counts=dict(r.get("v3_counts", {})),
            )
            ledger._roles[rid] = role
        for h in data.get("history", []):
            ledger._history.append(ObservationRecord(**h))
        return ledger
