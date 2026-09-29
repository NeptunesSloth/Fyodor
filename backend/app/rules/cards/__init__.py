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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CardScript:
    oracle_id: str
    name: str
    covers: frozenset[int] = frozenset()  # ability indices this script automates
    handlers: dict[int, Callable[..., Any]] = field(default_factory=dict)


_REGISTRY: dict[str, CardScript] = {}


def register(script: CardScript) -> CardScript:
    if script.oracle_id in _REGISTRY:
        raise ValueError(f"Duplicate script for {script.name}")
    _REGISTRY[script.oracle_id] = script
    return script


def get(oracle_id: str | None) -> CardScript | None:
    return _REGISTRY.get(oracle_id) if oracle_id else None


def all_scripts() -> list[CardScript]:
    return list(_REGISTRY.values())
