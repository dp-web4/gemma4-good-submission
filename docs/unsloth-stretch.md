# Unsloth stretch goal — Gemma 4 LoRA on audit-bundle data

The Gemma 4 Good Hackathon has a separate $10K Unsloth prize for "best
fine-tuned Gemma 4 model built with Unsloth." This submission's core
thesis — **dream bundles are training data by construction** — makes
that prize thematically aligned rather than a detour.

## The plan

Fine-tune a LoRA on Gemma 4 (E4B primary target; 26B-A4B as follow-up)
using data derived from the cognition loop itself:

1. **Synthetic ticks** via `StubExecutor` — cheap, high volume, varied
   law bundles / observations / SNARC inputs. Each tick produces a
   `(prompt, expected_output)` pair where the prompt is exactly what
   `GemmaOllamaExecutor._build_prompt()` produces and the expected
   output is a well-formed plan + JSON self-assessment.
2. **Real-model runs** via `GemmaOllamaExecutor` against local Gemma,
   filtered by outcome quality ≥ 0.75 — authentic examples that passed
   our own policy gate.
3. **Fleet dream bundles** — DreamEntry is already curated by SNARC
   composite threshold.
4. **ARC-AGI-3 solutions** — retroactive wrapping of the ARC-SAGE fleet's
   21/25 solved games as R6Actions; high-value behavioral signal.

Target mix to start: **40% synthetic / 40% filtered-real / 20% ARC-AGI-3
retrospective**. Target size: 10k–50k examples.

## Why this isn't "just another fine-tune"

The fine-tune isn't trying to beat a benchmark. It's compiling the
**audit shape** into the model's priors so that future agents produce
audit-bundle-native output on the first pass — no post-hoc parsing, no
prompt gymnastics, no brittle JSON coaxing.

Concretely, a successful LoRA would:
- Emit the self-assessment JSON block without being asked twice
- Structure plans to satisfy `acceptance_criteria` explicitly
- Refuse cleanly and self-consistently when the request contradicts
  the role's delegated permissions
- Maintain outcome quality high enough to earn V3 valuation above the
  ceiling-adjusted mean

## Fleet delegation

LoRA training on Gemma 4 needs real VRAM for backward passes —
≥ 24GB for 4-bit QLoRA at useful batch, ≥ 40GB for larger context.
Neither this submission's demo machine (RTX 4060 8GB) nor the fleet's
16GB workers (Legion, McNugget) can serve. **Thor (122GB VRAM) is the
natural home.**

The fleet coordination document lives at:

> `private-context/plans/2026-04-15-thor-unsloth-gemma4-finetune.md`

It spells out pipeline, success criteria, data sources, and an
explicit handoff to Thor's training track. Submission deadline is
the same as the main hackathon: May 18, 2026.

## Convergence with ARC-SAGE Phase 2

ARC-SAGE (MIT-0, ARC Prize 2026 Paper Track — 84.9% on public set using
Opus 4.6) already targets Gemma 4 E4B as the Phase 2 deployment model
with Andy Grossberg's paired-lattice cartridge architecture.

A LoRA fine-tuned on the audit-bundle shape + retrieval cartridges
built from dream bundles is **exactly the composition ARC-SAGE Phase 2
specifies**. Winning or losing the Unsloth prize is secondary to
producing a drop-in deployment LoRA for the AGI-3 competition.

## Evaluation shape

**For Unsloth submission:**
- Base vs fine-tuned on 100 demo ticks
- Metrics: average quality, % well-formed JSON self-assessment, %
  policy-compliance on contradicting-request tests
- Writeup linking training-data shape to the audit-bundle definition
  from this repo's `docs/paper.md`

**For ARC-SAGE Phase 2 validation:**
- LoRA drops into the ARC-SAGE harness
- Measurable improvement on ≥ 1 ARC-AGI-3 public game vs. baseline E4B
- Retrieval-cartridge + LoRA composition as proof-of-concept for the
  "capability compilation" thesis

## Status

Delegated to Thor's fleet track on 2026-04-15. See the private-context
plan for the handoff log and current state.
