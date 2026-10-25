"""-- multi (wave 100M) -- lines of cards whose missing lines span several families, as an equivalent native wording plus, where needed, a patch.

* Kozilek's Return: "this card" is ~, the card exiled from the graveyard (113.6m: the ability works only there; triggers.graveyard_ability).
* Phyrexian Processor: X is the life paid as its source entered (static_perm100d's choice), as it is or last existed (608.2h).
* Clone Shell: "exile one face down" is the exiling half of "the exiled card" (607.2a: exiled_with links the pick); one must be exiled (its
  ruling). Only the player who exiled it looked at it (406.3: a new controller of Clone Shell can't, its ruling).
* Spider-Man 2099: this turn's land plays (305.1, the "land_play" facts) and casts (601.2i) by you from a zone other than your hand (the command
  zone included), an intervening "if" (603.4).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any


def _recond(d: dict[str, Any], old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any] | None:
    """The native intervening "if" (603.4: as it triggers and as it resolves) with another condition."""
    es = d["effects"]
    if d.get("if") != old or es[0] != {"do": "only_if", "cond": old, "skip": 1}:
        return None
    return {**d, "if": new, "effects": [{**es[0], "cond": new}, *es[1:]]}


def _processor(d: dict[str, Any]) -> dict[str, Any] | None:
    es = d["effects"]
    if [e.get("do") for e in es] != ["create_token"]:
        return None
    paid = {"perm100d": "life_paid_lki"}
    return {**d, "effects": [{**es[0], "token": {**es[0]["token"], "power": paid, "toughness": paid}}]}


# text (after scripts.self_text) -> (the native wording it reads as, how its definition is completed)
_AS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any] | None] | None]] = {
    "Whenever you cast an Eldrazi creature spell with mana value 7 or greater, you may exile this card from your graveyard. If you do, this card "
    "deals 5 damage to each creature.": ("Whenever you cast an Eldrazi creature spell with mana value 7 or greater, you may exile this card from your "
                                         "graveyard. If you do, ~ deals 5 damage to each creature.", None),
    "{4}, {T}: Create an X/X black Phyrexian Minion creature token, where X is the life paid as ~ entered.":
        ("{4}, {T}: Create an X/X black Phyrexian Minion creature token, where X is the number of cards in your hand.", _processor),
    "When ~ enters, look at the top four cards of your library, exile one face down, then put the rest on the bottom of your library in any order.":
        ("When ~ enters, look at the top four cards of your library. Exile one of them face down and put the rest on the bottom of your library in "
         "any order.", None),
    "At the beginning of your end step, if you've played a land or cast a spell this turn from anywhere other than your hand, ~ deals damage equal to "
    "~'s power to any target.": ("At the beginning of your end step, if you've played a land this turn, ~ deals damage equal to ~'s power to any "
                                 "target.", lambda d: _recond(d, {"history": "lands", "n": 1}, {"history": "played_not_hand100m"})),
    # Tezzeret, Master of the Bridge: one X for both instructions (608.2h); "from among them" is the cards it exiled (400.7), onto the battlefield
    # under your control (110.2a)
    "+2: ~ deals X damage to each opponent, where X is the number of artifacts you control. You gain X life.":
        ("+2: ~ deals X damage to each opponent and you gain X life, where X is the number of artifacts you control.", None),
    "−8: Exile the top ten cards of your library. Put all artifact cards from among them onto the battlefield.":
        ("−8: Exile the top ten cards of your library. Put all artifact cards exiled this way onto the battlefield.", None),
    # Nissa, Ascended Animist: her loyalty is the number of loyalty counters on her (306.5b), as she last existed if she's gone (its ruling, 608.2h);
    # "+1/+1 for each Forest" is +X/+X, X counted once as it resolves, for the creatures you control then (its rulings, 611.2c)
    "+1: Create an X/X green Phyrexian Horror creature token, where X is ~'s loyalty.":
        ("+1: Create an X/X green Phyrexian Horror creature token, where X is the number of loyalty counters on ~.", None),
    "−7: Until end of turn, creatures you control get +1/+1 for each Forest you control and gain trample.":
        ("−7: Creatures you control get +X/+X and gain trample until end of turn, where X is the number of Forests you control.", None),
}


_BANE = "If X is 5 or more, this spell can't be countered and the damage can't be prevented."
_X5 = {"value": {"x": 1}, "op": ">=", "n": 5}


def _banefire(ability: Any, ch: Any, text: str) -> dict[str, Any] | None:
    """Banefire: the X chosen as it was cast (107.3, its ruling) — 5 or more, it can't be countered (a static of the spell, judged when something would
    counter it: permissions.spell_uncounterable) and its damage can't be prevented (615.12), as Demonfire's hellbent."""
    from app.rules import scripts

    if text == _BANE:
        return {"kind": "static", "static": "self_uncounterable", "cond": _X5, "effects": []}
    others = tuple(a for a in ch.abilities if scripts.self_text(a.text, ch.name) != _BANE)
    if text != "~ deals X damage to any target." or len(others) == len(ch.abilities):
        return None
    native = scripts.define(ability, replace(ch, abilities=others))
    if native is None or [e.get("do") for e in native["effects"]] != ["damage"]:
        return None
    hit = native["effects"][0]
    return {**native, "effects": [{"do": "only_if", "cond": _X5, "skip": 1, "bind": "bane100m"}, {**hit, "unpreventable": True},
                                  {"do": "only_if", "cond": {"flag": "bane100m", "negate": True}, "skip": 1}, hit]}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "spell" and (bane := _banefire(ability, ch, text)) is not None:
        return bane
    found = _AS.get(text)
    if found is None:
        return None
    native = scripts.define(replace(ability, text=found[0]), ch)
    return native if native is None or found[1] is None else found[1](native)
