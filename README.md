# Attested Resilience

**Self-governing AI for constrained environments.**

A heterogeneous fleet of edge devices, each with persistent cryptographic
identity, coordinating through trust-mediated federation. Every action
auditable under the R6 grammar. Policy evaluation as architectural conscience,
not fine-tune filter. Operates through network partitions. Runs on consumer
hardware.

Submission to the [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon)
(Kaggle + Google DeepMind, 2026).

**Tracks**: Safety, Global Resilience.

## What's Here

```
src/         — clean-room Apache 2.0 implementations
  identity/    — three-layer identity (manifest + sealed + attestation)
  policy/      — PolicyGate at the conscience checkpoint
  federation/  — peer discovery, trust tensors, attestation exchange
  r6/          — Rules + Role + Request + Reference + Resource → Result
  cognition/   — minimal consciousness loop for demo

demo/        — runnable demo scripts
notebooks/   — Kaggle-compatible notebooks
docs/        — technical writeup, architecture
video/       — video script and assets
```

## Quick Start

_(placeholder — populated as code lands)_

```bash
pip install -r requirements.txt
python -m src.cognition.demo
```

## Architecture

The submission stack:

1. **Gemma 4 E4B** — primary model, runs on 16GB consumer GPUs
2. **Gemma 4 26B-A4B** — optional reasoning head when hardware permits
3. **Web4 identity** — three-layer cryptographic identity, offline-capable
4. **SAGE cognition loop** — sense → salience → metabolize → posture → select
   → budget → execute → learn → remember → govern → filter → act
5. **PolicyGate** — conscience checkpoint between deliberation and effectors
6. **Trust-mediated federation** — machines discover, attest, coordinate

Deeper implementations are open-source elsewhere:
- [SAGE](https://github.com/dp-web4/SAGE) (AGPL v3) — full cognition kernel
- [web4](https://github.com/dp-web4/web4) (AGPL v3) — trust-native ontology

This submission repo provides a **clean-room minimal Apache 2.0 subset**
suitable for hackathon distribution and production integration.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Gemma 4 weights are used under Google's Gemma license terms.
