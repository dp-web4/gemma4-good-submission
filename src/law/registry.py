"""
LawRegistry — loads, verifies, indexes law bundles.

Keeps one active bundle per scope. Supersession chain tracked so audit can
trace how the current law got where it is.

Registry does not perform remote fetching in this iteration. Bundles are
loaded from disk or passed in-memory; production deployments would add a
fetch/distribute layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .law import LawBundle
from .signing import verify_bundle


class RegistryError(Exception):
    """Registry operation failed."""


@dataclass
class LawRegistry:
    """Indexed, verified collection of law bundles.

    Policy:
      - At most one ACTIVE bundle per scope.
      - A newer-version bundle for the same scope supersedes its predecessor.
      - Loading a malformed or invalid-signature bundle is rejected.

    Bundles themselves are immutable (they are signed). Supersession chains
    are tracked in an internal map keyed by the new bundle's id so the
    chain can be reconstructed later.
    """

    _by_scope: dict[str, LawBundle] = field(default_factory=dict)
    _history: list[LawBundle] = field(default_factory=list)
    _supersedes: dict[str, str] = field(default_factory=dict)  # new_id → old_id
    required_witnesses: int = 0

    def register(self, bundle: LawBundle) -> None:
        """Install a bundle. Replaces older version for the same scope."""
        if not verify_bundle(bundle, required_witnesses=self.required_witnesses):
            raise RegistryError(
                f"bundle {bundle.bundle_id} failed verification "
                f"(required_witnesses={self.required_witnesses})"
            )
        existing = self._by_scope.get(bundle.scope)
        if existing is not None:
            if bundle.version <= existing.version:
                raise RegistryError(
                    f"bundle {bundle.bundle_id} version {bundle.version} "
                    f"is not newer than active version {existing.version} "
                    f"for scope {bundle.scope!r}"
                )
            # Track supersession in registry-local map; do NOT mutate the
            # signed bundle — that would invalidate its signature.
            self._supersedes[bundle.bundle_id] = existing.bundle_id
        self._history.append(bundle)
        self._by_scope[bundle.scope] = bundle

    def active(self, scope: str) -> LawBundle | None:
        """The currently-active bundle for a scope, if any."""
        return self._by_scope.get(scope)

    def history(self) -> list[LawBundle]:
        """Append-only insertion history."""
        return list(self._history)

    def supersession_chain(self, scope: str) -> list[LawBundle]:
        """Walk back from active bundle through the supersession map.

        Most recent first. Last entry is the oldest bundle for this scope
        that we have on record. Uses the registry's internal supersession
        map (the bundles themselves are immutable signed artifacts).
        Bundles with their own legislator-set `supersedes_bundle` field
        are honored as a fallback when the registry hasn't recorded the
        link.
        """
        current = self.active(scope)
        if current is None:
            return []
        by_id = {b.bundle_id: b for b in self._history}
        chain = [current]
        while True:
            cur = chain[-1]
            prev_id = self._supersedes.get(cur.bundle_id) or cur.supersedes_bundle
            if not prev_id:
                break
            prev = by_id.get(prev_id)
            if prev is None:
                break
            chain.append(prev)
        return chain

    def scopes(self) -> list[str]:
        return list(self._by_scope.keys())

    # ----------------------------------------------------------------
    # Disk IO
    # ----------------------------------------------------------------

    def load_directory(self, dir_path: str | Path) -> int:
        """Load every *.json bundle from a directory. Returns the count loaded."""
        p = Path(dir_path)
        if not p.is_dir():
            raise RegistryError(f"{dir_path} is not a directory")
        count = 0
        for f in sorted(p.glob("*.json")):
            try:
                bundle = LawBundle.load(f)
            except (ValueError, KeyError) as e:
                raise RegistryError(f"failed to parse {f}: {e}") from e
            try:
                self.register(bundle)
                count += 1
            except RegistryError:
                # Older versions for an already-registered scope are ignored
                # silently — their content is still in the history via disk.
                continue
        return count
