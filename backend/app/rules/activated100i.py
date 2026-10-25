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
  this ability and only as a sorcery." (Detention Vortex), "… only if at least one creature is blocking ~ …" (Grizzled Wolverine), "… the number
  of other Caves you control plus the number of Cave cards in your graveyard is three or greater." (Cavernous Maw).
* With the Auras attached (303.4: Portal of Sanctuary, Essence Reliquary); the card a cost exiled (Storm Elemental); "target player who was dealt
  combat damage by ~ this turn" (Hope of Ghirapur); "target player other than ~'s owner" (108.3: Crown of Doom); "Put ~ and target creature on top
  of their owners' libraries, then those players shuffle" (701.24a: Void Stalker); two player targets (115.3: Cybernetica Datasmith); from the
  graveyard (113.6m: Carrionette, Soul of Shandalar).
* Elsewhere (marked "wave 100I"): Thaumaton Torpedo's "if you attacked with a Spacecraft this turn" (conditions.py), Monstrous War-Leech's "As ~
  enters, if it was kicked, mill four cards." (static_perm100d.py), Tornado's "Pay 3 life for each velocity counter" (costs.py, cost_payment.py),
  Kentaro and Conspiracy Unraveler (alt_costs.py), Krovikan Sorcerer (activated_card_outcomes.py), Mana Maze (cast_limits.py ``share_last100i``).
* Per player or per object in turn (101.4, 118.12a): Sivriss (mill, then that opponent may pay 3 life), Stench of Evil (each destroyed Plains'
  controller may pay {2}), Outpace Oblivion ("each player who doesn't have max speed"). Zareth San (from the hand, tapped and attacking, 508.4);
  Gerrard's Hourglass Pendant and Myojin of Grim Betrayal (cards put into graveyards this turn); Excavator (the sacrificed land's landwalks);
  Giant Albatross (the creatures that dealt it damage this turn, each unless its controller pays 2 life, no regeneration).
* Timestream Navigator's "Put ~ on the bottom of its owner's library" cost (costs.py ``LIBRARY_BOTTOM_SELF``); Arcum's Weathervane's snow supertype
  (layers ``remove_supertypes`` on a resolved effect, 205.4); tokens with their own rules text (Dragonbroods' Relic, Sengir Nosferatu's Bat).
