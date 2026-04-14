"""
Law — signed, versioned, witness-attested rules.

    Legislator signs a LawBundle. Witnesses countersign.
    Agents evaluate actions against the active bundle for a scope.
    Every audit record embeds a LawRef pointing at the exact bundle.

    from src.law import Law, LawBundle, LawRegistry, sign_bundle, add_witness
"""

from .law import (
    RULE_TYPES,
    Law,
    LawBundle,
    LawError,
    LawRef,
    WitnessSignature,
)
from .registry import LawRegistry, RegistryError
from .signing import (
    LawSignatureError,
    add_witness,
    sign_bundle,
    verify_bundle,
    verify_legislator,
    verify_witness,
)

__all__ = [
    "Law",
    "LawBundle",
    "LawRef",
    "LawRegistry",
    "WitnessSignature",
    "LawError",
    "LawSignatureError",
    "RegistryError",
    "RULE_TYPES",
    "sign_bundle",
    "verify_legislator",
    "add_witness",
    "verify_witness",
    "verify_bundle",
]
