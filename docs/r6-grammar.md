# R6 — the action grammar

> **Rules + Role + Request + Reference + Resource → Result**

Every action in the system is shaped as an `R6Action` record. The record IS the
audit bundle. The audit bundle IS the training example. One grammar, three uses.

## Why R6

Most action frameworks optimize for *doing*: call a function, return a value.
R6 optimizes for *justifying*: every action carries — by construction — the
context required to explain why it was taken, whether it was allowed, and what
it cost.

That context has three downstream consumers:

1. **Policy evaluation** — the Rules + Role + Request + Reference + Resource
   slice is exactly what a gate needs to decide allow/deny before the action
   runs.
2. **Audit** — the complete record (inputs + result) is a verifiable bundle
   that can be witnessed, signed, and replayed.
3. **Training data** — the same record shape is an instruction-tuned example:
   given rules/role/request/reference/resource, produce a result.

One shape, three uses. That's the leverage.

## The six components

### Rules
What is possible. Governing contracts, permission scope, constraints.

### Role
Who is acting, and in what capacity. Includes a `T3` tensor (Talent / Training /
Temperament) snapshotted at action time.

### Request
The intent. `action_type` + description + acceptance criteria + priority +
optional deadline.

### Reference
What the actor is looking at. Current observation, similar past actions, relevant
memory, horizon depth.

### Resource
What the action costs. Allocated budget, estimated cost, compute units, data
access requested.

### Result
What happened. Output + performance + `V3` value (Valuation / Veracity /
Validity) + side effects + witness attestations.

## Quick start

```python
from src.r6 import R6Action, Rules, Role, Request, Reference, Resource, Result
from src.r6 import ActionType, Priority, T3, to_json

action = R6Action(
    rules=Rules(
        permission_scope=["tool:click"],
        constraints={"max_cost": 1.0, "timeout_s": 5.0},
    ),
    role=Role(
        role_id="lct:nomad:gemma4-e4b",
        context="arc-agi-3-player",
        delegated_permissions=["tool:click"],
        t3=T3(talent=0.7, training=0.8, temperament=0.6),
    ),
    request=Request(
        action_type=ActionType.ACT,
        description="click at (12, 34)",
        priority=Priority.HIGH,
    ),
    reference=Reference(current_observation={"frame": "..."}),
    resource=Resource(cost_allocated=1.0, estimated_cost=0.1),
    initiator_id="lct:nomad:gemma4-e4b",
)

# pre-execution gate
conf = action.calc_confidence()
if conf.overall() < 0.4:
    action.mark_denied("low confidence")
else:
    action.mark_executing()
    # ... actually execute ...
    action.mark_completed(Result(output={"clicked": True}))

# serialize for audit / training
print(to_json(action))
```

## Status lifecycle

```
PENDING → EXECUTING → COMPLETED
                    ↘ FAILED
PENDING → DENIED
```

## JSON round-trip

`to_json(action)` and `from_json(text)` are round-trip stable. A record
serialized, transported, stored, and deserialized reconstructs an equal
action object. This is the contract audit and training both depend on.

## What this is NOT

- Not a workflow engine. No scheduling, no queuing.
- Not a policy engine. Consumes policies, doesn't define them.
- Not a crypto layer. Signatures live in `WitnessAttestation.signature` but
  signing/verifying is in the identity/federation modules.

R6 is the grammar. Everything else plugs in.
