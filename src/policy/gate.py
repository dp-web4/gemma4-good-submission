"""
PolicyGate — the law-in-the-loop evaluator.

Takes a pending R6Action and a LawBundle (or LawRegistry for scope
lookup), applies every matching active law, and returns a signed
Decision record pointing back at the exact bundle consulted.

The gate does not execute the action. It only judges. The action
proceeds only if the Decision is ALLOW; otherwise `action.mark_denied`
is called with the Decision reason.

Evaluator identity
------------------

Each gate instance carries (optional) evaluator credentials — an
IdentityProvider or SigningContext — so that every Decision it emits is
signed. Unsigned decisions are valid but carry lower audit weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..identity.provider import IdentityProvider
from ..identity.signing import SigningContext
from ..law.law import Law, LawBundle, LawRef
from ..law.registry import LawRegistry
from ..r6.action import R6Action
from .decision import Decision, RuleFailure, Verdict
from .rules import RateObserver, RuleVerdict, evaluate_law


@dataclass
class PolicyGate:
    """Law-aware evaluator for R6Actions."""

    evaluator_lct: str = ""
    _evaluator: SigningContext | None = None
    rate_observer: RateObserver = field(default_factory=RateObserver)

    def __init__(
        self,
        evaluator_lct: str = "",
        evaluator: IdentityProvider | SigningContext | None = None,
        rate_observer: RateObserver | None = None,
    ) -> None:
        self.evaluator_lct = evaluator_lct
        if isinstance(evaluator, IdentityProvider):
            self._evaluator = evaluator.context
        else:
            self._evaluator = evaluator
        self.rate_observer = rate_observer or RateObserver()

    # ------------------------------------------------------------------

    def evaluate(
        self,
        action: R6Action,
        bundle: LawBundle,
        *,
        identity_ceiling: float = 1.0,
        scope: str | None = None,
    ) -> Decision:
        """Evaluate an action against a single bundle."""
        # Which laws apply? Use scope argument if given, else derive from
        # action's rules.permission_scope entries, else fall back to action_type.
        target_scope = scope or (
            action.rules.permission_scope[0]
            if action.rules.permission_scope
            else action.request.action_type.value
        )
        applicable: list[Law] = bundle.laws_for_scope(target_scope)

        failures: list[RuleFailure] = []
        for law in applicable:
            verdict = evaluate_law(
                law,
                action,
                identity_ceiling=identity_ceiling,
                rate_observer=self.rate_observer,
            )
            if not verdict.passed:
                failures.append(RuleFailure(verdict.law_id, verdict.reason))

        if failures:
            decision = Decision(
                action_id=action.action_id,
                verdict=Verdict.DENY,
                law_ref=LawRef.from_bundle(bundle, applicable),
                reason=self._summarize(failures),
                failures=failures,
            )
        else:
            decision = Decision(
                action_id=action.action_id,
                verdict=Verdict.ALLOW,
                law_ref=LawRef.from_bundle(bundle, applicable),
                reason="all applicable laws passed"
                if applicable
                else "no applicable laws",
            )

        # Record the action for rate-limit tracking — only on allow, so a
        # denied action doesn't consume rate budget.
        if decision.is_allow and applicable:
            rate_key = f"{action.role.role_id}:{action.request.action_type.value}"
            self.rate_observer.record(rate_key)

        # Sign the decision if we have evaluator credentials.
        if self._evaluator is not None and self.evaluator_lct:
            decision.sign(self._evaluator, self.evaluator_lct)

        return decision

    def evaluate_with_registry(
        self,
        action: R6Action,
        registry: LawRegistry,
        *,
        identity_ceiling: float = 1.0,
    ) -> Decision:
        """Evaluate using the active bundle for the action's scope.

        If no bundle is registered for the action's scope, returns a DEFER
        decision with `reason='no_law_for_scope'`. This is intentional:
        the absence of law is not permission.
        """
        target_scope = (
            action.rules.permission_scope[0]
            if action.rules.permission_scope
            else action.request.action_type.value
        )
        bundle = registry.active(target_scope)
        if bundle is None:
            # DEFER: the absence of law isn't the same as permission.
            # Caller decides whether to fall back or escalate.
            decision = Decision(
                action_id=action.action_id,
                verdict=Verdict.DEFER,
                law_ref=LawRef(bundle_id="", bundle_digest="", version=0),
                reason=f"no_law_for_scope:{target_scope}",
            )
            if self._evaluator is not None and self.evaluator_lct:
                decision.sign(self._evaluator, self.evaluator_lct)
            return decision
        return self.evaluate(
            action, bundle, identity_ceiling=identity_ceiling, scope=target_scope
        )

    # ------------------------------------------------------------------

    def apply(self, action: R6Action, decision: Decision) -> None:
        """Apply a decision to the action's lifecycle.

        ALLOW — no change (caller proceeds to executing)
        DENY  — action.mark_denied(reason)
        DEFER — action.status left at PENDING; side-effect records defer
        """
        if decision.is_deny:
            action.mark_denied(decision.reason)
        elif decision.is_defer:
            action.result.side_effects.append(
                f"deferred:{decision.reason}"
            )

    # ------------------------------------------------------------------

    @staticmethod
    def _summarize(failures: Iterable[RuleFailure]) -> str:
        reasons = [f"{f.law_id}:{f.reason}" for f in failures]
        if len(reasons) == 1:
            return reasons[0]
        return "; ".join(reasons)
