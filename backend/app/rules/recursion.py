"""-- recursion & tutors (wave 4M) -- reanimation/recursion and tutor wordings the older grammar didn't read.
Researched against the Comprehensive Rules of 2026-09-25 (data/rules/comprehensive_rules/).

* A spell that moves itself (608.2m, 608.2n): "Exile Rally the Ancestors.", "Shuffle Green Sun's Zenith into
  its owner's library.", "Put Seasons Past on the bottom of its owner's library." The instruction moves the
  spell card off the stack where it stands in the text; the spell still resolves fully (608.2m) and isn't put
  into the graveyard afterwards (608.2n puts it there only from the stack). With flashback the card is
  exiled instead (702.34a: "any time it would leave the stack"). A copy of a spell isn't a card: it stays
  and ceases to exist as it leaves the stack (707.10a), so the instruction does nothing for it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
Definition = dict[str, Any]

SELF_MOVES = {"exile": "exile", "shuffle": "shuffle", "bottom": "bottom", "top": "top"}


def self_move_of(e: dict[str, Any]) -> str | None:
    """Where a spell's own "Exile ~." / "Shuffle ~ into …" / "Put ~ on the bottom of …" moves it (else None)."""
    if e.get("who") != "self":
        return None
    if e.get("do") == "exile" and set(e) <= {"do", "who"}:
        return "exile"
    if e.get("do") == "to_library" and set(e) <= {"do", "who", "place"} and e.get("place") in ("shuffle", "bottom", "top"):
        return str(e["place"])
    return None


def spell_self_move(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """608.2m / 608.2n: the resolving spell card leaves the stack now (see the module docstring)."""
    sid = ctx.get("stack_id")
    card = plan.state.cards.get(sid) if sid else None
    if card is None or card.zone != "stack" or ctx.get("kind") != "spell" or card.copy_of is not None or card.is_token:
        return True  # (a copy: 707.10a; the spell is already gone: nothing to move, 608.2m)
    oid = plan.oid(card)
    r = plan.rules
    to = e["to"]
    if oid in r.flashback:  # 702.34a: exiled instead of put anywhere else
        to = "exile"
    for name in ("flashback", "buyback", "rebound_cast", "exile_if_graveyard"):  # (graveyard replacements: never applied now)
        setattr(r, name, [o for o in getattr(r, name) if o != oid])
    controller = ctx["controller"]
    if to == "exile":
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "exile"}}, actor=controller)
    elif to == "shuffle":  # 701.24
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "library"}}, actor=controller)
        plan.do({"type": "shuffle", "player": card.owner, "zone": "library"}, actor=card.owner)
    else:
        plan.do({"type": "move", "card_ids": [card.id], "to": {"player": card.owner, "zone": "library"}, "position": to},
                actor=controller)
    return True


_SIZED_SEARCH_SPLIT = re.compile(r"(Search your library for up to X [^.]+?, where X is [^.]+)\. (?:Put those cards|Reveal those cards, put them) ")


def join_sized_search(body: str) -> str:
    """"Search your library for up to X basic land cards, where X is …. Put those cards onto the battlefield tapped, then
    shuffle." (Traverse the Outlands): one search instruction printed as two sentences, read as one."""
    return _SIZED_SEARCH_SPLIT.sub(lambda m: f"{m[1]}, " + ("put them " if m[0].endswith("Put those cards ") else "reveal them, put them "),
                                   body)


# 205.3i: the land types
LAND_TYPES = frozenset({"Cave", "Desert", "Forest", "Gate", "Island", "Lair", "Locus", "Mine", "Mountain", "Plains", "Planet",
                        "Power-Plant", "Sphere", "Swamp", "Tower", "Town", "Urza's", "Urza’s"})


def check_found(plan: Plan, e: dict[str, Any], chosen: list[str]) -> None:
    """"Search your library for up to two basic land cards that share a land type" (Myriad Landscape): the cards
    found must have a land type in common (205.3i). Refused as the searcher chooses (the choice is private)."""
    if not e.get("share_land_type") or len(chosen) < 2:
        return
    from app.rules import characteristics as chars

    common: set[str] | None = None
    for cid in chosen:
        card = plan.state.cards.get(cid)
        kinds = set(chars.of(card, plan.info).subtypes) & LAND_TYPES if card is not None else set()
        common = kinds if common is None else common & kinds
    if not common:
        from app.game.errors import ActionError

        raise ActionError("The lands you find must share a land type")


PRIMITIVES = {"spell_self_move": spell_self_move}
