"""-- planechase automation -- planes and phenomena as rules objects (CR 311, 312, 901; the table's procedure is
app/game/handlers/planechase.py).

**The object.** With a rules engine, the face-up plane or phenomenon is a card instance in the planar controller's command zone
(``handlers.planechase.sync``: id ``planar-…``, its printing's Oracle text, in no zone list so no view shows it as a card). 113.6p /
311.4 / 901.7: its abilities function there: its static abilities affect the game, its triggered abilities trigger. The engine's
collectors read it like an emblem (``face_card``): ``layers.statics`` (anthems and grants), ``permissions._all_table_statics`` (the
statics read through ``_table_statics``: cost changes), ``triggers._watchers`` / ``at_step`` / ``_step_abilities``
(ordinary trigger wordings: "Whenever a creature enters", "At the beginning of your upkeep" — "your" is the planar controller's,
normally the active player's, so it triggers in every player's upkeep, 311.5).

**Its own triggers** (``definition``, a ``hooks.DEFINE`` entry; read only on a Plane or Phenomenon):

* "Whenever chaos ensues, …" (311.7: a chaos ability; also "When chaos ensues") → ``planar_chaos``; it triggers on the chaos symbol
  (901.9b) and is controlled by the planar controller;
* "When you planeswalk to ~, …" / "When you planeswalk here, …" (701.31d) → ``planar_to``; with "… and at the beginning of your
  upkeep" one ability with both trigger events (603.2: ``multi:planar_to+upkeep_you``);
* "When you planeswalk away from ~, …" (701.31d) → ``planar_from`` (the object is gone by then: its printing is in the event);
* "When you encounter ~, …" (312.5: moving it off the planar deck face up) → ``planar_encounter``.

The ability's effect is read by the ordinary grammar (the same sentence after "At the beginning of your upkeep, "), so whatever that
grammar refuses stays manual. ``on_events`` puts them on the waiting list from the table's "planar" events (``collect``), and adds the
inherent planeswalking ability (901.8: no source, controlled by the roller) when the rules engine rolled the planeswalker symbol.

**Planeswalk** (701.31): the ``planeswalk901`` primitive ("planeswalk" in an effect: ``language.designation_instruction``). Only the
planar controller planeswalks (701.31a); outside a Planechase game nothing happens.

**Phenomena** (312.7 / 704.6f): a state-based action: when a face-up phenomenon isn't the source of a triggered ability that has
triggered but not yet left the stack, the planar controller planeswalks (``sba``). Only for a phenomenon whose encounter ability the
engine runs: one it can't read waits for the players ("Done — planeswalk"), as on a manual table.

**Coverage** (``ability_ok``): what the collectors above read, as ``designations.emblem_text_ok`` does for emblems: a static or trigger
the planar object isn't read for is not supported, so a plane is FULL only when every line is one of these.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from app.game.handlers import planechase
from app.game.rules_state import Event
from app.game.state import CardInstance, zone_key
from app.rules.characteristics import Characteristics
from app.rules.context import Context
from app.rules.oracle import AbilityText
from app.rules.plan import Plan

PLANAR_TYPES = frozenset({"Plane", "Phenomenon"})
TRIGGERS = {"chaos": "planar_chaos", "to": "planar_to", "from": "planar_from", "encounter": "planar_encounter"}
UPKEEP = "At the beginning of your upkeep, "

_CHAOS = re.compile(r"(?:Whenever|When) [Cc]haos ensues, (?P<body>.+)")
_TO = re.compile(r"(?:Whenever|When) you planeswalk (?:to ~|to this plane|here)(?P<upkeep> and at the beginning of your upkeep)?, (?P<body>.+)")
_FROM = re.compile(r"When you planeswalk away from ~, (?P<body>.+)")
_ENCOUNTER = re.compile(r"When you encounter ~, (?P<body>.+)")


def face_card(card: CardInstance) -> bool:
    """The face-up plane or phenomenon's rules object (311.4, 312.4): its abilities work from the command zone (113.6p)."""
    return planechase.is_face(card) and card.zone.endswith(":command")


def planar(ch: Characteristics) -> bool:
    return bool(PLANAR_TYPES & ch.types)


