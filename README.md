# Attested Resilience

**Self-governing AI for constrained environments.**

A heterogeneous fleet of edge devices, each with persistent cryptographic
identity, coordinating through trust-mediated federation under signed law.
Every action auditable under the R6 grammar. Policy as signed artifact, not
runtime filter. Operates through network partitions. Runs on consumer
hardware.

Submission to the [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon)
(Kaggle + Google DeepMind, May 2026).

**Tracks**: Safety, Global Resilience.

## The architecture in one diagram

```
                    Legislator (Ed25519)
                          │ signs
                          ▼
                     LawBundle ──┐  Witness(es) countersign
                                 │
                          ┌──────┴─────┐
                          │ LawRegistry│
                          └──────┬─────┘
                                 │
  R6Action (Rules+Role+Request+Reference+Resource+Result)
     │                           │
     ▼                           ▼
   SNARC ─────► salience ──► PolicyGate ──► Decision (signed)
                                 │               │
                                 ▼               ▼
                           Energy ledger    LawRef embedded
                           (ATP → ADP)         in audit
                                 │
                                 ▼
                          Trust ledger
                         (T3/V3 evolves)
                                 │
                                 ▼
                    Dreamcycle (consolidation)
                                 │
                                 ▼
                       DreamBundle (persisted)
                        = training data
                        = audit log
                        = cross-machine signal
                                 │
                                 ▼
                   Federation (peer exchange)
                   — attestation + law-state
```

Identity is the substrate. R6 is the action grammar. Law is the signed
conscience. Every artifact round-trips through JSON; every signature
verifies offline; every audit record carries its law reference.

## Modules

| Module | What it is | Tests | Docs |
|--------|-----------|-------|------|
| [`src/r6/`](src/r6/) | R6 action grammar — the audit bundle shape | 22 | [r6-grammar.md](docs/r6-grammar.md) |
| [`src/identity/`](src/identity/) | Three-layer identity: manifest + sealed + attestation | 29 | [identity.md](docs/identity.md) |
| [`src/trust/`](src/trust/) | T3/V3 trust tensor evolution | 22 | [trust-tensors.md](docs/trust-tensors.md) |
| [`src/law/`](src/law/) | Signed law bundles + registry + supersession | 25 | [law-in-the-loop.md](docs/law-in-the-loop.md) |
| [`src/policy/`](src/policy/) | PolicyGate evaluator → signed Decision | 24 | [law-in-the-loop.md](docs/law-in-the-loop.md) |
| [`src/snarc/`](src/snarc/) | 5D salience (Surprise/Novelty/Arousal/Reward/Conflict) | 30 | [snarc.md](docs/snarc.md) |
| [`src/energy/`](src/energy/) | ATP/ADP metabolic accountability | 31 | [atp-adp.md](docs/atp-adp.md) |
| [`src/dreamcycle/`](src/dreamcycle/) | Sleep/wake consolidation → DreamBundle | 20 | [dreamcycle.md](docs/dreamcycle.md) |
| [`src/federation/`](src/federation/) | Peer authentication + law-state convergence | 22 | [federation.md](docs/federation.md) |
| `src/cognition/` | Integration: full loop demo (in progress) | — | — |

**Running total: 225 tests, ~2720 LoC, all green.**

## What this actually demonstrates

1. **Law-in-the-loop.** Every action's audit record cites the signed law
   bundle it was judged under. You cannot inspect a past action without
   also being able to verify the law in effect. Compliance claims (EU AI
   Act Art. 15 etc.) rest on cryptographic proof, not prose.

2. **Audit = training data, by construction.** The R6Action + Decision
   shape that proves compliance is also the labeled instance a future
   model learns from. One grammar, three uses: policy input, audit
   bundle, training example.

3. **Partition tolerance by design.** Law bundles are signed, versioned,
   and content-addressed. When partitioned, agents operate under their
   last-valid law. On reconnect, law-state reconciliation is a first-class
   step of federation convergence — higher-version signed bundles
   supersede lower ones.

4. **Metabolic guardrails.** Every action costs energy from an allocated
   ATP pool. Overdraft is impossible by construction. Discharged packets
   carry V3 value assessments — consumption tied to output.

5. **Subjective trust.** Federated — each agent holds its own peer
   registry built from its own observations. Disagreement is expected,
   not an error. Cryptographic floor (signatures verify identically
   everywhere) plus observational ceiling (what you've witnessed).

## Quick start

```bash
git clone <repo>
cd gemma4-good-submission
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run the test suite (225 tests, ~3s)
.venv/bin/python -m pytest tests/ -v
```

## Deeper reading

- [`docs/paper.md`](docs/paper.md) — **Architecture paper** covering
  motivation, every module in depth, design decisions, composition,
  alignment with canonical SAGE/web4, and fleet deployment
- [`docs/narrative.md`](docs/narrative.md) — five video arcs mapping
  modules to demonstrable scenarios
- [`docs/architecture.md`](docs/architecture.md) — short architecture
  overview
- [`docs/unsloth-stretch.md`](docs/unsloth-stretch.md) — LoRA fine-tune
  stretch goal ($10K Unsloth prize); dream bundles as training data

## Related work

Deeper implementations from the broader dp-web4 collective:

- [SAGE](https://github.com/dp-web4/SAGE) (AGPL v3) — full cognition
  kernel; this submission is an Apache 2.0 clean-room subset preserving
  the public API
- [web4](https://github.com/dp-web4/web4) (AGPL v3) — trust-native
  ontology; the canonical equation
  `Web4 = MCP + RDF + LCT + T3/V3*MRH + ATP/ADP` drives every module
  name and shape in this repo
- [ARC-SAGE](https://github.com/dp-web4/ARC-SAGE) (MIT-0) —
  ARC-AGI-3 harness reporting 84.9% on the public set (21/25
  environments, 160/183 levels, ~$250 total cost). Phase 2 targets
  the same Gemma 4 model family (E4B primary, E2B edge, 26B-A4B
  aspirational). ARC Prize 2026 Paper Track.

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

Gemma 4 weights are used under Google's Gemma license terms.
