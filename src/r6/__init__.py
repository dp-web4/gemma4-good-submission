"""
R6 — the action grammar.

Rules + Role + Request + Reference + Resource → Result

Every action in the system is an R6Action record. The shape of the record
IS the shape of the audit bundle; the shape of the audit bundle IS the
shape of the training example. One grammar, three uses.
"""

from .action import R6Action
from .serialize import from_dict, from_json, to_dict, to_json
from .types import (
    ActionStatus,
    ActionType,
    Confidence,
    Performance,
    Priority,
    Reference,
    Request,
    Resource,
    Result,
    Role,
    Rules,
    T3,
    V3,
    WitnessAttestation,
)

__all__ = [
    "R6Action",
    "Rules",
    "Role",
    "Request",
    "Reference",
    "Resource",
    "Result",
    "Confidence",
    "T3",
    "V3",
    "Performance",
    "WitnessAttestation",
    "ActionType",
    "ActionStatus",
    "Priority",
    "to_dict",
    "to_json",
    "from_dict",
    "from_json",
]
