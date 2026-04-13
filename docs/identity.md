# Identity — three-layer, hardware-optional

An agent's identity is the substrate for every R6 action's `initiator_id`.
Without it, audit claims are decorative. With it, any party holding the public
key can verify that this agent — not a replay, not an impostor — signed this
action at this time.

## Three layers

| Layer | File | Contents | Secret? |
|-------|------|----------|---------|
| A | `identity.json` | Name, LCT id, public key fingerprint, anchor type | No |
| B | `identity.sealed` | Encrypted root secret (passphrase- or hardware-sealed) | Yes |
| C | `identity.attest.json` | Last signed attestation envelope | No |

**Why three?** Separation of concerns makes the security model legible. The
public manifest (A) names you. The sealed secret (B) proves you are you. The
attestation envelope (C) is a portable, time-bounded, replay-resistant proof
that peers can consume without touching your secret.

## Trust ceilings

The manifest's `anchor_type` determines how much trust the identity can
accrue. No amount of successful behavior raises trust above the ceiling.

| Anchor | Ceiling | When |
|--------|---------|------|
| `tpm2` | 1.0 | Full hardware attestation with platform state |
| `fido2` | 0.9 | YubiKey / platform authenticator |
| `tpm2_no_pcr` | 0.85 | TPM without platform state verification |
| `secure_enclave` | 0.85 | Apple SE |
| `software` | 0.4 | Dev / hackathon path — no hardware binding |

This submission ships the `software` path. Production deployments binding to
hardware upgrade the same manifest in place.

## Lifecycle

```python
from src.identity import IdentityProvider

# ---- first run: bootstrap ----
provider = IdentityProvider("./instance/nomad")
manifest = provider.bootstrap(
    name="nomad-gemma4-e4b",
    passphrase=os.environ["AGENT_PASSPHRASE"],
    machine="nomad",
    model="gemma4-e4b",
)
# Now identity.json and identity.sealed exist on disk.

# ---- every process start: authorize ----
ctx = provider.authorize(os.environ["AGENT_PASSPHRASE"])
# `ctx` holds the in-memory Ed25519 keypair. Never written to disk.

# ---- when challenged by a peer ----
envelope = provider.attest(nonce=peer_challenge)
# Signed with ctx. Verifiable by peer using ONLY the envelope itself.
```

## Peer verification

An envelope is self-contained: it carries the public key, the signed payload,
and the signature. A peer runs:

```python
from src.identity import verify_envelope

if verify_envelope(received):
    assert received.nonce == my_challenge  # replay protection
    assert received.is_fresh()              # time bound
    # Accept the peer as who they claim to be.
```

The peer didn't need to contact an authority, a CA, or the original agent's
filesystem. Envelopes are portable audit artifacts.

## What's software-mode good for

- Development
- Hackathon demos
- Federated environments where trust is built from *observed behavior*, not
  from hardware assertions
- Edge deployments where hardware anchors don't exist yet (the trust ceiling
  caps what can be delegated, but the identity still works)

## What it's not good for (yet)

- Compliance claims requiring hardware attestation (EU AI Act Art. 15 etc.)
- Adversarial environments where an attacker has filesystem access
- Any production claim where `trust_ceiling > 0.4` is required

Those need the hardware-bound path — same manifest, real sealing. Out of
scope for this submission.

## Alignment

This is a clean-room implementation derived from the spec documented in
`SAGE/sage/identity/README.md`. The AGPL upstream provides the full
implementation including the in-progress hardware anchors. This Apache 2.0
subset preserves the three-layer shape and the public API.

Canonical reference: `web4-standard/core-spec/LCT-linked-context-token.md`
