# ---
# jupyter:
#   jupytext:
#     formats: py:percent,ipynb
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Attested Resilience — Gemma 4 Good Hackathon
#
# **Self-governing AI for constrained environments.**
#
# This notebook runs the full architecture end-to-end: identity, signed law,
# policy evaluation, energy accounting, salience scoring, and dream-cycle
# consolidation. Gemma 4 (E2B, E4B, or 26B-A4B depending on your hardware)
# plugs in through a pluggable `Executor` interface.
#
# **Tracks**: Safety, Global Resilience.
# **Repo**: https://github.com/dp-web4/gemma4-good-submission
# **License**: Apache 2.0
#
# ---

# %% [markdown]
# ## 1. Environment setup
#
# Clone the submission repo and install the (minimal) dependencies.

# %%
# !git clone https://github.com/dp-web4/gemma4-good-submission.git 2>/dev/null || echo "already cloned"
# %cd gemma4-good-submission

# %%
# !pip install --quiet cryptography

# %% [markdown]
# ## 2. Run the test suite
#
# 252 tests cover every module. They all pass. Think of this as proof the
# architecture is buildable and composable — not a slide deck.

# %%
# !pip install --quiet pytest
# !python -m pytest tests/ -q 2>&1 | tail -5

# %% [markdown]
# ## 3. The five design commitments, demonstrated
#
# 1. **Identity precedes action** — three-layer cryptographic identity
# 2. **Actions are audit records** — R6 grammar, same shape for input/
#    output/training
# 3. **Policy is signed law** — LawBundle signed + witnessed + versioned;
#    every decision cites the exact bundle digest
# 4. **Energy is conserved** — ATP/ADP packets, no overdraft by construction
# 5. **Salience drives consolidation** — SNARC-scored ticks export to
#    dream bundles on sleep
#
# The cells below walk through each commitment on a real, wired-up loop.

# %% [markdown]
# ### 3.1 Cold start — identity bootstrap

# %%
import tempfile
from pathlib import Path
from src.identity import IdentityProvider

tmp = Path(tempfile.mkdtemp(prefix="kaggle-demo-"))
alice = IdentityProvider(tmp / "alice")
manifest = alice.bootstrap(name="alice", passphrase="demo-pp", machine="kaggle")
print(f"identity.lct_id         = {manifest.lct_id}")
print(f"identity.fingerprint    = {manifest.public_key_fingerprint}")
print(f"identity.anchor_type    = {manifest.anchor_type}")
print(f"identity.trust_ceiling  = {manifest.trust_ceiling}  "
      f"(software anchor — would be 1.0 with TPM2)")

# %%
# Attestation envelope — a peer can verify alice's identity using only this
envelope = alice.attest(nonce="kaggle-challenge-01")
from src.identity import verify_envelope
print(f"envelope.lct_id         = {envelope.lct_id}")
print(f"envelope.expires_at     = {envelope.expires_at}")
print(f"envelope.verifies       = {verify_envelope(envelope)}")

# %% [markdown]
# ### 3.2 Signed law — legislator + witness + registry

# %%
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import Law, LawBundle, LawRegistry, sign_bundle, add_witness

legislator = SigningContext.from_secret(generate_secret())
witness    = SigningContext.from_secret(generate_secret())

bundle = LawBundle(
    bundle_id="b:kaggle-demo",
    scope="demo",
    version=1,
    laws=[
        Law(law_id="law:permit-act", version=1, scope="demo",
            rule_type="permission", rule={"permit": ["demo", "act"]}),
        Law(law_id="law:cost-cap", version=1, scope="demo",
            rule_type="constraint", rule={"max_cost": 5.0},
            rationale="No single action may cost > 5 energy units."),
    ],
)
sign_bundle(bundle, legislator, "lct:legislator")
add_witness(bundle, witness, "lct:witness:1")

laws = LawRegistry()
laws.required_witnesses = 1
laws.register(bundle)
print(f"bundle.bundle_id  = {bundle.bundle_id}")
print(f"bundle.digest()   = {bundle.digest()[:16]}...")
print(f"legislator_lct    = {bundle.legislator_lct}")
print(f"witnesses         = {len(bundle.witnesses)}")

# %% [markdown]
# ### 3.3 Energy allocation

# %%
from src.energy import EnergyLedger

energy = EnergyLedger()
for _ in range(20):
    energy.issue(amount=1.0, to_lct=manifest.lct_id, from_issuer="lct:mint")
print(f"alice's balance = {energy.balance(manifest.lct_id)}")
print(f"conservation OK = {energy.check_conservation()}")

