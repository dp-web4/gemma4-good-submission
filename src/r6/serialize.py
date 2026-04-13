"""
JSON serialization for R6 records.

to_dict / from_dict / to_json / from_json — all round-trip-stable.
Audit bundles and training data both flow through this.
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from .action import R6Action
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


# --- encode ---


def _encode(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj):
        return {k: _encode(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_encode(v) for v in obj]
    return obj


def to_dict(action: R6Action) -> dict:
    return {"r6_action": _encode(action)}


def to_json(action: R6Action, indent: int | None = 2) -> str:
    return json.dumps(to_dict(action), indent=indent, sort_keys=False)


# --- decode ---
#
# Explicit per-class decoders keep this simple and predictable. If you
# change the dataclass shape, update the corresponding builder.


def _build_t3(d: dict | None) -> T3:
    return T3(**d) if d else T3()


def _build_v3(d: dict | None) -> V3:
    return V3(**d) if d else V3()


def _build_rules(d: dict | None) -> Rules:
    if not d:
        return Rules()
    return Rules(
        governing_contracts=list(d.get("governing_contracts", [])),
        permission_scope=list(d.get("permission_scope", [])),
        constraints=dict(d.get("constraints", {})),
    )


def _build_role(d: dict | None) -> Role:
    if not d:
        return Role(role_id="", context="")
    return Role(
        role_id=d.get("role_id", ""),
        context=d.get("context", ""),
        delegated_permissions=list(d.get("delegated_permissions", [])),
        t3=_build_t3(d.get("t3")),
    )


def _build_request(d: dict | None) -> Request:
    if not d:
        return Request(action_type=ActionType.OBSERVE, description="")
    return Request(
        action_type=ActionType(d.get("action_type", "observe")),
        description=d.get("description", ""),
        acceptance_criteria=list(d.get("acceptance_criteria", [])),
        priority=Priority(d.get("priority", "medium")),
        deadline=d.get("deadline"),
    )


def _build_reference(d: dict | None) -> Reference:
    if not d:
        return Reference()
    return Reference(
        current_observation=d.get("current_observation"),
        similar_actions=list(d.get("similar_actions", [])),
        relevant_memory=list(d.get("relevant_memory", [])),
        horizon_depth=int(d.get("horizon_depth", 2)),
    )


def _build_resource(d: dict | None) -> Resource:
    if not d:
        return Resource()
    return Resource(
        cost_allocated=float(d.get("cost_allocated", 0.0)),
        cost_consumed=float(d.get("cost_consumed", 0.0)),
        compute_units=int(d.get("compute_units", 0)),
        data_access=list(d.get("data_access", [])),
        estimated_cost=float(d.get("estimated_cost", 0.0)),
    )


def _build_performance(d: dict | None) -> Performance:
    if not d:
        return Performance()
    return Performance(
        completion_time_s=float(d.get("completion_time_s", 0.0)),
        quality_score=float(d.get("quality_score", 0.0)),
        criteria_met=list(d.get("criteria_met", [])),
    )


def _build_witness(d: dict) -> WitnessAttestation:
    return WitnessAttestation(
        witness_id=d.get("witness_id", ""),
        attestation_type=d.get("attestation_type", ""),
        signature=d.get("signature", ""),
    )


def _build_result(d: dict | None) -> Result:
    if not d:
        return Result()
    return Result(
        output=d.get("output"),
        performance=_build_performance(d.get("performance")),
        value=_build_v3(d.get("value")),
        side_effects=list(d.get("side_effects", [])),
        witnesses=[_build_witness(w) for w in d.get("witnesses", [])],
    )


def _build_confidence(d: dict | None) -> Confidence | None:
    if not d:
        return None
    return Confidence(
        role_capability=float(d.get("role_capability", 0.0)),
        historical_success=float(d.get("historical_success", 0.0)),
        resource_availability=float(d.get("resource_availability", 0.0)),
        risk_assessment=float(d.get("risk_assessment", 0.0)),
    )


def from_dict(data: dict) -> R6Action:
    payload = data.get("r6_action", data)
    return R6Action(
        rules=_build_rules(payload.get("rules")),
        role=_build_role(payload.get("role")),
        request=_build_request(payload.get("request")),
        reference=_build_reference(payload.get("reference")),
        resource=_build_resource(payload.get("resource")),
        result=_build_result(payload.get("result")),
        action_id=payload.get("action_id", ""),
        initiator_id=payload.get("initiator_id", ""),
        timestamp=payload.get("timestamp", ""),
        status=ActionStatus(payload.get("status", "pending")),
        confidence=_build_confidence(payload.get("confidence")),
    )


def from_json(text: str) -> R6Action:
    return from_dict(json.loads(text))
