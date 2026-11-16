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
SHORT = "Chaos: "

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



# -- planechase events (wave E2) -- "choose a color. … your devotion to that color" (700.5): the color chosen as it resolves
def _chosen_color(d: Def, *, mana: bool = False, other_than_target: bool = False) -> Def:
    from app.rules import planar_events as pe

    choose, *rest = d["effects"]
    assert choose["do"] == "choose_value" and choose["what"] == "color"
    bind = {"do": "bind_color_pce2", **({"other_than_target": True} if other_than_target else {})}
    if mana:
        rest = [{"do": "add_mana", "sym": pe.CHOSEN, "n": {"devotion": [pe.CHOSEN]}}]
    else:
        rest = json.loads(json.dumps(rest).replace('{"devotion": ["W"]}', json.dumps({"devotion": [pe.CHOSEN]})))
    return {**d, "effects": [{**choose, "as": pe.COLOR}, bind, *rest]}



def _ketria(d: Def, ability: AbilityText, ch: Characteristics) -> Def:
    """Ketria: Illuna, Apex of Wishes' library packet (library_packets101): exile until a nonland permanent card, then that card onto
    the battlefield or into its owner's hand (its controller's choice); the other exiled cards stay in exile."""
    from app.rules import library_packets101

    packet = {"do": "library_packet101", "mode": "exile", "as": "packet101", "hits": "ref:packet_hits101",
              "sel": library_packets101._selector("nonland permanent card"), "need": 1}
    return {**d, "effects": [packet, {"do": "packet_destination101", "who": "ref:packet_hits101"}]}


def _dining_car(d: Def, ability: AbilityText, ch: Characteristics) -> Def | None:
    from app.rules import scripts

    mod = scripts.define(replace(ability, kind="static", text="Activated abilities of artifact tokens you control cost {2} less to activate."), ch)
    if mod is None or mod.get("static") != "ability_cost_modifier":
        return None
    return {**d, "effects": [{"do": "ability_cut_pce2", "mod": mod}]}



