"""
Rule interpretation — how Law rule bodies are evaluated against an R6Action.

The rule language is deliberately small. Each Law carries a `rule` dict;
the interpreter here knows the supported keys and returns a per-law
verdict (passed, failed, failure_reason).

Supported keys:

    permit: list[str]              action_type or scope must be in list
    deny: list[str]                action_type or scope must NOT be in list
    max_cost: float                resource.estimated_cost <= value
    max_rate_per_minute: int       (rate limiter; checked by caller)
    require_ceiling: float         identity trust ceiling >= value
    require_t3_min: dict           role.t3.<dim> >= value for each key
    require_witness: int           len(result.witnesses) >= value

Any unknown key causes a rule to fail-closed with reason "unknown_rule_key".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..r6.action import R6Action
from ..law.law import Law


SUPPORTED_KEYS = frozenset(
    {
        "permit",
        "deny",
        "max_cost",
        "max_rate_per_minute",
        "require_ceiling",
        "require_t3_min",
        "require_witness",
    }
)


@dataclass
class RuleVerdict:
    law_id: str
    passed: bool
    reason: str = ""  # populated when passed=False


def _scope_or_action_type(action: R6Action) -> tuple[str, str]:
    """Tuple of (action_type, scope_hint) used to match permit/deny lists."""
    at = action.request.action_type.value
    # scope_hint is derived from permission_scope intersection: use first
    # permission in rules permission_scope as a readable scope key.
    # For the rule interpreter, "scope" is whatever the caller attributes
    # to this action via Rules.permission_scope entries.
    scope = action.rules.permission_scope[0] if action.rules.permission_scope else at
    return at, scope


def evaluate_law(
    law: Law,
    action: R6Action,
    *,
    identity_ceiling: float = 1.0,
    rate_observer: "RateObserver | None" = None,
) -> RuleVerdict:
    """Apply a single Law to an action. Returns the verdict."""
    rule = law.rule

    # Fail-closed on unknown keys. This is a feature: you cannot introduce
    # a typo or a new rule keyword without updating the interpreter.
    for key in rule:
        if key not in SUPPORTED_KEYS:
            return RuleVerdict(
                law.law_id, False, f"unknown_rule_key:{key}"
            )

    action_type, scope = _scope_or_action_type(action)

    # --- permit / deny ---
    if "permit" in rule:
        permitted = set(rule["permit"])
        if action_type not in permitted and scope not in permitted:
            return RuleVerdict(
                law.law_id,
                False,
                f"not_permitted:{action_type}/{scope}",
            )
    if "deny" in rule:
        denied = set(rule["deny"])
        if action_type in denied or scope in denied:
            return RuleVerdict(
                law.law_id, False, f"denied:{action_type}/{scope}"
            )

    # --- cost constraint ---
    if "max_cost" in rule:
        max_cost = float(rule["max_cost"])
        if action.resource.estimated_cost > max_cost:
            return RuleVerdict(
                law.law_id,
                False,
                f"cost_exceeded:{action.resource.estimated_cost}>{max_cost}",
            )

    # --- rate limit ---
    if "max_rate_per_minute" in rule:
        if rate_observer is None:
            return RuleVerdict(
                law.law_id, False, "rate_observer_missing"
            )
        limit = int(rule["max_rate_per_minute"])
        key = f"{action.role.role_id}:{action_type}"
        if rate_observer.count_last_minute(key) >= limit:
            return RuleVerdict(
                law.law_id, False, f"rate_exceeded:{limit}/min"
            )

    # --- trust ceiling requirement ---
    if "require_ceiling" in rule:
        need = float(rule["require_ceiling"])
        if identity_ceiling < need:
            return RuleVerdict(
                law.law_id,
                False,
                f"ceiling_too_low:{identity_ceiling}<{need}",
            )

    # --- T3 minima ---
    if "require_t3_min" in rule:
        mins: dict[str, Any] = rule["require_t3_min"]
        for dim, need in mins.items():
            have = getattr(action.role.t3, dim, None)
            if have is None:
                return RuleVerdict(
                    law.law_id, False, f"unknown_t3_dim:{dim}"
                )
            if have < float(need):
                return RuleVerdict(
                    law.law_id,
                    False,
                    f"t3_{dim}_too_low:{have}<{need}",
                )

    # --- witness requirement (post-execution check; pre-exec usually zero) ---
    if "require_witness" in rule:
        need = int(rule["require_witness"])
        if len(action.result.witnesses) < need:
            return RuleVerdict(
                law.law_id,
                False,
                f"witness_count_low:{len(action.result.witnesses)}<{need}",
            )

    return RuleVerdict(law.law_id, True)


# --------------------------------------------------------------------------
# Minimal in-memory rate observer. Production would use a proper sliding-
# window counter; for the demo a per-key list of timestamps is enough.
# --------------------------------------------------------------------------


class RateObserver:
    """Tracks per-key action timestamps for max_rate_per_minute enforcement."""

    def __init__(self) -> None:
        import time as _time

        self._time = _time
        self._events: dict[str, list[float]] = {}

    def record(self, key: str) -> None:
        self._events.setdefault(key, []).append(self._time.time())

    def count_last_minute(self, key: str) -> int:
        now = self._time.time()
        evs = self._events.get(key, [])
        # purge entries older than 60s
        kept = [t for t in evs if now - t <= 60.0]
        self._events[key] = kept
        return len(kept)
