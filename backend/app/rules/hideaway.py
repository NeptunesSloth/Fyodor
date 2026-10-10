"""-- hideaway (wave 29D) -- 702.75 Hideaway, researched against CR 2026-09-25.

702.75a: "Hideaway N" is a triggered ability: "When this permanent enters, look at the top N cards of your library. Exile one of them face
down and put the rest on the bottom of your library in a random order. The exiled card gains 'The player who controls the permanent that
exiled this card may look at this card in the exile zone.'" Each instance triggers separately (Evercoat Ursine's "Hideaway 3, hideaway 3").
702.75b: the older printings (no number, entering tapped) are in the Oracle as "Hideaway 4" and "This permanent enters tapped"; the
database holds the current Oracle text, so there is one wording.

* The look, the pick (face down: 406.3) and the random bottom are the library grammar's (``look_top`` / ``pick_looked`` / ``rest_looked``);
  here the pick is marked as the exiling half of a linked pair (607.2a: ``exiled_with``): the other abilities of the permanent that say
  "the exiled card" / "cards exiled with it" refer to it and to nothing else (``exiled_with.link`` counts the keyword as that exiling ability).
* Who may look (406.3, 702.75a): the player who exiled it (it was looked at first: 406.3 "may continue to look") and whoever controls the
  permanent that exiled it, while it does. A player who has been allowed to look may go on looking until the card leaves exile (406.3), so the
  permanent's controllers are recorded as they change (``RulesState.hideaway``, refreshed with the table's other standing reveals). Nobody
  else sees the card in a view, a decision, a log line or a hint (``app.game.visibility.hideaway_looks``).
* Playing the exiled card is the 608.2g path of the free cast (``permissions.free_cast``: lands 305.2-305.3 included); the face-down card is
  turned face up as it is played (406.3a).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import HideawayLook

if TYPE_CHECKING:
    from app.game.state import GameState
    from app.rules.plan import Plan

# 702.75a (the number: a digit, the grammar reads "the top 4 cards")
MEANING = ("When this permanent enters, look at the top {n} cards of your library. Exile one of them face down and put the rest on the "
           "bottom of your library in a random order.")


def link(d: dict[str, Any]) -> dict[str, Any] | None:
    """The keyword's trigger with its pick marked (607.2a / 702.75a), or None when it isn't the three instructions it is."""
    effects = d.get("effects") or []
    if [e.get("do") for e in effects] != ["look_top", "pick_looked", "rest_looked"] or effects[1].get("to") != "exile" \
            or not effects[1].get("face_down") or effects[2].get("to") != "bottom_random":
        return None
    return {**d, "effects": [effects[0], {**effects[1], "link": True, "hideaway": True}, effects[2]]}


def exiles(ch: Any) -> bool:
    """Does the card have a hideaway line the engine reads? (the exiling ability that "the exiled card" of its other abilities is linked to)"""
    from app.rules import keyword_triggers

    return any(ab.kind == "keywords" and "hideaway" in ab.keywords and keyword_triggers.supported("hideaway", ab.text) for ab in ch.abilities)


def each(d: dict[str, Any]) -> dict[str, Any]:
    """-- review 29D -- 607.3: when the hideaway trigger was copied or triggered twice (Strionic Resonator, Panharmonicon), "the exiled card"
    of the linked ability is each card it exiled (Clive's Hideaway ruling 2025-06-06: both may be played): a free play of "the exiled card"
    plays each of them, one at a time ("one of them", Evercoat Ursine, stays one)."""
    effects = d.get("effects") or []
    refs = {f"ref:{e['as']}" for e in effects if e.get("do") == "linked_cards" and e.get("as")}
    return {**d, "effects": [{**e, "n": 99, "each": True} if e.get("do") == "free_cast" and e.get("who") in refs and "n" not in e else e
                             for e in effects]}


def record(plan: Plan, ctx: dict[str, Any], cards: list[str]) -> None:
    """The card the pick exiled is now one its exiler (the ability's controller) has looked at, exiled by the permanent whose
    ability this is (as it is, or was: 608.2h)."""
    source = ctx.get("source_object")
    for cid in cards:
        card = plan.state.cards.get(cid)
        if source and card is not None and card.zone.endswith(":exile") and card.face_down:
            plan.rules.hideaway[plan.oid(card)] = HideawayLook(source=source, lookers=[ctx["controller"]])


def refresh(state: GameState) -> None:
    """After an action (with the standing reveals, ``permissions.refresh_reveals``): forget the cards that left exile (a new object,
    400.7) and add whoever now controls the permanent that exiled each one to those who may go on looking (406.3). Pure: a function of the
    table, so replay reproduces it."""
    r = state.rules
    if r is None or not r.hideaway:
        return
    for oid, entry in list(r.hideaway.items()):
        card = state.cards.get(oid.rsplit(".", 1)[0])
        if card is None or r.object_id(card.id) != oid or not card.zone.endswith(":exile") or not card.face_down:
            del r.hideaway[oid]
            continue
        src = state.cards.get(entry.source.rsplit(".", 1)[0])
        if src is not None and src.zone.endswith(":battlefield") and r.object_id(src.id) == entry.source \
                and src.controller not in entry.lookers:
            entry.lookers.append(src.controller)
