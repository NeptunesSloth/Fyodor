"""-- planechase events (wave E2) -- a plane's ordinary event triggers and the planar die's own events, in exact Oracle wordings the
ordinary grammar doesn't read (the playbook's cheapest hook): each line is read as a native wording through ``scripts.define`` (so it is
the ordinary trigger the collectors already read on the planar object: ``triggers._watchers``), then adjusted where the native wording
differs.

* "Whenever you roll the planar die, …" / "Whenever you roll a blank on the planar die, …" (Ten Wizards Mountain, The Drum, Pompeii):
  the table's "planar" ``roll`` / ``roll_blank`` events (``handlers.planechase.roll``), ``planar_roll`` / ``planar_roll_blank``
  triggers of the planar controller (901.6: "you" is the planar controller; only their own roll triggers it). The effect is read as the
  same sentence after "At the beginning of your upkeep, ". A blank that Chaotic Aether makes a chaos roll is no blank roll (its text: it
  "is a {CHAOS} roll"; 901.9a-b).
* Goldmeadow: "that land's controller" — the native "its controller". The Dark Barony: "put into a player's graveyard … that player"
  — a card goes to its owner's graveyard (400.3): the native "its owner". Mirrored Depths: "If the player loses the flip" — the native
  "If they lose the flip".
"""

from __future__ import annotations

import copy
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
Fix = Callable[[Def], "Def | None"]
UPKEEP = "At the beginning of your upkeep, "
ROLLS = {"roll": "planar_roll", "roll_blank": "planar_roll_blank"}
TRIGGER_KINDS = frozenset(ROLLS.values())

_ROLL = re.compile(r"Whenever you roll (?P<what>the planar die|a blank on the planar die), (?P<body>.+)")

def _exactly_two(d: Def) -> Def | None:
    """Valor's Reach: "exactly two creatures" — the native "two or more" capped at two (``max_attackers110j``, 508.1, 603.2)."""
    if d["cond"].get("min_attackers") != 2:
        return None
    return {**d, "cond": {**d["cond"], "max_attackers110j": 2}}


def _caster_copies(d: Def) -> Def | None:
    """Izzet Steam Maze: "that player copies it" (707.10: the copy is controlled by the player who copies it, the caster) "The player
    may choose new targets for the copy" (707.10c)."""
    (copy_it,) = d["effects"]
    if copy_it.get("do") != "copy_spell" or copy_it.get("who") != "event_spell":
        return None
    return {**d, "effects": [{**copy_it, "by": "event_player"}, {"do": "copy_new_targets", "optional": True}]}


def _kin(d: Def) -> Def | None:
    """Mondassian Colony Ship: "for each other creature its controller controls that shares a creature type with it" — the native
    "you control" count, with the attacking creature's controller as it resolves (``pump_kin_pce2``)."""
    (pump,) = d["effects"]
    if pump.get("do") != "pump" or pump.get("who") != "event" or pump["p"] != pump["t"]:
        return None
    return {**d, "effects": [{**pump, "do": "pump_kin_pce2"}]}


def _first_to_players(d: Def) -> Def | None:
    """Stensia: "deals damage to one or more players for the first time each turn" (603.2): the native damage event, the first of
    that creature this turn (``first_to_players``)."""
    if d["cond"].get("event") != "deal_damage" or d["cond"].get("to") != "players":
        return None
    return {**d, "cond": {**d["cond"], "first_players_pce2": True}}


def _its_controller_scries(d: Def) -> Def | None:
    """Gardens of Tranquil Repose: "Its controller scries 1." — the dead creature's controller as it last existed (608.2h)."""
    exile, scry = d["effects"]
    if exile.get("do") != "exile" or scry.get("do") != "scry" or scry.get("who") != "you":
        return None
    return {**d, "effects": [exile, {**scry, "who": "ref:event.controller"}]}


