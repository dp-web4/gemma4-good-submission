"""
CognitionLoop — the integration.

Ties every module together into one `tick` that takes an observation
and produces a signed, accounted, consolidated R6Action record.

Stages (one tick)
-----------------

  1.  Build R6Action from observation + intended request
  2.  Snapshot T3 from trust ledger → populate Role
  3.  SNARC score the observation
  4.  PolicyGate.evaluate(action, law_bundle) → Decision
  5.  If DENIED or DEFERRED: mark action, record, return (no execution)
  6.  Reserve energy (EnergyLedger.spend) covering estimated cost
  7.  Mark EXECUTING
  8.  Executor.execute(action) → Outcome
  9.  Mark COMPLETED with Result populated from Outcome
  10. Settle energy packets with V3 assessment
  11. Update trust ledger from outcome quality + V3
  12. Record (action, decision, snarc) into Consolidator buffer
  13. Return TickReport
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..dreamcycle.consolidator import Consolidator
from ..energy.ledger import EnergyLedger
from ..energy.packet import EnergyError
from ..identity.provider import IdentityProvider
from ..law.registry import LawRegistry
from ..policy.decision import Decision, Verdict
from ..policy.gate import PolicyGate
from ..r6.action import R6Action
from ..r6.types import (
    ActionType,
    Performance,
    Reference,
    Request,
    Resource,
    Result,
    Role,
    Rules,
)
from ..snarc.scorer import Scorer
from ..snarc.score import SnarcScore
from ..trust.ledger import TrustLedger
from .executor import Executor, Outcome, StubExecutor


@dataclass
class TickReport:
    """The full audit artifact produced by one CognitionLoop.tick() call."""

    action: R6Action
    decision: Decision
    snarc: SnarcScore
    outcome: Outcome | None = None
    energy_spent: float = 0.0
    energy_packets: list[str] = field(default_factory=list)  # packet ids
    reason: str = ""  # high-level summary of what happened

    @property
    def executed(self) -> bool:
        return self.outcome is not None

    def to_dict(self) -> dict:
        return {
            "action_id": self.action.action_id,
            "action_status": self.action.status.value,
            "decision": self.decision.to_dict(),
            "snarc": self.snarc.to_dict(),
            "outcome": {
                "output": self.outcome.output,
                "quality": self.outcome.quality,
                "value": {
                    "valuation": self.outcome.value.valuation,
                    "veracity": self.outcome.value.veracity,
                    "validity": self.outcome.value.validity,
                },
                "notes": self.outcome.notes,
            } if self.outcome else None,
            "energy_spent": self.energy_spent,
            "energy_packets": list(self.energy_packets),
            "reason": self.reason,
        }


@dataclass
class CognitionLoop:
    """The integration — stitches identity, law, policy, trust, energy,
    snarc, dreamcycle, and an executor into one tick().
    """

    identity: IdentityProvider
    role_id: str
    role_context: str
    scope: str  # which law scope this loop operates under
    laws: LawRegistry
    energy: EnergyLedger
    trust: TrustLedger
    snarc: Scorer
    consolidator: Consolidator
    gate: PolicyGate
    executor: Executor = field(default_factory=StubExecutor)

    def __post_init__(self) -> None:
        if not self.identity.is_authorized:
            raise RuntimeError(
                "CognitionLoop requires an authorized identity — "
                "call identity.authorize(passphrase) first"
            )
        # Ensure the role has a trust record with the identity's ceiling
        manifest = self.identity.load_manifest()
        self.trust.role(self.role_id, ceiling=manifest.trust_ceiling)

    # ------------------------------------------------------------------

    def tick(
        self,
        observation: Any,
        *,
        request_description: str,
        action_type: ActionType = ActionType.ACT,
        estimated_cost: float = 1.0,
        expectation: Any = None,
        arousal: float = 0.0,
        reward: float = 0.0,
        conflict: float = 0.0,
        acceptance_criteria: list[str] | None = None,
    ) -> TickReport:
        """One full cognition step."""
        manifest = self.identity.load_manifest()

        # 1. Build R6Action
        action = R6Action(
            rules=Rules(permission_scope=[self.scope]),
            role=Role(
                role_id=self.role_id,
                context=self.role_context,
                t3=self.trust.snapshot_t3(self.role_id),
            ),
            request=Request(
                action_type=action_type,
                description=request_description,
                acceptance_criteria=acceptance_criteria or [],
            ),
            reference=Reference(current_observation=observation),
            resource=Resource(estimated_cost=estimated_cost),
            initiator_id=manifest.lct_id,
        )
        action.calc_confidence()

        # 2. SNARC score
        snarc_score = self.snarc.score(
            observation,
            expectation=expectation,
            arousal=arousal,
            reward=reward,
            conflict=conflict,
        )

        # 3. PolicyGate.evaluate
        decision = self.gate.evaluate_with_registry(
            action, self.laws, identity_ceiling=manifest.trust_ceiling
        )

        # 4. Deny / defer → record and return
        if decision.is_deny:
            self.gate.apply(action, decision)
            self.consolidator.record(action, decision=decision, snarc=snarc_score)
            return TickReport(
                action=action, decision=decision, snarc=snarc_score,
                reason=f"denied: {decision.reason}",
            )
        if decision.is_defer:
            self.gate.apply(action, decision)
            self.consolidator.record(action, decision=decision, snarc=snarc_score)
            return TickReport(
                action=action, decision=decision, snarc=snarc_score,
                reason=f"deferred: {decision.reason}",
            )

        # 5. Reserve energy
        try:
            used = self.energy.spend(
                holder_lct=manifest.lct_id,
                amount=estimated_cost,
                action_ref=action.action_id,
            )
        except EnergyError as e:
            # Out of energy — treat as failure, record for audit
            action.mark_failed(f"energy_exhausted:{e}")
            self.consolidator.record(action, decision=decision, snarc=snarc_score)
            return TickReport(
                action=action, decision=decision, snarc=snarc_score,
                reason=f"no energy: {e}",
            )

        energy_spent = sum(p.amount for p in used)
        packet_ids = [p.packet_id for p in used]
        action.resource.cost_consumed = energy_spent

        # 6. Execute
        action.mark_executing()
        t0 = time.perf_counter()
        try:
            outcome = self.executor.execute(
                action, context={"observation": observation}
            )
        except Exception as e:
            action.mark_failed(f"executor_error:{e}")
            # Packets are already discharged; settle them with zero value
            for p in used:
                try:
                    self.energy.settle(p.packet_id, _zero_v3())
                except EnergyError:
                    pass
            self.consolidator.record(action, decision=decision, snarc=snarc_score)
            return TickReport(
                action=action, decision=decision, snarc=snarc_score,
                energy_spent=energy_spent, energy_packets=packet_ids,
                reason=f"executor failed: {e}",
            )
        elapsed = time.perf_counter() - t0

        # 7. Populate Result
        action.mark_completed(
            Result(
                output=outcome.output,
                performance=Performance(
                    completion_time_s=elapsed,
                    quality_score=outcome.quality,
                    criteria_met=list(action.request.acceptance_criteria),
                ),
                value=outcome.value,
                side_effects=[],
                witnesses=[],
            )
        )

        # 8. Settle energy
        for p in used:
            try:
                self.energy.settle(p.packet_id, outcome.value)
            except EnergyError:
                pass

        # 9. Update trust
        # Treat quality as a direct observation on T3.training;
        # V3 dimensions flow into V3 directly.
        self.trust.observe_t3(
            self.role_id,
            training=outcome.quality,
            action_ref=action.action_id,
        )
        self.trust.observe_v3(
            self.role_id,
            valuation=outcome.value.valuation,
            veracity=outcome.value.veracity,
            validity=outcome.value.validity,
            action_ref=action.action_id,
        )

        # 10. Record for consolidation
        self.consolidator.record(
            action, decision=decision, snarc=snarc_score,
            notes=outcome.notes,
        )

        return TickReport(
            action=action, decision=decision, snarc=snarc_score,
            outcome=outcome, energy_spent=energy_spent,
            energy_packets=packet_ids,
            reason=f"completed: quality={outcome.quality:.2f}",
        )


def _zero_v3():
    from ..r6.types import V3
    return V3()
