"""-- graveyard order (wave 40C) -- 404.3: "If an effect or rule puts two or more cards into the same graveyard at the same time, the owner
of those cards may arrange them in any order." (404.2: nobody else changes the order of a graveyard.) The engine used to keep whatever order
the move listed the cards in. Asking after every board wipe, mill or discard would make the game tedious, and almost always nothing reads
the order, so the owner of the cards is asked only when the answer could matter and the table can tell without looking at anyone's hidden
cards:

* a card on the battlefield, on the stack or in the command zone whose text reads the order of a graveyard ("the top creature card of your
  graveyard", READER) is there, or one that left the battlefield in the same batch (a creature that dies with the others: its trigger still
  reads the graveyard), or
* the owner set ``ask_graveyard_order`` ("always ask me"), which covers a reader in a hand or a library.

Both depend on public information and the asked player's own setting only, so the question never says what a hand or a library holds.
Otherwise the order stays the one the move listed (deterministic). A reader that comes from a hidden zone later is not helped by that: the
cards that read the order of a graveyard (Shallow Grave, Corpse Dance, Mistmoon Griffin, Necratog …) stay manual.

A batch is noted as it lands (``Plan.do``: the cards that are new in a graveyard after one move or mill), asked before anyone receives
priority (117.5: ``sba`` → ``offer``) and arranged in place: a move within the graveyard, which is no zone change (no replacement applies).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.game.state import zone_key
from app.rules import characteristics as chars
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.rules.plan import Plan

# "the top card of target player's graveyard", "the bottom card of …", "the top two cards of your graveyard", "from the top of your graveyard"
# (a library's top is not it: "the top card of your library into your graveyard")
READER = re.compile(r"\b(?:top|bottom)\b(?:(?!library)[^.:;]){0,30}?\bof (?:(?!library)[^.:;]){0,30}?graveyard", re.IGNORECASE)


def unordered(plan: Plan, payload: dict[str, Any]) -> dict[str, Any]:
    """-- lead fix (review 36) -- A hand's order is hidden (it is the order the cards were drawn in unless the player moved them), so cards a
    move puts from a hand into a graveyard (or face up into exile) together land by name, not in the hand's order ("discard your hand"); the owner may still arrange
    them (404.3, above)."""
    ids, to = payload.get("card_ids") or [], payload.get("to")
    if payload.get("type") != "move" or len(ids) < 2 or payload.get("face_down") \
            or (to.get("zone") if isinstance(to, dict) else to) not in ("graveyard", "exile"):  # (Rest in Peace sends them to exile)
        return payload
    cards = plan.state.cards
    if not any((c := cards.get(i)) is not None and c.zone.endswith(":hand") for i in ids):
        return payload
    return {**payload, "card_ids": sorted(ids, key=lambda i: ((c := cards.get(i)) is not None and c.name or "", i))}


def before(plan: Plan, payload: dict[str, Any]) -> dict[str, Any] | None:
    """The graveyards as a move or mill into one is about to happen (and whether a card leaves the battlefield with it)."""
    kind = payload.get("type")
    if plan.state.rules is None or kind not in ("move", "mill"):
        return None
    to = payload.get("to", "graveyard" if kind == "mill" else None)  # (a mill names a zone, a move a zone reference)
    if (to.get("zone") if isinstance(to, dict) else to) != "graveyard":
        return None
    cards = plan.state.cards
    leaving = any((c := cards.get(cid)) is not None and c.zone.endswith(":battlefield") for cid in payload.get("card_ids") or [])
    return {"yards": {k: list(v) for k, v in plan.state.zones.items() if k.endswith(":graveyard")}, "leaving": leaving}


def after(plan: Plan, seen: dict[str, Any]) -> None:
    """Note each graveyard that took two or more cards from the step (404.3) when its owner is to arrange them."""
    r = plan.rules
    for key, now in plan.state.zones.items():
        if not key.endswith(":graveyard"):
            continue
        old = set(seen["yards"].get(key, ()))
        new = [c for c in now if c not in old]
        owner = key.split(":")[0]
        if len(new) > 1 and owner in plan.live() and (r.prefs_for(owner).ask_graveyard_order or has_reader(plan, new if seen["leaving"] else ())):
            r.pending_gy_order.append({"owner": owner, "cards": new})


def has_reader(plan: Plan, extra: Any) -> bool:
    """Is there a card whose text reads a graveyard's order where everyone can see it (or among ``extra``: the batch of dying cards)?"""
    for c in plan.state.cards.values():
        if (c.zone.endswith((":battlefield", ":command")) or c.zone == "stack" or c.id in extra) and not c.face_down \
                and READER.search(chars.of(c, plan.info).oracle_text):
            return True
    return False


def offer(plan: Plan) -> bool:
    """Ask the first owner (APNAP, 101.4) with a batch still in their graveyard to arrange it. True while a question is open."""
    r = plan.rules
    order = plan.apnap()
    for batch in sorted(r.pending_gy_order, key=lambda b: order.index(b["owner"]) if b["owner"] in order else len(order)):
        r.pending_gy_order = [b for b in r.pending_gy_order if b is not batch]
        owner = batch["owner"]
        pile = plan.state.zones.get(zone_key(owner, "graveyard"), [])
        cards = [c for c in pile if c in batch["cards"]]
        if len(cards) < 2 or pile.index(cards[-1]) - pile.index(cards[0]) != len(cards) - 1 or owner not in plan.live():
            continue  # (cards left it meanwhile, or others came between them: the order stays as it is)
        decide(plan, player=owner, kind="order",
               prompt=f"Order the {len(cards)} cards put into your graveyard together (first chosen ends up on top)",
               options=[DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in reversed(cards)],
               min_choices=len(cards), max_choices=len(cards), resume={"step": "graveyard_order", "owner": owner, "cards": cards})
        return True
    return False


def resume(plan: Plan, d: Any, chosen: list[str]) -> None:
    owner, cards = d.resume["owner"], d.resume["cards"]
    pile = plan.state.zones.get(zone_key(owner, "graveyard"), [])
    if sorted(chosen) != sorted(cards) or any(c not in pile for c in cards):
        return
    plan.note(f"{plan.name(owner)} ordered the {len(cards)} cards put into their graveyard together", cards, actor=d.player)
    plan.do({"type": "move", "card_ids": list(reversed(chosen)), "to": {"player": owner, "zone": "graveyard"}, "index": min(pile.index(c) for c in cards)},
            actor=d.player)