# exact Oracle line → (the native ability read in its place, the adjustment)
REWRITES: dict[str, tuple[str, Fix | None]] = {
    "Whenever a land enters, that land's controller creates three 0/1 white Goat creature tokens.":
        ("Whenever a land enters, its controller creates three 0/1 white Goat creature tokens.", None),
    "Whenever a nonblack card is put into a player's graveyard from anywhere, that player loses 1 life.":
        ("Whenever a nonblack card is put into a graveyard from anywhere, its owner loses 1 life.", None),
    "Whenever a player casts a spell, that player flips a coin. If the player loses the flip, counter that spell.":
        ("Whenever a player casts a spell, that player flips a coin. If they lose the flip, counter that spell.", None),
    # (102.4: outside a game between teams, "your team" means "you")
    "Whenever your team attacks with exactly two creatures, those creatures gain double strike until end of turn.":
        ("Whenever you attack with two or more creatures, those creatures gain double strike until end of turn.", _exactly_two),
    "Whenever a player casts an instant or sorcery spell, that player copies it. The player may choose new targets for the copy.":
        ("Whenever a player casts an instant or sorcery spell, copy it.", _caster_copies),
    "Whenever a creature attacks, it gets +1/+1 until end of turn for each other creature its controller controls that shares a creature "
    "type with it.":
        ("Whenever a creature attacks, it gets +1/+1 until end of turn for each other creature you control that shares a creature type "
         "with it.", _kin),
    "Whenever a creature deals damage to one or more players for the first time each turn, put a +1/+1 counter on it.":
        ("Whenever a creature deals damage to one or more players, put a +1/+1 counter on it.", _first_to_players),
    "Whenever a player casts a creature spell that's black, red, or green, it gains devour 5.":
        ("Whenever a player casts a creature spell that's black, red, or green, draw a card.", lambda d: {**d, "effects": [{"do": "jund_pce2"}]}),
    "Suspended Animation — Whenever a creature dies, exile it. Its controller scries 1.":  # (207.2c: an ability word)
        ("Whenever a creature dies, exile it. You scry 1.", _its_controller_scries),
}


def definition(ability: AbilityText, ch: Characteristics) -> Def | None:
    """A plane's ability in one of the wordings above; else None."""
    from app.rules import planar, scripts

    if ability.kind != "triggered" or not planar.planar(ch):
        return None
    text = ability.text.strip()
    if (m := _ROLL.fullmatch(text)) is not None:
        d = scripts.define(replace(ability, text=UPKEEP + m["body"]), ch)
        if d is None or d.get("kind") != "triggered" or d.get("trigger") != "upkeep_you":
            return None
        return {**d, "trigger": "planar_roll" if m["what"] == "the planar die" else "planar_roll_blank"}
    entry = REWRITES.get(text)
    if entry is None:
        return None
    native, fix = entry
    d = scripts.define(replace(ability, text=native), ch)
    if d is None or d.get("kind") != "triggered":
        return None
    return fix(copy.deepcopy(d)) if fix is not None else d


# -- triggering ----------------------------------------------------------------------------------------------------------------
def on_events(plan: Plan, events: list[Event]) -> None:
    """The planar die was rolled (901.9): the face-up plane's "Whenever you roll …" abilities trigger when the roller is the planar
    controller (901.6), controlled by them."""
    from app.game.handlers import planechase
    from app.rules import triggers

    for e in events:
        if e.kind != "planar" or e.manual or e.counter not in ROLLS:
            continue
        ctl = planechase.planar_controller(plan.state)
        pc = plan.state.planechase
        if ctl is None or pc is None or e.player != ctl:
            continue
        for fid in planechase.all_face_ids(pc):  # (every face-up plane: Spatial Merging)
            card = plan.state.cards.get(fid)
            if card is None:
                continue
            ch = plan.ch(card)
            for i, d in triggers.abilities(plan, ch, ROLLS[e.counter or ""]):
                triggers._add(plan, controller=ctl, source_card=card.id, source_object=plan.oid(card), name=ch.name, index=i, definition=d)


def first_to_players(plan: Plan, info: dict[str, Any]) -> bool:
    """Stensia (603.2): this damage event is the creature's first damage to a player this turn when no earlier batch of the turn has
    it dealing damage to a player (the turn's log: ``history.note_events``; 400.7: a new object has dealt none yet)."""
    from app.rules import history

    batch, oid = int(info.get("batch") or 0), info.get("oid")
    return not any(f.kind == "damage" and f.object_id == oid and f.amount > 0 and f.batch and f.batch < batch
                   for f in history.log_for(plan).facts)