def _ossuary(d: Def, ability: AbilityText, ch: Characteristics) -> Def | None:
    """Grand Ossuary: every creature is exiled at once (each player exiles their own: one event, 101.4 / 608.2c), then each player creates
    Saprolings for the total power of their creatures exiled this way (planar_events ``ossuary_*``); then planeswalk (701.31)."""
    from app.rules import scripts

    exile, token = scripts.parse_effects("Exile all creatures."), scripts.parse_effects("Create a 1/1 green Saproling creature token.")
    first, *rest = d["effects"]
    if exile is None or token is None or first["do"] != "gain_life":
        return None
    return {**d, "effects": [{"do": "ossuary_mark_pce2"}, *copy.deepcopy(exile[0]),
                             {"do": "ossuary_tokens_pce2", "token": copy.deepcopy(token[0][0]["token"])}, *rest]}


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
    # -- planechase events (wave E2) -- Valor's Reach: "your team" is "you" outside a game between teams (102.4); "If it's a main
    # phase, …" as Sokenzan's
    "Whenever chaos ensues, untap up to two target creatures your team controls. If it's a main phase, there is an additional combat "
    "phase after this phase, followed by an additional main phase.":
        ("untap up to two target creatures you control. After this main phase, there is an additional combat phase followed by an "
         "additional main phase.", None),
    # Gardens of Tranquil Repose: "one plus the number of cards exiled with ~" (607.2a: exiled by its own exile ability, linked to this object)
    "Whenever chaos ensues, create X 3/3 black Dalek artifact creature tokens with menace, where X is one plus the number of cards exiled "
    "with Gardens of Tranquil Repose.":
        ("create X 3/3 black Dalek artifact creature tokens with menace, where X is the number of cards exiled with Gardens of Tranquil "
         "Repose.", lambda d, ability, ch: {**d, "effects": [{**d["effects"][0], "n": {"plus": [d["effects"][0]["n"], 1]}}]}),
    # Nyx: Nykthos' mana, from a chaos ability (not a mana ability: it triggers on chaos, 605.1b)
    "Whenever chaos ensues, choose a color. Add an amount of mana of that color equal to your devotion to that color.":
        ("choose a color. You gain 1 life.", lambda d, ability, ch: _chosen_color(d, mana=True)),
    # Hotel of Fears (after its ability word, 207.2c): "sacrifice another creature" — another than the target creature
    "Whenever chaos ensues, choose a color. Put X +1/+1 counters on target creature you control, where X is your devotion to that "
    "color. Then sacrifice another creature.":
        ("choose a color. Put X +1/+1 counters on target creature you control, where X is your devotion to white. Then sacrifice "
         "another creature.", lambda d, ability, ch: _chosen_color(d, other_than_target=True)),
    "Whenever chaos ensues, exile cards from the top of your library until you exile a nonland permanent card. Put that card onto the "
    "battlefield or into your hand.":
        ("you gain 1 life.", _ketria),
    "When chaos ensues, cards can't enter from exile this turn. Then planeswalk.":
        ("you gain 1 life. Then planeswalk.", _first_is({"do": "no_exile_entry_pce2"})),
    "Whenever chaos ensues, activated abilities of artifact tokens you control cost {2} less to activate this turn.":
        ("you gain 1 life.", _dining_car),
    "Whenever chaos ensues, for each opponent, you create a 3/3 black Dalek artifact creature token with menace that attacks that "
    "opponent this turn if able. Those tokens gain haste. Sacrifice them at the beginning of the next end step.":
        ("create a 3/3 black Dalek artifact creature token with menace. It gains haste. Sacrifice it at the beginning of the next end "
         "step.", lambda d, ability, ch: {**d, "effects": [{"do": "daleks_pce2", "per": d["effects"]}]}),
    # -- "Chaos: …" lines (above): The Food Court — "If you are already the Monarch" is judged before you become it (724): the draw first
    "Whenever chaos ensues, you become the Monarch. If you are already the Monarch, draw a card.":
        ("draw a card if you're the monarch. You become the monarch.", None),
    "Whenever chaos ensues, you may sacrifice a Food. If you do, draw a card, gain three life and each opponent loses 3 life.":
        ("you may sacrifice a Food. If you do, draw a card, gain 3 life, and each opponent loses 3 life.", None),
    "Whenever chaos ensues, put X +1/+1 counters on target legendary artifact creature you control, where X is the number of times "
    "you've rolled the planar die this turn.":
        ("put X +1/+1 counters on target legendary artifact creature you control, where X is the number of creatures you control.",
         lambda d, ability, ch: {**d, "effects": [{**d["effects"][0], "do": "rolls_counters_pce2"}]}),
    # Glimmervoid Basin: each player other than the target creature's controller (as it last existed, 608.2h) creates one copy (707.1)
    "Whenever chaos ensues, choose target creature. Each player except that creature's controller creates a token that's a copy of that "
    "creature.":
        ("create a token that's a copy of target creature.",
         lambda d, ability, ch: {**d, "effects": [{**d["effects"][0], "creator": "others100c:target_player_or_controller", "each_creator": True}]}),
    "Whenever chaos ensues, each player exiles all creatures they control and creates X 1/1 green Saproling creature tokens, where X is "
    "the total power of the creatures they exiled this way. Then planeswalk.":
        ("you gain 1 life. Then planeswalk.", _ossuary),
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

    if not planar.planar(ch):
        return None
    text = ability.text.strip()
    if ability.kind == "static" and text.startswith(SHORT):  # -- planechase events (wave E2) -- "Chaos: …" (the Unknown Event planes'
        # shorthand for a chaos ability, 311.7): read as "Whenever chaos ensues, …"
        from app.rules import scripts

        body = text[len(SHORT):]
        return scripts.define(replace(ability, kind="triggered", text=CHAOS + body[:1].lower() + body[1:]), ch)
    if ability.kind != "triggered":
        return None
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
