"""
GemmaOllamaExecutor — Executor that calls Gemma 4 via a local Ollama daemon.

Plugs into CognitionLoop as a drop-in replacement for StubExecutor.
Uses the Ollama HTTP API directly (no SDK dependency) so this adapter
is both tiny and transparent.

Prerequisites
-------------

  - `ollama` daemon running on localhost:11434 (default)
  - the desired Gemma 4 variant pulled, e.g. `ollama pull gemma4:e4b`

Model selection
---------------

Default model is `gemma4:e4b` (~4.5B effective, fits 8GB VRAM at
typical ollama quant). Override with `model="gemma4:e2b"` for smaller
edge deployments, or `model="gemma4:26b-a4b"` on workstation-class
hardware.

Output shape
------------

The model is prompted to produce a short plan + a self-rated quality
score and a three-dim V3 (valuation/veracity/validity) in [0, 1].
The adapter parses these from the tail of the response; if parsing
fails it falls back to mid-range defaults so the loop never deadlocks
on malformed output.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..r6.action import R6Action
from ..r6.types import V3
from .executor import Outcome


DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "gemma4:e4b"
DEFAULT_TIMEOUT_S = 60.0


_PROMPT_TEMPLATE = """You are an AI agent operating under a signed policy gate and energy budget.

Action request
  - Type: {action_type}
  - Description: {description}
  - Acceptance criteria: {criteria}
  - Scope: {scope}

Observation (what you are acting on):
  {observation}

Role trust snapshot:
  T3 talent={talent:.2f} training={training:.2f} temperament={temperament:.2f}

Produce a brief plan (1-3 short sentences) for executing this action,
then at the END of your reply append EXACTLY this JSON block on its own line:

{{"quality": <float in [0,1]>, "valuation": <float>, "veracity": <float>, "validity": <float>}}

The floats are your HONEST self-assessment of:
  - quality: how well this plan meets the acceptance criteria
  - valuation: usefulness of the result to the requester
  - veracity: truthfulness / factual correctness of the content
  - validity: internal coherence / well-formedness

Do not wrap the JSON in markdown. Do not add trailing commentary after it."""


_JSON_TAIL_RE = re.compile(
    r"\{[^{}]*\"quality\"[^{}]*\"valuation\"[^{}]*\"veracity\"[^{}]*\"validity\"[^{}]*\}",
    re.DOTALL,
)


def _clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except (TypeError, ValueError):
        return 0.5


@dataclass
class GemmaOllamaExecutor:
    """Executor that dispatches to a local Ollama-hosted Gemma model."""

    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST
    timeout_s: float = DEFAULT_TIMEOUT_S
    temperature: float = 0.2
    max_tokens: int = 256

    # ------------------------------------------------------------------

    def execute(self, action: R6Action, context: dict | None = None) -> Outcome:
        prompt = self._build_prompt(action, context or {})
        raw = self._call_model(prompt)
        quality, v3 = self._parse_self_assessment(raw)
        return Outcome(
            output={"text": raw.strip(), "model": self.model},
            quality=quality,
            value=v3,
            notes=f"gemma adapter: {self.model}",
        )

    # ------------------------------------------------------------------

    def _build_prompt(self, action: R6Action, context: dict) -> str:
        obs = context.get("observation", action.reference.current_observation)
        obs_repr = (
            json.dumps(obs, default=str)[:512]
            if obs is not None
            else "(none)"
        )
        criteria = (
            "; ".join(action.request.acceptance_criteria)
            if action.request.acceptance_criteria
            else "(none specified)"
        )
        scope = (
            action.rules.permission_scope[0]
            if action.rules.permission_scope
            else action.request.action_type.value
        )
        return _PROMPT_TEMPLATE.format(
            action_type=action.request.action_type.value,
            description=action.request.description or "(none)",
            criteria=criteria,
            scope=scope,
            observation=obs_repr,
            talent=action.role.t3.talent,
            training=action.role.t3.training,
            temperament=action.role.t3.temperament,
        )

    # ------------------------------------------------------------------

    def _call_model(self, prompt: str) -> str:
        # /api/chat (not /api/generate) because Gemma 4's thinking mode
        # produces tokens that /api/generate routes into an invisible
        # channel — we end up with empty `response` despite non-zero
        # eval_count. /api/chat with think=False yields the content
        # cleanly.
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            raise RuntimeError(f"ollama call failed: {e}") from e
        return body.get("message", {}).get("content", "")

    # ------------------------------------------------------------------

    def _parse_self_assessment(self, text: str) -> tuple[float, V3]:
        """Extract the trailing JSON block. Fall back to 0.5 defaults."""
        m = None
        for match in _JSON_TAIL_RE.finditer(text):
            m = match  # keep the last match
        if m is None:
            return 0.5, V3(0.5, 0.5, 0.5)
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return 0.5, V3(0.5, 0.5, 0.5)
        return _clip(data.get("quality", 0.5)), V3(
            valuation=_clip(data.get("valuation", 0.5)),
            veracity=_clip(data.get("veracity", 0.5)),
            validity=_clip(data.get("validity", 0.5)),
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def is_model_available(
    model: str = DEFAULT_MODEL, host: str = DEFAULT_HOST, timeout_s: float = 5.0
) -> bool:
    """Returns True iff the Ollama daemon reports this model is pulled."""
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False
    for entry in data.get("models", []):
        name = entry.get("name") or entry.get("model") or ""
        if name == model or name.startswith(f"{model}:"):
            return True
        # ollama list sometimes reports "gemma4:e4b" — match either form
        if model in name:
            return True
    return False