# -- primitives -------------------------------------------------------------------------------------------------------------------
def pump_kin(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Mondassian Colony Ship: the native pump, counting the creatures of the attacking creature's controller (as it resolves)."""
    from app.rules import effects, selectors

    cards = effects._cards(plan, ctx, e["who"])
    if not cards:
        return True
    sel = selectors.from_key(e["p"]["count"])
    count = {"count": selectors.replace(sel, controller=f"player:{plan.state.cards[cards[0]].controller}").key()}
    return effects.pump(plan, ctx, {**e, "do": "pump", "p": count, "t": count})


COLOR = "color_pce2"  # the binding of "choose a color" (Nyx, Hotel of Fears)
CHOSEN = "CHOSEN_pce2"  # the chosen color's place in the instructions after it
_LETTER = {"White": "W", "Blue": "U", "Black": "B", "Red": "R", "Green": "G"}


def bind_color(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"choose a color. … your devotion to that color" (700.5): the color chosen as the ability resolves (``choose_value`` bound as
    ``COLOR``) put in the instructions after this one. ``other_than_target``: Hotel of Fears' "sacrifice another creature" — another
    than the target creature (the plane is no creature)."""
    from app.rules import context, effects

    chosen = (context.refs(ctx).get(COLOR) or {}).get("value")
    letter = _LETTER.get(str(chosen))
    if letter is None:
        return True

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return letter if node == CHOSEN else node

    rest = walk(ctx["effects"][ctx["next"]:])
    if e.get("other_than_target"):
        from app.rules import selectors

        oids = [plan.oid(c) for c in effects._cards(plan, ctx, "target")]
        for x in rest:
            if x.get("do") == "sacrifice_choice":
                sel = selectors.from_key(x["sel"])
                x["sel"] = selectors.replace(sel, other=False, extras=(*sel.extras, *(f"exclude_successor58:{o}" for o in oids))).key()
    ctx["effects"] = [*ctx["effects"][:ctx["next"]], *rest]
    return True


# -- this turn's rules changes from chaos (Bad Wolf Bay, The Dining Car): ``RulesState.planar_walk_pcw`` records with the turn -------
NO_EXILE_ENTRY = "no_exile_entry_pce2"
ABILITY_CUT = "ability_cut_pce2"


def _this_turn(plan: Plan, record: Def) -> None:
    r, turn = plan.rules, plan.state.turn.number
    kept = [x for x in r.planar_walk_pcw if x.get("kind") not in (NO_EXILE_ENTRY, ABILITY_CUT) or x.get("turn") == turn]
    r.planar_walk_pcw = [*kept, {**record, "turn": turn}]


def no_exile_entry(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Bad Wolf Bay: "cards can't enter from exile this turn" (614.17: a card in exile that would enter the battlefield this turn
    stays in exile; ``cant_enter``)."""
    _this_turn(plan, {"kind": NO_EXILE_ENTRY, "label": ctx.get("name") or "Bad Wolf Bay"})
    plan.note("Cards can't enter the battlefield from exile this turn")
    return True


def cant_enter(plan: Plan, card: Any) -> tuple[str, bool] | None:
    """(the plane saying so, True: exile is public) when ``card`` is in exile and a "can't enter from exile this turn" holds."""
    if not card.zone.endswith(":exile"):
        return None
    turn = plan.state.turn.number
    found = next((x for x in plan.rules.planar_walk_pcw if x.get("kind") == NO_EXILE_ENTRY and x.get("turn") == turn), None)
    return (str(found.get("label") or "Bad Wolf Bay"), True) if found is not None else None


def ability_cut(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """The Dining Car: "activated abilities of artifact tokens you control cost {2} less to activate this turn" (602.2b, 601.2f,
    611.2a: an effect of the resolving chaos ability, for its controller this turn; ``ability_modifiers``)."""
    _this_turn(plan, {"kind": ABILITY_CUT, "player": ctx["controller"], "mod": e["mod"], "label": ctx.get("name") or "The Dining Car"})
    plan.note(f"{plan.name(ctx['controller'])}'s activated abilities of artifact tokens cost {{{-int(e['mod']['delta'])}}} less this turn")
    return True


def ability_modifiers(state: Any, player: str) -> list[tuple[Any, Def]]:
    """(source, ability_cost_modifier definition) pairs of this turn's ``ability_cut`` records of ``player`` (permissions.ability_mana:
    the source stands for the player, its controller)."""
    from app.game.state import CardInstance, zone_key

    r = state.rules
    if r is None or not r.planar_walk_pcw:
        return []
    return [(CardInstance(id=f"pce2-{i}", card_id="", name=x.get("label"), owner=player, controller=player, zone=zone_key(player, "command")),
             x["mod"]) for i, x in enumerate(r.planar_walk_pcw)
            if x.get("kind") == ABILITY_CUT and x.get("player") == player and x.get("turn") == state.turn.number]


def daleks(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """City of the Daleks: "for each opponent, you create a … token … that attacks that opponent this turn if able" — for each
    opponent in turn order (101.4), the native token instructions (``per``: create it, haste, sacrificed at the next end step) with
    their bindings renamed, and the requirement to attack that opponent (508.1d: ``attack_player:<player>``) this turn."""
    import json

    from app.rules.plan import live_players

    you = ctx["controller"]
    jobs: list[Def] = []
    for i, opp in enumerate(p for p in plan.apnap() if p != you and p in live_players(plan.state)):
        per = json.loads(json.dumps(e["per"]).replace('"e0"', f'"dalek{i}a"').replace('"ref:e0"', f'"ref:dalek{i}a"')
                         .replace('"e1"', f'"dalek{i}b"').replace('"ref:e1"', f'"ref:dalek{i}b"'))
        jobs += [per[0], {"do": "restrict", "who": f"ref:dalek{i}a", "rules": [f"attack_player:{opp}"]}, *per[1:]]
    ctx["effects"][ctx["next"]:ctx["next"]] = jobs
    return True


def rolls_counters(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Li'l Giri Saves the Day: "X is the number of times you've rolled the planar die this turn" — the planar die rolls of this turn
    (901.9: only the active player rolls; ``Planechase.rolls`` counts them), "you" being the planar controller (901.6)."""
    from app.rules import effects

    pc = plan.state.planechase
    n = pc.rolls if pc is not None and pc.roll_turn == plan.state.turn.number and plan.active == ctx["controller"] else 0
    return effects.add_counters(plan, ctx, {**e, "do": "add_counters", "n": n})


def jund(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Jund: "it gains devour 5" — the creature spell gains the ability (a layer 6 effect, 613.1f) and keeps it as the permanent it
    becomes (400.7a), so it devours as it enters (702.82a). A spell gone from the stack gains nothing (400.7)."""
    from app.rules import effects

    cards = effects._cards(plan, ctx, "event_spell")
    if not cards:
        return True
    if any(ab.kind == "keywords" and "devour" in ab.keywords for ab in plan.ch(plan.state.cards[cards[0]]).abilities):
        plan.note("It has devour already: the players sacrifice for each devour instance by hand (702.82)", cards)
    return effects.grant(plan, ctx, {"do": "grant", "who": "event_spell", "keywords": [], "abilities": ["Devour 5"], "duration": "permanent"})


OSSUARY = "_ossuary_pce2"


def ossuary_mark(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """Grand Ossuary: "each player exiles all creatures they control" — each creature's controller and power as it is now, just before
    the exile (608.2h: the creatures exiled this way, as they last existed on the battlefield)."""
    from app.rules import sba

    marks = {}
    for c in plan.state.cards.values():
        if c.zone.endswith(":battlefield"):
            ch = plan.ch(c)
            if ch.is_creature:
                marks[c.id] = [c.controller, sba.power(c, ch)]
    ctx[OSSUARY] = marks
    return True


def ossuary_tokens(plan: Plan, ctx: dict[str, Any], e: Def) -> bool:
    """"… and creates X 1/1 green Saproling creature tokens, where X is the total power of the creatures they exiled this way": only the
    creatures that are now in exile count (a commander its owner put into the command zone instead wasn't exiled, 903.9b); a total
    below zero is zero (107.1b). Each player's tokens are created in turn order (101.4)."""
    marks = ctx.pop(OSSUARY, {}) or {}
    totals: dict[str, int] = {}
    for cid, (who, power) in marks.items():
        card = plan.state.cards.get(cid)
        if card is not None and card.zone.endswith(":exile"):
            totals[who] = totals.get(who, 0) + int(power)
    made = [{"do": "create_token", "who": f"player:{pid}", "n": totals[pid], "token": e["token"]}
            for pid in plan.apnap() if totals.get(pid, 0) > 0]
    ctx["effects"][ctx["next"]:ctx["next"]] = made
    return True


PRIMITIVES: dict[str, Any] = {"pump_kin_pce2": pump_kin, "ossuary_mark_pce2": ossuary_mark, "ossuary_tokens_pce2": ossuary_tokens, "jund_pce2": jund, "rolls_counters_pce2": rolls_counters, "daleks_pce2": daleks, "bind_color_pce2": bind_color, "no_exile_entry_pce2": no_exile_entry, "ability_cut_pce2": ability_cut}
