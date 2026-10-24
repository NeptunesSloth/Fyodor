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


def parse(body: str) -> Parsed | None:
    build = _TEXTS.get(body.strip().casefold())
    return build() if build is not None else None
