# Federation — peer authentication and law-state convergence

Federation is what happens when an agent meets another agent. There is
no central authority, no global registry, no required quorum. Each
agent's view of its peers is local, and that's a feature.

This module implements the *shape* of federation — the protocols. The
transport layer (TLS, gRPC, message bus) is left to deployment. The
protocols here work the same regardless of how bytes get from A to B.

## What federation gives you

1. **Peer authentication** — challenge-response over signed attestation
   envelopes. A peer who passes this exchange has cryptographically
   demonstrated control of the private key bound to their LCT.
2. **Law-state convergence** — peers exchange per-scope law-bundle
   versions; higher-version supersedes; agents reconcile to the
   highest-version verified bundle they can reach.
3. **Trust accrual via interaction** — every exchange is an
   `ObservationRecord` candidate for the trust ledger; T3/V3 evolve
   from observed reliability across federated work.

## Peer authentication

```
Verifier (Bob)                          Prover (Alice)
   │                                       │
   │  AuthChallenge.fresh(bob_lct)         │
   ├───────── nonce ─────────────────────► │
   │                                       │
   │                          respond_to_challenge(alice, challenge)
   │                          → AttestationEnvelope (signed, fresh, embeds nonce)
   │                                       │
   │ ◄────── signed envelope ───────────── │
   │                                       │
   verify_response(bob_registry, challenge, envelope)
   → if signature valid AND nonce matches AND envelope fresh:
        Peer added to bob_registry
```

The envelope is **self-contained** — the verifier needs only the
envelope itself (it carries the prover's public key and signature) plus
the challenge it issued. No CA, no lookup, no third party.

`mutual_auth(alice, alice_reg, alice_lct, bob, bob_reg, bob_lct)` runs
both sides in one call. After it returns, `alice_reg.known(bob_lct)`
and `bob_reg.known(alice_lct)` are both true.

## Replay defense

The verifier issues a fresh nonce per challenge. The envelope embeds
the nonce. `PeerRegistry.observe()` rejects envelopes whose nonce
doesn't match the expected challenge. A captured envelope can be
replayed against any verifier who *didn't issue that nonce* — and they
will reject it.

This is the same pattern as TLS handshake nonces. The point isn't
secrecy — it's freshness.

## Law-state convergence

Each agent has a `LawRegistry` of currently-active law bundles per
scope. When two agents meet, they advertise their state and reconcile.

```python
from src.federation import LawStateAdvert, diff_law_state, reconcile_law

# alice and bob each build an advert from their local registry
a_advert = LawStateAdvert.from_registry(alice_lct, alice_law_registry)
b_advert = LawStateAdvert.from_registry(bob_lct, bob_law_registry)

# bob diffs against alice — discovers which scopes alice has newer in
delta = diff_law_state(b_advert, a_advert)
# delta.peer_newer is the list of scopes where alice should ship her bundle

# alice ships her newer bundles, bob reconciles
incoming = [alice_law_registry.active(scope) for scope in delta.peer_newer]
accepted, rejected = reconcile_law(bob_law_registry, incoming)
```

`reconcile_law` re-verifies every incoming bundle against the local
registry's witness requirements — a peer cannot push a bundle that
fails local verification policy.

After reconciliation, both agents have the same active version per
shared scope. Bundles bob already had at older versions remain in his
history; the new ones become active.

## Bundles are immutable

A signed bundle is signed forever. The registry's supersession chain
is tracked in an internal map keyed by bundle ids — the bundles
themselves are never mutated. This is essential for federation: a
bundle that travels from alice to bob to charlie must verify
identically at every hop. Mutation would break that.

## Subjective trust

Two peers can hold **different records about each other**. Alice's
view of Bob is built from her observations; Bob's view of Alice is
built from his. Different interaction counts, different trust
evolutions, different attestation histories.

This is correct — federated trust is subjective. There is no global
truth. There is only what each agent has observed. Disagreement is
not an error to be reconciled; it's the natural state of a
non-totalitarian network.

The shared invariants (signed bundles verify the same everywhere,
attestation envelopes are deterministic) provide the cryptographic
floor. Everything above that floor is local.

## Partition recovery

```
T0:   alice, bob both have law v1 for scope "demo"
T1:   network partition
T2:   alice's legislator issues v2; alice registers it; alice operates
      under v2
T3:   bob continues under v1 (he has no other source of truth)
T4:   partition heals
T5:   mutual_auth(alice, bob)
T6:   adverts exchanged
      → bob discovers alice has v2 for "demo"
T7:   alice ships v2 bundle to bob
      → bob's reconcile_law accepts (v2 > v1, signature verifies)
T8:   bob's active("demo") is now v2
T9:   any pending work bob queued under v1 may need re-evaluation
      under v2 — caller's responsibility
```

This is **principled partition tolerance**, not ad-hoc reconnect
logic. The same machinery that allows two agents to start fresh
allows them to recover from arbitrary downtime.

## What this isn't

- **Not a transport layer.** Functions take Python objects;
  serialize/deserialize at your network boundary.
- **Not a discovery service.** You need to know how to reach a peer
  before authenticating them. mDNS, DHT, hardcoded list — all valid;
  none implemented here.
- **Not a global consensus protocol.** Federated subjectivity is the
  point. If you need global truth on top of federation, layer it.

## Alignment

Clean-room implementation of the SAGE federation primitives
(`PeerMonitor`, `PeerClient`, `PeerTrustTracker` in
`SAGE/sage/gateway/`). The submission preserves the protocol shapes
and the local-knowledge model. A production deployment adds
discovery, transport (TLS), gossip, and the trust-ledger updates that
fold federation outcomes back into T3/V3 evolution.
