"""
R6 component types — Rules, Role, Request, Reference, Resource, Result.

Canonical form: Rules + Role + Request + Reference + Resource → Result

Every action in the system is shaped as an R6 record. The grammar makes
actions auditable by construction — training data and audit logs share
the same shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    """Coarse classification of what the action does."""

    ANALYZE = "analyze"
    COMPUTE = "compute"
    VERIFY = "verify"
    DELEGATE = "delegate"
    OBSERVE = "observe"
    ACT = "act"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionStatus(str, Enum):
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"


# --------------------------------------------------------------------------
# Rules — systemic boundaries defining what is possible
# --------------------------------------------------------------------------


@dataclass
class Rules:
    governing_contracts: list[str] = field(default_factory=list)
    permission_scope: list[str] = field(default_factory=list)
    constraints: dict[str, Any] = field(default_factory=dict)

    def permits(self, action: str) -> bool:
        return action in self.permission_scope

    def within_budget(self, cost: float) -> bool:
        return cost <= self.constraints.get("max_cost", float("inf"))

    def within_timeout(self, elapsed_seconds: float) -> bool:
        return elapsed_seconds <= self.constraints.get("timeout_s", float("inf"))


# --------------------------------------------------------------------------
# Role — operational identity for this action
# --------------------------------------------------------------------------


@dataclass
class T3:
    """Trust tensor: Talent / Training / Temperament, in [0, 1]."""

    talent: float = 0.5
    training: float = 0.5
    temperament: float = 0.5

    def composite(self) -> float:
        return (self.talent + self.training + self.temperament) / 3.0


@dataclass
class Role:
    role_id: str
    context: str
    delegated_permissions: list[str] = field(default_factory=list)
    t3: T3 = field(default_factory=T3)

    def has_permission(self, perm: str) -> bool:
        return perm in self.delegated_permissions


# --------------------------------------------------------------------------
# Request — the intent
# --------------------------------------------------------------------------


@dataclass
class Request:
    action_type: ActionType
    description: str
    acceptance_criteria: list[str] = field(default_factory=list)
    priority: Priority = Priority.MEDIUM
    deadline: str | None = None  # ISO-8601


# --------------------------------------------------------------------------
# Reference — context the actor is acting on
# --------------------------------------------------------------------------


@dataclass
class Reference:
    """What the actor is acting on: current frame, prior state, memory.

    For game play: the current game frame, detected objects, world model.
    For tool use: the request source, prior conversation, retrieved docs.
    For policy: the action being evaluated, trust tensors in play.
    """

    current_observation: Any = None
    similar_actions: list[str] = field(default_factory=list)
    relevant_memory: list[str] = field(default_factory=list)
    horizon_depth: int = 2

    def has_context(self) -> bool:
        return self.current_observation is not None or bool(self.relevant_memory)


# --------------------------------------------------------------------------
# Resource — what the action costs
# --------------------------------------------------------------------------


@dataclass
class Resource:
    """Cost and assets consumed by the action."""

    cost_allocated: float = 0.0
    cost_consumed: float = 0.0
    compute_units: int = 0
    data_access: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0

    def remaining(self) -> float:
        return self.cost_allocated - self.cost_consumed

    def can_afford(self) -> bool:
        return self.cost_allocated >= self.estimated_cost


# --------------------------------------------------------------------------
# Result — the outcome
# --------------------------------------------------------------------------


@dataclass
class V3:
    """Value tensor: Valuation / Veracity / Validity, in [0, 1]."""

    valuation: float = 0.0
    veracity: float = 0.0
    validity: float = 0.0

    def composite(self) -> float:
        return (self.valuation + self.veracity + self.validity) / 3.0


@dataclass
class Performance:
    completion_time_s: float = 0.0
    quality_score: float = 0.0
    criteria_met: list[str] = field(default_factory=list)


@dataclass
class WitnessAttestation:
    """A witness confirms some property of the result."""

    witness_id: str
    attestation_type: str  # "quality" | "time" | "audit" | ...
    signature: str = ""


@dataclass
class Result:
    output: Any = None
    performance: Performance = field(default_factory=Performance)
    value: V3 = field(default_factory=V3)
    side_effects: list[str] = field(default_factory=list)
    witnesses: list[WitnessAttestation] = field(default_factory=list)


# --------------------------------------------------------------------------
# Confidence — pre-execution assessment
# --------------------------------------------------------------------------


@dataclass
class Confidence:
    """Pre-execution confidence across four independent dimensions.

    overall = mean(role_capability, historical, resource, risk)
    """

    role_capability: float = 0.0
    historical_success: float = 0.0
    resource_availability: float = 0.0
    risk_assessment: float = 0.0

    def overall(self) -> float:
        return (
            self.role_capability
            + self.historical_success
            + self.resource_availability
            + self.risk_assessment
        ) / 4.0
