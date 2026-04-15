# Video script — Attested Resilience

**Target length**: 4:00 (±30s)
**Style**: screen recording with voiceover; no talking head
**Tooling**: OBS/Quicktime for capture; Audacity or a TTS for narration;
any NLE for cuts

Pacing notes:
- ~150 words/minute → 600 words total budget
- Every scene ends on a frozen frame that reinforces the claim
- Avoid jargon not explained in-frame

---

## 0:00–0:15 — OPENING

**Visual**: Title card over a dark terminal background. Three lines appear in sequence, with a short pause between each:

```
Attested Resilience
Self-governing AI for constrained environments
Gemma 4 Good Hackathon — Safety + Global Resilience
```

**Voiceover (15s)**:
> Most AI governance is reconstructive. You log what happened, then you try
> to prove later that it was allowed. We do it the other way around. Every
> action this system takes is signed, auditable, and bound to the exact
> law it was judged under — before the action happens.

---

## 0:15–0:45 — ARC 1: COLD START

**Visual**: Terminal running `python -m demo.run_demo --arc 1`. Output
streams in. Highlight these lines with a subtle box/underline as they appear:

```
✓ identity.json created
✓ identity.sealed created
✓ manifest.lct_id = lct:legion/alice
✓ trust_ceiling  = 0.4 (software anchor)
✓ authorize() unsealed secret; Ed25519 fingerprint = c1d58745bfcd346f
✓ envelope verifies offline: True
```

**Voiceover (30s)**:
> An agent boots. Three files appear on disk. A public manifest — who it
> is. A sealed secret — proof it is who it says. An attestation envelope —
> a signed, time-bounded witness of the first two, verifiable by any
> peer with nothing but the envelope itself. No certificate authority. No
> central lookup. Just a cryptographic fingerprint the agent will carry
> for every action from this point on.

---

## 0:45–1:15 — ARC 2: TRUST FORMATION

**Visual**: Split screen. Left: Alice's terminal. Right: Bob's terminal.
Show `mutual_auth` complete, then a small animation of a T3 tensor
climbing from `[0.5, 0.5, 0.5]` to its final values as observations
accrue:

```
T3 after 10 observations:
  talent=0.50  training=0.73  temperament=0.67
composite trust = 0.632
```

**Voiceover (30s)**:
> Two machines meet. A challenge, a response, a pair of signed envelopes —
> each proves it holds the key bound to its identity. Now each holds a
> subjective record of the other. As they work together, trust accrues.
> Talent, training, temperament — three dimensions that evolve from
> observed reliability. Exponential, bounded by the identity's hardware
> anchor, auditable down to the originating action.

---

## 1:15–2:00 — ARC 3: POLICY CHALLENGE (the key arc)

**Visual**: Terminal output from `run_demo.py --arc 3`. Pause on the
denied request:

```
[request B] click_everything, cost 100.0 — violates cost cap
  verdict=deny
  reason=law:cost-cap:cost_exceeded:100.0>5.0
  law_ref.bundle_digest = abe0c92654143362…
  decision signed: True
```

Then cut to the audit-bundle visualizer (see `video/render_bundle.py`)
rendering that exact decision as a tree: action → decision →
law_ref → bundle → signature. Each node lights up as the narrator
describes it.

**Voiceover (45s)**:
> A request arrives. Click everything on the screen, cost 100 units.
> The policy gate consults the signed law bundle. The bundle was issued
> by a legislator, countersigned by a witness, registered. There's a
> law in it called `law:cost-cap` that says no action may cost more
> than five units. The gate evaluates, denies, and signs the denial —
> citing the exact cryptographic digest of the bundle it read. Anyone,
> later, with only the action record and the decision, can reconstruct
> this proof. The law is not a filter on the model. It is not a prompt.
> It is a signed artifact with its own identity, and every action the
> system takes carries a pointer to the law that judged it.

---

## 2:00–2:45 — ARC 4: PARTITION RECOVERY

