"""-- multi (wave 100M) -- lines of cards whose missing lines span several families, as an equivalent native wording plus, where needed, a patch.

* Kozilek's Return: "this card" is ~, the card exiled from the graveyard (113.6m: the ability works only there; triggers.graveyard_ability).
* Phyrexian Processor: X is the life paid as its source entered (static_perm100d's choice), as it is or last existed (608.2h).
* Clone Shell: "exile one face down" is the exiling half of "the exiled card" (607.2a: exiled_with links the pick); one must be exiled (its
  ruling). Only the player who exiled it looked at it (406.3: a new controller of Clone Shell can't, its ruling).
* Spider-Man 2099: this turn's land plays (305.1, the "land_play" facts) and casts (601.2i) by you from a zone other than your hand (the command
  zone included), an intervening "if" (603.4).
* Ability-word lines of instants and sorceries (Banefire, Dark Dabbling, Savage Punch) are read into the line before them (``_MERGED``).
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


def _intervening(d: dict[str, Any]) -> dict[str, Any] | None:
    """The native "copy it if …" gate as an intervening "if" too (603.4: no trigger at all unless it holds as the spell is cast; again as it
    resolves): Morbid / Descend 8 "When you cast this spell, if …" (Bygone Marvels' ruling)."""
    es = d["effects"]
    if d.get("if") is not None or not es or es[0].get("do") != "only_if":
        return None
    return {**d, "if": es[0]["cond"]}


def _processor(d: dict[str, Any]) -> dict[str, Any] | None:
    es = d["effects"]
    if [e.get("do") for e in es] != ["create_token"]:
        return None
    paid = {"perm100d": "life_paid_lki"}
    return {**d, "effects": [{**es[0], "token": {**es[0]["token"], "power": paid, "toughness": paid}}]}


def _kraken(d: dict[str, Any]) -> dict[str, Any] | None:
    """Icebreaker Kraken: artifacts and creatures that player controls as that untap step comes (its ruling, 611.2c: next_untap's selectors)."""
    from app.rules.selectors import Selector

    es = d["effects"]
    if [e.get("do") for e in es] != ["stay_tapped"]:
        return None
    return {**d, "effects": [{**es[0], "sel": [Selector(types=("Artifact",)).key(), Selector(types=("Creature",)).key()]}]}


def _risk(d: dict[str, Any]) -> dict[str, Any] | None:
    """Risk Factor: only the target opponent chooses (shared_damage's "target"); an illegal target, the spell doesn't resolve (its ruling)."""
    es = d["effects"]
    if not es or es[0].get("do") != "shared_damage" or d.get("target") is not None:
        return None
    return {**d, "effects": [{**es[0], "who": "target"}, *es[1:]], "target": {"what": "opponent"}}


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
    # Descend upon the Sinful (delirium, counted after the exile, the spell itself on the stack: its rulings), Hymn of the Faller (void: "another card" is
    # one more), Under the Skin ("you may return a permanent card": up to one, the dread's milled one included, its ruling)
    "Create a 4/4 white Angel creature token with flying if there are four or more card types among cards in your graveyard.":
        ("If there are four or more card types among cards in your graveyard, create a 4/4 white Angel creature token with flying.", None),
    "If a nonland permanent left the battlefield this turn or a spell was warped this turn, draw another card.":
        ("If a nonland permanent left the battlefield this turn or a spell was warped this turn, draw a card.", None),
    "You may return a permanent card from your graveyard to your hand.": ("Return up to one permanent card from your graveyard to your hand.", None),
    # Blood for Bones: "another" — the first is on the battlefield by then (not targets; the sacrificed creature may be either: its rulings)
    "Return a creature card from your graveyard to the battlefield, then return another creature card from your graveyard to your hand.":
        ("Return a creature card from your graveyard to the battlefield. Return a creature card from your graveyard to your hand.", None),
    "{3}{U}{U}: Put this card from your graveyard onto the battlefield transformed. Activate only as a sorcery.":
        ("{3}{U}{U}: Return this card from your graveyard to the battlefield transformed. Activate only as a sorcery.", None),
    "When you cast this spell, if a creature died this turn, you may copy ~ and may choose a new target for the copy.":
        ("When you cast this spell, you may copy it if a creature died this turn. You may choose new targets for the copy.", _intervening),
    "When you cast this spell, if there are eight or more permanent cards in your graveyard, copy this spell twice. You may choose new targets for "
    "the copies.": ("When you cast this spell, copy it twice if there are eight or more permanent cards in your graveyard. You may choose new targets "
                    "for the copies.", _intervening),
    "When ~ enters, artifacts and creatures target opponent controls don't untap during that player's next untap step.":
        ("When ~ enters, creatures target opponent controls don't untap during that player's next untap step.", _kraken),
    "Target opponent may have ~ deal 4 damage to them. If that player doesn't, you draw three cards.":
        ("Any opponent may have ~ deal 4 damage to them. If no one does, you draw three cards.", _risk),
}


