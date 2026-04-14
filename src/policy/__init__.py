"""
PolicyGate — law-in-the-loop R6 action evaluator.

    gate = PolicyGate(evaluator_lct="lct:thor/judge", evaluator=identity)
    decision = gate.evaluate(action, bundle, identity_ceiling=0.9)
    if decision.is_allow:
        action.mark_executing()
    else:
        gate.apply(action, decision)

Every Decision carries a LawRef, pointing back at the exact signed
bundle. The Decision itself is signed. Together with the R6Action
audit record, they form a verifiable two-part audit bundle.
"""

from .decision import Decision, RuleFailure, Verdict
from .gate import PolicyGate
from .rules import (
    SUPPORTED_KEYS,
    RateObserver,
    RuleVerdict,
    evaluate_law,
)

__all__ = [
    "PolicyGate",
    "Decision",
    "RuleFailure",
    "Verdict",
    "RateObserver",
    "RuleVerdict",
    "evaluate_law",
    "SUPPORTED_KEYS",
]
