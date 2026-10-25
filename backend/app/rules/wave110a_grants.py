"""Wave 110A: spells you cast from hand gain a keyword cost as you cast them (a table alternative cost, like prowl/web-slinging)."""
from __future__ import annotations

import re
from typing import Any

# 702.74a: evoke is an alternative cost; "Elemental permanent spells you cast from your hand gain evoke {4} as you cast them." (Ashling, the Limitless)
_EVOKE = re.compile(r"^(?P<sel>[A-Za-z]+ permanent) spells you cast from your hand gain evoke (?P<cost>(?:\{[^}X]+\})+) as you cast them$")


def grant_evoke(t: str) -> dict[str, Any] | None:
    from app.rules import alt_costs
    from app.rules.permissions import spell_filter

    m = _EVOKE.fullmatch(t)
    if m is None or alt_costs.parse_cost(f"pay {m['cost']}") is None or (key := spell_filter(m["sel"])) is None:
        return None
    return {"kind": "static", "static": "alt_cost", "cost": f"pay {m['cost']}", "table": True, "filter": key, "once": False, "zone": "hand",
            "mv": None, "cond": None, "tag": "evoke", "effects": []}


UMBRA = "Auras attached to permanents you control have umbra armor."


def umbra_static(t: str) -> dict[str, Any] | None:
    """Umbra Mystic: a table static read by ``has_umbra``."""
    return {"kind": "static", "static": "umbra_grant110a", "effects": []} if t == UMBRA else None


def has_umbra(plan: Any, aura: Any, host: Any) -> bool:
    """702.89a: the Aura has umbra armor itself, or an Umbra Mystic-like static gives it to Auras on its controller's permanents."""
    from app.rules import permissions

    if not aura.zone.endswith(":battlefield") or plan.manual(aura):
        return False
    if any(ab.kind == "keywords" and "umbra armor" in ab.keywords for ab in plan.ch(aura).abilities):
        return True
    return "Aura" in plan.ch(aura).subtypes and any(
        src.controller == host.controller for src, _, _ in permissions._table_statics(plan.state, plan.info, {"umbra_grant110a"}))


def could_produce(plan: Any, card: Any, ch: Any, symbol: str) -> bool:
    """Whether one of the permanent's own mana abilities can add ``symbol`` (its controller's color identity for Command Tower-like text)."""
    from app.rules import mana as M
    from app.rules.casting import commander_identity

    for ab in ch.abilities:
        if ab.kind != "mana":
            continue
        parsed = M.parse_mana_ability(ab.text, commander_identity(plan.state, card.controller, plan.info), card_name=ch.name)
        if parsed is not None and any(symbol in opt for opt in parsed.options):
            return True
    return False


# 702.56a: "Each Sliver spell you cast has replicate. The replicate cost is equal to its mana cost." (Hatchery Sliver, Ian Chesterton)
_REPLICATE = re.compile(r"^each (?P<sel>[A-Za-z]+) spells? you cast has replicate\. the replicate cost is equal to its mana cost$", re.I)


def grant_replicate(t: str) -> dict[str, Any] | None:
    from app.rules.permissions import spell_filter

    m = _REPLICATE.fullmatch(t.strip().rstrip("."))
    if m is None or (key := spell_filter(m["sel"])) is None:
        return None
    return {"kind": "static", "static": "spell_replicate110a", "filter": key, "effects": []}


def with_replicate(state: Any, player: str, card: Any, ch: Any, info: Any) -> Any:
    """The spell as cast, with the replicate ability its caster's statics give it (602.. kicker_cost then reads it like a printed one)."""
    from dataclasses import replace

    from app.rules import cast_limits
    from app.rules.oracle import parse_abilities
    from app.rules.permissions import spell_matches

    if not ch.mana_cost or "replicate" in ch.keywords or "{X}" in ch.mana_cost:
        return ch
    if not any(src.controller == player and spell_matches(state, player, card, ch, d["filter"], info, src.id)
               for src, d in cast_limits._statics(state, info, "spell_replicate110a")):
        return ch
    extra = parse_abilities(f"Replicate {ch.mana_cost}.")
    at = max([a.index for a in ch.abilities], default=99) + 1
    return replace(ch, abilities=(*ch.abilities, *(replace(a, index=at + i) for i, a in enumerate(extra))))
