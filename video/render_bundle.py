#!/usr/bin/env python3
"""
Render an audit bundle (R6Action + Decision + LawBundle) as a standalone
HTML page suitable for screen recording. Dark theme, big type, tree
layout that lights up as the viewer scrolls.

Usage:
    python -m video.render_bundle               # uses a fresh demo run
    python -m video.render_bundle --out out.html

The output HTML is fully self-contained (inline CSS, no external deps).
Open it in a browser and scroll, or pipe through a browser screen
recorder for the arc 3 shot.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.cognition import CognitionLoop, StubExecutor
from src.dreamcycle import Consolidator
from src.energy import EnergyLedger
from src.identity import IdentityProvider
from src.identity.sealed import generate_secret
from src.identity.signing import SigningContext
from src.law import Law, LawBundle, LawRegistry, add_witness, sign_bundle
from src.policy import PolicyGate
from src.r6 import ActionType
from src.snarc import Scorer
from src.trust import TrustLedger


# --------------------------------------------------------------------------
# Generate a fresh denied-then-allowed pair (arc 3 shape)
# --------------------------------------------------------------------------


def gen_arc3_bundle() -> dict[str, Any]:
    """Run a mini arc-3 scenario and return:
        {allowed: TickReport.to_dict(), denied: TickReport.to_dict(),
         bundle: LawBundle.to_dict(), bundle_digest: str}"""
    tmp = Path(tempfile.mkdtemp(prefix="render-"))
    agent = IdentityProvider(tmp / "agent")
    agent.bootstrap(name="agent", passphrase="pp", machine="legion")

    legislator = SigningContext.from_secret(generate_secret())
    witness = SigningContext.from_secret(generate_secret())
    evaluator = SigningContext.from_secret(generate_secret())

    bundle = LawBundle(
        bundle_id="b:arc3-demo",
        scope="demo",
        version=1,
        laws=[
            Law(law_id="law:permit-act", version=1, scope="demo",
                rule_type="permission", rule={"permit": ["demo", "act"]}),
            Law(law_id="law:cost-cap", version=1, scope="demo",
                rule_type="constraint", rule={"max_cost": 5.0},
                rationale="No single action may cost more than 5 energy units."),
        ],
    )
    sign_bundle(bundle, legislator, "lct:legislator")
    add_witness(bundle, witness, "lct:witness:1")
    laws = LawRegistry()
    laws.required_witnesses = 1
    laws.register(bundle)

    energy = EnergyLedger()
    for _ in range(20):
        energy.issue(amount=1.0, to_lct=agent.load_manifest().lct_id, from_issuer="lct:mint")

    loop = CognitionLoop(
        identity=agent, role_id="lct:role/worker", role_context="demo",
        scope="demo", laws=laws, energy=energy,
        trust=TrustLedger(), snarc=Scorer(),
        consolidator=Consolidator(salience_threshold=0.0),
        gate=PolicyGate(evaluator_lct="lct:evaluator", evaluator=evaluator),
        executor=StubExecutor(),
    )

    allowed = loop.tick(
        observation={"frame": 1, "objects": ["green_block"]},
        request_description="click green block",
        estimated_cost=1.0,
    )
    denied = loop.tick(
        observation={"frame": 2, "objects": ["green_block", "red_target"]},
        request_description="click everything — exhaustive sweep",
        estimated_cost=100.0,
    )
    return {
        "allowed": allowed.to_dict(),
        "denied": denied.to_dict(),
        "bundle": bundle.to_dict(),
        "bundle_digest": bundle.digest(),
        "agent_lct": agent.load_manifest().lct_id,
    }


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------


CSS = """
body {
    background: #0d0d12;
    color: #e8e8ef;
    font-family: "JetBrains Mono", "Menlo", "Consolas", monospace;
    font-size: 17px;
    line-height: 1.55;
    margin: 0;
    padding: 48px 64px 120px;
}
h1 { color: #ffffff; font-size: 28px; margin: 0 0 28px; }
h2 { color: #ffffff; font-size: 20px; margin: 56px 0 16px;
     border-bottom: 1px solid #24242e; padding-bottom: 6px; }
h3 { color: #9aa0b3; font-size: 15px; letter-spacing: 0.06em;
     text-transform: uppercase; margin: 24px 0 8px; }
.verdict-allow { color: #8be08b; }
.verdict-deny  { color: #ff6b6b; }
.tag { color: #7abfff; }
.k   { color: #a28bff; }
.v   { color: #e8e8ef; }
.dim { color: #6c6c7a; }
.digest {
    color: #8be08b;
    background: rgba(122, 191, 255, 0.08);
    padding: 1px 6px;
    border-radius: 3px;
}
.box {
    background: #15151d;
    border: 1px solid #24242e;
    border-radius: 6px;
    padding: 14px 18px;
    margin: 10px 0;
}
.box.deny { border-left: 3px solid #ff6b6b; }
.box.allow { border-left: 3px solid #8be08b; }
.box.law { border-left: 3px solid #7abfff; }
.arrow { color: #6c6c7a; padding: 0 12px; }
.tree   { margin: 12px 0 0 20px; border-left: 1px dashed #24242e;
          padding-left: 22px; }
pre {
    background: #15151d;
    border: 1px solid #24242e;
    border-radius: 4px;
    padding: 12px 16px;
    overflow-x: auto;
    font-size: 14px;
}
.muted { color: #6c6c7a; }
"""


def _safe(x: Any) -> str:
    return html.escape(json.dumps(x, default=str))


def render(data: dict[str, Any]) -> str:
    a = data["allowed"]
    d = data["denied"]
    b = data["bundle"]
    dig = data["bundle_digest"]

    def render_decision(dec: dict, tick: dict, klass: str) -> str:
        verdict = dec["verdict"]
        verdict_cls = "verdict-allow" if verdict == "allow" else "verdict-deny"
        rows = [
            f'<div class="box {klass}">',
            f'  <h3>decision</h3>',
            f'  <div><span class="k">verdict</span>: '
            f'<span class="{verdict_cls}">{verdict}</span></div>',
            f'  <div><span class="k">reason</span>: <span class="v">{html.escape(dec["reason"])}</span></div>',
            f'  <div><span class="k">evaluated_at</span>: <span class="dim">{dec["evaluated_at"]}</span></div>',
            f'  <div><span class="k">evaluator_lct</span>: <span class="v">{dec["evaluator_lct"]}</span></div>',
            f'  <div><span class="k">signed</span>: <span class="tag">{"yes" if dec.get("signature_b64") else "no"}</span></div>',
            f'  <div class="tree">',
            f'    <h3>law_ref</h3>',
            f'    <div><span class="k">bundle_id</span>: <span class="v">{dec["law_ref"]["bundle_id"]}</span></div>',
            f'    <div><span class="k">bundle_digest</span>: <span class="digest">{dec["law_ref"]["bundle_digest"]}</span></div>',
            f'    <div><span class="k">version</span>: <span class="v">{dec["law_ref"]["version"]}</span></div>',
            f'    <div><span class="k">law_ids_applied</span>: <span class="v">{", ".join(dec["law_ref"]["law_ids_applied"])}</span></div>',
            f'  </div>',
        ]
        if dec.get("failures"):
            rows.append('  <div class="tree">')
            rows.append('    <h3>failures</h3>')
            for f in dec["failures"]:
                rows.append(f'    <div><span class="k">{f["law_id"]}</span> → '
                            f'<span class="verdict-deny">{html.escape(f["reason"])}</span></div>')
            rows.append('  </div>')
        rows.append('</div>')
        return "\n".join(rows)

    laws_html = "\n".join(
        f'''
        <div class="box law">
            <div><span class="k">law_id</span>: <span class="tag">{html.escape(lw["law_id"])}</span></div>
            <div><span class="k">rule_type</span>: <span class="v">{lw["rule_type"]}</span></div>
            <div><span class="k">rule</span>: <pre>{_safe(lw["rule"])}</pre></div>
            <div><span class="k">rationale</span>: <span class="dim">{html.escape(lw["rationale"] or "—")}</span></div>
        </div>
        ''' for lw in b["laws"]
    )

    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>Audit bundle</title><style>{CSS}</style></head>
<body>
<h1>One tick of the cognition loop, fully expanded.</h1>
<div class="muted">
  Agent <span class="tag">{html.escape(data["agent_lct"])}</span> —
  scope <span class="tag">demo</span> — law bundle digest
  <span class="digest">{dig[:24]}…</span>
</div>

<h2>The signed law in effect</h2>
<div class="box law">
  <div><span class="k">bundle_id</span>: <span class="tag">{b["bundle_id"]}</span></div>
  <div><span class="k">version</span>: <span class="v">{b["version"]}</span></div>
  <div><span class="k">legislator_lct</span>: <span class="v">{b["legislator_lct"]}</span></div>
  <div><span class="k">witnesses</span>: <span class="v">{len(b["witnesses"])}</span></div>
  <div><span class="k">digest</span>: <span class="digest">{dig}</span></div>
</div>
{laws_html}

<h2>Request A — click green block, cost 1.0</h2>
<div class="muted">permitted, cost within cap, low trust demands met</div>
{render_decision(a["decision"], a, "allow")}
<div class="box allow">
  <h3>outcome</h3>
  <div><span class="k">quality</span>: <span class="v">{a["outcome"]["quality"]:.2f}</span></div>
  <div><span class="k">v3.valuation</span>: <span class="v">{a["outcome"]["value"]["valuation"]:.2f}</span></div>
  <div><span class="k">v3.veracity</span>: <span class="v">{a["outcome"]["value"]["veracity"]:.2f}</span></div>
  <div><span class="k">v3.validity</span>: <span class="v">{a["outcome"]["value"]["validity"]:.2f}</span></div>
  <div><span class="k">energy_spent</span>: <span class="v">{a["energy_spent"]}</span></div>
</div>

<h2>Request B — click everything, cost 100.0</h2>
<div class="muted">violates <span class="tag">law:cost-cap</span> — denied pre-execution; no energy consumed</div>
{render_decision(d["decision"], d, "deny")}

<h2>Why this matters</h2>
<p>
Every field above is reconstructable from the R6 + Decision records alone.
The legislator's signature on the bundle verifies. The witness's
countersignature verifies. The evaluator's signature on the decision
verifies. The bundle digest in <span class="digest">law_ref</span> is
bit-exact. No trusted third party, no network call, no
reconstruction from logs — the audit trail is the action.
</p>

</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="video/audit_bundle.html",
                    help="output HTML path (default: video/audit_bundle.html)")
    args = ap.parse_args()

    data = gen_arc3_bundle()
    html_text = render(data)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text)
    print(f"wrote {out_path} ({len(html_text)} bytes)")
    print(f"agent LCT: {data['agent_lct']}")
    print(f"bundle digest: {data['bundle_digest'][:24]}…")
    print(f"allowed: {data['allowed']['decision']['verdict']}")
    print(f"denied: {data['denied']['decision']['verdict']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
