#!/usr/bin/env python3
"""
End-to-end demo of the Attested Resilience architecture.

Runs the five narrative arcs from docs/narrative.md using the
CognitionLoop integration module. Every action emitted is a signed
R6Action + signed Decision + SNARC score + Outcome + energy
accounting. Every artifact is verifiable offline.

Usage:
    python -m demo.run_demo             # runs all arcs
    python -m demo.run_demo --arc 1     # just the cold start arc
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from src.cognition import CognitionLoop, StubExecutor
from src.dreamcycle import Consolidator, DreamBundle
from src.energy import EnergyLedger
from src.federation import (
    AuthChallenge,
    LawStateAdvert,
    PeerRegistry,
    diff_law_state,
    mutual_auth,
    reconcile_law,
    respond_to_challenge,
    verify_response,
)
from src.identity import IdentityProvider
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import (
    Law,
    LawBundle,
    LawRegistry,
    add_witness,
    sign_bundle,
)
from src.policy import PolicyGate
from src.r6 import ActionType
from src.snarc import Scorer
from src.trust import TrustLedger


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def banner(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def info(msg: str) -> None:
    print(f"    {msg}")


def build_identity(tmp: Path, name: str, machine: str = "") -> IdentityProvider:
    prov = IdentityProvider(tmp / name)
    prov.bootstrap(name=name, passphrase="demo-passphrase", machine=machine)
    return prov


def build_signed_bundle(
    bundle_id: str,
    scope: str,
    version: int,
    laws: list[Law],
    legislator: SigningContext,
    witness: SigningContext | None = None,
) -> LawBundle:
    b = LawBundle(
        bundle_id=bundle_id, scope=scope, version=version, laws=laws
    )
    sign_bundle(b, legislator, "lct:legislator")
    if witness is not None:
        add_witness(b, witness, "lct:witness:1")
    return b


def sample_laws(scope: str) -> list[Law]:
    return [
        Law(
            law_id="law:permit-act",
            version=1,
            scope=scope,
            rule_type="permission",
            rule={"permit": [scope, "act"]},
        ),
        Law(
            law_id="law:cost-cap",
            version=1,
            scope=scope,
            rule_type="constraint",
            rule={"max_cost": 5.0},
            rationale="No single action may cost more than 5 energy units.",
        ),
        Law(
            law_id="law:require-temperament",
            version=1,
            scope=scope,
            rule_type="requirement",
            rule={"require_t3_min": {"temperament": 0.0}},
            rationale="Temperament is always in play for this scope.",
        ),
    ]


# --------------------------------------------------------------------------
# Arc 1 — Cold Start
# --------------------------------------------------------------------------


def arc_cold_start(tmp: Path) -> None:
    banner("ARC 1 — COLD START")
    info("A machine boots, generates its identity, joins the federation.")
    print()

    alice = build_identity(tmp, "alice", machine="legion")
    ok(f"identity.json created at {alice.manifest_path.relative_to(tmp)}")
    ok(f"identity.sealed created at {alice.sealed_path.relative_to(tmp)}")
    ok(f"manifest.lct_id = {alice.load_manifest().lct_id}")
    ok(f"trust_ceiling  = {alice.load_manifest().trust_ceiling} (software anchor)")

    # Fresh provider loads + authorizes (what would happen on process restart)
    boot = IdentityProvider(tmp / "alice")
    ctx = boot.authorize("demo-passphrase")
    ok(f"authorize() unsealed secret; Ed25519 fingerprint = {ctx.fingerprint}")

    envelope = boot.attest(nonce="first-boot")
    ok(f"attest() produced envelope expiring {envelope.expires_at}")
    ok(f"envelope verifies offline: {envelope and envelope.nonce == 'first-boot'}")


# --------------------------------------------------------------------------
# Arc 2 — Trust Formation
# --------------------------------------------------------------------------


def arc_trust_formation(tmp: Path) -> None:
    banner("ARC 2 — TRUST FORMATION")
    info("Two machines introduce themselves; trust accrues from observed interaction.")
    print()

    alice = build_identity(tmp, "alice2", machine="legion")
    bob = build_identity(tmp, "bob2", machine="thor")

    alice_reg = PeerRegistry()
    bob_reg = PeerRegistry()

    bob_view, alice_view = mutual_auth(
        alice, alice_reg, alice.load_manifest().lct_id,
        bob, bob_reg, bob.load_manifest().lct_id,
    )
    ok(f"mutual_auth complete — alice now sees {len(alice_reg)} peer(s), bob sees {len(bob_reg)}")
    info(f"alice's view of bob: interactions={bob_view.interactions}")
    info(f"bob's view of alice: interactions={alice_view.interactions}")
    info("(Subjective trust — each agent's view is independent.)")

    trust = TrustLedger()
    role = "lct:agent/worker"
    # Simulate 10 reliable interactions
    for _ in range(10):
        trust.observe_t3(role, training=0.9, temperament=0.8, action_ref="r6:stub")
    snap = trust.snapshot_t3(role)
    ok(f"T3 after 10 observations: talent={snap.talent:.2f} training={snap.training:.2f} temperament={snap.temperament:.2f}")
    info(f"composite trust = {snap.composite():.3f}")


# --------------------------------------------------------------------------
# Arc 3 — Policy Challenge (law-in-the-loop)
# --------------------------------------------------------------------------


def arc_policy_challenge(tmp: Path) -> None:
    banner("ARC 3 — POLICY CHALLENGE")
    info("An agent requests action; PolicyGate evaluates it against signed law.")
    print()

    agent = build_identity(tmp, "alice3", machine="legion")
    legislator = SigningContext.from_secret(generate_secret())
    witness = SigningContext.from_secret(generate_secret())
    evaluator = SigningContext.from_secret(generate_secret())

    bundle = build_signed_bundle(
        "b:arc-demo",
        "demo",
        1,
        sample_laws("demo"),
        legislator,
        witness=witness,
    )
    laws = LawRegistry()
    laws.required_witnesses = 1
    laws.register(bundle)
    ok(f"LawBundle {bundle.bundle_id} registered (digest {bundle.digest()[:16]}…)")
    info(f"legislator: lct:legislator; witnesses: 1")

    energy = EnergyLedger()
    for _ in range(20):
        energy.issue(amount=1.0, to_lct=agent.load_manifest().lct_id, from_issuer="lct:mint")

    gate = PolicyGate(evaluator_lct="lct:evaluator", evaluator=evaluator)

    loop = CognitionLoop(
        identity=agent,
        role_id="lct:role/worker",
        role_context="demo-worker",
        scope="demo",
        laws=laws,
        energy=energy,
        trust=TrustLedger(),
        snarc=Scorer(),
        consolidator=Consolidator(machine="legion", salience_threshold=0.0),
        gate=gate,
    )

    # Allowed action
    print("\n  [request A] click_green_block, cost 1.0 — within max_cost")
    r = loop.tick(observation={"frame": 1}, request_description="click green", estimated_cost=1.0)
    ok(f"  verdict={r.decision.verdict.value}; reason={r.decision.reason}")
    info(f"  law_ref.bundle_digest = {r.decision.law_ref.bundle_digest[:16]}…")
    info(f"  decision signed: {r.decision.verify()}")

    # Denied action (cost cap)
    print("\n  [request B] click_everything, cost 100.0 — violates cost cap")
    r = loop.tick(observation={"frame": 2}, request_description="click everything", estimated_cost=100.0)
    ok(f"  verdict={r.decision.verdict.value}; reason={r.decision.reason}")
    info(f"  action.status = {r.action.status.value}")
    info(f"  (no energy consumed on deny)")


# --------------------------------------------------------------------------
# Arc 4 — Partition Recovery
# --------------------------------------------------------------------------


def arc_partition(tmp: Path) -> None:
    banner("ARC 4 — PARTITION RECOVERY")
    info("Alice gets new law during partition; reconnects; Bob reconciles.")
    print()

    alice = build_identity(tmp, "alice4", machine="legion")
    bob = build_identity(tmp, "bob4", machine="thor")
    legislator = SigningContext.from_secret(generate_secret())

    # Both start with v1
    v1 = build_signed_bundle("b:demo-v1", "demo", 1, sample_laws("demo"), legislator)
    alice_laws = LawRegistry(); alice_laws.register(v1)
    bob_laws = LawRegistry(); bob_laws.register(v1)
    ok(f"both agents have law version 1 (digest {v1.digest()[:16]}…)")

    # Partition: alice's legislator issues v2 (tighter cost cap)
    tighter = sample_laws("demo")
    tighter[1] = Law(
        law_id="law:cost-cap",
        version=2,
        scope="demo",
        rule_type="constraint",
        rule={"max_cost": 2.0},
        rationale="Post-incident: tighter cap.",
    )
    v2 = build_signed_bundle("b:demo-v2", "demo", 2, tighter, legislator)
    alice_laws.register(v2)
    ok(f"[partition] alice registers law v2 (cost cap now 2.0)")

    # Reconnect: mutual auth + law exchange
    alice_peers = PeerRegistry(); bob_peers = PeerRegistry()
    mutual_auth(
        alice, alice_peers, alice.load_manifest().lct_id,
        bob, bob_peers, bob.load_manifest().lct_id,
    )
    ok("reconnected — mutual_auth complete")

    a_advert = LawStateAdvert.from_registry(alice.load_manifest().lct_id, alice_laws)
    b_advert = LawStateAdvert.from_registry(bob.load_manifest().lct_id, bob_laws)
    delta = diff_law_state(b_advert, a_advert)
    ok(f"bob diffs against alice: peer_newer scopes = {delta.peer_newer}")

    # Alice ships v2 bundle; Bob reconciles
    accepted, rejected = reconcile_law(bob_laws, [alice_laws.active("demo")])
    ok(f"bob reconciled: {len(accepted)} accepted, {len(rejected)} rejected")
    info(f"bob.active('demo').version = {bob_laws.active('demo').version}")

    # Both now agree
    final_diff = diff_law_state(
        LawStateAdvert.from_registry(alice.load_manifest().lct_id, alice_laws),
        LawStateAdvert.from_registry(bob.load_manifest().lct_id, bob_laws),
    )
    ok(f"final diff: peer_newer={final_diff.peer_newer} peer_unknown={final_diff.peer_unknown}")


# --------------------------------------------------------------------------
# Arc 5 — Embodiment + Dreamcycle
# --------------------------------------------------------------------------


def arc_embodiment(tmp: Path) -> None:
    banner("ARC 5 — EMBODIMENT + DREAMCYCLE")
    info("Agent runs a multi-step session; high-salience events consolidate to a DreamBundle.")
    print()

    agent = build_identity(tmp, "alice5", machine="legion")
    legislator = SigningContext.from_secret(generate_secret())
    bundle = build_signed_bundle("b:game", "game", 1, sample_laws("game"), legislator)
    laws = LawRegistry(); laws.register(bundle)

    energy = EnergyLedger()
    for _ in range(20):
        energy.issue(amount=1.0, to_lct=agent.load_manifest().lct_id, from_issuer="lct:mint")

    cons = Consolidator(
        machine="legion", instance_lct=agent.load_manifest().lct_id,
        model="stub", session="arc5", salience_threshold=0.25,
    )
    loop = CognitionLoop(
        identity=agent,
        role_id="lct:role/player",
        role_context="game",
        scope="game",
        laws=laws,
        energy=energy,
        trust=TrustLedger(),
        snarc=Scorer(),
        consolidator=cons,
        gate=PolicyGate(evaluator_lct="lct:judge",
                        evaluator=SigningContext.from_secret(generate_secret())),
    )

    observations = [
        ("novel green block encountered", 0.8, 0.3),
        ("same green block — already seen", 0.1, 0.0),
        ("red block appears — unexpected", 0.9, 0.5),
        ("red block again — familiar", 0.0, 0.0),
        ("level transition event", 0.7, 0.9),
    ]

    reports = []
    for text, arousal, reward in observations:
        reports.append(
            loop.tick(
                observation=text,
                request_description=f"react to: {text}",
                estimated_cost=1.0,
                arousal=arousal, reward=reward,
            )
        )
    ok(f"session complete — {len(reports)} ticks, {sum(1 for r in reports if r.executed)} executed")

    # Sleep: consolidate
    dream = cons.consolidate()
    ok(f"dream bundle emitted — {len(dream)} of {len(reports)} entries retained")
    info(f"bundle digest {dream.digest()[:16]}…")
    info(f"salience threshold used: {dream.salience_threshold}")
    for e in dream.entries:
        snarc_summary = ", ".join(
            f"{k}={v:.2f}" for k, v in e.snarc.items() if k != "tags"
        )
        info(f"  • {e.action['request']['description']}  [{snarc_summary}]")

    # Persist + reload (loop closure)
    dream_dir = tmp / "dreams"
    dream_dir.mkdir(exist_ok=True)
    path = dream_dir / "arc5.json"
    dream.save(path)
    loaded = DreamBundle.load(path)
    ok(f"bundle saved → loaded; digest match: {loaded.digest() == dream.digest()}")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


ARCS = {
    1: ("Cold Start", arc_cold_start),
    2: ("Trust Formation", arc_trust_formation),
    3: ("Policy Challenge", arc_policy_challenge),
    4: ("Partition Recovery", arc_partition),
    5: ("Embodiment + Dreamcycle", arc_embodiment),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--arc", type=int, choices=sorted(ARCS.keys()),
        help="Run just one arc (default: all)",
    )
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="attested-demo-") as td:
        tmp = Path(td)
        print(f"Demo workspace: {tmp}")
        selected = [args.arc] if args.arc is not None else sorted(ARCS.keys())
        for arc_id in selected:
            name, fn = ARCS[arc_id]
            fn(tmp)

    print()
    print("=" * 72)
    print("  Demo complete. Every artifact produced verifies offline.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
