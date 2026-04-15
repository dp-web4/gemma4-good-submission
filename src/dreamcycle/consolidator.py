"""
Consolidator — sleep/wake cycle that turns experience into DreamBundles.

The consolidator holds a wake-time experience buffer of (action, decision,
snarc) triples. On `consolidate()` it filters by salience threshold and
emits a DreamBundle ready to persist or transmit.

The cycle:
    1. wake: agent acts → record(action, decision, snarc)
    2. sleep: consolidator filters by salience, exports bundle
    3. dream: bundle becomes training data / cartridge / cross-machine signal
    4. wake: bundle is loaded back into context as priors

Step 4 is the loop closure: today's salient experiences are tomorrow's
priors. The dream-bundle shape persists across all four steps unchanged.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from ..policy.decision import Decision
from ..r6.action import R6Action
from ..snarc.score import DEFAULT_WEIGHTS, SnarcScore
from .bundle import DreamBundle, DreamEntry


@dataclass
class WakeRecord:
    """A single wake-time experience: action, optional decision, optional snarc."""

    action: R6Action
    decision: Decision | None = None
    snarc: SnarcScore | None = None
    notes: str = ""


@dataclass
class Consolidator:
    """Sleep/wake consolidator with a bounded experience buffer."""

    machine: str = ""
    instance_lct: str = ""
    model: str = ""
    session: str = ""
    salience_threshold: float = 0.5
    selection_weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    buffer_size: int = 1024
    _buffer: deque[WakeRecord] = field(default_factory=deque)

    def __post_init__(self) -> None:
        # Re-bind deque with maxlen now that buffer_size is known
        self._buffer = deque(maxlen=self.buffer_size)

    # ------------------------------------------------------------------
    # Wake — record experience
    # ------------------------------------------------------------------

    def record(
        self,
        action: R6Action,
        *,
        decision: Decision | None = None,
        snarc: SnarcScore | None = None,
        notes: str = "",
    ) -> WakeRecord:
        rec = WakeRecord(
            action=action, decision=decision, snarc=snarc, notes=notes
        )
        self._buffer.append(rec)
        return rec

    @property
    def buffer_len(self) -> int:
        return len(self._buffer)

    def clear_buffer(self) -> None:
        self._buffer.clear()

    # ------------------------------------------------------------------
    # Sleep — filter by salience, emit bundle
    # ------------------------------------------------------------------

    def select(
        self, *, threshold: float | None = None
    ) -> list[WakeRecord]:
        """Return buffered records whose snarc composite >= threshold.

        Records lacking SNARC scores are excluded by default — without
        salience signal they can't be ranked. Override threshold per call
        if needed (e.g., consolidate=0 emits everything).
        """
        thr = threshold if threshold is not None else self.salience_threshold
        kept: list[WakeRecord] = []
        for rec in self._buffer:
            if rec.snarc is None:
                continue
            if rec.snarc.composite(self.selection_weights) >= thr:
                kept.append(rec)
        return kept

    def consolidate(
        self,
        *,
        threshold: float | None = None,
        clear_buffer: bool = True,
    ) -> DreamBundle:
        """Emit a DreamBundle from current high-salience buffer contents."""
        selected = self.select(threshold=threshold)
        bundle = DreamBundle(
            machine=self.machine,
            instance_lct=self.instance_lct,
            model=self.model,
            session=self.session,
            salience_threshold=threshold
            if threshold is not None
            else self.salience_threshold,
            selection_weights=dict(self.selection_weights),
        )
        for rec in selected:
            bundle.add(
                rec.action,
                decision=rec.decision,
                snarc=rec.snarc,
                notes=rec.notes,
            )
        if clear_buffer:
            self.clear_buffer()
        return bundle

    # ------------------------------------------------------------------
    # Wake again — load a prior bundle as context
    # ------------------------------------------------------------------

    @staticmethod
    def replay_priors(bundle: DreamBundle) -> Iterable[DreamEntry]:
        """Iterate prior dream entries — caller decides how to inject them
        into model context (system prompt, RAG, retrieved cartridge, etc.).

        This is the loop-closure point: yesterday's salient experiences
        return as today's priors via this iterator. The shape is the same
        as it was when it was recorded; nothing transforms in transit.
        """
        return iter(bundle.entries)
