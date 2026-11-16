"""-- planechase chaos (wave B) -- chaos abilities ("Whenever chaos ensues, …", 311.7, 901.9b) of planes whose wording the
ordinary grammar doesn't read, by exact Oracle text (the playbook's cheapest hook): each is read as a native wording through
``planar.definition`` (so it is a ``planar_chaos`` trigger of the planar controller, 901.6: "you" is the planar controller), then
adjusted where the native wording differs.

* An ability word or flavor word before the trigger ("Will of the council — Whenever chaos ensues, …"): 207.2c / 207.2d, it has no
  rules meaning: the ability is read without it.
* Besieged Viking Village: "target creature you control that attacked this turn" (the "attacked this turn" selector extra; never
  "attacking": chaos is rolled in a main phase, 901.9, when no creature is attacking).
* Velis Vel: "gains all creature types until end of turn" (205.3m: a ``become`` with ``all_creature_types``, retaining its types).
* Lair of the Ashen Idol: "any number of target players each create …" (115.1, 601.2c: one target group of zero or more players).
* Kessig, Esper, Sokenzan: equivalent native sentences. Sokenzan's "If it's a main phase, there is an additional combat phase after
  this phase, followed by an additional main phase" is ``extra_phases`` after a main phase, which does nothing outside one (500.8).
* "until a player planeswalks" (Agyrem, Eloren Wilds, Celestine Reef): a duration (611.2a) that ends as any player planeswalks
  (701.31: the planar controller; ``on_events`` reads the table's "planar" ``from`` event). The effect is built as the native
  "until your next turn" one with this duration instead: a continuous effect (``ContinuousEffect.duration``), a cast limit
  (``cast_limits`` record ``until``), or a "can't lose / can't win" record (``game_result`` record ``until``).
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from app.rules.characteristics import Characteristics
from app.rules.oracle import AbilityText

if TYPE_CHECKING:
    from app.game.rules_state import Event
    from app.rules.plan import Plan

Def = dict[str, Any]
PLANESWALK = "planeswalk_pcb"  # the duration "until a player planeswalks"
LABEL = "until a player planeswalks"
CHAOS = "Whenever chaos ensues, "

_WORD = re.compile(r"(?P<word>[A-Z][\w'!,. -]*?) — (?P<rest>(?:Whenever|When) [Cc]haos ensues, .+)")


def _native(ability: AbilityText, ch: Characteristics, body: str) -> Def | None:
    from app.rules import planar

    return planar.definition(replace(ability, text=CHAOS + body), ch)


def _swap_duration(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    """"until your next turn" → "until a player planeswalks" (every place the native definition names that duration)."""
    return json.loads(json.dumps(d).replace('"next_turn"', json.dumps(PLANESWALK)))


def _celestine(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    effects = [{**e, "until": PLANESWALK} for e in d["effects"]]
    assert all(e["do"] == "cant_result" for e in effects)
    return {**d, "effects": effects}


def _attacked(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    from app.rules import selectors

    sel = selectors.from_key('sel:{"controller":"you","extras":["attacked_this_turn"],"types":["Creature"]}')
    return {**d, "target": {**d["target"], "what": sel.key()}}


def _all_types(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    (e,) = d["effects"]
    e = {k: v for k, v in e.items() if k != "add_creature_types"}
    return {**d, "effects": [{**e, "all_creature_types": True}]}


def _each_target_player_creates(d: Def, ability: AbilityText, ch: Characteristics) -> Def | None:
    token = _native(ability, ch, "create a 2/2 black Zombie creature token.")
    if token is None:
        return None
    (create,) = token["effects"]
    (mill,) = d["effects"]
    return {**d, "effects": [{**create, "who": mill["who"]}]}


def _treasures_deal(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    """The Western Cloud: the three Treasures just created (bound as they're made) are the sources, each its own (120.3, 608.2h)."""
    create, *hits = d["effects"]
    assert create["do"] == "create_token" and all(e["do"] == "damage" and str(e["src"]).startswith("each:") for e in hits)
    return {**d, "effects": [{**create, "as": "treasures_pcb"}, *({**e, "src": "ref:treasures_pcb", "src_many": True} for e in hits)]}


def _up_to_one_each(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    """The Great Aerie: "up to one target … and up to one target …" (115.1, 601.2c); with either missing nothing is dealt
    (damage_snapshot_outcomes ``grim``: "the other" doesn't exist)."""
    return {**d, "targets": [{**t, "min": 0, "max": 1} for t in d["targets"]]}


Fix = Callable[[Def, AbilityText, Characteristics], "Def | None"]


def _food_instead(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    """The Wilds: "If they do, you create a Food token. You create two Food tokens instead if the sacrificed creature's toughness was 4
    or greater." — one Food or (614.1a: instead) two, judged on the creature as it last existed (608.2h: ``ref:e0``, the sacrificed one)."""
    edict, did, food = d["effects"]
    assert edict["do"] == "edict" and edict.get("as") == "e0" and did["do"] == "only_if" and food["do"] == "create_token" and food["n"] == 1
    big = {"value": {"toughness": "ref:e0"}, "op": ">=", "n": 4}
    return {**d, "effects": [edict, {**did, "skip": 4}, {"do": "only_if", "cond": big, "skip": 1}, {**food, "n": 2},
                             {"do": "only_if", "cond": {"not": big}, "skip": 1}, food]}


def _grant_line(d: Def, line: str) -> Def:
    (grant,) = d["effects"]
    assert grant["do"] == "grant" and grant["keywords"] == ["trample"]
    return {**d, "effects": [{**grant, "keywords": [], "abilities": [line]}]}


def _first_is(effect: Def) -> Fix:
    """The native wording's first effect ("you gain 1 life.") replaced by an existing primitive; the rest (e.g. "Then planeswalk.",
    701.31) stays as read."""
    def fix(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
        first, *rest = d["effects"]
        assert first["do"] == "gain_life"
        return {**d, "effects": [dict(effect), *rest]}
    return fix


# exact Oracle line → (the native body read after "Whenever chaos ensues, ", the adjustment)
REWRITES: dict[str, tuple[str, Fix | None]] = {
    "Whenever chaos ensues, put an indestructible counter on target creature you control that attacked this turn.":
        ("put an indestructible counter on target creature you control.", _attacked),
    "Whenever chaos ensues, target creature gains all creature types until end of turn.":
        ("target creature becomes a Werewolf in addition to its other types until end of turn.", _all_types),
    "Whenever chaos ensues, any number of target players each create a 2/2 black Zombie creature token.":
        ("any number of target players each mill two cards.", _each_target_player_creates),
    "Whenever chaos ensues, each creature you control gets +2/+2, gains trample, and becomes a Werewolf in addition to its other types "
    "until end of turn.":
        ("each creature you control gets +2/+2 and gains trample until end of turn. Each creature you control becomes a Werewolf in "
         "addition to its other types until end of turn.", None),
    "Whenever chaos ensues, creatures you control that are white, blue, and/or black become artifacts in addition to their other types "
    "until end of turn. Then each artifact creature you control gains vigilance, menace, and lifelink until end of turn.":
        ("each creature you control that's white, blue, or black becomes an artifact in addition to its other types until end of turn. "
         "Then each artifact creature you control gains vigilance, menace, and lifelink until end of turn.", None),
    "Whenever chaos ensues, untap all creatures that attacked this turn. If it's a main phase, there is an additional combat phase after "
    "this phase, followed by an additional main phase.":
        ("untap all creatures that attacked this turn. After this main phase, there is an additional combat phase followed by an "
         "additional main phase.", None),
    "Whenever chaos ensues, create three tapped Treasure tokens. They each deal 1 damage to each creature and each planeswalker.":
        ("create three tapped Treasure tokens. Each creature deals 1 damage to each creature and each planeswalker.", _treasures_deal),
    "Whenever chaos ensues, choose up to one target creature you control and up to one target creature an opponent controls. Each of "
    "those creatures deals damage equal to its toughness to the other.":
        ("choose target creature you control and target creature an opponent controls. Each of those creatures deals damage equal to "
         "its toughness to the other.", _up_to_one_each),
    # Temple of Atropos: Aeon Engine's reversal (wave110m_cards ``reverse_turn_order110m``), then planeswalk (701.31)
    "When chaos ensues, reverse the game's turn order. Then planeswalk.":
        ("you gain 1 life. Then planeswalk.", _first_is({"do": "reverse_turn_order110m"})),
    # The Doctor's Tomb: The Sands of Time's redistribution (wave110o_cards ``redistribute110o``)
    "Whenever chaos ensues, redistribute any number of players' life totals.":
        ("you gain 1 life.", _first_is({"do": "redistribute110o"})),
    "Whenever chaos ensues, target player sacrifices a creature of their choice. If they do, you create a Food token. You create two Food "
    "tokens instead if the sacrificed creature's toughness was 4 or greater.":
        ("target player sacrifices a creature of their choice. If they do, you create a Food token.", _food_instead),
    # The Cheetah Planet: provoke granted as its ability line (702.39a, keyword_triggers: as "creatures you control gain flanking")
    "Whenever chaos ensues, all Cats gain provoke until end of turn.":
        ("all Cats gain trample until end of turn.", lambda d, ability, ch: _grant_line(d, "Provoke.")),
    # -- "until a player planeswalks" --
    "Whenever chaos ensues, creatures can't attack you until a player planeswalks.":
        ("creatures can't attack you until your next turn.", _swap_duration),
    "Whenever chaos ensues, target player can't cast spells until a player planeswalks.":
        ("target player can't cast spells until your next turn.", _swap_duration),
    "Whenever chaos ensues, until a player planeswalks, you can't lose the game and your opponents can't win the game.":
        ("you can't lose the game this turn and your opponents can't win the game this turn.", _celestine),
}


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's chaos ability in one of the wordings above; else None."""
    from app.rules import planar

    if ability.kind != "triggered" or not planar.planar(ch):
        return None
    text = ability.text.strip()
    if (m := _WORD.fullmatch(text)) is not None:  # 207.2c-d: an ability word / flavor word has no rules meaning
        from app.rules import scripts

        return scripts.define(replace(ability, text=m["rest"]), ch)
    entry = REWRITES.get(text)
    if entry is None:
        return None
    body, fix = entry
    d = _native(ability, ch, body)
    if d is None:
        return None
    return fix(copy.deepcopy(d), ability, ch) if fix is not None else d


# -- "until a player planeswalks" -----------------------------------------------------------------------------------------------
def on_events(plan: Plan, events: list[Event]) -> None:
    """611.2a: a player planeswalked (701.31, the table's "planar" ``from`` event): the effects lasting until then end — also when the
    table planeswalked by hand (a manual event: no trigger is read from it, but the planeswalk happened all the same)."""
    if not any(e.kind == "planar" and e.counter == "from" for e in events):
        return
    from app.rules import delayed

    r = plan.rules
    if ended := [x for x in r.effects if x.duration == PLANESWALK]:
        delayed._end(plan, ended)
    r.cast_limits = [x for x in r.cast_limits if x.get("until") != PLANESWALK]
    r.results = [x for x in r.results if x.get("until") != PLANESWALK]