# %% [markdown]
# ### 3.4 Wire the cognition loop
#
# The loop uses a pluggable `Executor`. Default is `StubExecutor` (deterministic,
# no model). If Ollama is available with a Gemma 4 tag, we use the real adapter.

# %%
from src.cognition import (
    CognitionLoop, StubExecutor, GemmaOllamaExecutor, is_model_available
)
from src.dreamcycle import Consolidator
from src.policy import PolicyGate
from src.snarc import Scorer
from src.trust import TrustLedger

# Try Gemma via Ollama; fall back to the deterministic stub
executor = StubExecutor()
for tag in ("gemma4:e4b", "gemma4:e2b", "gemma3:4b"):
    if is_model_available(tag):
        executor = GemmaOllamaExecutor(model=tag, timeout_s=60.0)
        print(f"Using Gemma via Ollama: {tag}")
        break
else:
    print("No Ollama model available — using StubExecutor")

cons = Consolidator(
    machine="kaggle", instance_lct=manifest.lct_id,
    model=getattr(executor, "model", "stub"),
    session="kaggle-demo", salience_threshold=0.2,
)
loop = CognitionLoop(
    identity=alice,
    role_id="lct:role/demo-worker",
    role_context="kaggle-demo",
    scope="demo",
    laws=laws,
    energy=energy,
    trust=TrustLedger(),
    snarc=Scorer(),
    consolidator=cons,
    gate=PolicyGate(
        evaluator_lct="lct:judge",
        evaluator=SigningContext.from_secret(generate_secret()),
    ),
    executor=executor,
)

# %% [markdown]
# ### 3.5 Run a session of ticks
#
# Each tick goes: observation → R6Action → SNARC → PolicyGate → Decision →
# (if allowed) spend energy → execute → settle → update trust → record.

# %%
observations = [
    ("green block upper-left, red target lower-right",
     "suggest first move toward target", 0.4, 0.6),
    ("same green block, no motion yet",
     "wait one tick — observe", 0.1, 0.0),
    ("red block appeared — unexpected",
     "re-identify movable objects", 0.8, 0.4),
    ("level transition — new layout",
     "restart world model", 0.7, 0.9),
    ("out-of-budget request: explore every tile",
     "exhaustive exploration", 0.0, 0.0),
]

reports = []
for i, (obs, req, arousal, reward) in enumerate(observations):
    cost = 100.0 if "exhaustive" in req else 1.0  # last one will fail the cost cap
    r = loop.tick(
        observation=obs, request_description=req, estimated_cost=cost,
        arousal=arousal, reward=reward,
        acceptance_criteria=["one concrete move"],
    )
    reports.append(r)
    print(f"[tick {i+1}] {r.decision.verdict.value:6s}  "
          f"status={r.action.status.value:10s}  "
          f"energy={r.energy_spent:4.1f}  "
          f"law_digest={r.decision.law_ref.bundle_digest[:12]}... "
          f"| {r.reason}")

# %% [markdown]
# ### 3.6 Inspect one audit bundle in full

# %%
import json
allowed = next(r for r in reports if r.decision.is_allow and r.executed)
print(json.dumps(allowed.to_dict(), indent=2, default=str)[:2000])

# %% [markdown]
# **Notice:**
# - `decision.verdict == "allow"`
# - `decision.law_ref.bundle_digest` exactly matches the LawBundle digest
# - `decision.signature_b64` is non-empty and verifies offline
# - `outcome.quality` and `outcome.value` come from the executor (real or stub)
# - `energy_spent` ties to specific packet IDs that are now SETTLED
#
# This is an **audit bundle** in the literal sense. It's also a labeled
# training instance for future models: `(rules, role, request, reference,
# resource) → (decision, outcome)`.

# %% [markdown]
# ### 3.7 Consolidate — sleep, dream, persist

# %%
dream = cons.consolidate(threshold=0.25)
print(f"bundle.bundle_id        = {dream.bundle_id}")
print(f"bundle.entries kept     = {len(dream)} of {len(reports)} ticks")
print(f"bundle.digest           = {dream.digest()[:16]}...")
print(f"bundle.salience_threshold = {dream.salience_threshold}")
print()
print("high-salience entries retained:")
for e in dream.entries:
    desc = e.action["request"]["description"]
    snarc_summary = ", ".join(f"{k}={v:.2f}"
                              for k, v in e.snarc.items() if k != "tags")
    print(f"  • {desc:40s}  [{snarc_summary}]")