_EMPTY: dict[str, Any] = {"kind": "spell", "effects": [], "target": None}
_X5 = {"value": {"x": 1}, "op": ">=", "n": 5}


def _bane(es: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Banefire: the X chosen as it was cast (107.3, its ruling) — 5 or more, its damage can't be prevented (615.12), as Demonfire's hellbent."""
    if [e.get("do") for e in es] != ["damage"]:
        return None
    return [{"do": "only_if", "cond": _X5, "skip": 1, "bind": "bane100m"}, {**es[0], "unpreventable": True},
            {"do": "only_if", "cond": {"flag": "bane100m", "negate": True}, "skip": 1}, es[0]]


def _also(text: str) -> list[dict[str, Any]]:
    from app.rules import scripts

    found = scripts.parse_effects(text)
    assert found is not None and found[0], text
    return [dict(e) for e in found[0]]


def _dabbling(es: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Dark Dabbling: "each other creature you control" — other than the target (608.2c); counted as it resolves, itself on the stack (its rulings)."""
    if [e.get("do") for e in es] != ["regenerate", "draw"]:
        return None
    gate, regen = _also("If there are two or more instant and/or sorcery cards in your graveyard, regenerate each creature you control.")
    return [{**es[0], "as": "dab100m"}, es[1], gate, {**regen, "who": "except:dab100m|" + regen["who"]}]


def _punch(es: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """Savage Punch: ferocious as it resolves; the pump first, on the creature you control (the first target: an illegal one gets nothing, its
    rulings), then the fight (701.14)."""
    if [e.get("do") for e in es] != ["fight"] or es[0].get("who") != "target:0":
        return None
    gate, pump = _also("If you control a creature with power 4 or greater, target creature you control gets +2/+2 until end of turn.")
    return [gate, {**pump, "who": "target:0"}, es[0]]


# an ability-word line read into the line before it (one resolution, in printed order: 608.2c): word line -> (the line before it, its effects
# completed, what the word line itself is); the word line alone does nothing
_MERGED: dict[str, tuple[str, Callable[[list[dict[str, Any]]], list[dict[str, Any]] | None], dict[str, Any]]] = {
    # (Banefire's "can't be countered": a static of the spell, judged when something would counter it: permissions.spell_uncounterable)
    "If X is 5 or more, this spell can't be countered and the damage can't be prevented.":
        ("~ deals X damage to any target.", _bane, {"kind": "static", "static": "self_uncounterable", "cond": _X5, "effects": []}),
    "If there are two or more instant and/or sorcery cards in your graveyard, also regenerate each other creature you control.":
        ("Regenerate target creature. Draw a card.", _dabbling, _EMPTY),
    "The creature you control gets +2/+2 until end of turn before it fights if you control a creature with power 4 or greater.":
        ("Target creature you control fights target creature you don't control.", _punch, _EMPTY),
}


def _merged(ability: Any, ch: Any, text: str) -> dict[str, Any] | None:
    from app.rules import scripts

    if text in _MERGED:  # (only with the line it is read into)
        return _MERGED[text][2] if any(scripts.self_text(a.text, ch.name) == _MERGED[text][0] for a in ch.abilities) else None
    words = [a for a in ch.abilities if scripts.self_text(a.text, ch.name) in _MERGED]
    if len(words) != 1 or _MERGED[(word := scripts.self_text(words[0].text, ch.name))][0] != text:
        return None
    native = scripts.define(ability, replace(ch, abilities=tuple(a for a in ch.abilities if a is not words[0])))
    es = _MERGED[word][1](native["effects"]) if native is not None else None
    return None if native is None or es is None else {**native, "effects": es}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    text = scripts.self_text(ability.text, ch.name)
    if ability.kind == "spell" and (merged := _merged(ability, ch, text)) is not None:
        return merged
    found = _AS.get(text)
    if found is None:
        return None
    native = scripts.define(replace(ability, text=found[0]), ch)
    return native if native is None or found[1] is None else found[1](native)
