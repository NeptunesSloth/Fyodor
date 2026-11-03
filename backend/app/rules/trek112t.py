"""-- Star Trek one-offs (wave 112T) -- Star Trek cards whose last missing line isn't one of the set's mechanics, and the ones the Star Trek
release notes (https://magic.wizards.com/en/news/feature/star-trek-release-notes) now settle. CR 2026-09-25.

* All Good Things...: "I, II, III — Draw two cards, then exile a card from your hand." (the card is chosen from the hand, privately, 608.2d, as Azor's
  Gateway's; linked to the Saga, 607.2a) and "IV — If all cards exiled with this Saga share a card type, you gain 10 life." Its release-notes
  ruling settles the count wave 111E refused on: "check whatever cards are exiled with this Saga …, even if that's fewer than three cards … You'll
  gain 10 life if there's only one exiled card … If there are no exiled cards, you will also gain 10 life." (``linked_aggregates`` "share_type112t")
* Commander Spock: "reveal the top card of your library. You may cast that card without paying its mana cost if that spell's mana value is equal
  to or less than the number of differently named lands you control. If it's a land card, you may put it onto the battlefield tapped. If that
  card is still on top of your library, draw a card." Its release-notes rulings settle what wave 111D refused on: "If the revealed card has {X} in
  its mana cost, X is 0 for the purpose of determining its mana value" (the card in the library, 202.3e; each way it can be cast is checked as
  that spell, 601.3e, as ``permissions.free_cast`` does), "You cast the card while Commander Spock's ability is resolving … Timing
  restrictions based on its types are ignored", X is 0 when cast (107.3b). "Still on top of your library": the revealed object, unmoved
  (400.7: a cast card or a land put onto the battlefield is a new object elsewhere) — ``draw_if_top112t``.
* Tell Me What You See: "target opponent may have you draw a card. If they don't, they lose 4 life and you surveil 1." The target opponent
  chooses as the ability resolves (608.2d), as for Bane, Lord of Darkness (wave110n_cards) and Terrapact Intimidator (counters100j).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

_TELL = "When ~ enters, target opponent may have you draw a card. If they don't, they lose 4 life and you surveil 1."


def _tell(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    head = scripts.define(replace(ability, text="When ~ enters, target opponent loses 4 life and you surveil 1."), ch)
    if head is None or [e.get("do") for e in head["effects"]] != ["lose_life", "surveil"]:
        return None
    return {**head, "effects": [
        {"do": "optional_payment", "who": "target", "ask": "Have its controller draw a card (if you don't, you lose 4 life and they surveil 1)",
         "bind": "tell112t"},
        {"do": "only_if", "cond": {"succeeded": "tell112t"}, "skip": 1},
        {"do": "draw", "who": "you", "n": 1},
        {"do": "only_if", "cond": {"succeeded": "tell112t", "negate": True}, "skip": len(head["effects"])},
        *head["effects"]]}


_SPOCK = ("Whenever ~ enters or attacks, reveal the top card of your library. You may cast that card without paying its mana cost if that spell's mana "
          "value is equal to or less than the number of differently named lands you control. If it's a land card, you may put it onto the battlefield "
          "tapped. If that card is still on top of your library, draw a card.")
_SPOCK_NATIVE = ("Whenever ~ enters or attacks, reveal the top card of your library. You may cast that card without paying its mana cost if its mana "
                 "value is less than or equal to the number of differently named lands you control. If it's a land card, you may put it onto the "
                 "battlefield tapped.")


def _spock(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    native = scripts.define(replace(ability, text=_SPOCK_NATIVE), ch)
    if native is None or [e.get("do") for e in native["effects"]] != ["look_top", "free_cast", "only_if", "pick_looked"] \
            or native["effects"][0].get("as") != "e0":
        return None
    return {**native, "effects": [*native["effects"], {"do": "draw_if_top112t", "ref": "e0"}]}


def draw_if_top(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Draw a card if the revealed card is still the same object on top of its owner's library (400.7)."""
    from app.rules import context
    from app.rules.effects import PRIMITIVES as EFFECTS

    still = context.objects(plan, ctx, e["ref"])
    library = plan.state.zones.get(f"{ctx['controller']}:library", [])
    if not still or not library or library[0] != still[0]:
        return True
    return bool(EFFECTS["draw"](plan, ctx, {"do": "draw", "who": "you", "n": 1}))


PRIMITIVES = {"draw_if_top112t": draw_if_top}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind == "triggered" and ability.index < 100 and scripts.self_text(ability.text, ch.name) == _TELL:
        return _tell(ability, ch)
    if ability.kind == "triggered" and ability.index < 100 and scripts.self_text(ability.text, ch.name) == _SPOCK:
        return _spock(ability, ch)
    return None


_DRAW_EXILE = "Draw two cards, then exile a card from your hand."


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    """All Good Things...'s chapters I-III."""
    from app.rules import selectors

    if body.strip() != _DRAW_EXILE:
        return None
    sel = selectors.parse("card in your hand")
    assert sel is not None
    return [{"do": "draw", "who": "you", "n": 2},
            {"do": "return_choice", "sel": sel.key(), "to": "exile", "n": 1, "upto": False, "random": False, "label": "card", "link": True}], None, False