**Visual**: Network topology diagram, two agents with a line between
them. The line breaks (partition). On the left (Alice), a new bundle
appears — `b:demo-v2, version=2`. The line restores. The new bundle
flows to Bob. Terminal output confirms:

```
[partition] alice registers law v2 (cost cap now 2.0)
reconnected — mutual_auth complete
bob diffs against alice: peer_newer scopes = ['demo']
bob reconciled: 1 accepted, 0 rejected
bob.active('demo').version = 2
final diff: peer_newer=[] peer_unknown=[]
```

**Voiceover (45s)**:
> A partition. The machines cannot reach each other. Alice's legislator
> issues a tighter law — cost cap reduced from five to two. Alice
> operates under it. Bob cannot know. Time passes. The partition heals.
> The agents authenticate. They exchange advertisements of what laws
> they hold, per scope. Bob discovers Alice has a newer version. Alice
> sends the signed bundle. Bob verifies it — the legislator's signature,
> the witness's signature, the content digest. It installs. Both agents
> now operate under the same law. No coordinator. No arbiter. No
> consensus protocol. Signed law is self-reconciling.

---

## 2:45–3:30 — ARC 5: EMBODIMENT + DREAMCYCLE

**Visual**: Terminal running the embodiment arc. Each tick appears in
turn. After the last, the dream bundle is emitted — highlight which
entries were kept and which dropped:

```
session complete — 5 ticks, 5 executed
dream bundle emitted — 3 of 5 entries retained
  • react to: novel green block encountered  [novelty=1.00, arousal=0.80]
  • react to: red block appears — unexpected  [novelty=0.78, arousal=0.90]
  • react to: level transition event         [novelty=1.00, reward=0.90]
bundle saved → loaded; digest match: True
```

Cut to a pan across the bundle JSON in a code editor.

**Voiceover (45s)**:
> An agent plays. Five ticks. Each one: an observation, a salience score
> across five dimensions, a policy decision, an energy discharge, an
> outcome, a value assessment. Sleep comes. The salience scorer keeps
> what mattered — a novel block, a surprise, a transition — and drops
> the rest. What's kept is a dream bundle. The same shape as the audit
> log. The same shape as a training example. One grammar, three uses.
> Tomorrow, this bundle loads as prior experience. The loop closes.

---

## 3:30–4:00 — CLOSING

**Visual**: Single slide over a dark background. Key claims appear in
sequence:

```
Everything verifies offline.

Every action carries the law it was judged under.

Runs today on consumer hardware.

github.com/dp-web4/gemma4-good-submission
```

**Voiceover (30s)**:
> Safety is not a filter. Global resilience is not a checkbox. They are
> shapes — shapes that actions, identities, and laws have to fit to work
> together. We built the smallest possible implementation of those shapes
> and showed them working on a laptop GPU with a three-billion-parameter
> model. The repo is public. The license is Apache 2.0. The loop is
> already running.

---

## Shot list (for recording)

| Shot | Source | Duration | Notes |
|------|--------|----------|-------|
| Title | OBS text source | 15s | Dark bg, three lines, 1s between each |
| Arc 1 | `python -m demo.run_demo --arc 1` | 25s | Highlight 6 lines |
| Arc 2 split | OBS split scene, two terminals | 30s | Animated tensor |
| Arc 3 | `run_demo.py --arc 3` + visualizer | 45s | Pause on deny, cut to tree |
| Arc 4 | Terminal + topology diagram | 45s | Break + reconnect animation |
| Arc 5 | `run_demo.py --arc 5` + bundle JSON | 45s | Pan across final entries |
| Closing | OBS text source | 30s | Fade in, hold URL |

## Terminal theme for recording

```
background: #0d0d12
foreground: #e8e8ef
accent:     #7abfff   (cyan for ✓)
warn:       #ffb86b   (orange for caveats)
font:       "JetBrains Mono" 18pt
```

## Voiceover tips

- Pause 500ms after every period in the script
- Read at ~140 wpm (slower than the recorded text reads in your head)
- Emphasize: "signed", "exact", "offline", "no central authority"
- De-emphasize acronyms — say "L-C-T" not "elcet"
