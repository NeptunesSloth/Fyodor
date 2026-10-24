"""-- activated (wave 100I) -- exact activated-ability wordings read onto existing machinery. Researched against CR 2026-09-25
(rule numbers at each entry; rulings by date).

* Native rewordings with the same meaning: "Red creatures and white creatures you control" is the creatures you control that are red or
  white (Rise of the Hobgoblins); "Destroy all permanents except for artifacts and lands." is "Destroy all nonartifact, nonland permanents."
  (Scourglass, ruling 2008-10-01); "… of the creature type / color of your choice" is a choice as it resolves then that group (608.2d:
  Riptide Chronologist, Root Greevil); "Creatures without defender can't block ~ this turn." is a blocking restriction on that creature
  (509.1b: Sabertooth Alley Cat); two group pumps of one sentence are fixed as it resolves (611.2c: Stronghold Overseer).
* No duration stated: the effect lasts for that object (611.2a, 400.7): "~ gains / loses flying." (Mist Dragon, latest timestamp wins,
  613.7); "~ becomes blue and has base power and toughness 5/4." (Surge Engine, 105.3, 613.4b); "~ gets +2/+0 and gains flying. Its
  controller sacrifices it at the beginning of the next end step." (Goblin Ski Patrol: whoever controls it then, ruling 2008-10-01).
* "loses first strike or swampwalk" / "loses your choice of …": one keyword, chosen as it resolves (608.2d; Urborg ruling 2009-10-01, Walking
  Sponge ruling 2004-10-04); "loses all landwalk abilities" (702.14: every landwalk variant, Hammerheim).
* Targets: "target permanent you both own and control" (Obelisk of Undoing), "target creature token, player, or planeswalker" (Coalborn Entity,
  targets.py), "target Aura attached to a land" (Savaen Elves, selectors ``attached_land``), "Target creature [that attacked this turn] becomes
  prepared." (722.3a: Skycoach Waypoint, Hexhaven Dueling Arena).
* "Put the top card of your graveyard on the bottom of your library." (Soldevi Digger: the last card put there, 404.2); "Choose a basic land type.
  Each land you control becomes that type until end of turn." (305.7: Terraformer, Elsewhere Flask); "Shuffle any number of cards from your
  hand into your library, then draw that many cards." (701.24d: Credit Voucher); "This Aura's controller sacrifices it, then draws two cards."
  (Soul Ransom: the activator is an opponent, the Aura's controller draws even if it's gone, ruling 2017-03-14).
* Restrictions (restrictions.py): "Activate only if you've controlled ~ continuously since the beginning of your most recent turn." (302.6's
  test, Rocket Launcher), "Activate no more times each turn than the number of …" (602.5b, Withering Wisps), "Only your opponents may activate
  this ability and only as a sorcery." (Detention Vortex).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

from app.rules import selectors

_REWORDED = {
    "Red creatures and white creatures you control gain first strike until end of turn.":
        "Creatures you control that are red or white gain first strike until end of turn.",
    "Creatures with shadow get +1/+0 until end of turn and creatures without shadow get -1/-0 until end of turn.":
        "Creatures with shadow get +1/+0 until end of turn. Creatures without shadow get -1/-0 until end of turn.",
    "Destroy all permanents except for artifacts and lands. Activate only during your upkeep.":
        "Destroy all nonartifact, nonland permanents. Activate only during your upkeep.",
    "Untap all creatures of the creature type of your choice.": "Choose a creature type. Untap all creatures of the chosen type.",
    "Destroy all enchantments of the color of your choice.": "Choose a color. Destroy all enchantments of the chosen color.",
    "Creatures without defender can't block ~ this turn.": "~ can't be blocked by creatures without defender this turn.",
}
# no duration stated (611.2a): the native "until end of turn" reading, lasting for the object instead
_LASTING = {
    "~ gains flying.": "~ gains flying until end of turn.",
    "~ loses flying.": "~ loses flying until end of turn.",
    "~ becomes blue and has base power and toughness 5/4. Activate only if ~ doesn't have defender.":
        "~ becomes blue and has base power and toughness 5/4 until end of turn. Activate only if ~ doesn't have defender.",
}
_LOSE_ONE = {
    "Target creature loses first strike or swampwalk until end of turn.": ("first strike", "swampwalk"),
    "Target creature loses your choice of flying, first strike, or trample until end of turn.": ("flying", "first strike", "trample"),
}


def _native(ability: Any, ch: Any, cost: str, body: str) -> dict[str, Any] | None:
    from app.rules import scripts

    return scripts.define(replace(ability, text=f"{cost}: {body}"), ch)


def _creature_target(d: dict[str, Any] | None) -> dict[str, Any] | None:
    return d if d is not None and d.get("target") == {"what": 'sel:{"types":["Creature"]}'} else None


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.kind != "activated" or not ability.cost:
        return None
    cost, _, body = scripts.self_text(ability.text, ch.name).partition(": ")
    if body in _REWORDED:
        return _native(ability, ch, cost, _REWORDED[body])
    if body in _LASTING:
        d = _native(ability, ch, cost, _LASTING[body])
        return None if d is None else {**d, "effects": [{**e, "duration": "permanent"} for e in d["effects"]]}
    if body == ("~ gets +2/+0 and gains flying. Its controller sacrifices it at the beginning of the next end step. Activate only once and "
                "only if you control a snow Mountain."):
        d = _native(ability, ch, cost, "~ gets +2/+0 and gains flying. Sacrifice ~ at the beginning of the next end step. Activate only once and "
                                       "only if you control a snow Mountain.")
        if d is None or d["effects"][-1] != {"do": "deferred:sacrifice", "who": "self"}:
            return None
        return {**d, "effects": [*d["effects"][:-1], {**d["effects"][-1], "by": "controller"}]}
    if body in _LOSE_ONE:
        d = _creature_target(_native(ability, ch, cost, "Target creature loses flying until end of turn."))
        options = [{"label": f"Loses {k}", "effects": [{"do": "grant", "who": "target", "keywords": [], "remove": [k]}]} for k in _LOSE_ONE[body]]
        return None if d is None else {**d, "effects": [{"do": "choose_effect", "who": "target", "options": options}]}
    if body == "Target creature loses all landwalk abilities until end of turn.":
        from app.rules.combat import LANDWALK

        d = _creature_target(_native(ability, ch, cost, "Target creature loses flying until end of turn."))
        return None if d is None else {**d, "effects": [{**d["effects"][0], "remove": list(LANDWALK)}]}
    if (made := _BUILT.get(body)) is not None:
        return _built(ability, body, *made())
    if body == "Until end of turn, target creature you control gains flying and has base toughness 1.":
        d = _native(ability, ch, cost, "Target creature you control gains flying until end of turn.")  # (the whole effect until end of turn: ruling 2004-10-04)
        return None if d is None else {**d, "effects": [*d["effects"], {"do": "become", "who": "target", "types": [], "duration": "end_of_turn", "t": 1}]}
    if body == "Return target permanent you both own and control to your hand.":
        return _built(ability, body, [{"do": "bounce", "who": "target"}], selectors.Selector(owner="you", controller="you").key())
    if body == "~ deals 1 damage to target creature token, player, or planeswalker.":
        d = _native(ability, ch, cost, "~ deals 1 damage to any target.")
        return None if d is None else {**d, "target": {"what": "creature_token_player_or_planeswalker"}}
    if body == "~'s controller sacrifices it, then draws two cards. Only your opponents may activate this ability.":
        d = _native(ability, ch, cost, "Destroy ~. Only your opponents may activate this ability.")  # (the Aura's controller draws even if it can't sacrifice it,
        return None if d is None else {**d, "effects": [{"do": "sacrifice", "who": "self", "by": "controller"},  # ruling 2017-03-14: as it last existed, 608.2h)
                                                         {"do": "draw", "who": "source_controller", "n": 2}]}
    return None


def _built(ability: Any, body: str, effects: list[dict[str, Any]], what: str | None) -> dict[str, Any] | None:
    from app.rules import restrictions

    _, rest = restrictions.split(body)
    limits = restrictions.parse(body) if rest else []
    if limits is None:
        return None
    return {"kind": "activated", "cost": ability.cost, "effects": effects, "target": {"what": what} if what else None, **({"restriction": limits} if limits else {})}


def _prepare(**sel: Any) -> tuple[list[dict[str, Any]], str]:
    return [{"do": "prepare", "who": "target"}], selectors.Selector(types=("Creature",), **sel).key()  # (722.3a: no prepare spell, nothing: ruling 2026-03-20)


_BASICS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]  # (205.3i)
_BUILT: dict[str, Callable[[], tuple[list[dict[str, Any]], str | None]]] = {
    "Target creature becomes prepared.": lambda: _prepare(),
    "Target creature that attacked this turn becomes prepared. Activate only as a sorcery.": lambda: _prepare(extras=("attacked_this_turn",)),
    "Destroy target Aura attached to a land.": lambda: ([{"do": "destroy", "who": "target"}], selectors.Selector(subtypes=("Aura",), extras=("attached_land",)).key()),
    "Put the top card of your graveyard on the bottom of your library.": lambda: ([{"do": "graveyard_bottom100i"}], None),
    # 305.7: the chosen basic land type replaces the others and their mana abilities (Terraformer rulings 2005-10-01); the lands are fixed as it resolves (611.2c)
    "Choose a basic land type. Each land you control becomes that type until end of turn.":
        lambda: ([{"do": "become", "who": selectors.Selector(types=("Land",), controller="you").key(), "types": [], "duration": "end_of_turn", "land_pick": _BASICS}], None),
    # 701.24d: the library is shuffled even with no card chosen; the cards aren't ordered first (hand_wheel ``shuffled100i``)
    "Shuffle any number of cards from your hand into your library, then draw that many cards.":
        lambda: ([{"do": "hand_to_bottom", "who": "you", "bind_amount": "voucher100i", "any_number": True, "shuffled100i": True},
                  {"do": "shuffle_library", "who": "you"}, {"do": "draw", "who": "you", "n": {"ref_amount": "voucher100i"}}], None),
}


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    from app.rules import casting

    card = plan.state.cards.get(ctx.get("source_card") or "")
    return card is not None and card.zone.endswith(":battlefield") and not casting.summoning_sick(plan.state, card)


def graveyard_bottom(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Put the top card of your graveyard on the bottom of your library." (Soldevi Digger): the last card put there (404.2-3, graveyard_order.py)."""
    you = ctx["controller"]
    yard = plan.state.zones.get(f"{you}:graveyard", [])
    if yard:
        plan.do({"type": "move", "card_ids": [yard[-1]], "to": {"player": you, "zone": "library"}, "position": "bottom"}, actor=you)
    return True


PRIMITIVES = {"graveyard_bottom100i": graveyard_bottom}
