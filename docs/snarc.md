# SNARC — 5D salience

SNARC is how the system decides *what's worth paying attention to*. Every
observation is scored across five dimensions. The composite score drives
downstream decisions: memory retention, policy escalation, dream-consolidation
selection.

## The five dimensions

| Dimension | Question it answers | Typical source |
|-----------|---------------------|----------------|
| **Surprise** | How different is this from what I expected? | Prediction vs. observation divergence |
| **Novelty** | How different is this from what I remember? | Similarity against memory ring |
| **Arousal** | How urgent / intense is this? | External signal (alarms, deadlines, stakes) |
| **Reward** | How much does this advance the goal? | Reward shaping, policy outcome |
| **Conflict** | How much does this contradict my world model? | Policy deny, validation failure, peer disagreement |

Each dimension is in `[0, 1]`. The composite is a weighted mean:

```
composite = Σ w_i * dim_i / Σ w_i
```

Default weights: surprise 0.25, novelty 0.25, arousal 0.15, reward 0.20,
conflict 0.15. Weights are per-call configurable because different tasks
reward different dimensions (consolidation favors novelty + reward; alerting
favors arousal + conflict).

## Quick start

```python
from src.snarc import Scorer

scorer = Scorer(memory_size=64)

# First observation — fully novel, no expectation → surprise 0, novelty 1
s1 = scorer.score("game frame #1 — green block at (4,5)")

# A second frame — some novelty, plus an expectation of what we expected
s2 = scorer.score(
    "game frame #2 — green block at (4,6), red block at (3,2)",
    expectation="green block at (4,5)",
    arousal=0.3,       # new object appeared — somewhat arousing
    reward=0.5,        # block moved toward target
)
# s2.surprise > 0, s2.novelty > 0, composite driven by both

# Use the composite to gate consolidation
if s2.above(threshold=0.4):
    keep_for_dreams(observation, s2)
```

## Integration points

- **Consciousness loop step 2 (Salience)** — every sensor observation is
  SNARC-scored before downstream steps consume it
- **Policy evaluation** — high-conflict scores escalate to a stricter
  evaluator or require additional witnesses
- **Dream consolidation** — only high-composite observations are exported
  to dream bundles; low-salience observations are discarded at sleep time
- **Training data curation** — salience is one signal for which R6 audit
  bundles become future training examples

## Design choices

### Surprise and Novelty are different

Surprise is relative to a *specific expectation* (what I thought would
happen next). Novelty is relative to *general memory* (have I seen
anything like this recently). An observation can be surprising but not
novel ("every day at 3pm the sky turns green" — surprising the first
day, novel for weeks, just surprising thereafter).

### Arousal / Reward / Conflict are caller-supplied

The scorer doesn't invent these. They come from elsewhere in the stack:
- Arousal from external state (time pressure, resource scarcity)
- Reward from policy evaluation and reward shaping
- Conflict from validation checks, policy denials, peer disagreements

The scorer is a *aggregator*, not a generator, of these signals. This
keeps concerns separated and makes each dimension individually
explainable.

### Similarity is Jaccard over tokens, for now

Novelty computation uses whitespace-split tokens and Jaccard. It's
deterministic, dependency-free, and good enough at hackathon scale.
Production swaps in embeddings — same scoring interface, same composite
math, better similarity backbone.

### Fail-open on missing expectation

If no expectation is supplied, surprise is 0 (not 1 or None). The scorer
doesn't penalize calls that simply have nothing to compare against. This
matters for open-world observations where predictions aren't always
available.

## Alignment

Clean-room implementation of the SNARC salience concept from the SAGE
consciousness loop (step 2, `sage/core/sage_consciousness.py`). Five
dimensions preserved exactly. Weights and similarity function simplified
for the Apache 2.0 submission; the interface contract stays the same so
the full stack can plug in directly.
