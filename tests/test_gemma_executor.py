"""
Integration tests for the Gemma Ollama adapter.

These tests require a running Ollama daemon with at least one of the
Gemma 4 tags pulled. They're skipped otherwise so the suite stays green
on CI / fresh clones.

To enable: `ollama pull gemma4:e2b` (or e4b), ensure daemon running.
"""

from __future__ import annotations

import pytest

from src.cognition import GemmaOllamaExecutor, is_model_available
from src.cognition.gemma_executor import _JSON_TAIL_RE
from src.r6 import (
    ActionType,
    R6Action,
    Reference,
    Request,
    Resource,
    Role,
    Rules,
    T3,
    V3,
)


def _pick_available_model() -> str | None:
    for tag in ("gemma4:e4b", "gemma4:e2b", "gemma3:4b"):
        if is_model_available(tag):
            return tag
    return None


AVAILABLE = _pick_available_model()
skip_no_ollama = pytest.mark.skipif(
    AVAILABLE is None,
    reason="no Ollama model available; run `ollama pull gemma4:e2b` to enable",
)


# --------------------------------------------------------------------------
# Prompt building and parsing — no model needed
# --------------------------------------------------------------------------


class TestPromptAndParse:
    def test_build_prompt_includes_all_components(self):
        ex = GemmaOllamaExecutor()
        action = R6Action(
            rules=Rules(permission_scope=["game"]),
            role=Role(role_id="r", context="c",
                      t3=T3(talent=0.4, training=0.6, temperament=0.7)),
            request=Request(
                action_type=ActionType.ACT,
                description="click the green block",
                acceptance_criteria=["one move", "object named"],
            ),
            reference=Reference(current_observation={"frame": 1}),
            resource=Resource(estimated_cost=1.0),
        )
        prompt = ex._build_prompt(action, {})
        assert "click the green block" in prompt
        assert "one move" in prompt
        assert "game" in prompt
        assert "talent=0.40" in prompt
        assert "training=0.60" in prompt
        assert "temperament=0.70" in prompt
        assert '{"quality"' in prompt or '"quality"' in prompt

    def test_parse_valid_json_tail(self):
        ex = GemmaOllamaExecutor()
        text = (
            "My plan is to click the green block.\n"
            '{"quality": 0.85, "valuation": 0.7, "veracity": 0.9, "validity": 0.95}'
        )
        q, v3 = ex._parse_self_assessment(text)
        assert q == pytest.approx(0.85)
        assert v3.valuation == pytest.approx(0.7)
        assert v3.veracity == pytest.approx(0.9)
        assert v3.validity == pytest.approx(0.95)

    def test_parse_clips_out_of_range(self):
        ex = GemmaOllamaExecutor()
        text = (
            "plan\n"
            '{"quality": 5.0, "valuation": -1, "veracity": 0.5, "validity": 0.5}'
        )
        q, v3 = ex._parse_self_assessment(text)
        assert q == 1.0
        assert v3.valuation == 0.0

    def test_parse_fallback_on_missing_json(self):
        ex = GemmaOllamaExecutor()
        q, v3 = ex._parse_self_assessment("just a plan, no json block")
        assert q == 0.5
        assert v3.valuation == 0.5

    def test_parse_fallback_on_malformed_json(self):
        ex = GemmaOllamaExecutor()
        # Has the keys but missing quotes etc.
        q, v3 = ex._parse_self_assessment(
            'plan\n{quality: 0.8, valuation: 0.7, veracity: 0.8, validity: 0.9}'
        )
        assert q == 0.5

    def test_parse_uses_last_match_when_multiple(self):
        """If the model produces multiple JSON-looking blocks, the final one
        (closest to the self-assessment convention) wins."""
        ex = GemmaOllamaExecutor()
        text = (
            'Example: {"quality": 0.1, "valuation": 0.1, "veracity": 0.1, "validity": 0.1}\n'
            'Actual:  {"quality": 0.9, "valuation": 0.9, "veracity": 0.9, "validity": 0.9}'
        )
        q, v3 = ex._parse_self_assessment(text)
        assert q == pytest.approx(0.9)


# --------------------------------------------------------------------------
# Live ollama integration — skipped if daemon / model unavailable
# --------------------------------------------------------------------------


@skip_no_ollama
class TestLive:
    def test_live_call_produces_outcome(self):
        ex = GemmaOllamaExecutor(model=AVAILABLE, timeout_s=60.0)
        action = R6Action(
            rules=Rules(permission_scope=["smoke"]),
            role=Role(role_id="r", context="c"),
            request=Request(
                action_type=ActionType.ACT,
                description="pick the green block",
                acceptance_criteria=["one concrete move"],
            ),
            reference=Reference(
                current_observation="green block upper-left, red target lower-right"
            ),
            resource=Resource(estimated_cost=1.0),
        )
        out = ex.execute(action)
        assert out.output["model"] == AVAILABLE
        assert isinstance(out.output["text"], str)
        assert 0.0 <= out.quality <= 1.0
        assert 0.0 <= out.value.valuation <= 1.0
        # With a working model + think=False, we should actually get content
        assert out.output["text"].strip(), f"empty response from {AVAILABLE}"
