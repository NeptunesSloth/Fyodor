"""-- xdamage (wave 100E) -- exact Oracle wordings of damage sized by a value and of X values that the sentence grammar doesn't read.

Each entry is one ability's whole text (``~`` for the card's name), read only when it matches exactly; it is built from what the grammar
already reads for its parts (scripts.parse_effects) and from existing primitives, so the engine carries it out with its usual machinery.
Any other wording stays unsupported (refuse rather than guess)."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

Parsed = tuple[list[dict[str, Any]], Any, bool]


def _p(text: str) -> Parsed:
    from app.rules import scripts

    got = scripts.parse_effects(text)
    if got is None:
        raise AssertionError(f"xdamage100e: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


def _reflexive(effects: list[dict[str, Any]]) -> dict[str, Any]:
    found = [e for e in effects if e.get("do") == "reflexive"]
    assert len(found) == 1
    return found[0]


_AMASSED: dict[str, Any] = {"value": {"live_ref_count": "army100e"}, "op": ">=", "n": 0}  # (701.47b: always amassed)


def _minsc() -> Parsed:
    """Minsc & Boo, Timeless Heroes −2 (603.12, 608.2h): the reflexive ability reads the sacrificed creature as it last existed (its event
    object): X is its power, and "If the sacrificed creature was a Hamster" its subtypes then. The draw is part of the reflexive ability (the
    ruling of 2022-06-10: with no legal target, no cards are drawn)."""
    effects, target, optional = _p("Sacrifice a creature. When you do, ~ deals X damage to any target, where X is that creature's power.")
    ability = _reflexive(effects)["ability"]
    assert ability["effects"] == [{"do": "damage", "who": "target", "n": {"power": "event"}}]
    ability["effects"] += [{"do": "only_if", "cond": {"object": "event", "is": 'sel:{"subtypes":["Hamster"]}'}, "skip": 1},
                           {"do": "draw", "who": "you", "n": {"power": "event"}}]
    return effects, target, optional


def _ajani() -> Parsed:
    """Ajani, Nacatl Avenger 0: one reflexive ability for each Cat Warrior created this way (the 2024-06-07 rulings), with an intervening
    "if" (603.4): it triggers only if you control a red permanent other than Ajani, and does nothing unless you still do as it resolves."""
    from app.rules import conditions

    effects, target, optional = _p("Create a 2/1 white Cat Warrior creature token. When you do, ~ deals damage equal to the number of "
                                   "creatures you control to any target.")
    cond = conditions.parse("you control a red permanent other than ~")
    assert cond is not None
    ability = _reflexive(effects)["ability"]
    ability["if"] = cond
    ability["effects"] = [{"do": "only_if", "cond": cond, "skip": len(ability["effects"])}, *ability["effects"]]
    return effects, target, optional


def _amass_reflexive(sub: str, n: int, rest: str) -> Parsed:
    """"Amass Orcs 2. When you do, … where X is the amassed Army's power." (Foray of Orcs): 701.47b — you amassed even if some of it was
    impossible, so the reflexive ability (603.12) always triggers; its event object is the amassed Army (701.47c), whose power X is as it
    resolves (as it last existed if it left, 608.2h). Its target is chosen as it is put on the stack (the 2023-06-16 ruling)."""
    effects = [{"do": "amass", "sub": sub, "n": n, "as": "army100e"}]
    body, b_target, b_optional = _p(rest)
    from app.rules.scripts import target_fields

    effects.append({"do": "reflexive", "cond": _AMASSED, "lki": "army100e",
                    "ability": {"kind": "triggered", "trigger": "reflexive", "effects": body, "optional": b_optional, **target_fields(b_target)}})
    return effects, None, False


def _foray() -> Parsed:
    effects, target, optional = _amass_reflexive("Orc", 2, "~ deals 1 damage to target creature an opponent controls.")
    ability = _reflexive(effects)["ability"]
    assert ability["effects"] == [{"do": "damage", "who": "target", "n": 1}]
    ability["effects"][0]["n"] = {"power": "event"}
    return effects, target, optional


def _brutality() -> Parsed:
    """Widespread Brutality: "Amass Zombies 2, then the Army you amassed deals damage equal to its power to each non-Army creature." — the
    Army chosen (701.47c) is the source (120.3: its own deathtouch / lifelink count), its power as the damage is dealt (608.2h)."""
    each = _p("~ deals 1 damage to each non-Army creature.")[0]
    assert len(each) == 1 and each[0]["do"] == "damage"
    return [{"do": "amass", "sub": "Zombie", "n": 2, "as": "army100e"},
            {**each[0], "n": {"power": "ref:army100e"}, "src": "ref:army100e"}], None, False


def _surrounded() -> Parsed:
    """Surrounded by Orcs: "Amass Orcs 3, then target player mills X cards, where X is the amassed Army's power." (701.47c, 608.2h)."""
    mill, target, _ = _p("Target player mills a card.")
    assert len(mill) == 1 and mill[0]["do"] == "mill" and mill[0]["n"] == 1
    return [{"do": "amass", "sub": "Orc", "n": 3, "as": "army100e"}, {**mill[0], "n": {"power": "ref:army100e"}}], target, False


def _pumpkin() -> Parsed:
    """Pumpkin Bombs: the draw, the counter, then damage equal to its fuse counters (as it last existed if it left: the 2025-09-19 ruling)
    to the target opponent, who then gains control of it (608.2c: "They" is that opponent)."""
    first = _p("Draw three cards, then put a fuse counter on ~.")[0]
    hit, target, _ = _p("~ deals damage equal to the number of fuse counters on ~ to target opponent.")
    give = _p("Target opponent gains control of ~.")[0]
    assert target == "opponent" and give == [{"do": "gain_control", "who": "self", "to": "target"}]
    return [*first, *hit, *give], target, False


def _reactor() -> Parsed:
    """Dragonspark Reactor: one damage instruction to the target player and "that much" to up to one target creature (the same amount, dealt
    at once: 120.3, 608.2h, its charge counters as it last existed — it was sacrificed as the cost). With one target illegal, the other is
    still dealt damage (the 2022-02-18 ruling, 608.2b)."""
    effects, target, optional = _p("~ deals 3 damage to target player and 3 damage to up to one target creature.")
    assert [e["n"] for e in effects] == [3, 3]
    for e in effects:
        e["n"] = {"counters": "charge", "on": "self"}
    return effects, target, optional


def _scions() -> Parsed:
    """The Royal Scions −8: the reflexive ability triggers only if four cards were drawn this way, once even if more were (the 2019-10-04
    rulings: drawing fewer, it doesn't trigger); its target is chosen after the draw, and the damage is the hand's size as it resolves."""
    hit, target, optional = _p("~ deals damage to any target equal to the number of cards in your hand.")
    from app.rules.scripts import target_fields

    return [{"do": "draw", "who": "you", "n": 4, "as": "scions100e"},
            {"do": "reflexive", "cond": {"value": {"this_way": "drawn", "ref_count": "scions100e", "players": "you"}, "op": ">=", "n": 4},
             "ability": {"kind": "triggered", "trigger": "reflexive", "effects": hit, "optional": optional, **target_fields(target)}}], None, False


_TEXTS: dict[str, Callable[[], Parsed]] = {
    "sacrifice a creature. when you do, ~ deals x damage to any target, where x is that creature's power. if the sacrificed creature was a "
    "hamster, draw x cards.": _minsc,
    "create a 2/1 white cat warrior creature token. when you do, if you control a red permanent other than ~, ~ deals damage equal to the "
    "number of creatures you control to any target.": _ajani,
    "amass orcs 2. when you do, ~ deals x damage to target creature an opponent controls, where x is the amassed army's power.": _foray,
    "amass zombies 2, then the army you amassed deals damage equal to its power to each non-army creature.": _brutality,
    "amass orcs 3, then target player mills x cards, where x is the amassed army's power.": _surrounded,
    "draw three cards, then put a fuse counter on ~. it deals damage equal to the number of fuse counters on it to target opponent. they "
    "gain control of ~.": _pumpkin,
    "it deals damage equal to the number of charge counters on it to target player and that much damage to up to one target creature.": _reactor,
    "draw four cards. when you do, ~ deals damage to any target equal to the number of cards in your hand.": _scions,
}


def _text(text: str) -> Callable[[Callable[[], Parsed]], Callable[[], Parsed]]:
    def register(build: Callable[[], Parsed]) -> Callable[[], Parsed]:
        _TEXTS[text.casefold()] = build
        return build
    return register


_ELF_WARRIOR = {"name": "Elf Warrior", "power": "1", "toughness": "1", "colors": ["G", "W"], "type_line": "Token Creature — Elf Warrior", "text": ""}


@_text("Target creature's controller sacrifices it, then creates X 1/1 green and white Elf Warrior creature tokens, where X is that creature's power.")
def _mercy_killing() -> Parsed:
    """Mercy Killing: 701.21a — whoever controls the target as it resolves sacrifices it (neither regeneration nor indestructible saves it: the
    2013-07-01 ruling), then that player creates X tokens, X its power as it last existed on the battlefield (608.2h)."""
    return [{"do": "sacrifice", "who": "target", "by": "controller", "as": "e0"},
            {"do": "create_token", "who": "ref:e0.controller", "n": {"power": "ref:e0"}, "token": dict(_ELF_WARRIOR)}], "creature", False


@_text("that player mills a card. Then they create X 1/1 black Minion creature tokens, where X is the milled card's mana value.")
def _infernal_genesis() -> Parsed:
    """Infernal Genesis: the upkeep's player mills, then creates as many tokens as the milled card's mana value (a land: 0, the 2008-08-01
    ruling) — "they" is that player (608.2c)."""
    return _p("that player mills a card. Then that player creates X 1/1 black Minion creature tokens, where X is the milled card's mana value.")


@_text("create X 2/2 green Wolf creature tokens, where X is the number of your opponents with four or more cards in hand.")
def _wolfcallers_howl() -> Parsed:
    """Wolfcaller's Howl: X is counted as the ability resolves (the 2014-11-07 ruling)."""
    return _p("create X 2/2 green Wolf creature tokens, where X is the number of opponents who have four or more cards in hand.")


@_text("Put target nonland permanent into its owner's library just beneath the top X cards of that library.")
def _unexpectedly_absent() -> Parsed:
    """Unexpectedly Absent: beneath the top X cards (X 0: on top; fewer than X cards: on the bottom — the 2016-06-08 rulings), 401.4."""
    effects, target, optional = _p("Put target nonland permanent into its owner's library third from the top.")
    assert effects == [{"do": "to_library", "who": "target", "place": 3}]
    return [{"do": "beneath_top100e", "who": "target", "n": {"x": 1}}], target, optional


@_text("put target creature into its owner's library just beneath the top X cards of that library, where X is the number of Plains you control.")
def _quarry_colossus() -> Parsed:
    """Quarry Colossus: X is the Plains you control as it resolves (no Plains: on top; fewer cards than X: on the bottom — the 2014-04-26
    rulings)."""
    from app.rules import values

    n = values.parse_count("the number of Plains you control")
    effects, target, optional = _p("Put target creature into its owner's library third from the top.")
    assert n is not None and effects == [{"do": "to_library", "who": "target", "place": 3}]
    return [{"do": "beneath_top100e", "who": "target", "n": n}], target, optional


@_text("Target player draws X cards plus an additional card for each time they've cast a commander from the command zone this game.")
def _commanders_insight() -> Parsed:
    """Commander's Insight: 903.8 — only a commander's owner casts it from the command zone, so "each time they've cast a commander from the
    command zone" is that player's commander tax count (state commander_casts)."""
    return [{"do": "draw", "who": "target", "n": {"plus": [{"x": 1}, {"for_player": "target", "of": {"commander_casts": 1}}]}}], "player", False


@_text("Until end of turn, double target creature's power X times.")
def _exponential_growth() -> Parsed:
    """Exponential Growth: 701.10b, one doubling after another (the 2021-04-16 rulings: a 2/2 doubled three times is 16/2; a negative power
    doubles to a more negative one, 701.10c)."""
    effects, target, optional = _p("Double target creature's power until end of turn.")
    assert effects == [{"do": "double_pt", "who": "target", "toughness": False}]
    return [{"do": "double_times100e", "who": "target", "n": {"x": 1}}], target, optional


@_text("Target creature gets -X/-X until end of turn. That creature gets an additional -3/-3 until end of turn if you controlled a Faerie as you cast this spell.")
def _faerie_fencing() -> Parsed:
    """Faerie Fencing: the Faeries you controlled as casting finished (601.2i; the 2023-09-01 ruling: whether you still do doesn't matter),
    from the spell's own cast record (casting._note_cast); a copy isn't cast and gets no additional -3/-3."""
    first, target, optional = _p("Target creature gets -X/-X until end of turn.")
    more = _p("Target creature gets -3/-3 until end of turn.")[0]
    return [*first, {"do": "only_if", "cond": {"object": "self", "cast": {"controlled_subtype100e": "Faerie"}}, "skip": 1}, *more], target, optional


@_text("Target creature gets -X/-X until end of turn, where X is 7 minus the number of cards in that creature's controller's hand.")
def _flunk() -> Parsed:
    """Flunk: X as it resolves (the 2021-04-16 rulings), never below 0 (107.1b: seven or more cards, -0/-0)."""
    effects, target, optional = _p("Target creature gets -X/-X until end of turn.")
    x = {"minus": [7, {"controller_hand100e": "target"}]}
    return [{**effects[0], "p": {"neg": x}, "t": {"neg": x}}], target, optional


@_text("Tap X target creatures. ~ deals 2 damage to each of those creatures with flying.")
def _winter_blast() -> Parsed:
    """Winter Blast: flying is checked as it resolves, not as a targeting restriction, and a tapped target with flying is dealt the damage too
    (the 2007-09-16 rulings); only the targets still legal (608.2b) are "those creatures"."""
    effects, target, optional = _p("Tap X target creatures.")
    assert effects == [{"do": "tap", "who": "target:0"}]
    return [*effects, {"do": "keep_keyword100e", "who": "target:0", "keyword": "flying", "as": "flyers100e"},
            {"do": "damage", "who": "ref:flyers100e", "n": 2}], target, optional


@_text("~ deals X damage divided as you choose among any number of targets. Tap each creature dealt damage this way. Players dealt damage this way can't cast noncreature spells this turn.")
def _aurelias_fury() -> Parsed:
    """Aurelia's Fury: X and the division announced as it is cast (601.2d; the 2013-01-24 rulings: each target at least 1, an illegal target's
    share isn't dealt); "dealt damage this way" is what was actually dealt (after prevention, 615): those creatures are tapped, those players
    can't cast noncreature spells this turn."""
    effects, target, optional = _p("~ deals X damage divided as you choose among any number of targets.")
    limit = _p("Target player can't cast noncreature spells this turn.")[0]
    assert effects == [{"do": "damage", "who": "target:0", "n": {"divided": 0}}] and limit[0]["do"] == "cast_limit"
    return [{**effects[0], "dealt_as": "ref:d0", "bind_damage_players": "fury_players100e"},
            {"do": "keep_dealt100e", "dealt": "ref:d0", "types": ["Creature"], "as": "fury_creatures100e"},
            {"do": "tap", "who": "ref:fury_creatures100e"},
            {**limit[0], "who": "ref:fury_players100e"}], target, optional


@_text("~ deals X damage divided as you choose among any number of target creatures. Creatures dealt damage this way can't block this turn.")
def _huatli() -> Parsed:
    """Huatli, Warrior Poet −X: the division as it is activated (the 2017-09-29 rulings: X 0, no targets), and the creatures actually dealt
    damage can't block this turn (a restriction on those objects, 400.7)."""
    effects, target, optional = _p("~ deals X damage divided as you choose among any number of target creatures. Creatures dealt damage this way "
                                   "can't be regenerated this turn.")
    assert effects[1] == {"do": "no_regen_turn", "dealt": "ref:d0", "types": ["Creature"]}
    return [effects[0], {"do": "restrict", "who": "dealt", "dealt": "ref:d0", "rules": ["cant_block"]}], target, optional


@_text("~ deals X damage divided as you choose among any number of target creatures, where X is the greatest amount of damage dealt by a source to a permanent or player this turn.")
def _impact_resonance() -> Parsed:
    """Impact Resonance: X is fixed as it is cast, when the division is announced (601.2d; the 2014-11-07 rulings): the most damage any one source
    dealt to any one permanent or player this turn (the turn's damage log, 120.3: prevented damage isn't dealt)."""
    effects, target, optional = _p("~ deals X damage divided as you choose among any number of target creatures, where X is the number of lands you control.")
    assert target[0]["divide"]["value"] == {"count": 'sel:{"controller":"you","types":["Land"]}'}
    target[0]["divide"]["value"] = {"greatest_damage100e": 1}
    return effects, target, optional


@_text("Target creature an opponent controls deals damage equal to its power to each other creature that player controls, then each of those creatures deals damage equal to its power to that creature.")
def _alpha_brawl() -> Parsed:
    """Alpha Brawl (the 2011-01-22 rulings): first the target deals damage equal to its power to each other creature its controller controls,
    then each of those creatures (state-based actions aren't checked in between: the ones dealt lethal damage still deal theirs) deals damage
    equal to its own power to it, all at once (120.3; lifelink and deathtouch count, it isn't combat damage)."""
    first, target, optional = _p("Target creature an opponent controls deals damage equal to its power to each other creature that player controls.")
    assert first[0]["src"] == "target" and first[0]["n"] == {"power": "target"}
    return [{"do": "bind_controlled100e", "of": "target", "sel": 'sel:{"types":["Creature"]}', "as": "brawl100e"},
            {"do": "damage", "who": "ref:brawl100e", "n": {"power": "target"}, "src": "target"},
            {"do": "damage", "who": "target", "n": {"power": "each"}, "src": "ref:brawl100e", "src_many": True}], target, optional


@_text("Iron Fist deals damage equal to his power to any other target.")
def _iron_fist_granted() -> Parsed:
    """The ability Iron Fist, Living Weapon gains: its name is ~ (its own ability), "any other target" any target but it (115.4)."""
    return _p("~ deals damage equal to its power to any other target.")


@_text('~ gains "{T}: Iron Fist deals damage equal to his power to any other target" until end of turn.')
def _iron_fist() -> Parsed:
    return _p('~ gains "{T}: ~ deals damage equal to its power to any other target" until end of turn.')


@_text("you may sacrifice another creature. When you do, ~ deals damage equal to the sacrificed creature's power to any target. If the sacrificed "
       "creature was a Giant, ~ deals twice that much damage instead.")
def _surtland_flinger() -> Parsed:
    """Surtland Flinger: the reflexive ability (603.12) reads the sacrificed creature as it was sacrificed (608.2h; the 2021-02-05 rulings): its
    power, or twice it for a Giant (one damage instruction either way: the "instead" replaces the amount)."""
    effects, target, optional = _p("you may sacrifice another creature. When you do, ~ deals damage equal to the sacrificed creature's power to any target.")
    ability = _reflexive(effects)["ability"]
    assert ability["effects"] == [{"do": "damage", "who": "target", "n": {"power": "event"}}]
    giant = {"object": "event", "is": 'sel:{"subtypes":["Giant"]}'}
    ability["effects"] = [{"do": "only_if", "cond": {"not": giant}, "skip": 1}, {"do": "damage", "who": "target", "n": {"power": "event"}},
                          {"do": "only_if", "cond": giant, "skip": 1}, {"do": "damage", "who": "target", "n": {"times": [2, {"power": "event"}]}}]
    return effects, target, optional


@_text("Target creature you control deals damage equal to its power to each other creature. Until end of turn, whenever a creature you control "
       "dies, exile the top card of your library. You may play it until the end of your next turn.")
def _waltz_of_rage() -> Parsed:
    """Waltz of Rage: the bite (the target is the source, its power as the spell resolves: the 2024-09-20 rulings), then a delayed trigger for
    the rest of the turn (603.7c) whose own resolution exiles your top card and lets you play it until the end of your next turn (with all
    costs and timing rules, the ruling). An illegal target: nothing happens, the delayed trigger isn't created (608.2b)."""
    from app.rules import delayed

    bite, target, optional = _p("Target creature you control deals damage equal to its power to each other creature.")
    watch = _p("Until end of turn, whenever a creature you control dies, draw a card.")[0]
    impulse = _p("Exile the top card of your library. You may play it until the end of your next turn.")[0]
    assert watch[0]["do"] == "delayed" and watch[0]["this_turn"] and not watch[0]["once"] and len(impulse) == 2
    head, *deferred = delayed.wrap_when(impulse, watch[0]["when"], this_turn=True)
    return [*bite, {**head, "once": False}, *deferred], target, optional


@_text("~ deals X plus 2 damage to each creature that didn't enter this turn.")
def _let_the_galaxy_burn() -> Parsed:
    """Let the Galaxy Burn: each creature that didn't enter the battlefield this turn (selectors "not_entered_this_turn"), X plus 2 damage."""
    from app.rules import selectors

    effects, target, optional = _p("~ deals X damage to each creature that entered this turn.")
    assert effects == [{"do": "damage", "who": 'sel:{"extras":["entered_this_turn"],"types":["Creature"]}', "n": {"x": 1}}]
    who = selectors.Selector(types=("Creature",), extras=("not_entered_this_turn",)).key()
    return [{"do": "damage", "who": who, "n": {"plus": [{"x": 1}, 2]}}], target, optional


@_text("~ deals half X rounded down damage to any target, and half X rounded up damage to you.")
def _banshee() -> Parsed:
    """Banshee: one damage instruction to the target and to you at once (120.3): half X rounded down, half X rounded up (107.1a); with its
    target illegal the ability doesn't resolve and you aren't dealt damage (the 2009-10-01 ruling, 608.2b)."""
    effects, target, optional = _p("~ deals X damage to any target and X damage to you.")
    assert [e["who"] for e in effects] == ["target", "you"]
    effects[0]["n"], effects[1]["n"] = {"half": {"x": 1}, "round": "down"}, {"half": {"x": 1}, "round": "up"}
    return effects, target, optional


@_text("Tap any number of untapped artifacts you control. When you do, ~ deals that much damage to target creature or planeswalker.")
def _yotia() -> Parsed:
    """Yotia Declares War II: the reflexive ability (603.12) triggers even when no artifact was tapped (the 2022-09-09 ruling: it then deals no
    damage); "that much" is how many were tapped this way (608.2c), its target chosen as it is put on the stack."""
    from app.rules.scripts import target_fields

    tap = _p("Tap any number of untapped artifacts you control.")[0]
    hit, target, optional = _p("~ deals 2 damage to target creature or planeswalker.")
    assert tap[0]["do"] == "tap_choice" and hit == [{"do": "damage", "who": "target", "n": 2}]
    return [{**tap[0], "as": "yotia100e"},
            {"do": "reflexive", "cond": {"value": {"this_way": "tapped", "of": None, "ref_count": "yotia100e"}, "op": ">=", "n": 0}, "lki": "cond_ref",
             "ability": {"kind": "triggered", "trigger": "reflexive", "effects": [{**hit[0], "n": {"event_amount": 1}}], "optional": optional,
                         **target_fields(target)}}], None, False


@_text("~ deals damage to each of those creatures equal to the number of attacking creatures.")
def _lightmine_field() -> Parsed:
    """Lightmine Field (the 2010-06-15 rulings): the creatures declared as attackers (the trigger's event objects, while each is still that
    object on the battlefield, even if removed from combat) are dealt damage equal to the number of attacking creatures as it resolves."""
    from app.rules import values

    n = values.parse_count("the number of attacking creatures")
    assert n is not None
    return [{"do": "damage", "who": "event", "n": n}], None, False


@_text("~ deals damage to each opponent who controls more lands than you equal to the difference. Then create a number of Treasure tokens equal to the damage dealt this way.")
def _spiteful_repossession() -> Parsed:
    """Spiteful Repossession: each opponent with more lands than you is dealt the difference, all at once (608.2h: each amount determined
    first); then as many Treasures as the damage actually dealt this way (after prevention: 120.3, 615)."""
    treasure = _p("Create a Treasure token.")[0]
    assert len(treasure) == 1 and treasure[0]["do"] == "create_token"
    return [{"do": "land_gap_damage100e", "bind_dealt": "spite100e"}, {**treasure[0], "n": {"ref_amount": "spite100e"}}], None, False


@_text("For each player, choose friend or foe. Each friend discards all cards from their hand, then draws that many cards plus one. ~ deals damage to each foe equal to the number of cards in their hand.")
def _khorvaths_fury() -> Parsed:
    """Khorvath's Fury (friend or foe, app/rules/friend_foe.py): each friend in turn order discards their hand, then draws that many plus one
    (zero cards: draws one — the 2018-06-08 rulings); then the spell deals each foe damage equal to the cards in their hand, all at once
    (friends act before foes, the ruling)."""
    friend = _p("Discard your hand, then draw that many cards plus one.")[0]
    assert [e["do"] for e in friend] == ["discard", "draw"]
    return [{"do": "friend_foe"}, {"do": "side_does", "side": "friend", "n": len(friend)}, *friend, {"do": "foe_hand_damage100e"}], None, False


@_text("target enchantment deals damage equal to its mana value to its controller unless that player sacrifices it.")
def _enchanters_bane() -> Parsed:
    """Enchanter's Bane: as it resolves, the target enchantment's controller chooses: sacrifice it (701.21a), or it deals damage equal to its
    mana value to them (120.3: the enchantment is the source). It must target an enchantment, Enchanter's Bane itself if no other (the
    2018-07-13 ruling)."""
    target = _p("Destroy target enchantment.")[1]
    return [{"do": "bane100e"}], target, False


@_text("Destroy all creatures target opponent controls. ~ deals damage to that player equal to their total power.")
def _angrath() -> Parsed:
    """Angrath, Minotaur Pirate −11 (the 2018-01-19 rulings): the creatures that player controls as it resolves are destroyed at once; their
    total power is each one's power as it last existed on the battlefield — or as it is, for one that wasn't destroyed (indestructible) — a
    negative power subtracting (107.1b: a total of 0 or less deals no damage); the player is dealt it before any dies trigger is put on the
    stack."""
    destroy, target, optional = _p("Destroy all creatures target opponent controls.")
    assert destroy == [{"do": "destroy", "who": 'controlled:target|sel:{"types":["Creature"]}'}] and target == "opponent"
    return [{"do": "bind_controlled100e", "player": "target", "sel": 'sel:{"types":["Creature"]}', "as": "angrath100e"},
            {"do": "destroy", "who": "ref:angrath100e"},
            {"do": "damage", "who": "target", "n": {"total_power100e": "angrath100e"}}], target, optional


@_text("put a +1/+0 counter on enchanted creature. If that creature has three or more +1/+0 counters on it, it deals damage equal to its power to "
       "its controller, then destroy that creature and it can't be regenerated.")
def _consuming_ferocity() -> Parsed:
    """Consuming Ferocity: the counter, then — only with three or more +1/+0 counters on it as that is checked (608.2c) — the creature deals
    damage equal to its power to its controller (120.3: it is the source), then it is destroyed and can't be regenerated (701.19c)."""
    counter = _p("put a +1/+0 counter on enchanted creature.")[0]
    doom = _p("Destroy enchanted creature. It can't be regenerated.")[0]
    assert counter == [{"do": "add_counters", "who": "host", "kind": "+1/+0", "n": 1}] and doom == [{"do": "destroy", "who": "host"}, {"do": "no_regen"}]
    bite = {"do": "damage", "who": "host_controller", "n": {"power": "host"}, "src": "host"}
    return [*counter, {"do": "only_if", "cond": {"object": "host", "counters": "+1/+0", "op": ">=", "n": 3}, "skip": 1 + len(doom)}, bite, *doom], None, False


@_text("it deals X damage to target creature, where X is 3 plus the amount of damage dealt to ~ this turn by other sources named Blazing Effigy.")
def _blazing_effigy() -> Parsed:
    """Blazing Effigy: X is 3 plus the damage this object was dealt this turn (before it died) by sources other than it named Blazing Effigy
    (the turn's damage log: 120.3, prevented damage isn't dealt; each source as it is, or as it last existed)."""
    effects, target, optional = _p("~ deals 3 damage to target creature.")
    assert effects == [{"do": "damage", "who": "target", "n": 3}]
    return [{**effects[0], "n": {"plus": [3, {"effigy_damage100e": "Blazing Effigy"}]}}], target, optional


@_text("each opponent faces a villainous choice — That opponent discards all the cards in their hand, then draws that many cards minus one, or ~ "
       "deals damage to that player equal to the number of cards in their hand.")
def _sycorax_commander() -> Parsed:
    """Sycorax Commander (701.55; the 2023-10-13 rulings): each opponent in turn order chooses, and that option is carried out before the next
    one chooses: discard their whole hand and draw one fewer, or be dealt damage equal to their hand's size."""
    a = _p("That player discards their hand, then draws that many cards minus one.")[0]
    assert [e["do"] for e in a] == ["discard", "draw"]
    b = [{"do": "damage", "who": "event_player", "n": {"hand": "event_player"}}]
    return [{"do": "villain", "who": "each_opponent", "a": a, "b": b,
             "labels": ["That player discards all the cards in their hand, then draws that many cards minus one",
                        "~ deals damage to that player equal to the number of cards in their hand"]}], None, False


@_text("you may discard your hand. Draw X cards, where X is the number of cards discarded this way. If you have an enduring story, ~ deals X damage to "
       "each opponent.")
def _balin() -> Parsed:
    """Balin, Loremaster: both X are the number of cards discarded this way (an empty hand may be discarded: X 0 — the 2026-06-29 rulings)."""
    effects, target, optional = _p("you may discard your hand. Draw X cards, where X is the number of cards discarded this way. If you have an enduring "
                                   "story, ~ deals 1 damage to each opponent.")
    assert [e["do"] for e in effects] == ["discard", "draw", "only_if", "damage"] and effects[3]["n"] == 1
    effects[3]["n"] = effects[1]["n"]
    return effects, target, optional


@_text("Up to X target creatures you control each gain haste until end of turn and can't be blocked this turn except by creatures with haste, where X "
       "is the number of Bobbleheads you control as you activate this ability.")
def _agility_bobblehead() -> Parsed:
    """Agility Bobblehead: the number of targets is fixed as it is activated (601.2c; the 2024-03-08 rulings), and a creature already blocked
    stays blocked (509.1h)."""
    grant, target, optional = _p("Up to X target creatures you control each gain haste until end of turn, where X is the number of Bobbleheads you "
                                 "control as you activate this ability.")
    unblockable = _p("Target creature can't be blocked this turn except by creatures with haste.")[0]
    assert grant[0]["do"] == "grant" and unblockable[0]["do"] == "restrict"
    return [*grant, {**unblockable[0], "who": "target:0"}], target, optional


@_text("Target opponent loses 2 life for each Swamp you control. ~ deals damage to target creature equal to the number of Mountains you control. "
       "Create a 1/1 green Saproling creature token for each Forest you control. You gain 2 life for each Plains you control. Draw a card for each "
       "Island you control, then discard that many cards.")
def _last_stand() -> Parsed:
    """Last Stand: each count as it resolves (608.2h); "that many" is the number of cards the draw instruction named (608.2c)."""
    effects, target, optional = _p("Target opponent loses 2 life for each Swamp you control. ~ deals damage to target creature equal to the number of "
                                   "Mountains you control. Create a 1/1 green Saproling creature token for each Forest you control. You gain 2 life for "
                                   "each Plains you control. Draw a card for each Island you control, then discard a card.")
    assert effects[-2]["do"] == "draw" and effects[-1] == {"do": "discard", "who": "you", "n": 1}
    effects[-1]["n"] = effects[-2]["n"]
    return effects, target, optional


@_text("target creature you control gets +X/+0 until end of turn and up to one target creature an opponent controls gets -0/-X until end of turn, "
       "where X is the number of Elves you control plus the number of Elf cards in your graveyard.")
def _gloom_ripper() -> Parsed:
    """Gloom Ripper: X once, as the ability resolves (the 2025-11-17 ruling); either target illegal, the other is still affected (608.2b)."""
    effects, target, optional = _p("target creature you control gets +1/+0 until end of turn. Up to one target creature an opponent controls gets -0/-1 "
                                   "until end of turn.")
    x = _p("target creature you control gets +X/+0 until end of turn, where X is the number of Elves you control plus the number of Elf cards in your "
           "graveyard.")[0][0]["p"]
    assert [(e["p"], e["t"]) for e in effects] == [(1, 0), (0, -1)]
    effects[0]["p"], effects[1]["t"] = x, {"neg": x}
    return effects, target, optional


@_text("Exile target nonland permanent. Its controller incubates X, where X is its mana value.")
def _excise_the_imperfect() -> Parsed:
    """Excise the Imperfect: the permanent's controller as it last existed incubates (701.53a), X its mana value then (608.2h); an illegal
    target: nothing happens (the 2023-04-14 ruling, 608.2b)."""
    effects, target, optional = _p("Exile target nonland permanent. Its controller creates a Treasure token.")
    assert effects[0] == {"do": "exile", "who": "target", "as": "e0"} and effects[1]["who"] == "ref:e0.controller"
    return [effects[0], {"do": "as_their100e", "who": "ref:e0.controller", "span": 1}, {"do": "incubate", "n": {"mana_value": "ref:e0"}},
            {"do": "as_player_end"}], target, optional


@_text("incubate 3 X times.")
def _progenitor_exarch() -> Parsed:
    """Progenitor Exarch: X Incubator tokens one after the other (701.53a), X the X it was cast with (0 when it wasn't cast: 107.3m)."""
    effects = _p("incubate 3 twice.")
    assert effects[0][0] == {"do": "repeat", "n": 2, "span": 1}
    effects[0][0]["n"] = {"x": 1}
    return effects


@_text("destroy up to one other target creature. Its controller amasses Goblins X, where X is that creature's power. If you controlled that creature, "
       "draw a card.")
def _azog() -> Parsed:
    """Azog, Moria's Ruin (the 2026-06-29 rulings): that creature's controller as it last existed amasses Goblins X (701.47a: their Army),
    X its power as it last existed; with no target, nobody amasses. Destroyed or not (indestructible), it is "that creature" (608.2c)."""
    effects, target, optional = _p("destroy up to one other target creature. Its controller creates X 1/1 green Elf Warrior creature tokens, where X is "
                                   "that creature's power.")
    draw = _p("destroy target creature. If you controlled that creature, draw a card.")[0][1:]
    assert effects[1]["who"] == "ref:e0.controller" and effects[1]["n"] == {"power": "ref:e0"} and draw[0]["cond"]["object"] == "ref:e0"
    return [effects[0], {"do": "as_their100e", "who": "ref:e0.controller", "span": 1}, {"do": "amass", "sub": "Goblin", "n": {"power": "ref:e0"}},
            {"do": "as_player_end"}, *draw], target, optional


@_text("create a 0/0 green and blue Fractal creature token. Put X +1/+1 counters on it and attach ~ to it.")
def _fractal_harness() -> Parsed:
    """Fractal Harness: the token, X counters (the X it was cast with; 0 when it wasn't cast: the 2021-04-16 ruling), then the Equipment
    attached to it — all as one resolution, before state-based actions see a 0/0 (704.3)."""
    effects, target, optional = _p("create a 0/0 green and blue Fractal creature token. Put X +1/+1 counters on it.")
    attach = _p("create a 1/1 colorless Germ creature token, then attach ~ to it.")[0][1]
    assert effects[0]["as"] == "e0" and effects[1]["who"] == "ref:e0" and attach == {"do": "attach_to", "src": "self", "who": "ref:e0"}
    return [*effects, attach], target, optional


@_text('Create X 1/1 green Minion creature tokens named Moloid, where X is the number of permanent cards in your graveyard. The tokens have "Whenever '
       'this token attacks, you may mill a card."')
def _return_of_the_mole_man() -> Parsed:
    """Return of the Mole Man: X counted as it resolves (608.2h) — the enchantment, sacrificed to activate it, is one of those cards."""
    effects, target, optional = _p("Create X 1/1 green Minion creature tokens named Moloid, where X is the number of permanent cards in your graveyard.")
    text = _p('Create a 1/1 green Minion creature token with "Whenever this token attacks, you may mill a card."')[0][0]["token"]["text"]
    assert effects[0]["token"]["name"] == "Moloid" and not effects[0]["token"]["text"]
    effects[0]["token"]["text"] = text
    return effects, target, optional


@_text("Until end of turn, target creature becomes a green and blue Fractal with base power and toughness each equal to X plus 1.")
def _fractalize() -> Parsed:
    """Fractalize: until end of turn green and blue (layer 5), a Fractal and no other creature type (layer 4: 205.1b, the reminder text),
    base power and toughness X plus 1 (layer 7b)."""
    effects, target, optional = _p("Until end of turn, target creature becomes a green and blue Fractal with base power and toughness 1/1.")
    assert effects[0]["do"] == "become" and (effects[0]["p"], effects[0]["t"]) == (1, 1) and effects[0]["creature_types"] == ["Fractal"]
    effects[0]["p"] = effects[0]["t"] = {"plus": [{"x": 1}, 1]}
    return effects, target, optional


@_text("Until end of turn, creatures you control have base power and toughness X/X, where X is the number of cards you own in exile and in your graveyard "
       "that are instant cards, are sorcery cards, and/or have an Adventure.")
def _candlekeep_inspiration() -> Parsed:
    """Candlekeep Inspiration (the 2022-06-10 rulings): X and the creatures affected are fixed as it resolves (608.2h, 611.2c); an adventurer
    card is a permanent card (715.2), so the two counts never overlap."""
    from app.rules import selectors

    effects, target, optional = _p("Until end of turn, creatures you control have base power and toughness X/X, where X is the number of instant and "
                                   "sorcery cards in your graveyard.")
    assert effects[0]["do"] == "become" and effects[0]["p"] == effects[0]["t"]
    mine = selectors.Selector(card=True, zones=("exile", "graveyard"), zone_owner="you")
    x = {"plus": [{"count": selectors.replace(mine, types=("Instant", "Sorcery")).key()},
                  {"count": selectors.replace(mine, extras=("has_adventure",)).key()}]}
    effects[0]["p"] = effects[0]["t"] = x
    return effects, target, optional


@_text("exile the top card of your library. If it's a creature card, ~ gets +X/+Y until end of turn, where X is the exiled creature card's power and Y "
       "is its toughness.")
def _bioplasm() -> Parsed:
    """Bioplasm: the exiled card's power and toughness in exile (a characteristic-defining ability counts there too: the 2014-02-01 ruling)."""
    effects, target, optional = _p("exile the top card of your library. If it's a creature card, ~ gets +X/+X until end of turn, where X is that card's power.")
    assert effects[2] == {"do": "pump", "who": "self", "p": {"power": "ref:e0"}, "t": {"power": "ref:e0"}}
    effects[2]["t"] = {"toughness": "ref:e0"}
    return effects, target, optional


@_text("target player reveals X cards from their hand, where X is the number of Faeries you control. You choose one of those cards. That player discards "
       "that card.")
def _thieving_sprite() -> Parsed:
    """Thieving Sprite: X is the Faeries you control as it resolves (the 2013-06-07 ruling); that player picks the cards revealed (701.20a)."""
    return _p("target player reveals a number of cards from their hand equal to the number of Faeries you control. You choose one of them. That player "
              "discards that card.")


@_text("Target player reveals X cards from their hand and you choose one of them. That player discards that card.")
def _cabal_interrogator() -> Parsed:
    effects, target, optional = _p("Target player reveals three cards from their hand and you choose one of them. That player discards that card.")
    assert effects[0] == {"do": "reveal_some", "who": "target", "n": 3}
    effects[0]["n"] = {"x": 1}
    return effects, target, optional


@_text("If target creature has toughness 5 or greater, it gets +4/-4 until end of turn. Otherwise, it gets +4/-X until end of turn, where X is its "
       "toughness minus 1.")
def _blood_lust() -> Parsed:
    """Blood Lust: its toughness as it resolves picks the branch; X is fixed then (the 2005-11-01 ruling), never below 0 (107.1b). The other
    branch is checked first: after it the creature's toughness is at most 1, so the first can't apply too."""
    effects, target, optional = _p("Target creature gets +4/-4 until end of turn.")
    assert effects == [{"do": "pump", "who": "target", "p": 4, "t": -4}]
    big = {"object": "target", "is": 'sel:{"compare":[["toughness",">=",5]],"types":["Creature"]}'}
    return [{"do": "only_if", "cond": {"not": big}, "skip": 1}, {**effects[0], "t": {"neg": {"minus": [{"toughness": "target"}, 1]}}},
            {"do": "only_if", "cond": big, "skip": 1}, effects[0]], target, optional


@_text("The owner of target artifact or creature with mana value 1 or greater shuffles it into their library. Then that player discovers X, where X is its "
       "mana value.")
def _zoyowas_justice() -> Parsed:
    """Zoyowa's Justice: its owner shuffles it in, then that player discovers X (701.57a), X its mana value as it last existed on the battlefield
    (608.2h: an X in its cost is 0, the 2023-11-10 rulings); an illegal target: nothing happens (608.2b)."""
    effects, target, optional = _p("The owner of target artifact or creature with mana value 1 or greater shuffles it into their library.")
    assert effects == [{"do": "to_library", "who": "target", "place": "shuffle"}]
    return [{**effects[0], "as": "e0"}, {"do": "as_their100e", "who": "ref:e0.owner", "span": 1},  # (continue_resolution: back to its controller
            {"do": "discover", "n": {"mana_value": "ref:e0"}, "continue_resolution": True}, {"do": "as_player_end"}], target, optional  # after a cast)


def _offering(token_text: str) -> Parsed:
    """Sylvan Offering: an opponent chosen as it resolves, for each line on its own (the 2014-11-07 rulings: not a target; the same one or
    another), then one instruction for you and that player (one event, as Benevolent Offering)."""
    made = _p(token_text)[0]
    assert len(made) == 1 and made[0]["do"] == "create_token"
    return [{"do": "choose_value", "who": "you", "what": "opponent", "as": "offer100e"},
            {"do": "with_you100e", "of": "ref:offer100e", "as": "offered100e"}, {**made[0], "who": "ref:offered100e"}], None, False


@_text("Choose an opponent. You and that player each create an X/X green Treefolk creature token.")
def _sylvan_offering_treefolk() -> Parsed:
    return _offering("Create an X/X green Treefolk creature token.")


@_text("Choose an opponent. You and that player each create X 1/1 green Elf Warrior creature tokens.")
def _sylvan_offering_elves() -> Parsed:
    return _offering("Create X 1/1 green Elf Warrior creature tokens.")


@_text("Each player may discard up to three cards. ~ deals damage to each player equal to 3 minus the number of cards they discarded this way.")
def _mind_bomb() -> Parsed:
    """Mind Bomb: each player in APNAP order chooses up to three cards, all discarded at once (101.4, 701.9a); then each player is dealt 3
    minus the cards they discarded, all at once (120.3)."""
    discard = _p("Each player discards up to three cards.")[0]
    assert discard == [{"do": "discard", "who": "each_player", "n": 3, "upto": True}]
    return [{**discard[0], "as": "bomb100e"}, {"do": "shortfall_damage100e", "of": "ref:bomb100e", "n": 3}], None, False


@_text("Draw four cards, then choose X cards in your hand and discard the rest.")
def _breakthrough() -> Parsed:
    """Breakthrough: keeping X cards is discarding all the others (701.9a: the player chooses); X at least the hand, nothing is discarded."""
    effects, target, optional = _p("Draw four cards, then discard a card.")
    assert effects[1] == {"do": "discard", "who": "you", "n": 1}
    effects[1]["n"] = {"minus": [{"hand": "you"}, {"x": 1}]}
    return effects, target, optional


# -- whole abilities (definitions) -----------------------------------------------------------------------------------------------------------
_DEFS: dict[str, Callable[[Any, Any], dict[str, Any]]] = {}


def _ability(text: str) -> Callable[[Callable[[Any, Any], dict[str, Any]]], Callable[[Any, Any], dict[str, Any]]]:
    def register(build: Callable[[Any, Any], dict[str, Any]]) -> Callable[[Any, Any], dict[str, Any]]:
        _DEFS[text.casefold()] = build
        return build
    return register


def _define(ability: Any, ch: Any, text: str) -> dict[str, Any]:
    from dataclasses import replace

    from app.rules import scripts

    got = scripts.define(replace(ability, text=text), ch)
    if got is None:
        raise AssertionError(f"xdamage100e: the grammar no longer reads {text!r}")
    return copy.deepcopy(got)


@_ability("When ~ enters, enchanted creature deals damage equal to its power to any other target.")
def _pain_for_all(ability: Any, ch: Any) -> dict[str, Any]:
    """Pain for All: "any other target" — any target but the enchanted creature, the one dealing the damage (115.4); its power as the ability
    resolves, or as it last existed if it left (the 2025-07-25 ruling: the creature the Aura enchanted as it last existed, 608.2h)."""
    d = _define(ability, ch, "When this Aura enters, enchanted creature deals damage equal to its power to any target.")
    assert d["effects"] == [{"do": "damage", "who": "target", "n": {"power": "host"}, "src": "host"}] and d["target"] == {"what": "any"}
    return {**d, "effects": [{"do": "host_bite100e"}], "target": {"what": "any_not_host100e"}}


@_ability("Whenever you cast a spell with mana value equal to the number of doom counters on ~, ~ deals that much damage to any target. Then put a "
          "doom counter on ~.")
def _imminent_doom(ability: Any, ch: Any) -> dict[str, Any]:
    """Imminent Doom: "that much" is the number of doom counters as it triggered (the 2017-07-14 ruling): the cast spell's mana value then (equal
    by the trigger condition; X counts on the stack, 202.3e), as the event recorded it — not the counters as it resolves."""
    d = _define(ability, ch, "Whenever you cast a spell with mana value equal to the number of doom counters on this enchantment, this enchantment "
                             "deals 1 damage to any target. Then put a doom counter on this enchantment.")
    assert d["effects"][0] == {"do": "damage", "who": "target", "n": 1} and d["effects"][1]["kind"] == "doom"
    d["effects"][0]["n"] = {"mana_value": "event"}
    return d


@_ability("Whenever you cast a spell with {H} in its mana cost, ~ deals damage equal to that spell's mana value to any target.")
def _rage_extractor(ability: Any, ch: Any) -> dict[str, Any]:
    """Rage Extractor: any spell whose mana cost has a Phyrexian mana symbol of any color, however it was paid (the 2011-06-01 rulings; 107.4f);
    its mana value counts each Phyrexian symbol as 1 (202.3)."""
    from app.rules import selectors

    d = _define(ability, ch, "Whenever you cast a spell, ~ deals damage equal to that spell's mana value to any target.")
    assert d["cond"]["event"] == "cast" and d["cond"]["spell"] == 'sel:{"zones":["stack"]}' and d["effects"][0]["n"] == {"mana_value": "event"}
    d["cond"]["spell"] = selectors.Selector(zones=("stack",), extras=("phyrexian_cost100e",)).key()
    return d


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    build = _DEFS.get(scripts.self_text(ability.text, ch.name).casefold())
    return build(ability, ch) if build is not None else None


# -- primitives ------------------------------------------------------------------------------------------------------------------------------
def beneath_top(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"just beneath the top X cards of that library": its owner's library, X cards above it (401.4); X 0 is the top, and a library of fewer
    cards puts it on the bottom."""
    from app.rules import effects

    cards = effects._cards(plan, ctx, e["who"])
    n = effects._amount(plan, ctx, e["n"])
    for cid in cards[:1]:
        depth = min(n, len(plan.state.zones.get(f"{plan.state.cards[cid].owner}:library", [])))
        effects.to_library(plan, ctx, {"do": "to_library", "who": e["who"], "place": depth + 1, **({"as": e["as"]} if e.get("as") else {})})
    return True


def double_times(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    from app.rules import combat_rules, effects

    for _ in range(effects._amount(plan, ctx, e["n"])):
        combat_rules.double_pt(plan, ctx, {"do": "double_pt", "who": e["who"], "toughness": False})
    return True


def keep_keyword(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the objects ``who`` names that have the keyword now (as the instruction is reached: 608.2h)."""
    from app.rules import context, effects

    context.bind_objects(plan, ctx, e["as"], [c for c in effects._cards(plan, ctx, e["who"]) if e["keyword"] in plan.ch(plan.state.cards[c]).keywords])
    return True


def keep_dealt(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the objects an earlier damage instruction actually dealt damage to (effects.DEALT_KEY), still those objects on the battlefield
    (400.7) and of these card types now."""
    from app.rules import context, effects

    oids = set((ctx.get(effects.DEALT_KEY) or {}).get(e["dealt"]) or [])
    kept = [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) in oids
            and (not e.get("types") or set(e["types"]) & plan.ch(c).types)]
    context.bind_objects(plan, ctx, e["as"], kept)
    return True


def total_power(plan: Any, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """The total power of the objects a binding names, each as it is while it's still that object, else as it last existed (608.2h); a
    negative power subtracts, and the total is never below 0 (107.1b)."""
    from app.rules import context

    return max(0, sum(ch.pt[0] for _, ch in context.infos(plan, ctx, v["total_power100e"]) if ch.pt is not None))


def effigy_damage(plan: Any, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """The damage dealt this turn to the source object (as it was on the battlefield: ctx source_object) by other sources with this name."""
    from app.rules.history import log_for

    me, name = ctx.get("source_object"), v["effigy_damage100e"]

    def named(oid: str | None) -> bool:
        if not oid or oid == me:
            return False
        card = next((c for c in plan.state.cards.values() if plan.oid(c) == oid), None)
        if card is not None:
            return plan.ch(card).name == name
        snap = plan.rules.lki.get(oid)
        return snap is not None and snap.name == name
    return sum(int(f.amount) for f in log_for(plan).facts if f.kind == "damaged" and f.object_id == me and f.amount > 0 and named(f.source))


def greatest_damage(plan: Any, ctx: dict[str, Any], v: dict[str, Any]) -> int:
    """"the greatest amount of damage dealt by a source to a permanent or player this turn": this turn's damage (the log records only damage
    dealt, 120.3, 615), added up for each source and each player or permanent dealt it (each object once: 400.7)."""
    from app.rules.history import log_for

    totals: dict[tuple[str | None, str | None], int] = {}
    for f in log_for(plan).facts:
        if f.kind in ("damage", "damaged") and f.amount > 0:
            key = (f.object_id, f.player) if f.kind == "damage" else (f.source, f.object_id)
            totals[key] = totals.get(key, 0) + int(f.amount)
    return max(totals.values(), default=0)


def bind_controlled(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind the permanents of ``sel`` the controller of the object ``of`` names controls now, other than it ("each other creature that player
    controls", Alpha Brawl): fixed as the instruction is reached (608.2c)."""
    from app.rules import context, effects, selectors

    of = effects._cards(plan, ctx, e["of"]) if e.get("of") else []
    owner = plan.state.cards[of[0]].controller if of else next(iter(effects._players(plan, ctx, e["player"])), None) if e.get("player") else None
    found = [c for c in selectors.candidates(plan, selectors.from_key(e["sel"]), ctx["controller"], ctx.get("source_card"))
             if owner is not None and plan.state.cards[c].controller == owner and c not in of]
    context.bind_objects(plan, ctx, e["as"], found)
    return True


def host_bite(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"Enchanted creature deals damage equal to its power to [the target]": the creature the Aura is attached to — or, the Aura gone, the one it
    was attached to as it last existed — as it is, or as it last existed (608.2h), is the source (120.3)."""
    from app.rules import effects

    src = effects._named_source(plan, ctx, "host")
    if src is None:
        aura = plan.state.cards.get(ctx.get("source_card") or "")
        live = aura is not None and aura.zone.endswith(":battlefield") and plan.oid(aura) == ctx.get("source_object")
        snap = None if live else plan.rules.lki.get(ctx.get("source_object") or "")
        host_oid = (plan.oid(aura.attached_to) if live and aura is not None and aura.attached_to else None) or (snap.attached_object if snap is not None else None)
        if host_oid is None and aura is not None:  # (the creature left first: the Aura was unattached then, 704.5m — the creature as it last
            host_oid = next((x.object_id for x in reversed(plan.rules.lki.values())  # existed, with this Aura attached)
                             if aura.id in x.attached and x.zone.endswith(":battlefield")), None)
        src = effects._named_source(plan, ctx, f"obj:{host_oid}") if host_oid else None
    if src is None:
        plan.note(f"{ctx.get('name') or 'It'}: the creature that would deal the damage is gone", actor=ctx["controller"])
        return True
    n = max(0, src.ch.pt[0]) if src.ch is not None and src.ch.pt is not None else 0
    keys = [*effects._cards(plan, ctx, "target"), *effects._players(plan, ctx, "target")]
    return effects._deal(plan, ctx, [(src, key, n) for key in keys], e) if n > 0 and keys else True


def land_gap_damage(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Each opponent who controls more lands than you is dealt the difference by the source, all at once (608.2h, 120.3)."""
    from app.rules import effects, selectors

    lands = selectors.from_key('sel:{"types":["Land"]}')
    held: dict[str, int] = {}
    for c in selectors.candidates(plan, lands, ctx["controller"], ctx.get("source_card")):
        held[plan.state.cards[c].controller] = held.get(plan.state.cards[c].controller, 0) + 1
    mine = held.get(ctx["controller"], 0)
    src = effects._ability_source(plan, ctx)
    hits = [(src, p, held.get(p, 0) - mine) for p in plan.live() if p != ctx["controller"] and held.get(p, 0) > mine]
    if not hits:
        from app.rules import context

        context.bind_amount(ctx, e["bind_dealt"], 0)
        return True
    return effects._deal(plan, ctx, hits, e)


def foe_hand_damage(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Friend or foe: the source deals each foe damage equal to the number of cards in their hand, each amount determined at once (608.2h)."""
    from app.rules import effects

    sides = ctx.get("sides") or {}
    foes = [p for p in sides.get("order", []) if sides.get("chosen", {}).get(p) == "foe" and p in plan.live()]
    src = effects._ability_source(plan, ctx)
    hits = [(src, p, len(plan.state.zones.get(f"{p}:hand", []))) for p in foes]
    return effects._deal(plan, ctx, hits, e) if any(n > 0 for _, _, n in hits) else True


def bane(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """"[Target permanent] deals damage equal to its mana value to its controller unless that player sacrifices it": its controller as it
    resolves chooses (a public choice); not sacrificed, the permanent is the source of the damage (120.3)."""
    from app.game.rules_state import DecisionOption
    from app.rules import effects
    from app.rules.plan import decide

    cards = effects._cards(plan, ctx, "target")
    if not cards:
        return True
    card = plan.state.cards[cards[0]]
    n = max(0, plan.ch(card).mana_value)
    answer = ctx.get("bane100e")
    if answer is None:
        decide(plan, player=card.controller, kind="confirm", prompt=f"{ctx.get('name') or 'It'}: sacrifice {card.name}? If you don't, it deals {n} damage to you.",
               options=[DecisionOption(id="yes", label=f"Sacrifice {card.name}"), DecisionOption(id="no", label=f"Take {n} damage")],
               resume={"step": "bane100e", "ctx": ctx, "e": e}, source=card)
        return False
    if answer == "yes":
        effects._sacrifice_cards(plan, [card.id], card.controller, ctx)
        return True
    hit = [(effects._card_source(plan, card.id), card.controller, n)] if n > 0 and card.controller in plan.live() else []
    return effects._deal(plan, ctx, hit, e) if hit else True


def resume_bane(plan: Any, d: Any, chosen: list[str]) -> None:
    from app.rules import effects

    ctx = d.resume["ctx"]
    ctx["bane100e"] = chosen[0] if chosen else "no"
    if bane(plan, ctx, d.resume["e"]):
        effects.continue_effects(plan, ctx)


def as_their(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """The next ``span`` instructions are done by the player ``who`` names ("Its controller incubates X"), until ``as_player_end``; nobody
    named (no target was chosen), they and the end are skipped."""
    from app.rules import effects, tempting

    players = effects._players(plan, ctx, e["who"])
    if not players:
        ctx["next"] += e["span"] + 1
        return True
    return tempting.as_player(plan, ctx, {"player": players[0]})


def with_you(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Bind you and the players ``of`` names ("You and that player each …")."""
    from app.rules import context, effects

    context.bind_players(ctx, e["as"], list(dict.fromkeys([ctx["controller"], *effects._players(plan, ctx, e["of"])])))
    return True


def shortfall_damage(plan: Any, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Each player is dealt ``n`` minus the number of cards they discarded this way (the binding ``of``), all at once (120.3, 608.2h)."""
    from app.rules import context, effects

    gone = [plan.state.cards[c].owner for c in context.objects(plan, ctx, e["of"].removeprefix("ref:"))]  # (the discarded cards, in the graveyards: 400.7j)
    src = effects._ability_source(plan, ctx)
    hits = [(src, p, e["n"] - gone.count(p)) for p in plan.live() if e["n"] - gone.count(p) > 0]
    return effects._deal(plan, ctx, hits, e) if hits else True


RESUME = {"bane100e": resume_bane}
PRIMITIVES = {"as_their100e": as_their, "with_you100e": with_you, "shortfall_damage100e": shortfall_damage, "land_gap_damage100e": land_gap_damage, "foe_hand_damage100e": foe_hand_damage, "bane100e": bane,
              "bind_controlled100e": bind_controlled, "host_bite100e": host_bite, "beneath_top100e": beneath_top, "double_times100e": double_times, "keep_keyword100e": keep_keyword, "keep_dealt100e": keep_dealt}


def parse(body: str) -> Parsed | None:
    build = _TEXTS.get(body.strip().casefold())
    return build() if build is not None else None