def definition(ability: AbilityText, ch: Characteristics) -> dict[str, Any] | None:
    """A plane's or phenomenon's own trigger (module docstring), its effect read by the ordinary grammar; else None."""
    if not planar(ch) or ability.kind != "triggered":
        return None
    text = ability.text.strip().replace(ch.name, "~") if ch.name else ability.text.strip()
    trigger, body = None, None
    if (m := _CHAOS.fullmatch(text)) is not None:
        trigger, body = "planar_chaos", m["body"]
    elif (m := _TO.fullmatch(text)) is not None:
        trigger, body = ("multi:planar_to+upkeep_you" if m["upkeep"] else "planar_to"), m["body"]
    elif (m := _FROM.fullmatch(text)) is not None:
        trigger, body = "planar_from", m["body"]
    elif (m := _ENCOUNTER.fullmatch(text)) is not None and "Phenomenon" in ch.types:
        trigger, body = "planar_encounter", m["body"]
    if trigger is None or body is None:
        return None
    from app.rules import scripts

    body = body.replace("~", ch.name) if ch.name else body
    d = scripts.define(replace(ability, text=UPKEEP + body), ch)
    if d is None or d.get("kind") != "triggered" or d.get("trigger") != "upkeep_you":
        return None
    return {**d, "trigger": trigger}


# -- triggering ----------------------------------------------------------------------------------------------------------------
def _source(plan: Plan, e: Event) -> CardInstance | None:
    """The object the event is about: the face-up card's, or (planeswalked away from: gone, 901.7a) one built from its printing."""
    card = plan.state.cards.get(e.card or "")
    if card is not None:
        return card
    ctl = planechase.planar_controller(plan.state)
    if not e.printing or ctl is None:
        return None
    return CardInstance(id=e.card or "planar-gone", card_id=e.printing, owner=ctl, controller=ctl, zone=zone_key(ctl, "command"))


def on_events(plan: Plan, events: list[Event]) -> None:
    """The table's "planar" events (handlers.planechase): chaos (311.7), planeswalking to / away from (701.31d), encountering
    (312.5) — the face-up card's abilities for them, controlled by the planar controller — and the planeswalking ability (901.8)."""
    from app.rules import characteristics as chars
    from app.rules import designations, planar_chaos, triggers

    planar_chaos.on_events(plan, events)  # -- planechase chaos (wave B) -- "until a player planeswalks" ends (611.2a)
    from app.rules import (
        planar_walk,  # -- planechase walk (wave C) -- Chaotic Aether ends as a player planeswalks away from a plane
    )

    planar_walk.on_events(plan, events)
    from app.rules import (
        planar_more,  # -- planechase more (wave E1) -- Unyaro's phasing ends; "if you planeswalked to ~ this turn"; Sea of Sand
    )

    planar_more.on_events(plan, events)
    from app.rules import planar_events  # -- planechase events (wave E2) -- the planar die's roll triggers

    planar_events.on_events(plan, events)
    from app.rules import (
        planar_more2,  # -- planechase more 2 (wave F1) -- Glen Elendra: this combat's combat damage to players
    )

    planar_more2.on_events(plan, events)
    from app.rules import (
        planar_more3,  # -- planechase more 3 (wave F2) -- The Doctor's Childhood Barn: a planeswalk's delayed triggers
    )

    planar_more3.on_events(plan, events)
    for e in events:
        if e.kind != "planar" or e.manual:
            continue
        if e.counter == "walk_roll":  # 901.8: "Whenever you roll the Planeswalker symbol on the planar die, planeswalk." (no source)
            if e.player:
                designations._add_trigger(plan, e.player, "Planeswalking ability", [{"do": "planeswalk901", "roll": True}], index=901)
            continue
        trigger = TRIGGERS.get(e.counter or "")
        ctl = planechase.planar_controller(plan.state)
        card = _source(plan, e)
        if trigger is None or card is None or ctl is None:
            continue
        live = plan.state.cards.get(card.id) is card
        ch = plan.ch(card) if live else chars.of(card, plan.info)
        oid = e.object_id or plan.oid(card)
        for i, d in triggers.abilities(plan, ch, trigger):
            triggers._add(plan, controller=ctl, source_card=card.id, source_object=oid, name=ch.name, index=i, definition=d)


