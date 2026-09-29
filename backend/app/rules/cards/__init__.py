"""Card behaviour scripts, keyed by Oracle id (so every printing shares them).

A script says which of a card's abilities (by index, see ``app.rules.oracle``) the engine
carries out, and how, using the engine's effect primitives. Scripts are ordinary, reviewed and
tested code in this repository: nothing downloaded or user-authored is ever executed (user
behaviour stays declarative macros). Keywords are implemented once in ``app.rules.keywords``
and don't need scripts.

The registry is empty until milestone 15/16 adds effect primitives; cards from the pod's own
decks are scripted first (see ``tools/rules_inventory.py``).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


def oracle_hash(oracle_text: str | None) -> str:
    """A fingerprint of a card's rules text (reminder text and whitespace don't count), stored
    with each script: the text the script was written and tested against."""
    from app.rules.oracle import strip_reminders  # oracle is a leaf module

    lines = [" ".join(strip_reminders(line).split()) for line in (oracle_text or "").splitlines()]
    normal = "\n".join(line for line in lines if line)
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class CardScript:
    oracle_id: str
    name: str
    covers: frozenset[int] = frozenset()  # ability indices this script automates
    handlers: dict[int, Callable[..., Any]] = field(default_factory=dict)
    # Which Oracle text the script was validated against, and its own version. When the local
    # card database has different text, the script is not trusted: the card drops to PARTIAL with
    # REVIEW NEEDED (and the engine resolves those abilities by hand) until someone re-checks it.
    oracle_hash: str = ""
    version: int = 1

    def matches(self, oracle_text: str | None) -> bool:
        return bool(self.oracle_hash) and self.oracle_hash == oracle_hash(oracle_text)


_REGISTRY: dict[str, CardScript] = {}


def register(script: CardScript) -> CardScript:
    if script.oracle_id in _REGISTRY:
        raise ValueError(f"Duplicate script for {script.name}")
    if not script.oracle_hash:
        raise ValueError(f"The script for {script.name} must record the Oracle text it was validated against")
    _REGISTRY[script.oracle_id] = script
    return script


def unregister(oracle_id: str) -> None:
    _REGISTRY.pop(oracle_id, None)


def get(oracle_id: str | None) -> CardScript | None:
    return _REGISTRY.get(oracle_id) if oracle_id else None


def trusted(oracle_id: str | None, oracle_text: str | None) -> CardScript | None:
    """The card's script, but only if it was validated against this Oracle text."""
    script = get(oracle_id)
    return script if script is not None and script.matches(oracle_text) else None


def all_scripts() -> list[CardScript]:
    return list(_REGISTRY.values())
