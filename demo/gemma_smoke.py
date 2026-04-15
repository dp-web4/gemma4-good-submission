#!/usr/bin/env python3
"""
Smoke test: run one cognition tick with a real Gemma 4 model via Ollama.

Usage:
    python -m demo.gemma_smoke                    # uses gemma4:e4b if available,
                                                  # else falls back to gemma4:e2b
    python -m demo.gemma_smoke --model gemma4:e2b

Requires ollama running locally with the model pulled.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from src.cognition import CognitionLoop, GemmaOllamaExecutor, is_model_available
from src.dreamcycle import Consolidator
from src.energy import EnergyLedger
from src.identity import IdentityProvider
from src.identity.signing import SigningContext
from src.identity.sealed import generate_secret
from src.law import Law, LawBundle, LawRegistry, sign_bundle
from src.policy import PolicyGate
from src.snarc import Scorer
from src.trust import TrustLedger


def pick_model(preferred: str | None) -> str:
    candidates = (
        [preferred] if preferred else ["gemma4:e4b", "gemma4:e2b", "gemma3:4b"]
    )
    for name in candidates:
        if is_model_available(name):
            return name
    raise SystemExit(
        f"No usable model available. Tried: {candidates}. "
        "Pull one with `ollama pull gemma4:e4b`."
    )


def run(model: str) -> int:
    print(f"Using model: {model}")
    with tempfile.TemporaryDirectory(prefix="gemma-smoke-") as td:
        tmp = Path(td)

        # Identity
        agent = IdentityProvider(tmp / "agent")
        agent.bootstrap(name="agent", passphrase="demo", machine="legion")

        # Law — permissive for this demo
        legislator = SigningContext.from_secret(generate_secret())
        bundle = LawBundle(
            bundle_id="b:smoke",
            scope="smoke",
            version=1,
            laws=[
                Law(law_id="law:permit", version=1, scope="smoke",
                    rule_type="permission", rule={"permit": ["smoke", "act"]}),
                Law(law_id="law:cost", version=1, scope="smoke",
                    rule_type="constraint", rule={"max_cost": 10.0}),
            ],
        )
        sign_bundle(bundle, legislator, "lct:legislator")
        laws = LawRegistry()
        laws.register(bundle)

        # Energy
        energy = EnergyLedger()
        for _ in range(10):
            energy.issue(amount=1.0,
                         to_lct=agent.load_manifest().lct_id,
                         from_issuer="lct:mint")

        # Wire the loop with the Gemma adapter
        loop = CognitionLoop(
            identity=agent,
            role_id="lct:role/smoke",
            role_context="demo",
            scope="smoke",
            laws=laws,
            energy=energy,
            trust=TrustLedger(),
            snarc=Scorer(),
            consolidator=Consolidator(machine="legion", salience_threshold=0.0),
            gate=PolicyGate(
                evaluator_lct="lct:judge",
                evaluator=SigningContext.from_secret(generate_secret()),
            ),
            executor=GemmaOllamaExecutor(model=model, timeout_s=120.0),
        )

        observations = [
            ("You see a green block in the upper-left and a red target in the "
             "lower-right. What is the most efficient action to take first?",
             "suggest a concrete first move that narrows options"),
            ("The previous action produced a state change. Objects in the grid "
             "have shifted. Re-identify what's movable.",
             "briefly list what to track in the new frame"),
        ]

        for i, (obs, req) in enumerate(observations, start=1):
            print(f"\n--- tick {i} ---")
            t0 = time.perf_counter()
            report = loop.tick(
                observation=obs,
                request_description=req,
                acceptance_criteria=["plan is a single move", "mentions an object"],
                estimated_cost=1.0,
                arousal=0.4, reward=0.5,
            )
            elapsed = time.perf_counter() - t0
            print(f"  verdict       : {report.decision.verdict.value}")
            print(f"  status        : {report.action.status.value}")
            print(f"  elapsed       : {elapsed:.2f}s")
            print(f"  quality       : {report.outcome.quality:.2f}"
                  if report.outcome else "  quality       : —")
            print(f"  v3.composite  : "
                  f"{report.outcome.value.composite():.2f}"
                  if report.outcome else "  v3            : —")
            print(f"  energy_spent  : {report.energy_spent}")
            print(f"  law_ref.digest: {report.decision.law_ref.bundle_digest[:16]}…")
            print(f"  signed        : {report.decision.verify()}")
            if report.outcome and report.outcome.output.get("text"):
                txt = report.outcome.output["text"]
                print(f"  output (head) : {txt[:240].strip()!r}")

    print("\nAll artifacts verified offline. Smoke test complete.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=None, help="Ollama model tag to use")
    args = ap.parse_args()
    return run(pick_model(args.model))


if __name__ == "__main__":
    sys.exit(main())
