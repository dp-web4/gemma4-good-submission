# Dreamcycle — sleep, consolidate, replay

Today's salient experience is tomorrow's prior. The dreamcycle module
closes the loop: every R6 action with its policy decision and SNARC
score becomes a candidate for export to a `DreamBundle`; bundles persist
to disk, transmit between machines, and reload as priors in future
sessions.

The bundle shape is the training-data shape. One file = one batch of
audit-grade examples ready for fine-tuning, retrieval, or cross-machine
knowledge transfer.

## The cycle

```
1.  Wake     →  agent acts; consolidator records (action, decision, snarc)
                                  ↓
2.  Sleep    →  consolidator filters by SNARC composite ≥ threshold,
                exports DreamBundle
                                  ↓
3.  Dream    →  bundle persists to disk / transmits to peers / feeds
                fine-tune or RAG cartridge build
                                  ↓
4.  Wake     →  next session loads bundle as priors via replay_priors()
                (caller injects into model context however suits them)
```

The shape is invariant across all four steps. Nothing transforms in transit.

## Quick start

```python
from src.dreamcycle import Consolidator
from src.snarc import SnarcScore

cons = Consolidator(
    machine="nomad",
    instance_lct="lct:nomad/agent",
    model="gemma-4-e4b-it",
    session="2026-04-14",
    salience_threshold=0.5,
)

# --- wake: record experience ---
for action, decision, snarc in events_during_session():
    cons.record(action, decision=decision, snarc=snarc)

# --- sleep: consolidate to bundle ---
bundle = cons.consolidate()
bundle.save("dreams/2026-04-14.json")

# --- next day: replay as priors ---
from src.dreamcycle import DreamBundle, Consolidator
priors = DreamBundle.load("dreams/2026-04-14.json")
for entry in Consolidator.replay_priors(priors):
    inject_into_context(entry)  # caller decides how
```

## What's in a bundle

```json
{
  "bundle_id": "dream:abc123...",
  "machine": "nomad",
  "instance_lct": "lct:nomad/agent",
  "model": "gemma-4-e4b-it",
  "session": "2026-04-14",
  "created_at": "2026-04-14T20:00:00Z",
  "salience_threshold": 0.5,
  "selection_weights": { "surprise": 0.25, "novelty": 0.25, ... },
  "entries": [
    {
      "action":   { ... full R6Action.to_dict() ... },
      "decision": { ... full Decision.to_dict() ... },
      "snarc":    { "surprise": 0.7, "novelty": 0.9, ... },
      "notes":    "first encounter with green-block puzzle"
    },
    ...
  ]
}
```

Each entry is self-describing: action carries its rules/role/request/
reference/resource/result, decision carries its law_ref, snarc carries
its 5D salience. Loading the bundle recovers the full audit shape.

## Selection model

`Consolidator.consolidate()` filters the wake buffer:

- Records lacking a SNARC score are excluded (no salience signal → can't rank)
- Records with `score.composite(weights) >= threshold` are included
- Threshold is per-call overridable; weights are per-consolidator
- `clear_buffer=True` (default) empties the buffer after export so the
  next session starts fresh

The defaults are chosen so a record needs broad cross-dimension signal
to qualify (high novelty alone won't do it — that's a feature, biases
toward genuinely meaningful events).

## What this enables

### Training data generation

Bundles ARE training examples. A future fine-tune step iterates dream
bundles, treating each entry as one labeled instance: `(action,
decision, salience) → next-step behavior`. The shape is consistent, the
provenance is intact, the audit chain is preserved.

### Cross-machine knowledge transfer

Bundles are JSON, machine-agnostic, signed-bundle-references intact.
Sprout's nightly dreams can ship to Thor for consolidation; Thor's
distillation can ship back to all machines as prior cartridges. The
fleet learns from itself.

### Retrieval cartridges

Andy Grossberg's paired-lattice cartridge architecture (used in the
ARC-SAGE paper for Phase 2) treats high-salience experience as
retrievable structured memory. Dream bundles are a natural input to
that pipeline — already curated by salience, already shaped as
auditable examples.

### Auditability across sessions

Yesterday's bundle is yesterday's audit log. The salience threshold and
weights used to select it are recorded in the bundle header. Future
review can re-derive selection deterministically.

## Design choices

### Records without SNARC are excluded

Without a salience signal there's no principled way to rank. Rather
than guessing (or including everything), the consolidator drops
unscored records by default. Want to keep them anyway? Score them
with neutral SNARC at record time — the cost is one tuple, the
benefit is explicit decision.

### Bundle digest is content-addressed

`bundle.digest()` hashes the canonical payload. A bundle that
roundtrips through disk (or network) preserves its digest; a bundle
whose contents have been mutated does not. Fingerprint for sharing,
caching, and integrity checks.

### Buffer is bounded

Default `buffer_size=1024`. Long-running sessions don't pile up
unbounded experience. If you need everything kept, increase the
buffer size or consolidate more frequently.

### Replay is just iteration

`Consolidator.replay_priors(bundle)` returns an iterator. The
caller decides what to do with each prior — system prompt injection,
RAG retrieval, cartridge build, fine-tune example. We don't prescribe
a downstream consumer because the right one varies by deployment.

## Alignment

Clean-room implementation of the SAGE sleep/wake/dream consolidation
pattern. Canonical reference:
`SAGE/sage/instances/sleep_capability.py` — `write_dream_bundle()`
and `read_dream_bundles()`. The Apache 2.0 submission preserves the
JSONL bundle-per-session shape, the salience-filtered selection
discipline, and the loop-closure pattern (today's salient experience
becomes tomorrow's prior).

The submission diverges in implementation details (in-memory consolidator
rather than process-spawned, single bundle per consolidate() rather than
streaming), keeping the interface contract that the full SAGE stack can
use as a drop-in.