"""

from __future__ import annotations

import re
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
    # (the graveyard's history this turn, 400.7: Gerrard's Hourglass Pendant, rulings 2022-09-09; Myojin of Grim Betrayal)
    "Return to the battlefield tapped all artifact, creature, enchantment, and land cards in your graveyard that were put there from the battlefield this turn.":
        "Return all artifact, creature, enchantment, and land cards in your graveyard that were put there from the battlefield this turn to the battlefield tapped.",
    "Put onto the battlefield under your control all creature cards in all graveyards that were put there from anywhere this turn.":
        "Put all creature cards in all graveyards that were put there from anywhere this turn onto the battlefield under your control.",
}
# no duration stated (611.2a): the native "until end of turn" reading, lasting for the object instead
_LASTING = {
    "~ gains flying.": "~ gains flying until end of turn.",
    "~ loses flying.": "~ loses flying until end of turn.",
    "~ becomes blue and has base power and toughness 5/4. Activate only if ~ doesn't have defender.":
        "~ becomes blue and has base power and toughness 5/4 until end of turn. Activate only if ~ doesn't have defender.",
}
_REWORDED["~ becomes a 3/3 Elemental creature until end of turn. It's still a Cave land. Activate only if the number of other Caves you control plus the "
          "number of Cave cards in your graveyard is three or greater."] = (  # (205.1b: "still a land" keeps every prior type and subtype, Cave too)
    "~ becomes a 3/3 Elemental creature until end of turn. It's still a land. Activate only if the number of other Caves you control plus the "
    "number of Cave cards in your graveyard is three or greater.")
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

    if ability.kind == "static" and ability.text == "Players can't cast spells that share a color with the spell most recently cast this turn.":
        # (Mana Maze: 601.3; the first spell each turn is free of it, its color as it was cast: rulings 2004-10-04; cast_limits ``share_last100i``)
        return {"kind": "static", "static": "cast_limit", "who": "each", "when": None, "filter": None, "from": None, "act": None, "max": None,
                "share_last100i": True, "effects": []}
    if ability.kind == "spell" and scripts.self_text(ability.text, ch.name) == (
            "Destroy all Plains. For each land destroyed this way, ~ deals 1 damage to that land's controller unless they pay {2}."):
        # (Stench of Evil: 118.12a for each land in turn, its controller as it last existed, 608.2h; one destroyed, not regenerated or indestructible, 701.8b)
        return {"kind": "spell", "effects": [{"do": "destroy", "who": selectors.Selector(subtypes=("Plains",)).key(), "as": "e0"}, {"do": "stench100i", "ref_count": "e0"}],
                "target": None}
    if ability.kind == "triggered" and scripts.self_text(ability.text, ch.name) == (
            "When ~ dies, you may pay {1}{U}. If you do, for each creature that dealt damage to ~ this turn, destroy that creature unless its controller "
            "pays 2 life. A creature destroyed this way can't be regenerated."):
        # (Giant Albatross: however it died, redirected damage too, rulings 2004-10-04; 118.12a for each creature in turn, 101.4; 701.19c)
        d = scripts.define(replace(ability, text="When ~ dies, you may pay {1}{U}. If you do, draw a card."), ch)
        if d is None or [e["do"] for e in d["effects"]] != ["optional_payment", "only_if", "draw"]:
            return None
        return {**d, "effects": [*d["effects"][:2], {"do": "albatross100i"}]}
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
    if body == "Until your next turn, target player who was dealt combat damage by ~ this turn can't cast noncreature spells.":
        d = _native(ability, ch, cost, "Until your next turn, target player can't cast noncreature spells.")  # (Hope of Ghirapur: from now on only, rulings 2017-02-09)
        who = selectors.Selector(player="any", damaged_by_source_this_turn=True, extras=("combat100i",)).key()
        return None if d is None or d.get("target") != {"what": "player"} else {**d, "target": {"what": who}}
    if body == "Target player other than ~'s owner gains control of it. Activate only during your turn.":
        d = _native(ability, ch, cost, "Target player gains control of ~. Activate only during your turn.")  # (Crown of Doom: never back to its owner,
        who = selectors.Selector(player="any", extras=("not_source_owner100i",)).key()  # ruling 2014-11-07)
        return None if d is None or d.get("target") != {"what": "player"} else {**d, "target": {"what": who}}
    if body == "Put ~ and target creature on top of their owners' libraries, then those players shuffle their libraries.":
        # 701.24a: put there then shuffled is shuffled into it; only the owners of what moved shuffle, a Void Stalker that left stays put
        # (rulings 2012-07-01)
        d = _creature_target(_native(ability, ch, cost, "Target creature loses flying until end of turn."))
        return None if d is None else {**d, "effects": [{"do": "to_library", "who": "union:self+target", "place": "shuffle"}]}
    if body == 'Target player draws a card. Another target player creates a 4/4 colorless Robot artifact creature token with "This token can\'t block."':
        token = scripts.parse_effects('Target player creates a 4/4 colorless Robot artifact creature token with "This token can\'t block."')
        if token is None or len(token[0]) != 1:
            return None  # (both targets chosen on activation: ruling 2022-10-07; 115.3 "another")
        return {"kind": "activated", "cost": ability.cost, "effects": [{"do": "draw", "who": "target:0", "n": 1}, {**token[0][0], "who": "target:1"}],
                "target": None, "targets": [{"what": "player", "min": 1, "max": 1}, {"what": "player", "min": 1, "max": 1, "distinct_from": [0]}]}
    if body == "Exile this card and target creature unless that creature's controller pays {2}. Activate only if this card is in your graveyard.":
        # 118.12a: that player may pay; if not, both are exiled (the card itself while it's still that graveyard card, 400.7; exiled by the
        # effect, so it can be activated again in response: Carrionette ruling 2004-10-04)
        d = _native(ability, ch, cost, "Exile target creature unless its controller pays {2}. Activate only if this card is in your graveyard.")
        if d is None or [e["do"] for e in d["effects"]] != ["optional_payment", "only_if", "exile"]:
            return None
        return {**d, "effects": [*d["effects"][:2], {**d["effects"][2], "who": "union:self_gy+target"}]}
    if (soul := re.fullmatch(r"(?P<it>~|It) deals 3 damage to target player or planeswalker and 3 damage to up to one target creature that player or that "
                             r"planeswalker's controller controls\.", body)) is not None:
        # (Soul of Shandalar: a player must be targeted, a creature needn't, ruling 2014-07-18; a planeswalker's controller is "that player",
        # player_relative.players_of; "It": the card the cost exiled, 608.2h)
        d = _native(ability, ch, cost, f"{soul['it']} deals 3 damage to target player and 3 damage to up to one target creature that player controls.")
        groups = (d or {}).get("targets") or []
        if d is None or len(groups) != 2 or groups[0]["what"] != "player":
            return None
        return {**d, "targets": [{**groups[0], "what": "player_or_planeswalker"}, groups[1]]}
    if body == "For each opponent, you mill a card, then return that card from your graveyard to your hand unless that player pays 3 life.":
        d = _native(ability, ch, cost, "Draw a card.")  # (Sivriss: one opponent at a time, in turn order, ruling 2022-06-10; 118.12a)
        return None if d is None else {**d, "effects": [{"do": "mill_unless100i"}]}
    if body == "Put this card from your hand onto the battlefield tapped and attacking.":
        # (Zareth San: from the hand only, 113.6m; 508.4: you choose whom it attacks, never "declared"; gone from the hand, nothing: rulings 2020-09-25)
        d = _native(ability, ch, cost, "Put this card from your hand onto the battlefield.")
        if d is None or [e.get("who") for e in d["effects"]] != ["self_hand"]:
            return None
        return {**d, "effects": [{**d["effects"][0], "tapped": True, "attacking": True}]}
    if body == "Target creature gains landwalk of each of the land types of the sacrificed land until end of turn.":
        d = _creature_target(_native(ability, ch, cost, "Target creature loses flying until end of turn."))  # (Excavator)
        return None if d is None else {**d, "effects": [{"do": "landwalk_of100i"}]}
    if body == "It deals 2 damage to each player who doesn't have max speed.":
        # (Outpace Oblivion: max speed is speed 4, none is 0, rulings 2025-02-07; player_filter's predicate, read as it resolves, 608.2h)
        from app.rules import player_filter

        d, pred = _native(ability, ch, cost, "It deals 2 damage to each player."), player_filter.parse_pred("doesn't have max speed")
        if d is None or pred is None or [e.get("who") for e in d["effects"]] != ["each_player"]:
            return None
        return {**d, "effects": [{"do": "players_where", "as": "slow100i", "base": "player", "pred": pred}, {**d["effects"][0], "who": "ref:slow100i"}]}
    if body == ('Create a 4/4 Dragon creature token named Reliquary Dragon that\'s all colors. It has flying, lifelink, and "When this token enters, '
                'it deals 3 damage to any target." Activate only as a sorcery.'):
        # (Dragonbroods' Relic: the token's own rules text, 111.4; its enters ability is the token's, 603.6a)
        d = _native(ability, ch, cost, "Draw a card. Activate only as a sorcery.")
        tok: dict[str, Any] = {"name": "Reliquary Dragon", "power": "4", "toughness": "4", "colors": ["W", "U", "B", "R", "G"], "type_line": "Token Creature — Dragon",
                 "text": "Flying\nLifelink\nWhen this creature enters, it deals 3 damage to any target."}
        return None if d is None else {**d, "effects": [{"do": "create_token", "who": "you", "n": 1, "token": tok}]}
    if body == ('Create a 1/2 black Bat creature token with flying. It has "{1}{B}, Sacrifice this token: Return an exiled card named Sengir Nosferatu to '
                'the battlefield under its owner\'s control."'):
        d = _native(ability, ch, cost, "Draw a card.")  # (Sengir Nosferatu: the token's own rules text, 111.4)
        tok = {"name": "Bat", "power": "1", "toughness": "2", "colors": ["B"], "type_line": "Token Creature — Bat",
                 "text": "Flying\n{1}{B}, Sacrifice this creature: Return an exiled card named Sengir Nosferatu to the battlefield under its owner's control."}
        return None if d is None else {**d, "effects": [{"do": "create_token", "who": "you", "n": 1, "token": tok}]}
    if body == "Return an exiled card named Sengir Nosferatu to the battlefield under its owner's control.":
        # (the Bat's: any face-up exiled card with that name, whoever owns it, rulings 2006-09-25 / 2007-05-01; 201.2, 406.3)
        d = _native(ability, ch, cost, "Draw a card.")
        sel = selectors.Selector(card=True, zones=("exile",), extras=("name:Sengir Nosferatu",)).key()
        return None if d is None else {**d, "effects": [{"do": "return_choice", "to": "battlefield", "tapped": False, "under": "owner", "sel": sel, "n": 1,
                                                          "upto": False, "random": False, "label": "card named Sengir Nosferatu"}]}
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


def _with_auras(target: selectors.Selector, auras: selectors.Selector) -> tuple[list[dict[str, Any]], str]:
    from app.rules.static_spell100c import ATTACHED

    return [{"do": "bounce", "who": f"union:target+{ATTACHED}target|{auras.key()}"}], target.key()


def _prepare(**sel: Any) -> tuple[list[dict[str, Any]], str]:
    return [{"do": "prepare", "who": "target"}], selectors.Selector(types=("Creature",), **sel).key()  # (722.3a: no prepare spell, nothing: ruling 2026-03-20)


_BASICS = ["Plains", "Island", "Swamp", "Mountain", "Forest"]  # (205.3i)
_BUILT: dict[str, Callable[[], tuple[list[dict[str, Any]], str | None]]] = {
    "Target creature becomes prepared.": lambda: _prepare(),
    "Target creature that attacked this turn becomes prepared. Activate only as a sorcery.": lambda: _prepare(extras=("attacked_this_turn",)),
    "Destroy target Aura attached to a land.": lambda: ([{"do": "destroy", "who": "target"}], selectors.Selector(subtypes=("Aura",), extras=("attached_land",)).key()),
    # 303.4, 608.2c: the Auras attached to it as it resolves go with it (Equipment stays: Portal ruling 2019-07-12); Reliquary's only yours
    "Return target creature you control and each Aura attached to it to their owners' hands. Activate only during your turn.":
        lambda: _with_auras(selectors.Selector(types=("Creature",), controller="you"), selectors.Selector(subtypes=("Aura",))),
    "Return another target permanent you control and all Auras you control attached to it to their owner's hand. Activate only during your turn.":
        lambda: _with_auras(selectors.Selector(controller="you", other=True), selectors.Selector(subtypes=("Aura",), controller="you")),
    # the card the cost exiled (its first ability is chosen apart, ruling 2008-10-01; not a snow land: nothing)
    "If the exiled card is a snow land, ~ gets +1/+1 until end of turn.":
        lambda: ([{"do": "only_if", "cond": {"object": "cost:exiled", "is": selectors.Selector(types=("Land",), supertypes=("Snow",), card=True).key()}, "skip": 1},
                  {"do": "pump", "who": "self", "p": 1, "t": 1}], None),
    "Put the top card of your graveyard on the bottom of your library.": lambda: ([{"do": "graveyard_bottom100i"}], None),
    # 205.4: a supertype added or taken away for good (611.2a; any land may lose snow, adding it doesn't touch the others: rulings 2006-10-15)
    "Target snow land is no longer snow.": lambda: ([{"do": "supertype100i", "who": "target", "remove": ["Snow"]}], selectors.Selector(types=("Land",), supertypes=("Snow",)).key()),
    "Target nonsnow basic land becomes snow.":
        lambda: ([{"do": "supertype100i", "who": "target", "add": ["Snow"]}], selectors.Selector(types=("Land",), supertypes=("Basic",), not_supertypes=("Snow",)).key()),
    # 305.7: the chosen basic land type replaces the others and their mana abilities (Terraformer rulings 2005-10-01); the lands are fixed as it resolves (611.2c)
    "Choose a basic land type. Each land you control becomes that type until end of turn.":
        lambda: ([{"do": "become", "who": selectors.Selector(types=("Land",), controller="you").key(), "types": [], "duration": "end_of_turn", "land_pick": _BASICS}], None),
    # 701.24d: the library is shuffled even with no card chosen; the cards aren't ordered first (hand_wheel ``shuffled100i``)
    "Shuffle any number of cards from your hand into your library, then draw that many cards.":
        lambda: ([{"do": "hand_to_bottom", "who": "you", "bind_amount": "voucher100i", "any_number": True, "shuffled100i": True},
                  {"do": "shuffle_library", "who": "you"}, {"do": "draw", "who": "you", "n": {"ref_amount": "voucher100i"}}], None),
}


_CONDITIONS = {
    "you've controlled ~ continuously since the beginning of your most recent turn": "controlled_since_turn",  # (302.6's test, any permanent: Rocket Launcher)
    "at least one creature is blocking ~": "blocked_now",  # (a creature blocking it now: not "blocked", which stays after the blocker leaves, 509.1h)
    "the number of other Caves you control plus the number of Cave cards in your graveyard is three or greater": "caves3",  # (Cavernous Maw)
}


def condition(text: str) -> dict[str, Any] | None:
    """restrictions._condition's part: "Activate only if …" wordings read here (602.5: checked as it would be activated)."""
    return {"activated100i": _CONDITIONS[text]} if text in _CONDITIONS else None


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    from app.rules import casting

    card = plan.state.cards.get(ctx.get("source_card") or "")
    if card is None or not card.zone.endswith(":battlefield"):
        return False
    kind = cond["activated100i"]
    if kind == "blocked_now":
        return any(c.zone.endswith(":battlefield") and (c.blocking == card.id or card.id in c.blocking_more) for c in plan.state.cards.values())
    if kind == "caves3":
        you = ctx["controller"]
        caves = sum(1 for c in plan.state.cards.values() if c.id != card.id and plan.in_game(c) and "Cave" in plan.ch(c).subtypes
                    and (c.zone == f"{you}:graveyard" or c.zone.endswith(":battlefield") and c.controller == you))
        return caves >= 3
    return not casting.summoning_sick(plan.state, card)


