# ATP / ADP — metabolic accountability

Every action the system takes costs energy. Energy comes from a signed
allocation. Discharged packets carry proof of value produced. Overdrafts
are impossible by construction.

This is "anti-Ponzi accounting" for AI: you can't consume what you don't
have, and every unit consumed is traced to a specific action that either
did or did not produce proportional value.

## The packet lifecycle

```
        issue()                   discharge()              settle()
mint ──────────────► CHARGED ──────────────► DISCHARGED ──────────────► SETTLED
                      ↑                         │                         │
                      │                         │                         │
                    held by                 spent on                   returnable
                     entity                 specific                   to pool as
                                           R6 action                      ADP
```

| State | What it means |
|-------|---------------|
| **CHARGED** | Held by an entity, spendable |
| **DISCHARGED** | Spent on a specific R6 action; value not yet assessed |
| **SETTLED** | Value (V3) recorded; ready to return to pool |

## Conservation invariant

```
total_issued == Σ amount(all packets regardless of state)
```

No packet is created outside `issue()`. No packet amount ever changes
after issuance. `EnergyLedger.check_conservation()` verifies this
invariant; it holds after every operation.

## What it enables

### Safety

A runaway agent can't burn unlimited compute. An agent's authority to
act is bounded by its balance — a metabolic guardrail enforceable without
a supervisor in the loop.

### Auditable cost

Every R6 action that cost energy can be traced to specific discharged
packets, each of which names the issuer, amount, action it was spent
on, and (after settlement) the value produced. "This agent spent X on
action Y which produced value Z" is a fully reconstructable claim.

### Value accounting

V3 assessments on settled packets make "work produced" first-class.
Discharging a packet without producing value (no settlement) is visible
as an outstanding DISCHARGED balance, and can be penalized in trust
updates to the role that spent it.

### EU AI Act Article 15 alignment

Transparency claims about resource use require exactly this: every
consumption event traceable to its source, its purpose, and its output.
ATP/ADP makes that tracing mechanical rather than reconstructive.

## Quick start

```python
from src.energy import EnergyLedger
from src.r6 import V3, R6Action, Resource

ledger = EnergyLedger()

# Issuer mints energy for an agent
for _ in range(10):
    ledger.issue(amount=1.0, to_lct="lct:nomad/agent", from_issuer="lct:mint")

# Agent takes an action costing 3 units
action = R6Action(resource=Resource(estimated_cost=3.0))
used = ledger.spend(
    holder_lct="lct:nomad/agent",
    amount=action.resource.estimated_cost,
    action_ref=action.action_id,
)

# Action completes; assess value and settle
for packet in used:
    ledger.settle(packet.packet_id, V3(valuation=0.7, veracity=0.8, validity=0.9))

assert ledger.check_conservation()
```

## Design choices

### Packets are indivisible

Each packet is an atomic unit, like a coin. To spend 3 units from a 10-unit
packet, the whole packet is discharged. Production deployments "mint
change" by discharging a large packet and issuing smaller ones back — but
the hackathon submission keeps it simple. Issue packets at the
denomination you expect to spend.

### Signing is out of scope for the ledger

Packets themselves are not signed here. The issuer's authority to mint and
the agent's authority to spend flow from the surrounding identity and
audit records (R6Action + Decision). In production, ATP mints would
typically be an R6Action of type "ALLOCATE" witnessed by the legislator,
making the allocation itself auditable under the law-in-the-loop
framework.

### Spend is greedy smallest-first

To minimize overspend on a given action, `spend()` selects the smallest
CHARGED packets first. This preserves larger packets for future operations
that might need them. Deterministic and order-independent.

### Overdrafts fail, they don't partial-spend

If `spend(amount=10)` is requested but the holder only has 5, the call
raises `EnergyError` and nothing is discharged. You can't get halfway
through a failing operation. This matters for transactional integrity.

## Alignment

Clean-room implementation of ATP/ADP from the canonical equation:

```
Web4 = MCP + RDF + LCT + T3/V3*MRH + ATP/ADP
```

Where ATP is allocation transfer packet (charged) and ADP is allocation
discharge packet (spent, returning). Canonical spec:
`web4-standard/core-spec/atp-adp-cycle.md`.

The submission preserves the lifecycle and conservation properties. A
production deployment would extend with: signed minting envelopes, ATP
pool governance, recharge rate limits, temporal decay, and
discharge-to-V3 shaping curves — all layered on top of the same
CHARGED/DISCHARGED/SETTLED state machine.
