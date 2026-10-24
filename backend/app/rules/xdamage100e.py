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


PRIMITIVES = {"beneath_top100e": beneath_top, "double_times100e": double_times, "keep_keyword100e": keep_keyword, "keep_dealt100e": keep_dealt}


def parse(body: str) -> Parsed | None:
    build = _TEXTS.get(body.strip().casefold())
    return build() if build is not None else None
