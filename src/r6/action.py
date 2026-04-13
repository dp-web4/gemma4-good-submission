"""
R6Action — the complete audit record for a single action.

A record is the shape of intent: the six inputs, the one output.
Every record is serializable to JSON. Every JSON record is parseable
back to a Python object. That round-trip is the contract on which
audit bundles and training data both depend.
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field

from .types import (
    ActionStatus,
    ActionType,
    Confidence,
    Reference,
    Request,
    Resource,
    Result,
    Role,
    Rules,
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _new_action_id() -> str:
    return f"r6:{hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:16]}"


@dataclass
class R6Action:
    """A complete R6 action record.

    Before execution, `result` is empty and `status` is PENDING. After
    execution, `result` is populated and `status` reflects outcome.

    The six inputs (rules, role, request, reference, resource) are
    immutable once the action starts executing; result accumulates.
    """

    rules: Rules = field(default_factory=Rules)
    role: Role = field(
        default_factory=lambda: Role(role_id="", context="")
    )
    request: Request = field(
        default_factory=lambda: Request(
            action_type=ActionType.OBSERVE,
            description="",
        )
    )
    reference: Reference = field(default_factory=Reference)
    resource: Resource = field(default_factory=Resource)
    result: Result = field(default_factory=Result)

    action_id: str = field(default_factory=_new_action_id)
    initiator_id: str = ""
    timestamp: str = field(default_factory=_now_iso)
    status: ActionStatus = ActionStatus.PENDING
    confidence: Confidence | None = None

    def calc_confidence(self, risk_factor: float = 0.9) -> Confidence:
        """Compute pre-execution confidence from role + reference + resource."""
        self.confidence = Confidence(
            role_capability=self.role.t3.composite(),
            historical_success=0.5
            if not self.reference.similar_actions
            else min(1.0, 0.5 + 0.05 * len(self.reference.similar_actions)),
            resource_availability=1.0 if self.resource.can_afford() else 0.0,
            risk_assessment=risk_factor,
        )
        return self.confidence

    def mark_executing(self) -> None:
        self.status = ActionStatus.EXECUTING

    def mark_completed(self, result: Result) -> None:
        self.result = result
        self.status = ActionStatus.COMPLETED

    def mark_failed(self, side_effect: str = "") -> None:
        if side_effect:
            self.result.side_effects.append(side_effect)
        self.status = ActionStatus.FAILED

    def mark_denied(self, reason: str) -> None:
        self.result.side_effects.append(f"denied:{reason}")
        self.status = ActionStatus.DENIED