# -- planeswalk (701.31) --------------------------------------------------------------------------------------------------------
def planeswalk(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """701.31a-b: the planar controller puts the face-up card on the bottom of the planar deck and turns the next one face up.
    Outside a Planechase game, or for a player who isn't the planar controller, nothing happens (701.31a)."""
    pc = plan.state.planechase
    ctl = planechase.planar_controller(plan.state)
    if pc is None or not pc.deck:
        plan.note("Not a Planechase game: nothing happens (701.31a)")
        return True
    who = ctx.get("controller")  # (the planeswalking ability's controller is the roller, 901.8: the active player, the planar controller)
    if who != ctl or ctl is None:
        plan.note("Only the planar controller planeswalks (701.31a): nothing happens")
        return True
    from app.rules import (
        planar_walk,  # -- planechase walk (wave C) -- Fixed Point in Time: chaos ensues instead (614.1a)
    )

    if e.get("roll") and planar_walk.chaos_instead(plan, ctx):
        return True
    from app.rules import (
        planar_deck,  # -- planechase deck (wave D) -- several face-up planes: their owner orders them (901.11c)
    )

    return planar_deck.planeswalk(plan, ctx, ctl)


PRIMITIVES: dict[str, Any] = {"planeswalk901": planeswalk}


# -- 704.6f: a phenomenon planeswalks away -----------------------------------------------------------------------------------------
def sba(plan: Plan) -> bool:
    """312.7 / 704.6f: a face-up phenomenon that isn't the source of a triggered ability that has triggered but not yet left the
    stack: the planar controller planeswalks. True if it did. (Only when the engine runs its encounter ability: see the docstring.)"""
    state = plan.state
    pc = state.planechase
    if pc is None or not pc.deck or not pc.deck[0].phenomenon or pc.face_id is None:
        return False
    face = state.cards.get(pc.face_id)
    ctl = planechase.planar_controller(state)
    if face is None or ctl is None or not encounter_automated(plan, face):
        return False
    r = plan.rules
    if any(t.source_card == face.id for t in r.pending_triggers):
        return False
    if any(s.source_card == face.id for s in r.stack.values()):
        return False
    if any(e.kind == "planar" and e.card == face.id and e.counter == "encounter" and e.batch > r.trigger_batch and not e.manual
           for e in r.events):  # (encountered, its ability not looked at yet: it has triggered, 603.2)
        return False
    plan.do({"type": "planeswalk"}, actor=ctl)
    return True


def encounter_automated(plan: Plan, face: CardInstance) -> bool:
    from app.rules import triggers

    return bool(triggers.abilities(plan, plan.ch(face), "planar_encounter"))


# -- coverage ---------------------------------------------------------------------------------------------------------------------
# The trigger kinds the collectors read on the planar object (triggers._watchers: "event" conditions and the kinds below; at_step:
# upkeep / end step; _step_abilities: "step:…"), and the static kinds: layers.statics reads "grant" (as for emblems: not a zone static
# or a paired sentence), permissions._all_table_statics the kinds read through ``_table_statics`` (filtered by this function) — only the kinds listed here are
# known to be read that way and nowhere else (a kind read by a battlefield-only collector, e.g. replacement effects, combat limits or
# hand size, is not supported until that collector reads the planar object too).
TRIGGER_KINDS = frozenset({"planar_chaos", "planar_to", "planar_from", "planar_encounter", "event", "upkeep_you", "end_step_you",
                           "enters_other", "state", "tap_for_mana"})  # (wave A: planar_statics.py)
STATIC_KINDS = frozenset({"cost_modifier",
                          "escape_grant", "no_max_hand", "top_reveal", "replace", "prevent", "skip", "attack_limit_all", "block_limit_all",
                          "enters_tapped_others", "spend_as", "zone_grant", "permission"})  # (wave A: planar_statics.py, each collector reads the plane)
from app.rules import planar_more as _planar_more  # noqa: E402  -- planechase more (wave E1) -- its static kinds (each read by its collector)

STATIC_KINDS = STATIC_KINDS | _planar_more.STATIC_KINDS
from app.rules import planar_more2 as _planar_more2  # noqa: E402  -- planechase more 2 (wave F1) -- its static kinds

STATIC_KINDS = STATIC_KINDS | _planar_more2.STATIC_KINDS
from app.rules import planar_more3 as _planar_more3  # noqa: E402  -- planechase more 3 (wave F2) -- its static kinds

STATIC_KINDS = STATIC_KINDS | _planar_more3.STATIC_KINDS
TRIGGER_KINDS = TRIGGER_KINDS | _planar_more3.TRIGGER_KINDS


def _trigger_ok(trigger: str) -> bool:
    parts = trigger.removeprefix("multi:").split("+") if trigger.startswith("multi:") else [trigger]
    from app.rules import planar_events  # -- planechase events (wave E2) --

    return all(p in TRIGGER_KINDS or p in planar_events.TRIGGER_KINDS or p.startswith("step:") for p in parts)


def ability_ok(d: dict[str, Any] | None) -> bool:
    """Does the engine run this ability of a face-up plane or phenomenon from the command zone (the module docstring)?"""
    if d is None:
        return False
    if d.get("kind") == "triggered":
        return _trigger_ok(str(d.get("trigger") or ""))
    if d.get("kind") == "static":
        from app.rules.statics import zone_static

        if d.get("static") == "grant":
            return not zone_static(d) and not d.get("also")
        return d.get("static") in STATIC_KINDS
    return False