def graveyard_bottom(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Put the top card of your graveyard on the bottom of your library." (Soldevi Digger): the last card put there (404.2-3, graveyard_order.py)."""
    you = ctx["controller"]
    yard = plan.state.zones.get(f"{you}:graveyard", [])
    if yard:
        plan.do({"type": "move", "card_ids": [yard[-1]], "to": {"player": you, "zone": "library"}, "position": "bottom"}, actor=you)
    return True


def mill_unless(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """For each opponent in turn order (101.4): mill a card, then that player may pay 3 life; unless they did, the card returns to your hand."""
    you = ctx["controller"]
    steps: list[dict[str, Any]] = []
    for j, pid in enumerate(p for p in plan.apnap() if p != you):
        steps += [{"do": "mill", "who": "you", "n": 1, "as": f"siv{j}"}, {"do": "optional_payment", "who": f"player:{pid}", "cost": "Pay 3 life", "bind": f"sivpay{j}"},
                  {"do": "only_if", "cond": {"succeeded": f"sivpay{j}", "negate": True}, "skip": 1}, {"do": "bounce", "who": f"ref:siv{j}"}]
    ctx["effects"][ctx["next"]:ctx["next"]] = steps
    return True


def stench(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """For each land destroyed this way (this_way, 701.8b), 1 damage to its controller unless they pay {2} (118.12a), in APNAP order (101.4)."""
    from app.rules import this_way

    per = this_way.by_controller(plan, ctx, {"ref_count": e["ref_count"], "this_way": "destroyed", "of": selectors.Selector(types=("Land",)).key()})
    steps: list[dict[str, Any]] = []
    for pid in (p for p in plan.apnap() if per.get(p)):
        for _ in range(per[pid]):
            k = f"stench{len(steps)}"
            steps += [{"do": "optional_payment", "who": f"player:{pid}", "cost": "{2}", "bind": k},
                      {"do": "only_if", "cond": {"succeeded": k, "negate": True}, "skip": 1}, {"do": "damage", "who": f"player:{pid}", "n": 1}]
    ctx["effects"][ctx["next"]:ctx["next"]] = steps
    return True


def albatross(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The creatures that dealt damage to the dying creature this turn (the turn's log, 120.3), each destroyed unless its controller pays 2 life."""
    from app.rules import context, history

    refs = context._object_refs(ctx, context.EVENT, was=True)
    oid = refs[0].object_id if refs else ctx.get("source_object")
    sources = {f.source for f in history.log_for(plan).facts if f.kind == "damaged" and f.object_id == oid and f.source}
    order = plan.apnap()
    hit = sorted((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) in sources and plan.ch(c).is_creature),
                 key=lambda c: order.index(c.controller) if c.controller in order else len(order))
    steps: list[dict[str, Any]] = []
    for j, c in enumerate(hit):
        steps += [{"do": "optional_payment", "who": f"player:{c.controller}", "cost": "Pay 2 life", "bind": f"alb{j}"},
                  {"do": "only_if", "cond": {"succeeded": f"alb{j}", "negate": True}, "skip": 1}, {"do": "destroy", "who": f"object:{plan.oid(c)}"}]
    ctx["effects"][ctx["next"]:ctx["next"]] = [*steps, {"do": "no_regen"}] if steps else []
    return True


def supertype(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Layer 4 (613.1d): the target gains or loses a supertype, for as long as it is that object (611.2a, 400.7)."""
    from app.rules import effects, layers

    cards = [c for c in effects._cards(plan, ctx, e["who"]) if plan.state.cards[c].zone.endswith(":battlefield")]
    words = [*(s.lower() for s in e.get("add") or ()), *(f"not {s.lower()}" for s in e.get("remove") or ())]
    if cards:
        layers.add_effect(plan, affected=[plan.oid(c) for c in cards], layer="4", source=ctx.get("source_object"), controller=ctx["controller"],
                          duration="permanent", label=f"{', '.join(words)} ({ctx.get('name', '')})", add_supertypes=list(e.get("add") or ()),
                          remove_supertypes=list(e.get("remove") or ()))
    return True


def landwalk_of(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """702.14a: "[type]walk" for each land type the sacrificed land had as it last existed (608.2h; several on a basic land: ruling 2005-11-01)."""
    from app.rules import effects, values
    from app.rules.combat import LANDWALK

    got = values._object(plan, ctx, "cost:sacrificed")
    # ponytail: a land type with no landwalk keyword in combat.LANDWALK (Gate, Cave …, only by a type-changing effect on a basic land) is skipped
    walks = [] if got is None else [w for t in sorted(got[1].subtypes) if (w := f"{t.lower()}walk") in LANDWALK]
    return effects.grant(plan, ctx, {"do": "grant", "who": "target", "keywords": walks}) if walks else True


PRIMITIVES = {"graveyard_bottom100i": graveyard_bottom, "mill_unless100i": mill_unless, "landwalk_of100i": landwalk_of, "stench100i": stench,
              "albatross100i": albatross, "supertype100i": supertype}
