# Attested Resilience: Self-Governing AI for Constrained Environments

**A clean-room architecture for cryptographically-auditable, partition-tolerant, metabolically-bounded AI agents built on Gemma 4.**

- **Authors**: Dennis Palatov (Metalinxx Inc.), Claude Opus 4.6 (via Claude Code)
- **Submission**: Kaggle + Google DeepMind [Gemma 4 Good Hackathon](https://www.kaggle.com/competitions/gemma-4-good-hackathon), May 2026
- **Tracks**: Safety, Global Resilience
- **License**: Apache 2.0
- **Draft**: 2026-04-15

---

## Abstract

We present a compact, end-to-end architecture for deploying AI agents in
constrained, accountable environments. The system centers on five design
commitments: every action is shaped as a six-component auditable record
(R6); every agent holds a three-layer cryptographic identity; every policy
is a signed, witness-attested law entity referenced by digest from every
audit bundle; every computation costs energy from a conservable metabolic
pool (ATP/ADP); and salient experiences consolidate into training-data-
shaped dream bundles that close the learning loop.

The submission is a clean-room Apache 2.0 implementation (~2720 LoC,
225 tests, fully green) distilled from the AGPL-licensed SAGE cognition
kernel and the web4 trust-native ontology. It is model-agnostic by design
and targets Gemma 4 E4B as primary runtime (fits 16GB GPUs),
Gemma 4 26B-A4B as optional reasoning head on workstation-class
hardware, and Gemma 4 E2B for edge devices. Sprout (Jetson Orin Nano,
8GB) remains on Qwen — heterogeneous fleet is treated as feature, not
bug.

Two principles unify the architecture. First, **law-in-the-loop**: the
policy an action was judged under is not a runtime config; it is a
signed, versioned, witness-attested artifact whose cryptographic digest
is embedded in every audit record. Compliance claims reduce to digest
verification. Second, **audit = training data**: the R6Action + Decision
pair that proves a compliance claim is, by construction, the labeled
instance a future model learns from. One shape, three uses.

We describe each module in depth, the composition pattern that binds
them, alignment with the canonical web4 equation, and how the system
supports both Safety and Global Resilience judging criteria in the
hackathon. We close with limitations, what's deliberately out of scope
for this submission, and directions for production deployment.

---

## 1 Motivation

The hackathon prompt names two constraints that most AI deployments
treat as afterthoughts: *operating in constrained environments*
(edge devices, limited bandwidth, intermittent connectivity) and
*technical innovation in safety* (multimodal, function-calling models
that must be governable without a human on every step).

A common industry response is to bolt guardrails on top of a frontier
model behind an API. That strategy fails both constraints: it requires
reliable network, it centralizes trust, and it makes per-action audit
reconstructive rather than mechanical. For AI in the hospital, the
field clinic, the disaster response tent, or the battery pack, that's
the wrong shape.

We take the opposite stance. The system must:

1. **Run offline.** Federation is a capability, not a requirement.
2. **Produce audit artifacts by construction.** Every action carries
   the exact law it was judged under.
3. **Survive partitions principledly.** Last-valid-law survives
   downtime; reconnection reconciles law state.
4. **Bound resource use.** Energy accounting is not a monitoring
   overlay; it's a precondition for action.
5. **Compose heterogeneous fleets.** Jetson-class edge and
   workstation-class reasoning share the same trust fabric.

These commitments reshape the stack from inside. The result is not a
model — it's scaffolding that lets a small model (Gemma 4 E4B) behave
accountably in exactly the places where accountability is hardest to
prove.

---

## 2 Architectural commitments

The nine modules implement five compound commitments:

### 2.1 Actions are audit records

Every action in the system is an **R6Action** — a dataclass carrying
Rules, Role, Request, Reference, Resource, and (on completion) Result.
This isn't a logging shim; it's the native shape. The code that
*decides to take an action* builds an R6Action; the code that *judges
an action* consumes an R6Action; the code that *learns from past
action* reads R6Action bundles. One type, three consumers.

This matters because the *shape of the audit bundle is the shape of the
training example*. `(rules, role, request, reference, resource) → result`
is a supervised learning instance. The same record that proves
compliance teaches a future model what to do next time.

### 2.2 Identity precedes action

Every R6Action carries an `initiator_id` — a cryptographic LCT. Without
a verifiable identity, the rest of the audit chain is decorative. The
identity module implements three layers:

- **Layer A (manifest)**: public, readable by anyone, names the agent
- **Layer B (sealed secret)**: passphrase-sealed (software path) or
  hardware-sealed (TPM2, FIDO2, SE); holds the Ed25519 seed
- **Layer C (attestation envelope)**: signed, time-bounded, nonce-
  embedded proof that *at this time, this agent held this key*

Envelopes are self-contained — a verifier needs only the envelope itself
plus the challenge it issued. No CA, no lookup, no third party.

Trust ceilings per anchor type (TPM2 = 1.0, FIDO2 = 0.9, software = 0.4)
cap how much trust an identity can ever accrue regardless of track
record. A software-anchored agent can participate, but the system
knows to discount its attestations.

### 2.3 Policy is signed law

The submission's most distinctive commitment. Policy is not a runtime
filter. It is a `LawBundle`:

- A named collection of `Law` records for a specific scope
- Signed by a **Legislator** entity using its own identity
- Optionally countersigned by **Witnesses**
- Versioned; a newer version for the same scope supersedes
- Content-addressed by SHA-256 of the canonical payload

The **PolicyGate** takes an R6Action and a LawBundle; applies every
applicable law's rule body; produces a signed **Decision** record
containing:

- Verdict: `allow | deny | defer`
- `LawRef`: `{bundle_id, bundle_digest, version, law_ids_applied}`
- Reasons and failure records if not allow
- Evaluator signature

The Decision is paired with the R6Action as a two-part audit bundle.
Every future reader of that audit bundle can:

1. Reconstruct the exact signed law bundle (via bundle_digest)
2. Verify the legislator's signature on that bundle
3. Verify the witness countersignatures
4. Verify the evaluator's signature on the decision
5. Replay the rule interpreter against the action + law
6. Confirm the decision was produced correctly

Every step of that chain is offline, deterministic, and
cryptographically anchored. **This is what "law in the loop" means.**

### 2.4 Energy is conserved

Every action costs energy from an ATP pool. Energy is issued by a
legitimate issuer to an agent; held in `AtpPacket` units (CHARGED
state); spent on specific R6 actions (DISCHARGED state); settled with
a V3 value assessment (SETTLED state).

The ledger enforces:

- `total_issued == Σ amount(all packets)` — strict conservation
- Overdraft raises, doesn't partial-fill — transactional integrity
- Packets are indivisible (atomic units, like coins)
- Signed ownership trail: issuer → holder → action → assessment

Compared to cost counters bolted onto API middleware, ATP/ADP makes
resource accounting *structurally impossible to lie about*. The agent
cannot consume compute it wasn't allocated. The auditor cannot find
actions whose cost doesn't trace to a specific issuer.

### 2.5 Salience drives consolidation

During wake-time, every action + decision + sensor-observation gets a
**SNARC** score — five-dimensional salience (Surprise, Novelty, Arousal,
Reward, Conflict). At sleep-time, the **Consolidator** filters the
experience buffer by composite-threshold and emits a **DreamBundle**.

The bundle is the audit log, the training example, and the cross-machine
knowledge transfer artifact — all simultaneously. When the next session
starts, `replay_priors(bundle)` injects yesterday's salient experience
back as today's priors. The shape is invariant across all four steps:
wake → sleep → dream → wake.

---

## 3 Module details

### 3.1 R6 action grammar (`src/r6/`)

The R6Action dataclass carries six inputs and one output. Each is its
own dataclass:

- **Rules** — governing contracts, permission scope, constraints (max
  cost, timeout, quality threshold)
- **Role** — role_id, context, delegated permissions, T3 snapshot
  (talent/training/temperament)
- **Request** — action_type enum, description, acceptance criteria,
  priority, optional deadline
- **Reference** — current observation, similar past actions, relevant
  memory, horizon depth
- **Resource** — allocated / consumed cost, compute units, data access,
  estimated cost
- **Result** — output, Performance (time, quality), V3 value assessment,
  side effects, witness attestations

Status lifecycle: `PENDING → EXECUTING → COMPLETED / FAILED / DENIED`.

`to_json(action)` and `from_json(text)` are round-trip stable. Enums
serialize as string values; nested dataclasses reconstruct explicitly
(per-field decoders).

Pre-execution confidence is computed from role capability (T3
composite), historical success (count of similar actions), resource
availability (can_afford), and a risk factor:

```
Confidence.overall = (role + historical + resource + risk) / 4
```

Tests: 22 covering construction, lifecycle, serialization, confidence,
and the audit-bundle shape contract.

### 3.2 Identity (`src/identity/`)

The three layers each have a dedicated file:

- `manifest.py` — `IdentityManifest` dataclass, trust ceiling
  derivation, roundtrip JSON
- `sealed.py` — AES-256-GCM over PBKDF2-SHA256 (200k iterations);
  16-byte salt, 12-byte nonce; version field for future migration
- `signing.py` — `SigningContext` wrapping Ed25519 private key; sign,
  verify, fingerprint (first 16 hex of SHA-256 of raw public key)
- `attestation.py` — `AttestationEnvelope` with lct_id, anchor_type,
  public_key_b64, manifest_digest, nonce, issued_at, expires_at,
  signature; `attest()` and `verify_envelope()`
- `provider.py` — `IdentityProvider` orchestrates bootstrap /
  authorize / attest; enforces fingerprint-binding (swapping the
  sealed file fails authorization with a distinct error)

**Notable**: we use real Ed25519 rather than the HMAC placeholder
present in the SAGE canonical. AES-256-GCM for sealing (the canonical
is in-progress). Manifest's `trust_ceiling` is *derived* from
`anchor_type` and not stored — prevents attacker-injected ceiling
override.

Tests: 29 covering all three layers, peer exchange (Alice attests, Bob
verifies offline), and the fingerprint binding defense.

### 3.3 Trust tensors (`src/trust/`)

T3 and V3 are defined in `src/r6/types.py` (three-dim each, composite
is mean). The trust module adds evolution via exponential moving
average with diminishing returns:

```
t_new = clip(t_old + lr(n) * (observation - t_old), 0, ceiling)
lr(n) = max(base_rate * decay^n, min_rate)
```

- `base_rate = 0.10`, `decay = 0.95`, `min_rate = 0.01`
- `ceiling` from identity's `trust_ceiling`

R6 snapshots (what's in Role) and TrustLedger live state (what's
current per role_id) are deliberately separated. Every update emits
an immutable `ObservationRecord` with prior_value, posterior_value,
action_ref, witness_id, timestamp — the audit trail of how trust
got where it is.

Tests: 22 covering math (rate decay, diminishing returns, ceiling
enforcement), ledger ops (role isolation, snapshot immutability),
observation records (order preservation, filtering), persistence,
and R6 integration.

### 3.4 Law (`src/law/`)

Three files:

- `law.py` — `Law`, `LawBundle`, `WitnessSignature`, `LawRef`
- `signing.py` — sign_bundle, add_witness, verify_legislator,
  verify_witness, verify_bundle (with required_witnesses quorum)
- `registry.py` — LawRegistry with active-per-scope, supersession
  chain, directory loading

A Law has scope (`arc-agi-3-player`, `tool:*`, `federation`), a
`rule_type` (permission, constraint, ceiling, prohibition, requirement),
a rule body (predicate dict), rationale (for humans), and effective/
expiry windows.

Rule bodies speak a deliberately small language:

```
permit: list[str]             allowlist
deny: list[str]               blocklist
max_cost: float               resource.estimated_cost ≤ value
max_rate_per_minute: int      sliding window counter
require_ceiling: float        identity trust ceiling ≥ value
require_t3_min: dict          per-dimension T3 minimums
require_witness: int          result must carry ≥ N witness attestations
```

**Unknown keys fail closed.** You cannot introduce a typo or a new
keyword without updating the interpreter. Silent no-ops are impossible.

`LawBundle.canonical_payload()` builds the bytes that are signed. It
*includes* `legislator_lct` and `legislator_pubkey_b64` (so two different
signers producing identical law content have different digests) and
*excludes* `signature_b64` and `witnesses` (so attaching witnesses
doesn't change the digest). This layering is essential: a bundle's
identity is its signed content, and a LawRef pointing at that identity
must be stable across witness accretion.

The registry is append-only in history; supersession tracked in an
internal map keyed by bundle_id — **bundles themselves are never
mutated**. This is critical for federation: a bundle that travels
alice → bob → charlie must verify identically at every hop.

Tests: 25 across Law, LawBundle (digest, sign/verify, witness), LawRef,
LawRegistry (supersession, isolation by scope, witness quorum,
directory loading).

### 3.5 Policy (`src/policy/`)

- `rules.py` — rule interpreter and RateObserver
- `decision.py` — Decision dataclass with signing, verification,
  canonical payload
- `gate.py` — PolicyGate

The gate flow:

1. Caller provides R6Action (pending) + LawBundle (or LawRegistry)
2. Gate identifies applicable laws via scope match (exact or glob)
3. For each law, rule interpreter returns verdict (passed, reason)
4. Any failures → Decision.verdict = DENY; reasons captured
5. No failures + applicable laws → ALLOW
6. No bundle for scope → DEFER (absence of law is not permission)
7. If evaluator has identity, Decision is signed

`Decision.canonical_payload()` is stable across serialization. Decision
+ R6Action form a two-part audit bundle; each part verifies
independently.

Tests: 24 covering rule interpreter per-key, gate allow/deny/defer,
rate limit across calls, signed/tampered decisions, end-to-end flow
with witnesses and trust ceilings.

### 3.6 SNARC (`src/snarc/`)

Five-dimensional salience with configurable weights:

```
default_weights = surprise 0.25, novelty 0.25, arousal 0.15,
                  reward 0.20, conflict 0.15
```

**Separation of concerns:**

- **Surprise** — relative to a specific expectation (caller-supplied);
  no expectation → 0
- **Novelty** — relative to general memory (ring buffer); Jaccard on
  whitespace-split tokens
- **Arousal / Reward / Conflict** — caller-supplied from external
  signals (alarms, reward shaping, policy denials, validation)

The scorer is an *aggregator*, not a *generator*, of the last three.
Separation keeps each dimension individually explainable.

Tests: 30 across score math, similarity, surprise, novelty ring,
scorer integration, and a composite-threshold filter for
consolidation.

### 3.7 Energy (`src/energy/`)

Lifecycle: CHARGED → DISCHARGED → SETTLED.

- **Issue** — new CHARGED packet held by `to_lct`, issuer recorded
- **Transfer** — CHARGED packet changes hands (disallowed once
  discharged)
- **Discharge** — holder spends packet on a specific R6 action
- **Spend** — greedy smallest-first multi-packet discharge to cover
  an amount; fail-all on overdraft (never partial)
- **Settle** — DISCHARGED packet receives a V3 assessment; becomes
  SETTLED

Conservation is mechanical: `total_issued == Σ amount(all packets
regardless of state)`. `check_conservation()` verifies after every
operation; holds through every lifecycle state.

Packets are indivisible. Production deployments "mint change"
(discharge large, issue small); the submission keeps it simple.

Tests: 31 covering packet state transitions, issuance, transfer,
discharge, spend (exact, multi-packet, smallest-first, overdraft,
atomicity), settle, conservation invariants, persistence, and R6
integration.

### 3.8 Dreamcycle (`src/dreamcycle/`)

- `bundle.py` — `DreamBundle` (header + entries), `DreamEntry`
- `consolidator.py` — `Consolidator` with bounded buffer, threshold
  selection, custom weights, replay iterator

Wake: `consolidator.record(action, decision=decision, snarc=snarc)`.
Sleep: `consolidator.consolidate(threshold=0.5)` → DreamBundle of
high-salience entries. Persistence via `bundle.save(path)`.

Next session: `DreamBundle.load(path)` then
`Consolidator.replay_priors(bundle)` yields DreamEntries — caller
decides how to inject into model context (system prompt, RAG, cartridge).

The bundle digest is content-addressed: roundtrip through disk
preserves it; mutation changes it. Fingerprint for sharing, caching,
integrity.

Tests: 20 across bundle ops (add, digest stability, roundtrip),
consolidator recording (bounded buffer), selection (threshold, custom
weights, unscored exclusion), consolidation (clear/no-clear, metadata
preservation), replay, and end-to-end identity→policy→snarc→bundle.

### 3.9 Federation (`src/federation/`)

- `peer.py` — `Peer` with anchor-derived ceiling
- `registry.py` — `PeerRegistry` with verify-on-observe, nonce check,
  freshness check, persistence
- `exchange.py` — `AuthChallenge`, `respond_to_challenge`, `verify_response`,
  `mutual_auth`; `LawStateAdvert`, `diff_law_state`, `reconcile_law`

Peer auth is challenge-response over attestation envelopes. The verifier
issues a fresh nonce; the prover's envelope embeds it; verifier rejects
mismatched or replayed envelopes.

Law-state convergence: peers advertise per-scope `{bundle_id, version,
digest}`; diff identifies who holds newer; newer bundles ship across
and reconcile (re-verified against local witness requirements).

**Bundles stay immutable during federation.** The bug we flagged
during implementation: the registry originally mutated
`supersedes_bundle` on register, which would invalidate the legislator's
signature. Fix: track supersession in an internal map; leave bundles
untouched. A signed bundle is signed forever.

Subjective trust is explicit. Alice's view of Bob ≠ Bob's view of
Alice. Disagreement is correct, not an error. Cryptographic floor
(everyone verifies the same signatures) plus observational ceiling
(what you've witnessed).

Tests: 22 covering peer and registry basics, auth (single + mutual),
law adverts, diffs, reconcile (accept/reject/supersede), and an
end-to-end partition recovery scenario.

---

## 4 Composition patterns

Nine modules compose via three patterns.

### 4.1 Audit bundle = (R6Action, Decision)

The composite artifact that proves compliance for a single action.
Both parts are signed — the action by the agent's identity, the
decision by the evaluator's — and both verify offline. Adding a
third component (witness attestations in Result) turns it into a
quorum-attested audit bundle.

### 4.2 Law-in-the-loop

`Decision.law_ref` embeds `{bundle_id, bundle_digest, version}` of
the LawBundle consulted. The bundle itself is signed; the decision is
signed; the action is signed. A verifier reconstructs the full proof
chain without a network call.

### 4.3 Wake → Sleep → Dream → Wake loop closure

1. **Wake**: agent emits R6Actions; PolicyGate produces Decisions;
   SNARC scores them; Consolidator buffers the triples
2. **Sleep**: Consolidator filters by salience threshold; emits
   DreamBundle
3. **Dream**: bundle persists to disk / transmits to peers / feeds
   fine-tune or retrieval cartridge builder
4. **Wake (next)**: next session loads bundle; `replay_priors`
   injects as priors

The shape is invariant across all four steps. Nothing transforms.
Nothing loses its signed provenance.

---

## 5 Canonical alignment

Every module name and shape derives from the Web4 canonical equation:

```
Web4 = MCP + RDF + LCT + T3/V3 * MRH + ATP/ADP
```

- **LCT** → identity (manifest + sealed + attestation)
- **T3/V3** → trust and value tensors; R6 Role and Result
- **MRH** → Reference.horizon_depth
- **ATP/ADP** → energy module
- **R6** → the action grammar
- **SNARC** → salience scoring (from SAGE consciousness loop step 2)

Canonical specs referenced:

- `web4-standard/core-spec/LCT-linked-context-token.md`
- `web4-standard/ontology/t3v3-ontology.ttl`
- `web4-standard/core-spec/atp-adp-cycle.md`
- `web4-standard/core-spec/r6-framework.md`

The submission is a **clean-room implementation**: it reimplements the
concepts in lean Apache 2.0 code without copying AGPL source. Where the
canonical placeholder was incomplete (e.g., HMAC-signed contexts), we
upgraded to real Ed25519. Where the canonical was principled but not
yet wired, we wired it (registry supersession, bundle immutability,
policy decision signing). Interface shapes match so the full SAGE
stack can use this subset as a drop-in.

---

## 6 Fleet deployment

Target fleet (configuration realized today):

| Machine | Hardware | Model | Role |
|---------|----------|-------|------|
| Thor | 122GB VRAM | Gemma 4 26B-A4B | Flagship reasoning head |
| Legion | 16GB | Gemma 4 E4B | Worker |
| McNugget | 16GB | Gemma 4 E4B | Worker |
| Nomad | varies | Gemma 4 E4B (migration) | Worker |
| CBP | **8GB laptop GPU** | Gemma 4 E2B | Worker (E4B too tight) |
| Sprout | **8GB Jetson Orin Nano** | Qwen (stays) | Edge demonstrator |

### 6.1 VRAM gate for Gemma 4 variants

| Variant | Smallest ollama tag | Size | Fits |
|---------|---------------------|------|------|
| E2B | `gemma4:e2b` | 7.2GB | ≥ 8GB VRAM (tight) |
| E4B | `gemma4:e4b-it-q4_K_M` | 9.6GB | ≥ 12GB VRAM recommended |
| 26B-A4B | `gemma4:26b-a4b-q4_K_M` | varies | ≥ 24GB VRAM |

We confirmed live on a RTX 4060 8GB (WSL) that E2B runs comfortably
(~1s per cognition tick with think=False); E4B at q4_K_M exceeds the
8GB budget and forces CPU offload to the point of being unusable.
CBP hit the same wall. Legion and McNugget (16GB) are the real E4B
homes in the fleet. Thor runs 26B-A4B.

**Sprout stays on Qwen.** 8GB total memory is tight for Gemma 4 E2B
after accounting for OS, attention, and other fleet services. Rather
than force homogeneity, we lean into heterogeneity: the trust fabric
doesn't care what model a machine runs. Attestation envelopes,
policy decisions, dream bundles — all are model-agnostic. An audit
bundle signed by Sprout (Qwen) verifies identically to one signed by
Thor (Gemma 4 26B-A4B).

**Different Gemma 4 variants per machine is a feature.** An 8GB
laptop GPU runs E2B; a 16GB workstation GPU runs E4B; a
workstation with 24GB+ runs 26B-A4B. The `GemmaOllamaExecutor`
adapter is identical across all three — only the model tag changes.
This makes the submission deployable on realistic, non-uniform
consumer hardware without per-machine code paths.

This is the real "constrained environments" story: the system works
*across* constraint boundaries, not by pretending they don't exist.

---

## 7 How this scores against judging criteria

### 7.1 Safety

**"Policy as architectural conscience, not fine-tune filter."**

The hackathon rewards technical innovation in safety. The submission's
claim is direct:

- Policy is a **signed, versioned, witness-attested law entity**.
  Not a fine-tune filter, not config flags, not prose guidelines.
- Every R6 audit bundle embeds a LawRef pointing at the exact signed
  bundle. No audit record is interpretable without knowing the exact
  law in force.
- Supersession chain is cryptographic — you can trace how today's law
  was derived from yesterday's.
- Failed-closed on unknown rule keys. Silent no-ops are impossible.
- Decisions themselves are signed — a denial has the same provenance
  as an allowance.

EU AI Act Article 15 auditability maps directly onto this shape. A
compliance query is a digest lookup followed by a cryptographic
verification.

### 7.2 Global Resilience

**"AI that survives partition, attack, and the unknown."**

- **Three-layer identity persists across reboots, network outages, and
  attacks**. Software fallback means edge devices can participate even
  without hardware attestation (trust-ceiling-capped at 0.4).
- **Offline-capable cognition**. Federation is a capability, not a
  requirement. Sprout running Qwen on 8GB Jetson is a first-class
  citizen, not a stripped-down afterthought.
- **Law bundles survive partition**. Agents cache their last-valid
  law; operate autonomously under it; on reconnect, law-state
  reconciliation is a first-class step of federation convergence.
- **Heterogeneous trust fabric**. Model-agnostic — mixed-model fleets
  coordinate via attestations and signed bundles, not shared weights.

---

## 8 Limitations and out-of-scope

We are deliberately explicit about what this submission does *not*
include.

### 8.1 Software-only crypto path

Ed25519 keys held in passphrase-sealed files. Sufficient for
demonstration and internal fleet operation; insufficient for
production compliance claims requiring hardware attestation. The
trust ceiling (0.4 for software anchor) is the architectural
acknowledgment. Upgrading to TPM2 / FIDO2 / Secure Enclave requires
only swapping the seal/unseal implementation in
`src/identity/sealed.py` — manifest shapes, envelope shapes, law
signing, policy evaluation all stay unchanged.

### 8.2 No transport layer

Federation functions take Python objects. In production, envelopes
and bundles would ship over TLS / gRPC / mesh networks. The protocol
shapes are transport-agnostic; serialization is JSON-native.

### 8.3 No real ML in the submission

This is intentional. The submission is *architecture* — the part
that works identically regardless of which Gemma 4 variant is
plugged in. The Gemma 4 integration, tool-use adapters, IRP
plugins, and consciousness-loop stitching are ready to land as the
next module (`src/cognition/`) now that the substrate is proven.

### 8.4 No law language compiler

Rule bodies are hand-authored predicate dicts. A production
deployment would layer a more expressive rule language (Datalog,
Rego, etc.) compiling down to the same interpreter interface. The
fail-closed-on-unknown-keys property would still hold.

### 8.5 No minted-change logic in ATP/ADP

Packets are indivisible. Spending 3 from a 10-unit packet discharges
the whole 10. Production adds "discharge + re-issue smaller" change
logic. Out of scope for hackathon; trivially additive.

### 8.6 No full SAGE 12-step consciousness loop

The cognition loop demo module is in progress. This paper describes
what's been built; the demo module stitches them into the video
arcs (identity boot → law load → R6 action with SNARC → policy →
energy → dream consolidation → federation exchange).

---

## 9 Related work

### 9.1 Within the dp-web4 collective

- **SAGE** (AGPL v3): the full cognition kernel. 12-step consciousness
  loop, IRP plugin framework, raising curriculum, tool use integration.
  This submission is an Apache 2.0 subset.
- **web4** (AGPL v3): the trust-native ontology. Canonical equation,
  R6 framework spec, T3/V3 tensor ontology, LCT-linked-context-token
  spec.
- **ARC-SAGE** (MIT-0): the ARC-AGI-3 harness. 84.9% public-set result
  using Opus 4.6 + membot cartridges. Phase 2 targets the same Gemma 4
  model family. The capability-transfer thesis in ARC-SAGE parallels
  the architecture-transfer thesis here: frontier-model capability
  compiled into structured artifacts a small model can retrieve rather
  than re-derive.

### 9.2 External

The Web4 equation was developed independently of but resonates with
several research threads:

- **Attestation envelopes** — parallels in TPM Remote Attestation,
  FIDO2 Attestation Statement, and Apple's DeviceCheck
- **Law-in-the-loop** — echoes Rego / Open Policy Agent (OPA) with
  the critical addition of cryptographic signing
- **ATP/ADP conservation** — inspired by bio-metabolic analogues;
  mechanically similar to token-bucket rate limiting plus capability-
  based resource accounting
- **SNARC** — related to intrinsic motivation literatures (surprise-
  driven exploration, novelty seeking); distilled to the 5 dims that
  matter for consolidation decisions
- **Federated trust** — parallels in distributed systems literature
  on local-only views (PBFT under partition, CRDTs); the novelty
  here is binding trust accrual to signed R6-shaped interactions

---

## 10 Conclusion

The submission compiles several years of collective work — the SAGE
cognition kernel, the web4 trust-native ontology, the ARC-SAGE harness
— into a 2,720-LoC Apache 2.0 subset that demonstrates the essential
shape: cryptographic identity as substrate, R6 grammar as audit
primitive, signed law as architectural conscience, metabolic accounting
as resource guardrail, salience-driven consolidation as learning loop,
subjective federation as coordination.

All 225 tests pass. Every module is independently usable; composition
is via the R6 grammar plus digest-referenced signed artifacts. The
system runs on a heterogeneous fleet today — from 8GB Jetson Orin Nano
to 122GB workstation — and the trust fabric doesn't care which model
is underneath.

What we are submitting is not a polished product. It is a proof that
the *architectural commitments* are buildable, compact, and composable.
The next step is the cognition loop that binds these modules into a
live agent; the step after is the video and the writeup; the step
after that is production deployment where hardware attestation
replaces the software path and transport layer replaces the in-memory
exchange. The architecture doesn't change.

**The shape that proves compliance is the shape the system already
uses.** Everything else follows.

---

## Appendices

### A Test summary

```
tests/test_r6.py           22 passed
tests/test_identity.py     29 passed
tests/test_trust.py        22 passed
tests/test_law.py          25 passed
tests/test_policy.py       24 passed
tests/test_snarc.py        30 passed
tests/test_energy.py       31 passed
tests/test_dreamcycle.py   20 passed
tests/test_federation.py   22 passed
─────────────────────────────────────
                          225 passed
```

### B File layout

```
gemma4-good-submission/
├── LICENSE                  Apache 2.0
├── NOTICE                   attribution to AGPL upstream
├── README.md                entry point
├── requirements.txt         cryptography>=43, (future: transformers)
├── src/
│   ├── r6/                  action grammar
│   ├── identity/            three-layer identity
│   ├── trust/               T3/V3 evolution
│   ├── law/                 signed law bundles
│   ├── policy/              PolicyGate + Decision
│   ├── snarc/               5D salience
│   ├── energy/              ATP/ADP
│   ├── dreamcycle/          sleep/wake consolidation
│   ├── federation/          peer auth + law convergence
│   └── cognition/           integration loop (in progress)
├── tests/                   one test file per module
└── docs/
    ├── paper.md             this document
    ├── architecture.md      short overview
    ├── narrative.md         5 video arcs
    ├── r6-grammar.md        per-module specs
    ├── identity.md
    ├── trust-tensors.md
    ├── law-in-the-loop.md
    ├── snarc.md
    ├── atp-adp.md
    ├── dreamcycle.md
    └── federation.md
```

### C Canonical references

| Concept | Canonical spec |
|---------|---------------|
| R6 | `web4-standard/core-spec/r6-framework.md` |
| LCT | `web4-standard/core-spec/LCT-linked-context-token.md` |
| T3/V3 | `web4-standard/ontology/t3v3-ontology.ttl` |
| ATP/ADP | `web4-standard/core-spec/atp-adp-cycle.md` |
| Identity | `SAGE/sage/identity/README.md` |
| PolicyGate | `SAGE/sage/docs/SOIA_IRP_MAPPING.md` |
| SNARC | `SAGE/sage/core/sage_consciousness.py` (step 2) |
| Dream bundles | `SAGE/sage/instances/sleep_capability.py` |

---

*End of paper.*
