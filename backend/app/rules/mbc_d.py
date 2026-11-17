"""-- Mystery Booster Commander (wave MBC-D) -- the last two oval-stamped (Commander-legal) Mystery Booster Commander Edition cards that the
engine left by hand (docs/research/mbc-refused.md), each read in its exact Oracle wording. CR 2026-09-25.

* Miss Highwater (Menace, then): "Whenever ~ deals combat damage to a player who doesn't have a contract counter, they may discard their hand. If
  they do, they draw seven cards and get a contract counter. For as long as they have a contract counter, when they lose the game, for each
  artifact and creature they controlled, create a token that's a copy of it."
  - "a player who doesn't have a contract counter": part of the trigger event (603.2), judged as the damage is dealt (triggers.py
    ``recipient_lacks_counter_mbc``; a player's counters are ``PlayerState.resources``, 122.1).
  - "they may discard their hand. If they do": the damaged player decides as the ability resolves (608.2d); a player with no cards in hand can
    still choose to (discarding an empty hand discards nothing, and "If they do" then holds: they did discard their hand). Then they draw seven
    cards and get a contract counter (122.1), through the counter choke point (a replacement may change it).
  - The last sentence creates a delayed triggered ability (603.7a) controlled by Miss Highwater's controller, which outlives her: it waits for
    that player to lose the game (704.5, an effect, or a concession, 104.3a), "for as long as they have a contract counter" (611.2b: judged as
    they lose; if they have none as it would begin, nothing is created). It sees the artifacts and creatures that player controlled as they left
    the game (800.4a: snapshots taken before anything left with them, app/rules/left_game.py) and creates a token copy of each (707.2, from
    their copiable values as they last existed, 608.2h) under its controller's control — Miss Highwater's controller as the trigger resolved.

* Chira, All In: "Whenever you discard one or more cards at random, select one or more targets at random, choose one or more modes at random,
  flip one or more coins, or roll one or more dice, put a +1/+1 counter on ~ and create a tapped Treasure token."
  One trigger on five kinds of the random choices the rules engine makes (app/rules/randomness.py: every random pick goes through one helper
  that records a ``random_choice`` event — who made it, which kind): a random discard (701.9b: the discarding player), a target selected at
  random and a mode chosen at random (their controller), a coin flip (705: the flipper, heads/tails flips included) and a die roll (706: the
  roller; 706.7 / 901.9d: rolling the planar die too). "One or more": once for each such event of an event batch, per player (603.2c).
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.oracle import AbilityText
    from app.rules.plan import Plan

Def = dict[str, Any]

HIGHWATER = ("Whenever ~ deals combat damage to a player who doesn't have a contract counter, they may discard their hand. If they do, they "
             "draw seven cards and get a contract counter. For as long as they have a contract counter, when they lose the game, for each "
             "artifact and creature they controlled, create a token that's a copy of it.")
CHIRA = ("Whenever you discard one or more cards at random, select one or more targets at random, choose one or more modes at random, flip one "
         "or more coins, or roll one or more dice, put a +1/+1 counter on ~ and create a tapped Treasure token.")
CONTRACT = "contract"


def _native(ability: AbilityText, ch: Characteristics, text: str) -> Def | None:
    from app.rules import scripts

    d = scripts.define(replace(ability, text=text, kind="triggered"), ch)
    return copy.deepcopy(d) if d is not None else None


def _does(d: Def | None, *names: str) -> bool:
    return d is not None and [e.get("do") for e in d.get("effects") or []] == list(names)


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """One of the lines of the module docstring, in its exact wording; else None."""
    from app.rules import scripts

    if ability.index >= 100 or ability.kind != "triggered":
        return None
    text = scripts.self_text(ability.text.strip(), ch.name)
    if text == HIGHWATER:
        return _highwater(ability, ch)
    if text == CHIRA:
        return _chira(ability, ch)
    return None


def _highwater(ability: AbilityText, ch: Characteristics) -> Def | None:
    may = _native(ability, ch, "Whenever ~ deals combat damage to a player, that player may draw seven cards.")
    discard = _native(ability, ch, "Whenever ~ deals combat damage to a player, that player discards their hand.")
    counter = _native(ability, ch, "Whenever ~ deals combat damage to a player, that player gets a poison counter.")
    if not _does(may, "optional_payment", "only_if", "draw") or not _does(discard, "discard") or not _does(counter, "player_counter"):
        return None
    assert may is not None and discard is not None and counter is not None
    pay, gate, draw = may["effects"]
    if pay.get("who") != "event_player" or draw.get("who") != "event_player" or draw.get("n") != 7 or not discard["effects"][0].get("all"):
        return None
    if (may.get("cond") or {}).get("event") != "deal_combat_damage_player":
        return None
    bind = "highwater_mbc"
    return {**may, "cond": {**may["cond"], "recipient_lacks_counter_mbc": CONTRACT}, "effects": [
        {**pay, "ask": "discard your hand (if you do, you draw seven cards and get a contract counter)", "bind": bind},
        {**gate, "cond": {"succeeded": bind}, "skip": 4},
        discard["effects"][0],
        draw,
        {**counter["effects"][0], "counter": CONTRACT, "n": 1},
        {"do": "highwater_mbc"}]}


def _chira(ability: AbilityText, ch: Characteristics) -> Def | None:
    from app.rules import randomness

    d = _native(ability, ch, "Whenever you roll one or more dice, put a +1/+1 counter on ~ and create a tapped Treasure token.")
    if not _does(d, "add_counters", "create_token") or (d or {}).get("cond", {}).get("event") != "roll":
        return None
    assert d is not None
    return {**d, "cond": {"event": "random_choice", "subject": "player", "player": "you", "aggregate": True,
                          "random_kinds": list(randomness.CHIRA_KINDS)}}


def highwater(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """The delayed triggered ability on the damaged player's loss (app/rules/left_game.py), for as long as they have a contract counter."""
    from app.rules import effects, left_game

    for pid in effects._players(plan, ctx, "event_player")[:1]:
        left_game.create(plan, ctx, pid, [{"do": "copy_left_game", "types": ["Artifact", "Creature"]}], while_counter=CONTRACT)
    return True


PRIMITIVES: dict[str, Any] = {"highwater_mbc": highwater}
