# Trust tensors — T3 and V3 evolution

Trust in this system is not a binary — you are / you aren't — and not a single
scalar. It's a pair of three-dimensional vectors that evolve from observed
behavior, bounded by cryptographic trust ceilings.

## The two tensors

**T3 — Talent / Training / Temperament.** What the role *can do*.
- **Talent** — raw capability at the task type
- **Training** — accumulated learning from successful executions
- **Temperament** — consistency, reliability, alignment under pressure

**V3 — Valuation / Veracity / Validity.** What the output *was worth*.
- **Valuation** — did the result matter to the requester?
- **Veracity** — was the claim true?
- **Validity** — was the work internally consistent / well-formed?

T3 lives on the *role*. V3 lives on the *result*. Neither is global.

## Snapshot vs. live state

Every R6Action embeds a T3 snapshot in its `Role`. That snapshot is the trust
state *at the moment of action*. It does not change after the action lands.

Live, evolving state is held in a `TrustLedger`:

```python
from src.trust import TrustLedger

ledger = TrustLedger()
ledger.role("lct:nomad/agent", ceiling=0.4)   # ceiling from identity
ledger.observe_t3("lct:nomad/agent", training=1.0, action_ref="r6:abc")
snap = ledger.snapshot_t3("lct:nomad/agent")  # for embedding in next R6Action
```

## Evolution math

Exponential moving average with diminishing returns:

```
t_new = clip(t_old + lr(n) * (observation - t_old), 0, ceiling)
lr(n) = max(base_rate * decay^n, min_rate)
```

- `base_rate = 0.10` — early observations move quickly
- `decay = 0.95` — each observation slows future updates
- `min_rate = 0.01` — never fully freezes
- `ceiling` — comes from identity `trust_ceiling` (e.g., 0.4 for software
  anchor, 1.0 for TPM2)

**What this gives you:**
- Fast ramp-up from neutral (0.5) to established (≈0.9) in ~30 observations
- Stability against a single bad observation once established
- Ceiling-enforced cap: a software-anchored agent cannot accrue trust beyond
  its identity allows, regardless of track record
- Asymmetry: easier to earn than to recover (floor is 0.0 with same decay)

## Observation records

Every ledger update produces an `ObservationRecord`:

```python
ObservationRecord(
    role_id="lct:nomad/agent",
    tensor="t3",
    dimension="training",
    observation=1.0,
    prior_value=0.72,
    posterior_value=0.74,
    action_ref="r6:abc",
    witness_id="lct:thor/judge",
    timestamp="2026-04-13T19:00:00Z",
    signature_b64="",  # populated when witness signs
)
```

Records are immutable. They're the audit proof of how trust got where it is.
A verifier can replay them deterministically and arrive at the current T3/V3.

## Why two tensors, not one

A role can be highly *capable* (T3 high) while producing a result that turns
out to be wrong, irrelevant, or incoherent (V3 low). Merging them into one
number loses that signal. Keeping them separate lets the system say:

> "The agent knew what it was doing, but the answer was wrong."
>
> or
>
> "The answer is correct, but it came from a source we don't trust."

Both distinctions matter for downstream routing, for policy evaluation, and
for training data curation.

## Integration with identity

A role's trust ceiling comes from the identity's `anchor_type`:

| Anchor | Ceiling | Meaning |
|--------|---------|---------|
| `tpm2` | 1.0 | Can become fully trusted |
| `fido2` | 0.9 | Can become highly trusted |
| `software` | 0.4 | Capped at "probably genuine" |

Software-anchored agents can participate, but the system knows to discount
their attestations and cap their authority.

## Integration with R6

When building an R6Action, pull the current snapshot:

```python
from src.r6 import R6Action, Role

snap = ledger.snapshot_t3("lct:agent")
action = R6Action(role=Role(role_id="lct:agent", context="demo", t3=snap))
confidence = action.calc_confidence()
# role_capability = snap.composite()
```

After the action completes, feed the assessed result back:

```python
# If action quality was 0.9 (from witness or post-hoc check):
ledger.observe_t3("lct:agent", training=0.9, action_ref=action.action_id)
ledger.observe_v3(
    "lct:agent",
    valuation=result_value,
    veracity=result_truth,
    validity=result_coherence,
    action_ref=action.action_id,
)
```

The ledger closes the loop: actions produce observations, observations evolve
trust, trust informs future actions.
