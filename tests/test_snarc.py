"""Tests for SNARC 5D salience."""

from __future__ import annotations

import pytest

from src.snarc import (
    DEFAULT_WEIGHTS,
    Scorer,
    SnarcScore,
    jaccard,
    novelty_against_ring,
    surprise_between,
)


class TestSnarcScore:
    def test_defaults_zero(self):
        s = SnarcScore()
        assert s.composite() == pytest.approx(0.0)

    def test_all_max_composite_one(self):
        s = SnarcScore(1.0, 1.0, 1.0, 1.0, 1.0)
        assert s.composite() == pytest.approx(1.0)

    def test_clamped_constructor(self):
        s = SnarcScore.clamped(surprise=5.0, novelty=-1.0)
        assert s.surprise == pytest.approx(1.0)
        assert s.novelty == pytest.approx(0.0)

    def test_weighted_composite(self):
        s = SnarcScore(surprise=1.0, novelty=0.0, arousal=0.0,
                       reward=0.0, conflict=0.0)
        weights_surprise_only = {"surprise": 1.0, "novelty": 0.0,
                                 "arousal": 0.0, "reward": 0.0, "conflict": 0.0}
        assert s.composite(weights_surprise_only) == pytest.approx(1.0)

    def test_default_weights_sum_to_one(self):
        assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)

    def test_above_threshold(self):
        s = SnarcScore(0.8, 0.8, 0.8, 0.8, 0.8)
        assert s.above(0.5)
        assert not s.above(0.9)

    def test_roundtrip(self):
        s1 = SnarcScore(0.1, 0.2, 0.3, 0.4, 0.5, tags=["test"])
        s2 = SnarcScore.from_dict(s1.to_dict())
        assert s2.surprise == pytest.approx(s1.surprise)
        assert s2.tags == ["test"]

    def test_max_dim(self):
        s = SnarcScore(0.1, 0.9, 0.3, 0.2, 0.4)
        dim, val = s.max_dim()
        assert dim == "novelty"
        assert val == pytest.approx(0.9)


class TestSimilarity:
    def test_jaccard_identical(self):
        assert jaccard("hello world", "hello world") == pytest.approx(1.0)

    def test_jaccard_disjoint(self):
        assert jaccard("foo bar", "baz qux") == pytest.approx(0.0)

    def test_jaccard_partial(self):
        # "a b c" vs "b c d" → intersect={b,c}, union={a,b,c,d} = 2/4 = 0.5
        assert jaccard("a b c", "b c d") == pytest.approx(0.5)

    def test_jaccard_case_insensitive(self):
        assert jaccard("Hello World", "hello world") == pytest.approx(1.0)

    def test_jaccard_empty_both(self):
        assert jaccard("", "") == pytest.approx(1.0)  # vacuous


class TestSurprise:
    def test_no_expectation_zero_surprise(self):
        assert surprise_between("anything", None) == pytest.approx(0.0)

    def test_matching_expectation_zero_surprise(self):
        assert surprise_between("hello world", "hello world") == pytest.approx(0.0)

    def test_full_divergence_max_surprise(self):
        assert surprise_between("apple banana", "car truck") == pytest.approx(1.0)

    def test_dict_observations(self):
        # Same dict = no surprise regardless of key order
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        assert surprise_between(a, b) == pytest.approx(0.0)


class TestNoveltyRing:
    def test_empty_ring_full_novelty(self):
        from collections import deque

        assert novelty_against_ring("hello", deque()) == pytest.approx(1.0)

    def test_exact_match_zero_novelty(self):
        from collections import deque

        ring = deque(["hello world", "foo bar"])
        assert novelty_against_ring("hello world", ring) == pytest.approx(0.0)

    def test_partial_match_intermediate(self):
        from collections import deque

        ring = deque(["a b c"])
        score = novelty_against_ring("b c d", ring)
        assert 0.4 < score < 0.6  # ~0.5


class TestScorer:
    def test_first_observation_full_novelty(self):
        scorer = Scorer()
        s = scorer.score("hello world")
        assert s.novelty == pytest.approx(1.0)

    def test_repeated_observation_no_novelty(self):
        scorer = Scorer()
        scorer.score("hello world")
        s = scorer.score("hello world")
        assert s.novelty == pytest.approx(0.0)

    def test_memory_ring_bounded(self):
        scorer = Scorer(memory_size=2)
        scorer.score("a b c")
        scorer.score("d e f")
        scorer.score("g h i")
        # "a b c" should have been evicted
        assert len(scorer.memory) == 2
        s = scorer.score("a b c")
        assert s.novelty == pytest.approx(1.0)  # novel again!

    def test_surprise_from_expectation(self):
        scorer = Scorer()
        s = scorer.score("hello world", expectation="hello world")
        assert s.surprise == pytest.approx(0.0)
        s2 = scorer.score("totally different", expectation="hello world")
        assert s2.surprise == pytest.approx(1.0)

    def test_caller_supplied_dimensions(self):
        scorer = Scorer()
        s = scorer.score("x", arousal=0.8, reward=0.3, conflict=0.1)
        assert s.arousal == pytest.approx(0.8)
        assert s.reward == pytest.approx(0.3)
        assert s.conflict == pytest.approx(0.1)

    def test_tags_propagate(self):
        scorer = Scorer()
        s = scorer.score("x", tags=["level-1", "game:r11l"])
        assert "level-1" in s.tags

    def test_clear_resets_memory(self):
        scorer = Scorer()
        scorer.score("hello")
        scorer.score("world")
        scorer.clear()
        s = scorer.score("hello")
        assert s.novelty == pytest.approx(1.0)

    def test_caller_values_clipped(self):
        scorer = Scorer()
        s = scorer.score("x", arousal=2.0, reward=-1.0)
        assert s.arousal == pytest.approx(1.0)
        assert s.reward == pytest.approx(0.0)


class TestIntegration:
    def test_composite_balances_dimensions(self):
        """A novel but non-rewarding, non-surprising observation gets
        a moderate composite. A high-reward repeat gets a different one."""
        scorer = Scorer()
        scorer.score("initial")

        novel_only = scorer.score("entirely new")
        # novelty dominates (~1.0), others 0 → composite ≈ 0.25 default weight
        assert 0.2 <= novel_only.composite() <= 0.3

        scorer.clear()
        scorer.score("initial")
        reward_only = scorer.score(
            "initial", expectation="initial", reward=1.0
        )
        # novelty 0, surprise 0, reward 1 → composite = 0.2 * 1 / 1
        assert 0.15 <= reward_only.composite() <= 0.25

    def test_score_suitable_for_consolidation_filter(self):
        """Can use composite() > threshold as a keep-for-dreams filter."""
        scorer = Scorer()
        high = scorer.score("novel event", arousal=0.9, reward=0.8)
        scorer.score("novel event")  # repeat → low novelty
        low = scorer.score("novel event")  # repeat again

        keep_threshold = 0.5
        assert high.composite() > keep_threshold
        assert low.composite() < keep_threshold