# %%
# Persist + reload — digest must match for loop closure
dream.save(tmp / "dream.json")
from src.dreamcycle import DreamBundle
loaded = DreamBundle.load(tmp / "dream.json")
assert loaded.digest() == dream.digest(), "roundtrip digest mismatch"
print(f"\n✓ saved → loaded → digest matches ({loaded.digest()[:16]}...)")
print(f"  tomorrow's session loads this file as priors.")

# %% [markdown]
# ## 4. Federation — two machines, mutual attestation, law convergence

# %%
from src.federation import (
    PeerRegistry, mutual_auth, LawStateAdvert, diff_law_state, reconcile_law
)

# Spin up a second identity to play the peer
bob = IdentityProvider(tmp / "bob")
bob.bootstrap(name="bob", passphrase="bob-pp", machine="kaggle-peer")

alice_peers = PeerRegistry()
bob_peers = PeerRegistry()
bob_seen, alice_seen = mutual_auth(
    alice, alice_peers, manifest.lct_id,
    bob, bob_peers, bob.load_manifest().lct_id,
)
print(f"after mutual auth:")
print(f"  alice sees {len(alice_peers)} peer(s)  →  {bob_seen.lct_id}")
print(f"  bob   sees {len(bob_peers)} peer(s)  →  {alice_seen.lct_id}")
print(f"  (subjective trust — each agent's view is independent)")

# %%
# Alice gets a tighter v2 law during a "partition"
tighter_laws = [
    Law(law_id="law:permit-act", version=1, scope="demo",
        rule_type="permission", rule={"permit": ["demo", "act"]}),
    Law(law_id="law:cost-cap", version=2, scope="demo",
        rule_type="constraint", rule={"max_cost": 2.0},
        rationale="Tightened post-incident."),
]
v2 = LawBundle(bundle_id="b:kaggle-demo-v2", scope="demo", version=2,
               laws=tighter_laws)
sign_bundle(v2, legislator, "lct:legislator")
add_witness(v2, witness, "lct:witness:1")
laws.register(v2)

# Bob still has v1. Reconcile.
bob_laws = LawRegistry()
bob_laws.required_witnesses = 1
bob_laws.register(bundle)  # v1

a_advert = LawStateAdvert.from_registry(manifest.lct_id, laws)
b_advert = LawStateAdvert.from_registry(bob.load_manifest().lct_id, bob_laws)
delta = diff_law_state(b_advert, a_advert)
print(f"diff (bob vs alice): peer_newer = {delta.peer_newer}")

accepted, rejected = reconcile_law(bob_laws, [laws.active("demo")])
print(f"reconcile: {len(accepted)} accepted, {len(rejected)} rejected")
print(f"bob now has active('demo').version = {bob_laws.active('demo').version}")

# %% [markdown]
# ## 5. What just happened (for the judges)
#
# We ran a complete compliance-auditable AI cognition pipeline end-to-end:
#
# - Two agents bootstrapped with Ed25519 identities
# - A legislator signed a LawBundle; a witness countersigned
# - An agent ran 5 cognition ticks, each producing:
#   - A signed R6Action
#   - A signed Decision with `law_ref.bundle_digest` pointing at the exact
#     law consulted
#   - A SNARC salience score
#   - An Outcome from Gemma 4 (or a deterministic stub)
#   - Energy accounting: ATP packets discharged and settled with V3 values
# - The Consolidator filtered high-salience ticks into a DreamBundle
# - The bundle round-tripped through disk with stable digest
# - Two agents authenticated via attestation exchange
# - One agent reconciled a newer law version from the other — the partition
#   recovery story
#
# Every signed artifact verifies offline. No CA, no central authority, no
# third-party lookup. Bundle digest + signature is sufficient for audit.
#
# **The shape that proves compliance is the shape the system already uses.**

# %% [markdown]
# ## 6. Further reading
#
# - [README](https://github.com/dp-web4/gemma4-good-submission) — entry
# - [docs/paper.md](https://github.com/dp-web4/gemma4-good-submission/blob/main/docs/paper.md)
#   — architecture paper
# - [docs/law-in-the-loop.md](https://github.com/dp-web4/gemma4-good-submission/blob/main/docs/law-in-the-loop.md)
#   — the load-bearing Safety-track concept
# - [demo/run_demo.py](https://github.com/dp-web4/gemma4-good-submission/blob/main/demo/run_demo.py)
#   — runnable 5-arc demo
# - [SAGE](https://github.com/dp-web4/SAGE) (AGPL v3) — full cognition kernel
# - [web4](https://github.com/dp-web4/web4) (AGPL v3) — trust-native ontology
# - [ARC-SAGE](https://github.com/dp-web4/ARC-SAGE) (MIT-0) — 84.9% on
#   ARC-AGI-3 public set, Gemma 4 Phase 2 deployment target
