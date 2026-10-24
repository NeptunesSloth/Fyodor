"""-- trigger lines (wave 100A) -- triggered abilities read as an equivalent native wording plus, where needed, instructions of their own.

* Calculating Lich: "Whenever a creature attacks one of your opponents, that player loses 1 life." — the attack is declared against that opponent
  directly (508.3a; the "opponent" defender is a player, not a planeswalker), so "that player" is the attacking creature's defending player (508.5).
* Invasion of Ulgrotha: "When this Siege enters, it deals 3 damage to any other target …" — "it" is the Siege the trigger is about (608.2k) and
  "any other target" is any target but the Siege (115.4).
* Primordial Plasm: "… another target creature gets +2/+2 and loses all abilities until end of turn." — one effect: +2/+2 (613.4c) and losing all
  abilities (613.1f) from the same resolution, both until end of turn (514.2).
* Spreading Plague: "Whenever a creature enters, destroy all other creatures that share a color with it. They can't be regenerated." — "it" is the
  entering creature as it is as the ability resolves, or as it last existed (608.2h); a colorless one shares no color (105.2c); "other" is other than
  that object (a new object it became is another one, 400.7); all are destroyed at once (701.8a), without regeneration (701.19c).
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

# text (after scripts.self_text) -> (the native wording it reads as, instructions, whether they replace the native effects or follow them)
_AS: dict[str, tuple[str, list[dict[str, Any]], bool]] = {
    "Whenever a creature attacks one of your opponents, that player loses 1 life.":
        ("Whenever a creature attacks one of your opponents, defending player loses 1 life.", [], False),
    "When ~ enters, it deals 3 damage to any other target and you gain 3 life.":
        ("When ~ enters, ~ deals 3 damage to any other target and you gain 3 life.", [], False),
    # Dinrova Horror: "that player" is the owner whose hand it went to (the one player named before)
    "When ~ enters, return target permanent to its owner's hand, then that player discards a card.":
        ("When ~ enters, return target permanent to its owner's hand. Its owner discards a card.", [], False),
    # Carrion Locust: "that player" is the opponent whose graveyard held it, the card's owner (404.2: a card goes to its owner's graveyard)
    "When ~ enters, exile target card from an opponent's graveyard. If it was a creature card, that player loses 1 life.":
        ("When ~ enters, exile target card from an opponent's graveyard. If it was a creature card, its owner loses 1 life.", [], False),
    "At the beginning of combat on your turn, another target creature gets +2/+2 and loses all abilities until end of turn.":
        ("At the beginning of combat on your turn, another target creature gets +2/+2 until end of turn.",
         [{"do": "become", "who": "target", "types": [], "lose_abilities": True, "duration": "end_of_turn"}], False),
    "Whenever a creature enters, destroy all other creatures that share a color with it. They can't be regenerated.":
        ("Whenever a creature enters, destroy it.", [{"do": "plague100a"}, {"do": "destroy", "who": "ref:plague100a"}, {"do": "no_regen"}], True),
    # Saltskitter: "this creature" after it was exiled is the card that left (400.7: the object the exile made), which "it" reads
    "Whenever another creature enters, exile ~. Return ~ to the battlefield under its owner's control at the beginning of the next end step.":
        ("Whenever another creature enters, exile ~. Return it to the battlefield under its owner's control at the beginning of the next end step.", [], False),
    # Ghastlord of Fugue: the revealed hand's owner exiles the card its controller chose (406.1: to exile; nothing here asks who did it)
    "Whenever ~ deals combat damage to a player, that player reveals their hand. You choose a card from it. That player exiles that card.":
        ("Whenever ~ deals combat damage to a player, that player reveals their hand. You choose a card from it. Exile that card.", [], False),
    "Whenever a player casts a spell, they may pay {1}. If the player does, they draw a card at the beginning of the next end step.":
        ("Whenever a player casts a spell, that player may pay {1}. If they do, they draw a card at the beginning of the next end step.", [], False),
    "At the beginning of the upkeep of enchanted artifact's controller, ~ deals 2 damage to that player unless they sacrifice that artifact.":
        ("At the beginning of the upkeep of enchanted artifact's controller, ~ deals 2 damage to that player unless they sacrifice enchanted artifact.",
         [], False),
    "When ~ is turned face up, copy target instant or sorcery spell. You may choose new targets for that copy.":
        ("When ~ is turned face up, copy target instant or sorcery spell. You may choose new targets for the copy.", [], False),
    # Volatile Arsonist: "it" is the creature (608.2k); "and/or" over groups of up to one target each is any of them (115.1, 601.2c)
    **{f"Whenever ~ attacks, it deals {n} damage to each of up to one target creature, up to one target player, and/or up to one target planeswalker.":
       (f"Whenever ~ attacks, ~ deals {n} damage to each of up to one target creature, up to one target player, and up to one target planeswalker.", [], False)
       for n in (1, 2)},
    # Cloaked Cadet: one trigger per Human (603.2c), but only the first each turn (the limit), draws: the ruling's one card for any number
    "Whenever one or more +1/+1 counters are put on one or more Humans you control, draw a card. This ability triggers only once each turn.":
        ("Whenever one or more +1/+1 counters are put on a Human you control, draw a card. This ability triggers only once each turn.", [], False),
    # Tenuous Truce: "Enchant opponent" — the enchanted player is an opponent (303.4)
    "At the beginning of enchanted opponent's end step, you and that player each draw a card.":
        ("At the beginning of enchanted player's end step, you and that player each draw a card.", [], False),
    # Day of the Dragons: "that many" is the creatures exiled, tokens too (the ruling); the exiled cards are linked to its leaves ability (607.2a)
    "When ~ enters, exile all creatures you control. Then create that many 5/5 red Dragon creature tokens with flying.":
        ("When ~ enters, exile all creatures you control. Then create a 5/5 red Dragon creature token with flying for each card exiled this way.", [], False),
}

_MUTAVAULT: dict[str, Any] = {"name": "Mutavault", "power": None, "toughness": None, "colors": [], "type_line": "Token Land",
              "text": "{T}: Add {C}.\n{1}: This land becomes a 2/2 creature with all creature types until end of turn. It's still a land."}
_ANGEL: dict[str, Any] = {"name": "Angel", "power": "3", "toughness": "3", "colors": ["W"], "type_line": "Token Creature — Angel", "text": "Flying"}


def _nettling(d: dict[str, Any]) -> dict[str, Any] | None:
    """Nettling Nuisance: the token the damaged player created is goaded by you for the rest of the game (701.15a: by the ability's controller)."""
    effects = d["effects"]
    if len(effects) != 1 or effects[0].get("do") != "create_token":
        return None
    return {**d, "effects": [{**effects[0], "as": "nuisance100a"}, {"do": "permanent_copy_goad", "who": "ref:nuisance100a"}]}


def _kav(d: dict[str, Any]) -> dict[str, Any] | None:
    """Kav Landseeker: "the end step on your next turn" — an end step of yours in a later turn than this one (never this turn's)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["create_token", "delayed", "deferred:sacrifice"]:
        return None
    return {**d, "effects": [effects[0], {**effects[1], "when": {**effects[1]["when"], "next_turn_only": True}}, effects[2]]}


def _mutavault(d: dict[str, Any]) -> dict[str, Any] | None:
    """Mutable Explorer: a token that's a copy of the card Mutavault (707.2, 111.4: the card's own characteristics — its name, types and rules text), tapped."""
    effects = d["effects"]
    if len(effects) != 1 or effects[0].get("do") != "create_token" or not effects[0].get("tapped"):
        return None
    return {**d, "effects": [{**effects[0], "token": dict(_MUTAVAULT)}]}


def _naturalist(d: dict[str, Any]) -> dict[str, Any] | None:
    """Patient Naturalist: the land card isn't optional ("Put …"); "If you can't" is that no land card was among the milled cards to put."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["mill", "pick_looked", "only_if", "create_token"]:
        return None
    return {**d, "effects": [effects[0], {**effects[1], "optional": False}, *effects[2:]]}


