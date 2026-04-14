# Law in the loop

Policy in this system is not a runtime filter. It is not a set of config
flags. It is not a guardrail baked into a model's weights.

**Policy is a signed law.** Every action the system takes was judged against
a specific law bundle at a specific version, and the audit record cites the
cryptographic digest of that exact bundle. You cannot inspect a past action
without also being able to inspect the law it was judged under.

This is what "law in the loop" means.

## The artifacts

```
Legislator → LawBundle (signed)
     │        │
     │        ├── Law (rule body)
     │        ├── Law (rule body)
     │        └── ...
     │
     ├── Witness (signs bundle digest)
     ├── Witness (signs bundle digest)
     └── ...
```

| Artifact | What it is | Signed by |
|----------|-----------|-----------|
| `Law` | Single rule with scope + rule body + validity window | Not directly — lives inside a bundle |
| `LawBundle` | Named, versioned collection of laws for a scope | Legislator (Ed25519) |
| `WitnessSignature` | Countersignature attesting the bundle is accepted | Witness entity (Ed25519) |
| `LawRef` | Compact pointer: `{bundle_id, digest, version, laws_applied}` | Embedded in every Decision |
| `Decision` | Allow / deny / defer outcome of a PolicyGate evaluation | Evaluator (Ed25519) |

## The evaluation flow

```
1. Agent constructs an R6Action (PENDING)
2. Gate: decision = gate.evaluate(action, law_bundle)
   ├── Gate finds applicable laws by scope match
   ├── Each law's rule is applied; failures collected
   ├── Verdict: allow (no failures), deny (any failure), defer (no law)
   ├── LawRef built from bundle digest + applied law ids
   └── Decision signed by evaluator
3. If decision.is_allow: action proceeds to EXECUTING
   Else: gate.apply(action, decision) marks it denied / deferred
4. Audit bundle = (R6Action, Decision). Both verifiable offline.
```

## What's in a rule body

Rule bodies are small predicate dicts. The interpreter knows exactly this set:

| Key | Meaning |
|-----|---------|
| `permit: list[str]` | Only these action_types or scopes allowed |
| `deny: list[str]` | These action_types or scopes blocked |
| `max_cost: float` | `resource.estimated_cost <= value` |
| `max_rate_per_minute: int` | Sliding 60s counter enforced |
| `require_ceiling: float` | Identity trust ceiling must be ≥ value |
| `require_t3_min: dict` | Per-dimension T3 minimums |
| `require_witness: int` | Result must carry ≥ N witness attestations |

**Unknown keys fail closed.** You cannot introduce a typo or a new rule
keyword without updating the interpreter. This is a feature — prevents
silent no-ops.

## Why this matters

### Safety

"Our agents follow policy" is a claim. "Every action record cryptographically
cites the signed law under which it was evaluated, by a legislator whose
identity is verifiable offline, with a witness chain of N peers" is a
**provable claim**. EU AI Act Article 15 auditability maps directly onto
this shape: you can produce the exact law any specific action was judged
under, in signed form, including the supersession chain showing how that
law came to be current.

### Global Resilience

A partitioned agent has its last-valid law bundle cached. It operates under
that law autonomously. When the partition heals, law-state reconciliation
is a first-class step of federation convergence:

1. Peers exchange active bundle digests per scope
2. Higher-version signed bundles supersede lower ones
3. Agents that were operating under superseded law re-evaluate pending work

This is not ad-hoc — it's a direct consequence of laws being signed
versioned artifacts with a supersession chain.

### Training data

Every R6Action → Decision pair is a supervised learning example of what
the system allows and why. "Given rules + role + request + reference +
resource + law, the correct output is this decision." The same audit
bundle that proves compliance is also the training signal for future
policy models.

One shape, three uses. That's the leverage.

## Example: building a law bundle

```python
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import Law, LawBundle, sign_bundle, add_witness

legislator = SigningContext.from_secret(generate_secret())
witness    = SigningContext.from_secret(generate_secret())

bundle = LawBundle(
    bundle_id="b:arc-agi-3:v1",
    scope="arc-agi-3-player",
    version=1,
    laws=[
        Law(
            law_id="law:no-delegation",
            version=1,
            scope="arc-agi-3-player",
            rule_type="prohibition",
            rule={"deny": ["delegate"]},
            rationale="Game-playing agents must not delegate to other systems.",
        ),
        Law(
            law_id="law:cost-cap",
            version=1,
            scope="arc-agi-3-player",
            rule_type="constraint",
            rule={"max_cost": 5.0},
        ),
        Law(
            law_id="law:require-temperament",
            version=1,
            scope="arc-agi-3-player",
            rule_type="requirement",
            rule={"require_t3_min": {"temperament": 0.6}},
            rationale="Low-temperament roles may not play under the live API.",
        ),
    ],
)

sign_bundle(bundle, legislator, "lct:legislator")
add_witness(bundle, witness, "lct:witness:1")
bundle.save("./law/bundles/arc-agi-3-v1.json")
```

## Evaluating against it

```python
from src.policy import PolicyGate
from src.law import LawRegistry

registry = LawRegistry()
registry.required_witnesses = 1
registry.register(bundle)

gate = PolicyGate(evaluator_lct="lct:evaluator",
                  evaluator=evaluator_identity)

decision = gate.evaluate_with_registry(action, registry)
if decision.is_allow:
    action.mark_executing()
else:
    gate.apply(action, decision)  # sets action.status = DENIED

# Audit bundle for this action:
audit = {
    "action": action.to_dict()  if False else None,  # see src/r6
    "decision": decision.to_dict(),
}
```

## What's software-mode good for, and not

This submission ships the software identity path — software legislators,
software witnesses, software evaluators. Bundles are signed with Ed25519,
which is real cryptography, but nothing binds a signer to hardware.

Good enough for:
- Demonstrating the architecture and audit shape
- Internal fleet operation where peer behavior is the trust signal
- Hackathon use

Not good enough for:
- Claims that a specific legal entity signed a specific law (no hardware
  binding means the sealed key can in principle be copied)
- Compliance contexts requiring hardware attestation (production adds
  TPM2 / HSM for legislator keys)

Same architecture, harder substrate. The laws themselves need no change
when upgrading — the binding to hardware happens in the identity layer.