def _emancipation(d: dict[str, Any]) -> dict[str, Any] | None:
    """Soul of Emancipation: one Angel for each target still legal as it resolves, created by that permanent's controller as the destruction
    found it (608.2b: an illegal target gets none; the official ruling: one that wasn't destroyed — a shield counter — still gets one)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["destroy"] or effects[0].get("who") != "target:0":
        return None
    return {**d, "effects": [{"do": "emancipate100a"}, *effects]}


def _dream(d: dict[str, Any]) -> dict[str, Any] | None:
    """Dream Eater: after the surveil, a reflexive ability (603.12) whose target is chosen then; it triggers even when fewer than four
    cards were surveilled (the official ruling)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["surveil"]:
        return None
    back = {"kind": "triggered", "trigger": "reflexive", "effects": [{"do": "bounce", "who": "target"}], "optional": True,
            "target": {"what": "nonland_permanent_opp"}}
    return {**d, "effects": [*effects, {"do": "reflexive", "cond": {"always100a": True}, "ability": back}]}


def _antelope(d: dict[str, Any]) -> dict[str, Any] | None:
    """Graceful Antelope: "you may have target land become a Plains until ~ leaves the battlefield" — optional (decided on resolution, 603.5),
    the land's types replaced (305.7) for as long as the source remains on the battlefield (611.2b; nothing if it has already left)."""
    return {**d, "optional": True} if [e.get("do") for e in d["effects"]] == ["until", "become"] else None


def _boars(d: dict[str, Any]) -> dict[str, Any] | None:
    """Crashing Boars: the defending player (508.5) chooses as it resolves; the chosen creature must block ~ this turn if able (509.1c) —
    not if it's tapped by then (the official ruling), nothing when there's no untapped creature to choose."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["player_chooses", "tap"] or not effects[0].get("as"):
        return None
    return {**d, "effects": [effects[0], {"do": "restrict", "who": "ref:" + effects[0]["as"], "rules": ["must_block_obj:@src"]}]}


def _gravestorm(d: dict[str, Any]) -> dict[str, Any] | None:
    """Gravestorm: when the target opponent doesn't exile a card (or can't: an empty graveyard), you may draw."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["optional_payment", "only_if", "draw"] or effects[1].get("skip") != 1:
        return None
    return {**d, "effects": [effects[0], {**effects[1], "skip": 2}, {"do": "may_rest"}, effects[2]]}


def _upkeep_cost(name: str) -> Any:
    """Egon / Anurid Scavenger / Chisei: an upkeep instruction carried out by its primitive, then the rest unless it was done."""
    def build(d: dict[str, Any]) -> dict[str, Any] | None:
        effects = d["effects"]
        if not effects or effects[0].get("do") != "sacrifice" or effects[0].get("who") != "self":
            return None
        return {**d, "effects": [{"do": name}, {"do": "only_if", "cond": {"flag": name, "negate": True}, "skip": len(effects)}, *effects]}
    return build


def _war_zone(d: dict[str, Any]) -> dict[str, Any] | None:
    """Contested War Zone: "that creature's controller" — who controlled the creature that dealt the damage (its last known information
    once it's gone, 608.2h) gains control of it for good (613.1b). "You" is its current controller (the official ruling)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["draw"] or effects[0].get("who") != "ref:event.controller":
        return None
    return {**d, "effects": [{"do": "gain_control", "who": "self", "to": "ref:event.controller"}]}


def _jurin(d: dict[str, Any]) -> dict[str, Any] | None:
    return {**d, "effects": [{"do": "jurin100a"}]} if [e.get("do") for e in d["effects"]] == ["pump"] else None


def _namor(d: dict[str, Any]) -> dict[str, Any] | None:
    """Namor: "attacks a player who has more life than you" is part of the trigger event, read as attackers are declared (603.2; no
    intervening "if": it isn't asked again as it resolves)."""
    if [e.get("do") for e in d["effects"]] != ["pump"] or (d.get("cond") or {}).get("event") != "attack":
        return None
    return {**d, "cond": {**d["cond"], "while": {"more_life100a": True}}, "effects": [{"do": "namor100a"}]}


def _trapper(d: dict[str, Any]) -> dict[str, Any] | None:
    """Mirkwood Trapper: an intervening "if" (603.4): none of that player's creatures attacks you (attacking a planeswalker or battle of
    yours doesn't count: the official ruling); that player chooses one of the attacking creatures."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["player_chooses", "pump"]:
        return None
    from app.rules import selectors

    sel = selectors.Selector(types=("Creature",), attacking=True).key()
    return {**d, "if": {"not_attacking_you100a": True}, "effects": [{**effects[0], "sel": sel, "label": "attacking creature"}, effects[1]]}


def _linked_gain(n: int) -> Any:
    """Soul Scourge / Laquatus's Champion: "that player" is the player its enters ability targeted (the official ruling: the target of the
    first ability, or, while that ability is still on the stack, its target), noted as that ability went on the stack: ``linked_players100a``."""
    def build(d: dict[str, Any]) -> dict[str, Any] | None:
        if [e.get("do") for e in d["effects"]] != ["gain_life"]:
            return None
        return {**d, "effects": [{"do": "linked_gain100a", "n": n}]}
    return build


# Soul Scourge / Laquatus's Champion: the enters ability whose target the leaves ability's "that player" is (when both are printed on it)
_LINKED = {f"When ~ enters, target player loses {n} life.": f"When ~ leaves the battlefield, that player gains {n} life." for n in (3, 6)}


def _all_players(d: dict[str, Any]) -> dict[str, Any] | None:
    """Master of Barbs / Mindblade Render / Magmatic Galleon: "one or more opponents are dealt noncombat damage" / "your opponents are dealt
    combat damage" / "one or more creatures your opponents control are dealt excess noncombat damage": one trigger for the batch, however many
    were dealt it (603.2c; Mindblade Render's ruling)."""
    cond = d.get("cond") or {}
    return {**d, "cond": {**cond, "all_players": True}} if cond.get("event") == "dealt_damage" else None


def _mindblade(d: dict[str, Any]) -> dict[str, Any] | None:
    """Mindblade Render: an intervening "if" (603.4): a Warrior (anyone's, as it dealt the damage: the ruling) dealt some of that batch's combat
    damage to an opponent."""
    got = _all_players(d)
    return {**got, "if": {"warrior_damage100a": True}} if got is not None else None


def _hornbeetle(d: dict[str, Any]) -> dict[str, Any] | None:
    return {**d, "effects": [{"do": "hornbeetle100a"}, *d["effects"]]} if [e.get("do") for e in d["effects"]] == ["create_token"] else None


def _athlete(d: dict[str, Any]) -> dict[str, Any] | None:
    """Star Athlete: the target's controller chooses as it resolves (118.12: "may … If they don't"); "that player" is that controller. An
    illegal target: nothing happens (608.2b; the ruling)."""
    if [e.get("do") for e in d["effects"]] != ["destroy"]:
        return None
    return {**d, "effects": [{"do": "optional_payment", "who": "target:0", "ask": "sacrifice it (if you don't, it deals 5 damage to you)", "bind": "pay0"},
                             {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1},
                             {"do": "sacrifice", "who": "target:0", "by": "controller"},
                             {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1},
                             {"do": "damage", "who": "target_player_or_controller", "n": 5}]}


def _marauder(d: dict[str, Any]) -> dict[str, Any] | None:
    """Ogre Marauder: 118.12a — the defending player (508.5) may sacrifice a creature as it resolves; if they don't, it can't be blocked."""
    if [e.get("do") for e in d["effects"]] != ["restrict"]:
        return None
    return {**d, "effects": [{"do": "optional_payment", "who": "defending_player", "cost": "Sacrifice a creature", "bind": "pay0"},
                             {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}, *d["effects"]]}


def _vortex(d: dict[str, Any]) -> dict[str, Any] | None:
    """Mana Vortex: 118.12a — you may sacrifice a land as the cast trigger resolves; if you don't, the spell is countered (the ruling)."""
    if d.get("trigger") != "cast_self":
        return None
    return {**d, "effects": [{"do": "optional_payment", "who": "you", "cost": "Sacrifice a land", "bind": "pay0"},
                             {"do": "only_if", "cond": {"succeeded": "pay0", "negate": True}, "skip": 1}, {"do": "counter", "who": "event_spell"}]}


def _antagonism(d: dict[str, Any]) -> dict[str, Any] | None:
    """Antagonism: "unless one of their opponents was dealt damage this turn" — a condition read as it resolves (the turn's log, 608.2i)."""
    if [e.get("do") for e in d["effects"]] != ["damage"]:
        return None
    return {**d, "effects": [{"do": "only_if", "cond": {"unhurt_opponents100a": True}, "skip": 1}, *d["effects"]]}


def _karmic(d: dict[str, Any]) -> dict[str, Any] | None:
    """Karmic Justice: a destroy (701.8, an effect's: not a sacrifice, the ruling) by a spell or ability an opponent controls — the player
    whose effect it was (``by``) is "that opponent", whose permanents are the targets (triggers.bind_that_player)."""
    from app.rules import selectors

    if (d.get("cond") or {}).get("event") != "destroyed":
        return None
    return {**d, "cond": {**d["cond"], "cause": "opponent"}, "target": {"what": selectors.Selector(controller=selectors.THAT_PLAYER).key()}}


def _here(d: dict[str, Any]) -> dict[str, Any]:
    """Myr Servitor: an intervening "if" (603.4) on the source itself, still that object on the battlefield as it resolves (the ruling)."""
    return {**d, "if": {"object": "self", "test": "on_battlefield"}}


def _scales(d: dict[str, Any]) -> dict[str, Any] | None:
    return {**d, "effects": [{"do": "scales100a"}, {"do": "bounce", "who": "ref:scales100a"}]} if [e.get("do") for e in d["effects"]] == ["bounce"] else None


def _death_match(d: dict[str, Any]) -> dict[str, Any] | None:
    """Death Match: the entering creature's controller chooses the target as it goes on the stack (603.3d: a player other than its
    controller) and, as it resolves, whether to have it happen (118.12-style "may have")."""
    from app.rules import selectors

    if [e.get("do") for e in d["effects"]] != ["pump"] or (d.get("cond") or {}).get("event") != "enter":
        return None
    return {**d, "cond": {**d["cond"], "sel": selectors.Selector(types=("Creature",)).key()}, "target_choice": "event_player",
            "effects": [{"do": "optional_payment", "who": "ref:event.controller", "ask": "give it -3/-3", "bind": "pay0"},
                                                             {"do": "only_if", "cond": {"succeeded": "pay0"}, "skip": 1}, *d["effects"]]}


def _gate(d: dict[str, Any]) -> dict[str, Any] | None:
    """Gate to the Aether: an artifact, creature, enchantment, or land card (not a planeswalker or battle card)."""
    from app.rules import selectors

    effects = d["effects"]
    if [e.get("do") for e in effects] != ["look_top", "only_if", "pick_looked"]:
        return None
    sel = selectors.Selector(card=True, types=("Artifact", "Creature", "Enchantment", "Land"), zones=()).key()
    return {**d, "effects": [effects[0], {**effects[1], "cond": {**effects[1]["cond"], "is": sel}}, effects[2]]}


def _trap(d: dict[str, Any]) -> dict[str, Any] | None:
    """Entangling Trap: "If you won" — the clash the trigger is about (the event's ``amount``)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["tap", "stay_tapped"]:
        return None
    return {**d, "effects": [effects[0], {"do": "only_if", "cond": {"clash_won100a": True}, "skip": 1}, effects[1]]}


def _suspected(d: dict[str, Any]) -> dict[str, Any] | None:
    """Clandestine Meddler: "suspected creatures" — those with the designation (701.60a), as the attack is declared."""
    from app.rules import selectors

    cond = d.get("cond") or {}
    if cond.get("event") != "attack" or not cond.get("sel"):
        return None
    sel = selectors.from_key(cond["sel"])
    return {**d, "cond": {**cond, "sel": selectors.replace(sel, extras=(*sel.extras, "suspected")).key()}}


def _truce(d: dict[str, Any]) -> dict[str, Any] | None:
    """Tenuous Truce: you attack the enchanted player (or a planeswalker they control), or they attack you (or one of yours): ``truce100a``."""
    cond = d.get("cond") or {}
    if cond.get("event") != "you_attack" or cond.get("defender") != "enchanted_player":
        return None
    return {**d, "cond": {**cond, "player": "any", "defender": "truce100a"}}


_GABRIEL = ["flying", "first strike", "trample", "rampage 3"]


def _gabriel(d: dict[str, Any]) -> dict[str, Any] | None:
    """Gabriel Angelfire: the choice is made as it resolves (608.2d), the ability lasts until your next upkeep (delayed.DURATIONS)."""
    effects = d["effects"]
    if [e.get("do") for e in effects] != ["until", "grant"]:
        return None
    options = [{"label": kw[0].upper() + kw[1:], "effects": [effects[0], {**effects[1], "keywords": [], "abilities": ["Rampage 3"]} if kw == "rampage 3"
                                                              else {**effects[1], "keywords": [kw]}]} for kw in _GABRIEL]
    return {**d, "effects": [{"do": "choose_effect", "who": "self", "options": options}]}


_PIRATE = 'that player creates a 4/2 red Pirate creature token with "This token can\'t block."'
# text (after scripts.self_text) -> (the native wording, how its definition is completed)
_BUILD: dict[str, tuple[str, Any]] = {
    f"Whenever one or more Faeries you control deal combat damage to a player, {_PIRATE} The token is goaded for the rest of the game.":
        (f"Whenever one or more Faeries you control deal combat damage to a player, {_PIRATE}", _nettling),
    "When ~ enters, create a Lander token. At the beginning of the end step on your next turn, sacrifice that token.":
        ("When ~ enters, create a Lander token. At the beginning of your next end step, sacrifice that token.", _kav),
    "When ~ enters, create a tapped Mutavault token.": ("When ~ enters, create a tapped Treasure token.", _mutavault),
    "When ~ enters, mill three cards. Put a land card from among the milled cards into your hand. If you can't, create a Treasure token.":
        ("When ~ enters, mill three cards. You may put a land card from among the milled cards into your hand. If you don't, create a Treasure token.",
         _naturalist),
    "When ~ enters, destroy up to three other target nonland permanents. For each of those permanents, its controller creates a 3/3 white Angel "
    "creature token with flying.": ("When ~ enters, destroy up to three other target nonland permanents.", _emancipation),
    "When ~ enters, surveil 4. When you do, you may return target nonland permanent an opponent controls to its owner's hand.":
        ("When ~ enters, surveil 4.", _dream),
    "Whenever ~ deals combat damage to a player, you may have target land become a Plains until ~ leaves the battlefield.":
        ("Whenever ~ deals combat damage to a player, target land becomes a Plains for as long as ~ remains on the battlefield.", _antelope),
    "Whenever ~ attacks, defending player chooses an untapped creature they control. That creature blocks ~ this turn if able.":
        ("Whenever ~ attacks, defending player chooses an untapped creature they control. Tap that creature.", _boars),
    "At the beginning of your upkeep, target opponent may exile a card from their graveyard. If that player doesn't, you may draw a card.":
        ("At the beginning of your upkeep, target opponent may exile a card from their graveyard. If they don't, you draw a card.", _gravestorm),
    "At the beginning of your upkeep, exile two cards from your graveyard. If you can't, sacrifice ~ and draw a card.":
        ("At the beginning of your upkeep, sacrifice ~ and draw a card.", _upkeep_cost("egon100a")),
    "At the beginning of your upkeep, sacrifice ~ unless you put a card from your graveyard on the bottom of your library.":
        ("At the beginning of your upkeep, sacrifice ~.", _upkeep_cost("scavenger100a")),
    "At the beginning of your upkeep, sacrifice ~ unless you remove a counter from a permanent you control.":
        ("At the beginning of your upkeep, sacrifice ~.", _upkeep_cost("chisei100a")),
    "At the beginning of your upkeep, choose flying, first strike, trample, or rampage 3. ~ gains that ability until your next upkeep.":
        ("At the beginning of your upkeep, ~ gains flying until your next upkeep.", _gabriel),
    "Whenever a creature deals combat damage to you, that creature's controller gains control of ~.":
        ("Whenever a creature deals combat damage to you, that creature's controller draws a card.", _war_zone),
    "Whenever ~ attacks, each creature you control attacking a player gets +1/+0 until end of turn for each creature that player controls.":
        ("Whenever ~ attacks, creatures you control get +1/+0 until end of turn.", _jurin),
    "Whenever ~ attacks a player who has more life than you, other creatures you control attacking that player get +2/+0 until end of turn.":
        ("Whenever ~ attacks a player, creatures you control get +2/+0 until end of turn.", _namor),
    "Whenever a player attacks, if they aren't attacking you, that player chooses an attacking creature. It gets +2/+0 until end of turn.":
        ("Whenever a player attacks, that player chooses a creature they control. It gets +2/+0 until end of turn.", _trapper),
    **{ltb: (ltb.replace("that player gains", "you gain"), _linked_gain(n)) for n, ltb in zip((3, 6), _LINKED.values(), strict=True)},
    "Whenever one or more opponents are dealt noncombat damage, creatures you control get +1/+0 until end of turn.":
        ("Whenever an opponent is dealt noncombat damage, creatures you control get +1/+0 until end of turn.", _all_players),
    "Whenever your opponents are dealt combat damage, if any of that damage was dealt by a Warrior, you draw a card and you lose 1 life.":
        ("Whenever an opponent is dealt combat damage, you draw a card and you lose 1 life.", _mindblade),
    "At the beginning of your end step, create a 1/1 green Insect creature token for each +1/+1 counter you've put on creatures under your control "
    "this turn.": ("At the beginning of your end step, create a 1/1 green Insect creature token.", _hornbeetle),
    "Whenever ~ attacks, choose up to one target nonland permanent. Its controller may sacrifice it. If they don't, ~ deals 5 damage to that player.":
        ("Whenever ~ attacks, destroy up to one target nonland permanent.", _athlete),
    'Whenever ~ attacks, it gains "~ can\'t be blocked" until end of turn unless defending player sacrifices a creature of their choice.':
        ('Whenever ~ attacks, it gains "This creature can\'t be blocked" until end of turn.', _marauder),
    "At the beginning of your upkeep, sacrifice ~ unless you exile the top creature card of your graveyard.":
        ("At the beginning of your upkeep, sacrifice ~.", _upkeep_cost("ghoul100a")),
    "When you attack enchanted opponent or a planeswalker they control or when they attack you or a planeswalker you control, sacrifice ~.":
        ("When you attack enchanted player, sacrifice ~.", _truce),
    "Whenever a spell or ability an opponent controls destroys a noncreature permanent you control, you may destroy target permanent that opponent "
    "controls.": ("Whenever a noncreature permanent you control is destroyed, you may destroy target permanent.", _karmic),
    "At the beginning of your upkeep, if ~ is on the battlefield, each player returns all cards named Myr Servitor from their graveyard to the battlefield.":
        ("At the beginning of your upkeep, return all cards named Myr Servitor from all graveyards to the battlefield under their owners' control.", _here),
    "At the beginning of each player's upkeep, return to its owner's hand each creature that player controls with power greater than the number of cards "
    "in their hand.": ("At the beginning of each player's upkeep, return each creature that player controls to its owner's hand.", _scales),
    "Whenever a creature enters, that creature's controller may have target creature of their choice get -3/-3 until end of turn.":
        ("Whenever a creature an opponent controls enters, target creature gets -3/-3 until end of turn.", _death_match),
    "At the beginning of each player's upkeep, that player reveals the top card of their library. If it's an artifact, creature, enchantment, or land "
    "card, the player may put it onto the battlefield.": ("At the beginning of each player's upkeep, that player reveals the top card of their library. If it's "
                                                          "a creature card, that player may put it onto the battlefield.", _gate),
    # Fearless Swashbuckler: an intervening "if" (603.4) on the creatures declared as attackers (event.objects, ``min_attackers``)
    "Whenever you attack, if a Pirate and a Vehicle attacked this combat, draw three cards, then discard two cards.":
        ("Whenever you attack with one or more creatures, draw three cards, then discard two cards.", lambda d: {**d, "if": {"pirate_vehicle100a": True}}),
    "Whenever you clash and win, you may draw a card.": ("Whenever you clash, you may draw a card.", lambda d: {**d, "if": {"clash_won100a": True}}),
    "Whenever you clash, tap target creature an opponent controls. If you won, that creature doesn't untap during its controller's next untap step.":
        ("Whenever you clash, tap target creature an opponent controls. That creature doesn't untap during its controller's next untap step.", _trap),
    "When you cast this spell, counter it unless you sacrifice a land.": ("When you cast this spell, draw a card.", _vortex),
    "At the beginning of each player's end step, ~ deals 2 damage to that player unless one of their opponents was dealt damage this turn.":
        ("At the beginning of each player's end step, ~ deals 2 damage to that player.", _antagonism),
    "Whenever one or more suspected creatures you control attack, surveil 1.": ("Whenever one or more creatures you control attack, surveil 1.", _suspected),
    "Whenever one or more creatures your opponents control are dealt excess noncombat damage, create a Treasure token.":
        ("Whenever a creature an opponent controls is dealt excess noncombat damage, create a Treasure token.", _all_players),
}


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts, trigger_attacking_player65, trigger_leaf51_staged

    if ability.kind != "triggered":
        return None
    if ability.text in (trigger_leaf51_staged.DJINN, trigger_attacking_player65.TEXT):  # staged exact modules (Indentured Djinn, Contested Game Ball)
        staged = trigger_leaf51_staged if ability.text == trigger_leaf51_staged.DJINN else trigger_attacking_player65
        return staged.definition(ability, ch)
    text = scripts.self_text(ability.text, ch.name)
    if (ltb := _LINKED.get(text)) is not None:  # the enters ability notes its target player (triggers._put) only when the leaves ability is printed too
        native = scripts.define(replace(ability, text="When ~ enters, target player loses 1 life."), ch)
        linked = any(scripts.self_text(a.text, ch.name) == ltb for a in ch.abilities)
        return {**native, "effects": [{**native["effects"][0], "n": int(text.split()[-2])}], "link_player100a": True} if native and linked else None
    if (built := _BUILD.get(text)) is not None:
        native = scripts.define(replace(ability, text=built[0]), ch)
        return built[1](native) if native is not None else None
    found = _AS.get(text)
    if found is None:
        return None
    native = scripts.define(replace(ability, text=found[0]), ch)
    if native is None:
        return None
    if found[2]:
        return {**native, "effects": list(found[1])}
    return {**native, "effects": [*native["effects"], *found[1]]} if found[1] else native


def plague(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Spreading Plague: bind every other creature on the battlefield sharing a color with the entering creature (as it is, or last existed)."""
    from app.rules import context

    got = context.info(plan, ctx, context.EVENT)
    refs = context._object_refs(ctx, context.EVENT)
    colors = set(got[1].colors) if got is not None else set()
    oid = refs[0].object_id if refs else None
    victims = [c.id for c in plan.state.cards.values() if colors and c.zone.endswith(":battlefield") and plan.in_game(c)
               and plan.oid(c) != oid and (o := plan.ch(c)).is_creature and o.colors & colors]
    context.bind_objects(plan, ctx, "plague100a", victims)
    return True


def emancipate(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Soul of Emancipation: before the destruction, each legal target's controller; the Angels follow it (one creation per player)."""
    from app.rules import effects

    counts: dict[str, int] = {}
    for t in effects.target_refs(ctx, "target:0"):
        card = plan.state.cards.get(t["id"])
        if card is not None and card.zone.endswith(":battlefield") and plan.oid(card) == t.get("object_id"):
            counts[card.controller] = counts.get(card.controller, 0) + 1
    angels = [{"do": "create_token", "who": f"player:{pid}", "n": n, "token": dict(_ANGEL)} for pid, n in counts.items()]
    at = ctx["next"] + 1  # after the destroy instruction that follows this one
    ctx["effects"][at:at] = angels
    return True


def _attackers(plan: Any, pid: str) -> dict[str, list[str]]:
    """The creatures ``pid`` controls attacking a player (not a planeswalker or battle), by that player (508.5)."""
    out: dict[str, list[str]] = {}
    for c in plan.state.cards.values():
        t = c.attacking
        if t is not None and t.kind == "player" and c.controller == pid and c.zone.endswith(":battlefield") and plan.in_game(c) and plan.ch(c).is_creature:
            out.setdefault(str(t.id), []).append(c.id)
    return out


def _pump(plan: Any, ctx: dict[str, Any], groups: list[tuple[list[str], int]]) -> None:
    from app.rules import context

    pumps = []
    for i, (ids, n) in enumerate(groups):
        if ids and n:
            context.bind_objects(plan, ctx, f"pump100a_{i}", ids)
            pumps.append({"do": "pump", "who": f"ref:pump100a_{i}", "p": n, "t": 0})
    ctx["effects"][ctx["next"]:ctx["next"]] = pumps


def jurin(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Jurin, Leading the Charge: the attackers and each player's creatures counted as it resolves (608.2h), a fixed +N/+0 (613.4c)."""
    creatures = lambda pid: sum(1 for c in plan.state.cards.values() if c.controller == pid and c.zone.endswith(":battlefield")  # noqa: E731
                                and plan.in_game(c) and plan.ch(c).is_creature)
    _pump(plan, ctx, [(ids, creatures(pid)) for pid, ids in _attackers(plan, ctx["controller"]).items()])
    return True


def namor(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Namor, Atlantean King: "that player" is the one it attacked as it triggered (the event's defended player, even if Namor has left
    combat since); "other" creatures: not Namor (the object it is)."""
    pid = (ctx.get("event") or {}).get("defended")
    me = ctx.get("source_card")
    ids = [c for c in _attackers(plan, ctx["controller"]).get(str(pid), []) if c != me]
    _pump(plan, ctx, [(ids, 2)])
    return True


def linked_gain(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Soul Scourge / Laquatus's Champion: the player its enters ability targeted gains the life. More than one such player (its enters
    ability triggered twice: Panharmonicon) is not settled by any ruling: resolved by hand."""
    from app.game.rules_state import DecisionOption
    from app.rules.plan import decide

    players = list(dict.fromkeys(plan.rules.linked_players100a.get(ctx.get("source_object") or "", [])))
    if len(players) > 1:
        names = ", ".join(plan.name(p) for p in players)
        decide(plan, player=ctx["controller"], kind="manual_resolution", options=[DecisionOption(id="done", label="Done")],
               prompt=f"{ctx.get('name') or 'It'}: its enters ability targeted {names}. Resolve which of them gains {e['n']} life by hand, then press Done.",
               resume={"step": "linked_gain100a", "ctx": ctx})
        return False
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "gain_life", "who": f"player:{p}", "n": e["n"]} for p in players]
    return True


def hornbeetle(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Iridescent Hornbeetle: the +1/+1 counters you put (122.6, entering with them included) on creatures you controlled this turn, as the
    turn's log has them (the ruling: wherever those creatures are now); that many tokens."""
    from app.rules.history import log_for

    me = ctx["controller"]
    n = sum(f.amount for f in log_for(plan, False).facts
            if f.kind == "counters" and f.counter == "+1/+1" and f.actor == me and f.player == me and "Creature" in f.types)
    ctx["effects"][ctx["next"]] = {**ctx["effects"][ctx["next"]], "n": n}
    return True


def ghoul(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Barrow Ghoul: "the top creature card of your graveyard" — the one put there most recently (the official ruling; 404.2: the last in the
    zone, graveyard_order asks the owner to arrange simultaneous arrivals while this card is on the battlefield)."""
    from app.rules import context

    top = next((c for c in reversed(_graveyard(plan, ctx["controller"])) if plan.ch(plan.state.cards[c]).is_creature), None)
    if top is None:
        context.bind_flag(ctx, "ghoul100a", False)
        return True
    return _ask(plan, ctx, "ghoul100a", "exile the top creature card of your graveyard (none: sacrifice it)", _card_options(plan, [top]), 0, 1)


def scales(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Noetic Scales: that player's creatures with power greater than the cards in their hand, both read as it resolves (the ruling, 608.2h)."""
    from app.rules import context, selectors

    pid = next(iter((ctx.get("event") or {}).get("players") or []), None)
    hand = len(plan.state.zones.get(f"{pid}:hand", []))
    big = [c.id for c in plan.state.cards.values() if c.controller == pid and c.zone.endswith(":battlefield") and plan.in_game(c)
           and (o := plan.ch(c)).is_creature and (selectors._stat(o, "power") or 0) > hand]
    context.bind_objects(plan, ctx, "scales100a", big)
    return True


def _done(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    effects.continue_effects(plan, d.resume["ctx"])


def holds(plan: Any, ctx: dict[str, Any], cond: dict[str, Any]) -> bool:
    me = ctx["controller"]
    if cond.get("more_life100a"):  # Namor: the player it attacks (as attackers are declared) has more life than you
        t = getattr(plan.state.cards.get(ctx.get("source_card") or ""), "attacking", None)
        return t is not None and t.kind == "player" and t.id in plan.state.players and plan.state.players[t.id].life > plan.state.players[me].life
    if cond.get("not_attacking_you100a"):  # Mirkwood Trapper: no creature attacks you (a planeswalker or battle of yours doesn't count)
        return not any(c.attacking is not None and c.attacking.kind == "player" and c.attacking.id == me and c.zone.endswith(":battlefield")
                       for c in plan.state.cards.values())
    if cond.get("unhurt_opponents100a"):  # Antagonism: no opponent of that player (the end step's) was dealt damage this turn
        from app.rules.history import log_for

        hurt = {f.player for f in log_for(plan, False).facts if f.kind == "damage" and f.amount > 0}
        return not hurt - set((ctx.get("event") or {}).get("players") or [])
    if cond.get("pirate_vehicle100a"):  # Fearless Swashbuckler: among the attackers, as they are or last existed (one Pirate Vehicle is both: the ruling)
        from app.rules import triggers

        subs = {t for o in (ctx.get("event") or {}).get("objects") or [] if (got := triggers._object_then(plan, o.get("card"), o.get("object_id")))
                for t in got[1].subtypes}
        return {"Pirate", "Vehicle"} <= subs
    if cond.get("clash_won100a"):  # Sylvan Echoes / Entangling Trap: you won the clash the trigger is about (701.30d)
        return int((ctx.get("event") or {}).get("amount") or 0) == 1
    if cond.get("warrior_damage100a"):  # Mindblade Render: this batch's combat damage to an opponent, a Warrior's (as it dealt it, 608.2i)
        from app.rules.history import log_for

        batch = int((ctx.get("event") or {}).get("batch") or 0)
        return any(f.kind == "damage" and f.combat and f.batch == batch and f.player != me and "Warrior" in f.source_subtypes
                   for f in log_for(plan, False).facts)
    return bool(cond.get("always100a"))  # Dream Eater: the surveil always happened (603.12)


def _graveyard(plan: Any, pid: str) -> list[str]:
    return list(plan.state.zones.get(f"{pid}:graveyard", []))


def _ask(plan: Any, ctx: dict[str, Any], step: str, prompt: str, options: list[Any], least: int, most: int) -> bool:
    from app.rules.plan import decide

    decide(plan, player=ctx["controller"], kind="choose_cards", prompt=f"{ctx.get('name') or 'It'}: {prompt}", options=options,
           min_choices=least, max_choices=most, resume={"step": step, "ctx": ctx})
    return False


def _card_options(plan: Any, cards: list[str]) -> list[Any]:
    from app.game.rules_state import DecisionOption

    return [DecisionOption(id=c, label=plan.state.cards[c].name or "Card", card_id=c) for c in cards]


def egon(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Egon, God of Death: "Exile two cards from your graveyard. If you can't, …" — with two or more cards two must be exiled (no choice to
    decline); with one, none is (the official rulings: you can't exile two, so the rest happens)."""
    from app.rules import context

    gy = _graveyard(plan, ctx["controller"])
    if len(gy) < 2:
        context.bind_flag(ctx, "egon100a", False)
        return True
    if len(gy) == 2:
        _exile_now(plan, ctx, gy, "egon100a")
        return True
    return _ask(plan, ctx, "egon100a", "exile two cards from your graveyard", _card_options(plan, gy), 2, 2)


def _exile_now(plan: Any, ctx: dict[str, Any], cards: list[str], flag: str) -> None:
    from app.rules import context

    context.bind_objects(plan, ctx, "egon_cards100a", cards)
    context.bind_flag(ctx, flag, bool(cards))
    ctx["effects"][ctx["next"]:ctx["next"]] = [{"do": "exile", "who": "ref:egon_cards100a"}]


def scavenger(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Anurid Scavenger: "… unless you put a card from your graveyard on the bottom of your library" — the controller may (118.12a: none, an
    empty graveyard, is not doing it); the card goes to the bottom of its owner's library (the controller's own graveyard)."""
    from app.rules import context

    gy = _graveyard(plan, ctx["controller"])
    if not gy:
        context.bind_flag(ctx, "scavenger100a", False)
        return True
    return _ask(plan, ctx, "scavenger100a", "put a card from your graveyard on the bottom of your library (none: sacrifice it)",
                _card_options(plan, gy), 0, 1)


def _counter_options(plan: Any, pid: str) -> dict[str, tuple[str, str]]:
    from app.rules import cost_payment

    mine = [c.id for c in plan.state.cards.values() if c.zone == f"{pid}:battlefield" and plan.in_game(c) and any(n > 0 for n in c.counters.values())]
    return cost_payment.counter_tokens(plan, mine)


def chisei(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Chisei, Heart of Oceans: "… unless you remove a counter from a permanent you control" — any one counter of any kind on any one of
    them (122.8), or none (then it's sacrificed)."""
    from app.game.rules_state import DecisionOption
    from app.rules import context

    tokens = _counter_options(plan, ctx["controller"])
    if not tokens:
        context.bind_flag(ctx, "chisei100a", False)
        return True
    seen: dict[tuple[str, str], str] = {}
    for t, key in tokens.items():
        seen.setdefault(key, t)  # one choice per permanent and kind of counter
    options = [DecisionOption(id=t, label=f"{kind} counter on {plan.state.cards[cid].name or 'it'}", card_id=cid) for (cid, kind), t in seen.items()]
    return _ask(plan, ctx, "chisei100a", "remove a counter from a permanent you control (none: sacrifice it)", options, 0, 1)


def resume(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.game.errors import ActionError
    from app.rules import context, counter_removal_results, effects

    ctx, step = d.resume["ctx"], d.resume["step"]
    valid = {o.id for o in d.options}
    if not set(chosen) <= valid or not d.min_choices <= len(chosen) <= d.max_choices or len(set(chosen)) != len(chosen):
        raise ActionError("Choose from the offered options")
    pid = ctx["controller"]
    if step in ("egon100a", "ghoul100a"):
        _exile_now(plan, ctx, [c for c in chosen if c in _graveyard(plan, pid)], step)
    elif step == "scavenger100a":
        cards = [c for c in chosen if c in _graveyard(plan, pid)]
        for cid in cards:
            plan.do({"type": "move", "card_ids": [cid], "to": {"player": plan.state.cards[cid].owner, "zone": "library"}, "position": "bottom"}, actor=pid)
        context.bind_flag(ctx, "scavenger100a", bool(cards))
    else:
        tokens = _counter_options(plan, pid)
        picked = [tokens[t] for t in chosen if t in tokens]
        for cid, kind in picked:
            counter_removal_results.remove(plan, cid, kind, 1, by=pid)
        context.bind_flag(ctx, "chisei100a", bool(picked))
    effects.continue_effects(plan, ctx)


# the staged exact modules wired here (Contested Game Ball, Indentured Djinn)
from app.rules import trigger_attacking_player65 as _ball65  # noqa: E402
from app.rules import trigger_leaf51_staged as _leaf51  # noqa: E402

PRIMITIVES = {"plague100a": plague, "emancipate100a": emancipate, "egon100a": egon, "scavenger100a": scavenger, "chisei100a": chisei,
              "jurin100a": jurin, "namor100a": namor, "hornbeetle100a": hornbeetle, "ghoul100a": ghoul, "scales100a": scales, "linked_gain100a": linked_gain, "trigger_leaf51_djinn_draws": _leaf51.djinn_draws,
              **_ball65.PRIMITIVES}
RESUME = {"egon100a": resume, "scavenger100a": resume, "chisei100a": resume, "ghoul100a": resume, "linked_gain100a": _done, "trigger_leaf51_djinn_count": _leaf51.resume_djinn}
