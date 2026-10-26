"""Delayed triggered abilities (CR 603.7) and effect durations (611.2), researched against CR 2026-09-25.

**Delayed triggers.** A resolving spell or ability may say "at the beginning of the next end step,
exile it" or "when that creature dies this turn, return it to the battlefield". The grammar turns
that into a ``delayed`` effect followed by the ``n`` effects it defers (app/rules/scripts.py, the
appended block; the wording helpers are at the bottom of this module). As the creating spell or
ability resolves (603.7a), the ``delayed`` primitive captures everything the deferred effects
will need into a ``DelayedTrigger`` (app/game/rules_state.py): the objects they name as
ObjectRefs — the target as chosen, "it" of an earlier instruction, the source — bound now
(603.7c: it still affects them whatever their characteristics become, but not if they have left
the zone they're expected in; an object that left and came back is a new object, 400.7), the
controller and source as they were (603.7d-e), the resolution bindings so far and the creating
trigger's event. It is JSON in ``RulesState.delayed``, so it survives saves, undo/redo and replay.

When its event happens — a step begins (500.6), or a watched object dies / leaves the battlefield
(603.6c, 603.10a) — it triggers like any other triggered ability: a PendingTrigger that the
trigger collector puts on the stack in APNAP order with the others (603.3b), resolved with its
own context (``bind_refs`` restores the bindings; "it" is read through app/rules/context.py,
never by rescanning the table). It triggers once (603.7b): "when that creature dies this turn"
triggers only for the object it was bound to, not for the new object it becomes if it returns
(603.7c / 400.7); "this turn" ones stop watching at cleanup (514.2). A watched object that has
already left when the trigger would be created never triggers it (603.7a).

**Durations.** "Until end of turn" effects end at cleanup (514.2, app/rules/layers.py). "Until
your next turn" ends as that player's next turn begins (500.4; ``turn_began``); "until the end of your next turn" (``end_of_next_turn``, wave 32C)
in the cleanup step of that player's next turn, a later turn than the one it began in (514.2; ``end_of_next_turn``). "For as long as ~
remains on the battlefield / you control ~ / ~ remains tapped" (611.2b) ends the moment that stops
being true (``expire``, checked after every table change); if it isn't true as the effect would
begin, the effect does nothing at all. "For as long as that creature has a bounty counter on it"
(``while_counter``, quoted grants: app/rules/granted.py) is the same for each object it affects:
one that has no such counter any more drops out, and the effect ends with the last. A duration
doesn't change what an effect applies to: a characteristic-changing effect stays locked to the
objects it began on (611.2c), so a "this turn" pump keeps going when the creature changes controllers.

-- as long as (wave 37A) -- One duration may cover a list of effects of one sentence ("gain control of that permanent, it loses all abilities, and it can't
attack or block", ``duration_pieces``), and "until this card is cast from exile" (``until_cast``) ends as the object its cost exiled from the hand is
cast (601.2i; ``spell_cast``, 400.7j) — if that object already left, the effect lasts (the ruling for Rakish Revelers).

-- turn-long triggers (wave 35B) -- A "this turn" one may watch several objects ("Whenever a creature dealt damage this way dies this turn":
each permanent the damage was actually dealt to, a trigger for each, 603.7b) or one object a later part of the spell named ("When the creature
an opponent controls dies this turn", app/rules/watches.py), have an intervening "if" (603.4) and a target of its own for what it does.

Not modelled here (the wording stays manual, never guessed; turn watches: app/rules/watches.py): (an "each"
duration), conditions on the deferred effect
("… if it didn't attack this turn"), "dealt damage by that creature" watches, and linked leaves-the-battlefield abilities of a
*second* ability line (607).
"""

from __future__ import annotations

import re
import secrets
from typing import TYPE_CHECKING, Any

from app.game.rules_state import DelayedTrigger, ObjectRef, TriggerEvent
from app.game.state import PHASES
from app.rules.world_durations80 import native as world_native80

if TYPE_CHECKING:
    from app.game.rules_state import ContinuousEffect, Event, PendingTrigger
    from app.rules.plan import Plan

Context = dict[str, Any]

# -- the wording of when a delayed trigger triggers ---------------------------------------------
WHEN: dict[str, dict[str, Any]] = {
    "the next end step": {"kind": "step", "step": "end", "whose": "next"},
    "your next end step": {"kind": "step", "step": "end", "whose": "you"},
    "the next turn's upkeep": {"kind": "step", "step": "upkeep", "whose": "next_turn"},
    "the next upkeep": {"kind": "step", "step": "upkeep", "whose": "next_turn"},
    "your next upkeep": {"kind": "step", "step": "upkeep", "whose": "you"},
    # -- triggers (wave 17D) -- "return it to the battlefield under its owner's control at the beginning of their next upkeep"
    # (Phytotitan): the next upkeep of the player who owns the card the clause moves (fixed as the delayed trigger is created)
    "its owner's next upkeep": {"kind": "step", "step": "upkeep", "whose": "owner"},
    "their next upkeep": {"kind": "step", "step": "upkeep", "whose": "owner"},
    # -- player-relative selectors (wave 53A) -- "Return that card to the battlefield under its owner's control at the beginning of that player's next end step." (The Eternal Wanderer):
    # the owner of the card the clause moves, as for the upkeep
    "that player's next end step": {"kind": "step", "step": "end", "whose": "owner"},
    "its owner's next end step": {"kind": "step", "step": "end", "whose": "owner"},
    "their next end step": {"kind": "step", "step": "end", "whose": "owner"},
    # -- stack interaction (wave 5B) -- Mana Drain: the next main phase (precombat or postcombat, 505.1) of a turn of
    # yours to begin; a later one this turn if you're in your precombat main phase or combat now (engine: main1 / main2)
    "your next main phase": {"kind": "step", "step": "main", "whose": "you"},
    # -- cards (wave 110E) -- 603.7: "the next main phase this turn" (Vivien's Stampede): whoever's, and never a later turn's (until_turn)
    "the next main phase this turn": {"kind": "step", "step": "main", "whose": "next", "this_turn110e": True},
    # -- attached (wave 100F) -- "sacrifice this Aura at the beginning of the next cleanup step" (Cunning): it goes on the stack after 514.1-514.2 (514.3a; engine at_step "cleanup")
    "the next cleanup step": {"kind": "step", "step": "cleanup", "whose": "next"},
}
END_OF_COMBAT = {"kind": "step", "step": "end_combat", "whose": "next"}  # -- other side (wave 6D) -- "at end of combat" (511.2)
WHEN_RE = "|".join(re.escape(k) for k in sorted(WHEN, key=len, reverse=True))
# "when that creature dies / leaves the battlefield this turn": the object an earlier part named
EVENT_SUBJECTS = ("it", "that creature", "that permanent", "that token", "that card", "~", "this creature",
                  "target creature", "target creature other than ~", "target permanent")  # (wave 35B: Adarkar Valkyrie)
EVENT_VERBS = {"dies": "die", "leaves the battlefield": "leave", "is put into a graveyard": "die",
               "is put into your graveyard": "die"}  # (-- this-turn state (wave 42B) -- Saffi: into ITS OWNER's graveyard, who is you: ``owner``)
EVENT_RE = "|".join(re.escape(k) for k in sorted(EVENT_VERBS, key=len, reverse=True))

# -- the wording of durations --------------------------------------------------------------------
# text → (duration, what replaces it so the ordinary "until end of turn" grammar reads the clause)
DURATIONS: dict[str, str] = {
    "until your next turn": "next_turn",
    "until the end of your next turn": "end_of_next_turn",  # -- end of next turn (wave 32C) -- 611.2a, 514.2
    "for as long as ~ remains on the battlefield": "source_on_battlefield",
    "for as long as you control ~": "source_controlled",
    "for as long as ~ remains tapped": "source_tapped",
    "for as long as that creature is enchanted": "while_enchanted",  # -- wave 110J -- Rootwater Matriarch: 611.2b, 303.4: an Aura is attached to it
    "until this card is cast from exile": "until_cast",  # -- as long as (wave 37A) -- 611.2a: ends as that card (the object its cost exiled) is cast
    # -- untap choice (wave 7F) -- Rubinia Soulsinger: both must stay true (611.2b: it ends the moment either stops)
    "for as long as you control ~ and ~ remains tapped": "source_controlled_tapped",
    # -- trigger lines (wave 100A) -- 611.2a: "until your next upkeep" (Erhnam Djinn, Gabriel Angelfire) ends as that player's next upkeep step begins
    # (Gabriel's ruling: it still has the ability through the untap step, not in the upkeep); ``at_step``, and 800.4m for a player who left
    "until your next upkeep": "next_upkeep",
    "for as long as they're the monarch": "monarch_player",  # -- durations (wave 110D) -- 611.2b, 725.2: the target's controller (Garland, Royal Kidnapper)
}
# -- quoted grants (wave 2D) -- "for as long as that creature has a bounty counter on it" (Mathas): the
# duration names a kind of counter ("while_counter:<kind>"): the effect lasts while the object it affects
# has one (611.2b), and does nothing if it has none as the effect would begin
COUNTER_DURATION = r"for as long as (?:that \w+|it|~) has an? (?P<kind>[\w+/-]+) counters? on it"
DURATION_RE = "|".join([*(re.escape(k) for k in sorted(DURATIONS, key=len, reverse=True)), COUNTER_DURATION])
LABELS = {"next_turn": "until your next turn", "end_of_next_turn": "until the end of your next turn", "source_on_battlefield": "for as long as ~ remains on the battlefield",
          "source_controlled": "for as long as you control ~", "source_tapped": "for as long as ~ remains tapped",
          "until_cast": "until this card is cast from exile",
          "source_controlled_tapped": "for as long as you control ~ and ~ remains tapped",
          "while_counter": "for as long as it has a counter on it", "while_enchanted": "for as long as that creature is enchanted", "next_upkeep": "until your next upkeep",
          "monarch_player": "for as long as they're the monarch",
          "creature_cast110m": "until a player casts a creature spell",
          "roll1_110f": "until end of turn or until any player rolls a 1"}  # -- (wave 110M) -- ends as any player casts a creature spell (601.2i): wave110m_cards.spell_cast
MARKER = "until end of turn"  # the table marker text app/rules/effects._mark writes


def wrap_when(effects: list[dict[str, Any]], when: dict[str, Any], *, who: str | None = None,
              this_turn: bool = False, next_turn: bool = False, this_combat: bool = False) -> list[dict[str, Any]]:
    """The ``delayed`` effect and the ``n`` effects it defers, as one flat list (so the pronoun
    resolver and the target-group bookkeeping see the deferred effects like any others)."""
    head: dict[str, Any] = {"do": "delayed", "when": dict(when), "n": len(effects)}
    if who is not None:
        head["who"] = who
    if this_turn:
        head["this_turn"] = True
    if next_turn:  # -- turn-long triggers (wave 50G) -- "Until your next turn, whenever …": ends as its controller's next turn begins (500.4, turn_began)
        head["next_turn"] = True
    if this_combat:  # -- block events (wave 53C) -- "whenever … this combat": watches until the combat phase ends (500.5), the turn's cleanup the backstop
        head["this_turn"] = head["this_combat"] = True
    # (marked as deferred: a later sentence's "that creature" must not bind to what the deferred
    # exile will record — it hasn't happened when the creating ability resolves)
    return [head, *({**e, "do": DEFERRED + e["do"]} for e in effects)]


DEFERRED = "deferred:"
# effects a delayed trigger doesn't defer
UNDEFERRABLE = ("delayed", "until", "optional_payment")


_MOVES = {"bounce", "return_card", "exile", "destroy", "sacrifice"}


def inner_for_event(effects: list[dict[str, Any]]) -> list[dict[str, Any]] | None:
    """The deferred effects of "when that creature dies this turn, …": "it" / "that card" there is
    the object the event happened to — the new object where it went for a move ("return it to the
    battlefield": 400.7e, 603.6c), the object as it last existed otherwise (603.10a) — never an
    earlier target. Anything that still needs an antecedent stays manual (None)."""
    out = []
    for e in effects:
        e = dict(e)
        who = e.get("who")
        if who in ("it", "them"):
            e["who"] = "event.new" if e.get("do") in _MOVES else "event"
        elif who in ("it.controller", "it.owner"):
            e["who"] = f"ref:event.{who[3:]}"
        elif isinstance(who, str) and who.startswith("graveyard_of:it."):  # -- turn-long triggers (wave 35B) -- "exile its controller's graveyard": the
            e["who"] = "graveyard_of:ref:event." + who[len("graveyard_of:it."):]  # controller as it last was (608.2h, 603.10a)
        elif who == "it:exiled":  # -- hidden exile (wave 18A) -- "the exiled card": the earlier instruction's, bound by resolve_it (Ugin)
            pass
        elif who == "that_player" or (isinstance(who, str) and who.startswith(("it:", "them:"))):
            return None
        n = e.get("n")
        if isinstance(n, dict) and any(n.get(k) in ("it", "that_spell") for k in ("power", "toughness", "mana_value")):
            e["n"] = {k: ("event" if v in ("it", "that_spell") else v) for k, v in n.items()}  # ("that_spell": wave 3R3)
        if e.get("src") == "it":
            return None
        out.append(e)
    return out


# -- creating one (as the spell or ability resolves, 603.7a) --------------------------------------
_BIND_NOW = ("target", "self", "host")  # who-values that mean "this object, as it is now" (603.7c)


def _bind_now(plan: Plan, ctx: Context, effects: list[dict[str, Any]], refs: dict[str, Any]) -> list[dict[str, Any]]:
    """The deferred effects with every reference to a particular object turned into a binding of
    the object as it is now: the target as chosen, the source, what the source is attached to.
    Selectors ("each creature you control") stay: they're read when the ability resolves."""
    from app.rules import block_events, context
    from app.rules.effects import _cards

    out = []
    for k, e in enumerate(effects):
        e = dict(block_events.bind(plan, ctx, e))  # -- block events (wave 53C) -- "destroy all creatures that blocked or were blocked by it this turn": the creature, as now
        who = e.get("who")
        exact_union = isinstance(who, str) and who.startswith("union:") and all(
            part in _BIND_NOW or part.startswith(("target:", "ref:")) for part in who[len("union:"):].split("+"))
        if isinstance(who, str) and (who in _BIND_NOW or who.startswith("target:") or exact_union):
            name = f"d{len(refs)}_{k}"
            context.bind_objects(plan, {"refs": refs}, name, _cards(plan, ctx, who))
            e["who"] = f"ref:{name}"
        out.append(e)
    return out


def create(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The ``delayed`` primitive: capture the next ``n`` effects of this resolution as a delayed
    triggered ability (603.7a) and skip them now."""
    n = int(e.get("n", 0))
    start = ctx["next"]
    deferred = [{**x, "do": x["do"].removeprefix(DEFERRED)} for x in ctx["effects"][start:start + n]]
    ctx["next"] = start + n
    # -- transform (wave 47D) -- 701.27f: a delayed triggered ability transforms the permanent only if it hasn't transformed since the ability was created
    deferred = [{**x, "since": plan.rules.next_object} if x["do"] == "transform" else x for x in deferred]
    refs = {k: v for k, v in (ctx.get("refs") or {}).items()}
    when = dict(e["when"])
    if e.get("watch_foreign105"):
        when["after_batch105"] = plan.rules.batch  # 603.7a: no event before this watcher existed.
    if when["kind"] == "event" or (when["kind"] == "watch" and when.get("bound")):  # (-- turn-long triggers (wave 33A) -- a watch on one object)
        from app.rules import context
        from app.rules.effects import _cards

        watched = dealt_cards(plan, ctx, e["dealt"], e.get("types")) if e.get("dealt") else _cards(plan, ctx, e["who"])  # (wave 35B)
        watched = [c for c in watched if plan.state.cards[c].zone.endswith(":battlefield")]
        if when.get("event") in ("lose_control", "lose_or_untap110i") and not e.get("watch_foreign105"):  # -- attached (wave 100F) -- only what its controller controls can be lost
            from app.rules import attached100f

            watched = attached100f.watching(plan, ctx, watched)
        if not watched:  # 603.7a: it already left — the event can't happen to that object
            plan.note(f"{ctx.get('name') or 'The ability'}: nothing to watch (it already left)")
            return True
        context.bind_objects(plan, {"refs": refs}, "watch", watched)
    if when["kind"] == "watch":  # -- turn watches (wave 7D) -- events after this resolution step only (603.7a)
        when["since"] = plan.rules.batch
        if when.get("recipient_ref"):
            from app.rules.effects import _players

            when["recipient_players"] = _players(plan, ctx, when.pop("recipient_ref"))
        from app.rules import watches

        deferred = watches.bind_x(deferred, int(ctx.get("x") or 0))  # (the X the creating spell was cast with)
    if when.get("whose") == "owner":  # the owner of the one card the deferred move acts on (parse: scripts._deferred)
        from app.rules.effects import _cards

        moved = _cards(plan, ctx, deferred[0].get("who", "")) if len(deferred) == 1 or deferred[0].get("owner110i") else []  # (wave 110I: Noctis' move comes with a rider)
        if len(moved) != 1:
            plan.note(f"{ctx.get('name') or 'The ability'}: nothing to return (it is gone)")
            return True
        when["player"] = plan.state.cards[moved[0]].owner
    turn = plan.state.turn.number
    end_of = ctx["controller"]
    if e.get("player_ref110d"):  # -- (wave 110D) -- Nuka-Nuke Launcher: "until the end of defending player's next turn, that player gets … whenever they cast a spell"
        from app.rules.effects import _players

        who = _players(plan, ctx, e["player_ref110d"])
        if not who:
            return True
        when["actor_players110d"], end_of = who, who[0]
    trigger = DelayedTrigger(
        id=secrets.token_hex(4), controller=ctx["controller"], source_card=ctx.get("source_card"),
        source_object=ctx.get("source_object"), name=ctx.get("name") or "", when=when,
        effects=_bind_now(plan, ctx, deferred, refs), refs=refs, event=ctx.get("event"), turn=turn,
        step=plan.state.turn.phase, created_step=plan.rules.step_serial, until_turn=turn if e.get("this_turn") else None, until_combat=bool(e.get("this_combat")), until_player=ctx["controller"] if e.get("next_turn") else None, once=bool(e.get("once", True)),
        until_end_next_player=end_of if e.get("end_of_next_turn") else None,
        target=e.get("target"), targets=e.get("targets"))
    plan.rules.delayed.append(trigger)
    plan.note(f"{trigger.name or 'A delayed ability'} will trigger {describe_when(when)}")
    return True


def object_deferred(effects: list[dict[str, Any]]) -> set[int]:
    """-- turn-long triggers (wave 35B) -- the indices of the effects a "When that creature dies / leaves the battlefield this turn" trigger
    defers: the one object its event is about (as it last existed, 603.10a) is what they name of "the event" ("lesser mana value")."""
    out: set[int] = set()
    for i, e in enumerate(effects):
        if e.get("do") == "delayed" and e.get("when", {}).get("kind") == "event":
            out.update(range(i + 1, i + 1 + int(e.get("n", 0))))
    return out


def dealt_cards(plan: Plan, ctx: Context, key: str, types: list[str] | None) -> list[str]:
    """-- turn-long triggers (wave 35B) -- "a creature dealt damage this way": the permanents (of those types) that the damage instruction
    before it actually dealt damage to (after prevention, effects.DEALT_KEY), each still the object that was dealt it (400.7)."""
    from app.rules.effects import DEALT_KEY

    oids = set((ctx.get(DEALT_KEY) or {}).get(key) or [])
    return [c.id for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) in oids
            and (not types or set(types) & plan.ch(c).types)]


def create_move(plan: Plan, controller: str, card_id: str, oid: str, to: str, name: str, *, sacrifice: bool = False,
                warp: bool = False, step: str = "end") -> None:
    """Unearth (702.84a) / dash (702.109a): "at the beginning of the next end step, exile it /
    return it to its owner's hand" — the object as it is now (603.7c)."""
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=controller, source_card=card_id, source_object=oid, name=name,
        when={"kind": "step", "step": step, "whose": "next"},
        effects=[{"do": "delayed_move", "card": card_id, "object": oid, "to": to, **({"sacrifice": True} if sacrifice else {}),
                  **({"by_now": True} if step == "cleanup" else {}),  # (-- flash auras (wave 46B) -- "the controller of the permanent it becomes sacrifices it")
                  **({"warp": True} if warp else {})}],
        turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial))


def create_plain(plan: Plan, controller: str, card_id: str, oid: str, name: str, when: dict[str, Any],
                 effects: list[dict[str, Any]]) -> None:
    """-- delayed triggers (wave 23B) -- a delayed triggered ability a mana ability creates as it resolves (603.7a: Barbed Sextant's "Draw a
    card at the beginning of the next turn's upkeep"): its controller and source as they were (603.7d-e), nothing bound to an object."""
    plan.rules.delayed.append(DelayedTrigger(
        id=secrets.token_hex(4), controller=controller, source_card=card_id, source_object=oid, name=name, when=when, effects=effects,
        turn=plan.state.turn.number, step=plan.state.turn.phase, created_step=plan.rules.step_serial))


def describe_when(when: dict[str, Any]) -> str:
    if when.get('manual_combat_scope'):
        return 'by hand for its remaining duration (older save: recipient scope unavailable)'
    if when["kind"] == "designation":  # (wave 3E: app/rules/designations.py fires these)
        return "when an opponent becomes the monarch"
    if when["kind"] == "watch":  # -- turn watches (wave 7D) --
        return f"when {when['text']} this turn"
    if when["kind"] == "event":
        if when["event"] == "die_or_exile":  # -- wave 3F -- (earthbend: no "this turn")
            return "when it dies or is put into exile"
        return "when it " + ("is put into your graveyard" if when.get("owner") else "dies" if when["event"] == "die" else "leaves the battlefield") + (
            " under your control" if when.get("ctl") else "") + ("" if when.get("open") else " this turn")
    if when.get("step") == "end_combat":  # -- other side (wave 6D) --
        return "at end of combat"
    if when.get("tag") is not None:  # (wave 49B)
        return "at the beginning of that combat"
    if when.get("whose") == "this_turn" and when.get("step") == "begin_combat":
        return "at the beginning of each combat this turn"
    whose = {"next": "the next", "you": "your next", "next_turn": "the next turn's", "owner": "its owner's next", "payer": "the affected player's next"}[when["whose"]]
    step = {"end": "end step", "main": "main phase", "cleanup": "cleanup step", "draw": "draw step"}.get(when["step"], "upkeep")  # (main: wave 5B)
    return f"at the beginning of {whose} {step}"


# -- triggering (603.2) and going on the stack with the other triggers (603.3b) --------------------
WATCH_TARGET = "watch_target"


def _swap_who(v: Any, old: str, new: str) -> Any:
    if isinstance(v, list):
        return [_swap_who(x, old, new) for x in v]
    if isinstance(v, dict):
        return {k: (new if k == "who" and x == old else _swap_who(x, old, new)) for k, x in v.items()}
    return v


def mark_target(effects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """-- if you do (wave 25C) -- a turn watch's own target, kept apart from the creating ability's target groups while it is parsed."""
    return _swap_who(effects, "target", WATCH_TARGET)


def restore_targets(value: Any) -> Any:
    """Future delayed targets bind when the trigger is put on the stack, not when created."""
    if isinstance(value, str) and (value == WATCH_TARGET or value.startswith(WATCH_TARGET + ':')):
        return 'target' + value[len(WATCH_TARGET):]
    if isinstance(value, list):
        return [restore_targets(item) for item in value]
    if isinstance(value, dict):
        return {key: restore_targets(item) for key, item in value.items()}
    return value


def _fire(plan: Plan, t: DelayedTrigger, event: TriggerEvent | None) -> PendingTrigger | None:
    from app.rules.triggers import _add

    if t.controller not in plan.live():
        return None
    definition = {"kind": "triggered", "trigger": "delayed", "optional": False, "target": t.target,  # (target: wave 25C, a turn watch's own)
                  **({'targets': t.targets} if t.targets else {}),
                  **({"if": t.when["if"]} if t.when.get("if") else {}),  # (-- turn-long triggers (wave 35B) -- an intervening "if", 603.4: as it triggers; as it resolves is its first effect)
                  "effects": [{"do": "bind_refs", "refs": t.refs}, *(restore_targets(t.effects) if t.target or t.targets else t.effects)]}
    return _add(plan, controller=t.controller, source_card=t.source_card or "", source_object=t.source_object or "",
                name=t.name, index=7000, definition=definition, event=event)


def _step_due(plan: Plan, t: DelayedTrigger, phase: str) -> bool:
    w = t.when
    if w.get("tag") is not None:  # -- commander sweep (wave 49B) -- "At the beginning of that combat" (Moraug): the one combat phase it was made with, wherever it falls in the turn (500.8)
        return w.get("kind") == "step" and w.get("step") == phase and plan.rules.combat_tag == w["tag"] and (
            t.until_turn is None or plan.state.turn.number <= t.until_turn)
    main = w.get("step") == "main" and phase in ("main1", "main2")  # -- stack interaction (wave 5B) -- (505.1)
    if w.get("kind") != "step" or (w.get("step") != phase and not main):
        return False
    turn = plan.state.turn.number
    if t.until_turn is not None and turn > t.until_turn:
        return False  # (its turn is over: "that turn's end step" never came)
    later_turn = turn > t.turn
    if w.get('next_turn_only') and not later_turn:
        return False
    created_at = PHASES.index(t.step) if t.step in PHASES else -1
    same_turn_before = turn == t.turn and created_at < PHASES.index(phase) + (phase == "cleanup")  # (-- flash auras (wave 46B) -- made in a cleanup step: due at the one that follows it, 514.3a)
    if t.created_step is not None:
        same_turn_before = turn == t.turn and plan.rules.step_serial > t.created_step
    whose = w.get("whose")
    if whose == "this_turn":  # 603.7b: every future matching step this turn, including extra phases after main2.
        return turn == t.turn
    if whose == "next":  # the next such step to begin, this turn's if it hasn't yet (500.6)
        return later_turn or same_turn_before
    if whose == "you":
        return plan.active == t.controller and (later_turn or same_turn_before)
    if whose in ("owner", "payer"):
        return plan.active == w.get("player") and (later_turn or same_turn_before)
    return later_turn  # "the next turn's upkeep"


def at_step(plan: Plan, phase: str) -> None:
    """A step began: delayed triggers waiting for it trigger (500.6, 603.7). They join the
    other step triggers in ``pending_triggers`` and go on the stack in APNAP order (603.3b)."""
    r = plan.rules
    if phase == "upkeep":
        r.permissions = [p for p in r.permissions if not (p.until == "next_upkeep" and (p.until_player or p.player) == plan.active
                          and (p.granted_step is None or r.step_serial > p.granted_step))]
        upkept = [e for e in r.effects if e.duration == "next_upkeep" and e.until_player == plan.active and plan.state.turn.number > e.turn]
        if upkept:  # -- trigger lines (wave 100A) -- "until your next upkeep" ends as it begins
            _end(plan, upkept)
            from app.rules import layers

            layers.control_sync(plan)
    over = [e for e in r.effects if e.duration == "end_of_next_upkeep110g" and e.until_player == plan.active and plan.state.turn.number > e.turn]
    if phase == "draw" and over:  # -- wave 110G -- Halfdane: "until the end of your next upkeep" ends as the draw step begins (611.2a, 501.1)
        _end(plan, over)
    due = [t for t in r.delayed if _step_due(plan, t, phase)]
    due_ids = {t.id for t in due}
    live_ids = {t.id for t in r.delayed}
    r.deferred_payments = [w for w in r.deferred_payments if w.delayed in live_ids and w.delayed not in due_ids]
    if not due:
        return
    r.delayed = [t for t in r.delayed if t not in due or not t.once]
    for t in due:
        event = TriggerEvent.model_validate(t.event) if t.event else None
        _fire(plan, t, event)


def on_events(plan: Plan, events: list[Event]) -> None:
    """The watched object died / left the battlefield (603.6c; 603.10a: the object as it last
    existed, and what it became where it went, 400.7e)."""
    from app.rules.triggers import _new_ref, _zone, pile_refs

    r = plan.rules
    watching = [t for t in r.delayed if t.when.get("kind") == "event"]
    if not watching:
        return
    fired: list[DelayedTrigger] = []
    # -- attached (wave 100F) -- "When you lose control of the creature, …": another player gains control of it, or it leaves (603.10d; attached100f)
    from app.rules import attached100f

    untappers = [t for t in watching if t.when.get("event") == "lose_or_untap110i"]  # -- cards (wave 110I) -- Coffin Queen: "becomes untapped or you lose control of it"
    for t in [t for t in watching if t.when.get("event") in ("lose_control", "lose_or_untap110i")]:
        eligible = [e for e in events if e.batch > int(t.when.get("after_batch105", -1))]
        if (gone := attached100f.lost(plan, t, eligible)):
            fired.append(t)
            _fire(plan, t, TriggerEvent(kind="lose_control", batch=events[-1].batch, count=1, objects=gone[:1]))
    watching = [t for t in watching if t.when.get("event") not in ("lose_control", "lose_or_untap110i")]
    for e in events:
        if e.kind == "untapped" and not e.manual:  # -- (wave 110M) -- "When ~ leaves the battlefield or becomes untapped" (Merieke Ri Berit): the watched permanent became untapped (603.2)
            for t in [t for t in watching if t.when["event"] == "leave_or_untap110m" and t not in fired]:
                if e.object_id in {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []} and (obj := plan.state.cards.get(e.card or "")) is not None:
                    fired.append(t)
                    _fire(plan, t, TriggerEvent(kind="untapped", batch=e.batch, count=1, objects=[ObjectRef(card=obj.id, object_id=e.object_id or "", zone=obj.zone)]))
        if e.kind == "untapped" and not e.manual:
            for t in [t for t in untappers if t not in fired]:
                if e.object_id in {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []} and (obj := plan.state.cards.get(e.card or "")) is not None:
                    fired.append(t)
                    _fire(plan, t, TriggerEvent(kind="untapped", batch=e.batch, count=1, objects=[ObjectRef(card=obj.id, object_id=e.object_id or "", zone=obj.zone)]))
        if e.kind == "untapped":
            continue
        if e.kind != "zone_change" or e.manual or _zone(e.from_zone) != "battlefield" or _zone(e.to_zone) == "battlefield":
            continue
        snap = r.lki.get(e.object_id or "")
        if snap is None:
            continue
        died = _zone(e.to_zone) == "graveyard" or (e.to_zone is None and snap.is_token)
        for t in watching:
            if t in fired and t.once:  # (-- turn-long triggers (wave 35B) -- a "this turn" one on several objects triggers for each: 603.7b)
                continue
            oids = {o["object_id"] for o in (t.refs.get("watch") or {}).get("objects") or []}
            if t.when.get("damager110g"):  # -- wave 110G -- Touch of Moonglove: any dying creature the watched one dealt damage to this turn (120.3)
                log = r.turn_log
                if not died or log.turn != plan.state.turn.number or not any(
                        f.kind == "damaged" and f.object_id == e.object_id and f.source in oids for f in log.facts):
                    continue
            elif e.object_id not in oids or (t.when["event"] == "die" and not died):
                continue
            if t.when.get("ctl") and snap.controller != t.controller:
                continue  # -- long tail (wave 16D) -- "dies under your control": who controlled it as it died (603.10a)
            if t.when.get("owner") and snap.owner != t.controller:
                continue  # -- this-turn state (wave 42B) -- "is put into your graveyard" (Saffi): a card goes to its owner's graveyard (400.3)
            if t.when["event"] == "die_or_exile" and not (died or _zone(e.to_zone) == "exile"):
                continue  # -- keyword actions & face-down (wave 3F) -- earthbend's "dies or is put into exile" (701.66a)
            kind = "die" if t.when["event"] in ("die", "die_or_exile") and died else "leave"
            event = TriggerEvent(kind=kind, batch=e.batch, count=1,
                                 objects=[ObjectRef(card=snap.card, object_id=snap.object_id, zone=snap.zone, snapshot=snap)],
                                 new_objects=_new_ref(snap.card, e.new_object_id, e.to_zone) + pile_refs(plan, e))  # (review 18D: 730.3c)
            fired.append(t)
            _fire(plan, t, event)
    from app.rules import random_artifact_tables42

    expired = random_artifact_tables42.departed_watchers(plan, events)
    if fired or expired:
        r.delayed = [t for t in r.delayed if (t not in fired or not t.once) and t.id not in expired]


def cleanup(plan: Plan) -> None:
    """514.2: "this turn" delayed triggers stop watching."""
    turn = plan.state.turn.number
    plan.rules.delayed = [t for t in plan.rules.delayed
                          if (t.until_turn is None or t.until_turn > turn)
                          and not (t.until_end_next_player == plan.active and turn > t.turn)]
    # -- end of next turn (wave 32C) -- "Players can't cast … until the end of your next turn" ends in that turn's cleanup (611.2a, 514.2)
    plan.rules.cast_limits = [x for x in plan.rules.cast_limits if not (
        x.get("until") == "end_of_next_turn" and x.get("controller") == plan.active and turn > int(x.get("turn") or 0))]


# -- durations (611.2) -------------------------------------------------------------------------------
def _effects_cards(plan: Plan, ctx: Context, who: str) -> list[str]:
    from app.rules import effects

    return effects._cards(plan, ctx, who)


def apply_duration(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The ``until`` primitive: carry out the next ``n`` effects, then give the continuous effects
    they created this duration instead of "until end of turn". If a "for as long as" duration
    isn't true as the effects would begin, they do nothing (611.2b)."""
    from app.rules.effects import PRIMITIVES

    n = int(e.get("n", 0))
    start = ctx["next"]
    inner = list(ctx["effects"][start:start + n])
    ctx["next"] = start + n
    duration = e["duration"]
    counter = None
    if duration.startswith("while_counter:"):  # (quoted grants, wave 2D)
        duration, counter = "while_counter", duration.split(":", 1)[1]
    if duration.startswith("source_") and not _source_ok(plan, duration, ctx.get("source_card"), ctx.get("source_object"),
                                                          ctx["controller"]):
        plan.note(f"{ctx.get('name') or 'The effect'} does nothing: its duration has already ended")
        return True
    if duration == "while_enchanted" and not any(_enchanted(plan, plan.oid(plan.state.cards[c])) for c in _held(plan, ctx, inner)):
        plan.note(f"{ctx.get('name') or 'The effect'} does nothing: its duration has already ended")  # 611.2b
        return True
    r = plan.rules
    mark = r.timestamp
    monarch = None
    if duration == "monarch_player":  # (wave 110D) the target's controller before it changes hands: the one who must stay the monarch
        monarch = next((plan.state.cards[c].controller for c in _effects_cards(plan, ctx, "target")), None)
        if monarch is None or monarch != plan.state.table.monarch:
            plan.note(f"{ctx.get('name') or 'The effect'} does nothing: its duration has already ended")
            return True
    before = {cid: {m.id for m in c.effects} for cid, c in plan.state.cards.items()}
    until_player = ctx["controller"]
    if e.get("controller110j"):  # -- wave 110J -- "until its controller's next untap step" (Orcish Farmer): the target's controller, as the effect begins
        from app.rules.effects import _cards

        held = _cards(plan, ctx, inner[0]["who"])
        until_player = plan.state.cards[held[0]].controller if held else until_player
    for x in inner:
        if not PRIMITIVES[x["do"]](plan, ctx, x):
            raise AssertionError("a duration wraps only effects that never pause")  # (the grammar only wraps pumps and grants)
    label = LABELS[duration].replace("~", ctx.get("name") or "it")
    until_object = None
    if duration == "until_cast":  # -- as long as (wave 37A) -- 611.2a, 400.7j: the object the cost exiled; one that already left exile can never be cast from
        # there as that object, so the effect lasts (the ruling for Rakish Revelers)
        from app.rules import effects as _effects

        found = _effects._cards(plan, ctx, "cost_exiled_self")
        until_object = plan.oid(found[0]) if found else None
        if until_object is None:
            duration = "permanent"
    if counter:
        label = f"for as long as it has a {counter} counter on it"
    written = _relabel(plan, before, label)
    for effect in r.effects:
        if effect.timestamp > mark:
            effect.duration = duration
            effect.until_object = until_object
            effect.until_player = monarch or until_player
            effect.turn = plan.state.turn.number
            if counter:
                effect.counter = counter
                effect.counter_since_batch = plan.rules.batch
            if duration.startswith("source_"):
                effect.source = ctx.get("source_object")
                effect.source_card = ctx.get("source_card")
            # each effect of the clause ("gets +2/+2 and gains flying") owns the markers on the
            # objects it affects; ``_end`` keeps a marker another effect still owns
            # (-- attack restrictions (wave 32B) -- a group effect, "Until your next turn, creatures can't attack you", has no objects of its own: it owns the markers
            # the clause wrote on the creatures it matched, so they go when it ends)
            effect.markers = [m for cid, ids in written.items() if effect.who or plan.oid(cid) in effect.affected for m in ids]
    if counter:
        expire(plan)  # 611.2b: a counter the objects don't have as the effect begins — it does nothing
    return True


def roll_one110f(plan: Plan) -> None:
    """-- wave 110F -- a player rolled a 1: the effects lasting "until end of turn, or until any player rolls a 1" end (Drop Tower)."""
    if ended := [e for e in plan.rules.effects if e.duration == "roll1_110f"]:
        _end(plan, ended)


def spell_cast(plan: Plan, from_object: str | None) -> None:
    """-- as long as (wave 37A) -- 611.2a: "until this card is cast from exile" ends as that card is cast (601.2i): the effects naming the object it was
    in exile (``from_object``, before it became the spell). A mana ability they gave was usable while it was paid for (601.2g)."""
    ended = [e for e in plan.rules.effects if e.duration == "until_cast" and from_object is not None and e.until_object == from_object]
    if ended:
        _end(plan, ended)


def _relabel(plan: Plan, before: dict[str, set[str]], label: str) -> dict[str, list[str]]:
    """The table markers the clause's effects just wrote say "until end of turn": say the real
    duration. Returns the new markers' ids by card (the effects remember them: ``_end``)."""
    written: dict[str, list[str]] = {}
    for cid, card in plan.state.cards.items():
        for m in [m for m in card.effects if m.id not in before.get(cid, set()) and m.text == MARKER]:
            plan.do({"type": "remove_effect", "card_ids": [cid], "effect_id": m.id})
            added = plan.do({"type": "add_effect", "card_ids": [cid], "name": m.name, "value": m.value, "text": label[:200]})
            written.setdefault(cid, []).extend(marker_ids(added))
    return written


def _source_ok(plan: Plan, duration: str, source_card: str | None, source_object: str | None, controller: str | None) -> bool:
    card = plan.state.cards.get(source_card or "")
    if card is None or not card.zone.endswith(":battlefield") or plan.oid(card) != source_object:
        return False
    if not plan.in_game(card):
        return False  # 800.4a: its owner (or controller) left the game, and it left with them
    if duration in ("source_controlled", "source_controlled_tapped") and card.controller != controller:
        return False
    if duration in ("source_tapped", "source_controlled_tapped"):
        return card.tapped
    return True


def marker_ids(action: Any) -> list[str]:
    """The ids of the table markers an ``add_effect`` action just wrote."""
    return list(getattr(getattr(action, "r", None), "ids", None) or [])


@world_native80
def _end(plan: Plan, ended: list[ContinuousEffect]) -> None:
    """The effects end, and with them the table markers they wrote (keyed by the effect: another
    effect's marker with the same wording on the same creature stays)."""
    r = plan.rules
    ids = {e.id for e in ended}
    r.effects = [e for e in r.effects if e.id not in ids]
    still = {m for e in r.effects for m in e.markers or ()}  # (one marker can stand for several effects)
    for effect in ended:
        label = LABELS.get(effect.duration, "")
        if effect.markers is None and not label:
            continue
        for cid, card in plan.state.cards.items():
            if effect.markers is not None:
                gone = [m for m in card.effects if m.id in effect.markers and m.id not in still]
            elif plan.oid(card) in effect.affected:  # (an effect saved before effects remembered their markers)
                gone = [m for m in card.effects if m.text and m.text.startswith(label.split("~")[0].strip())
                        and m.text != MARKER and m.id not in still]
            else:
                continue
            for m in gone:
                plan.do({"type": "remove_effect", "card_ids": [cid], "effect_id": m.id})


def turn_began(plan: Plan, skipped: list[tuple[str, int]] | None = None) -> None:
    """500.4: as a player's turn begins, effects lasting "until [their] next turn" end. 800.4m:
    for a player who left the game, they end when that turn would have begun (``skipped``: the
    seats of departed players passed on the way here, with the turn number each would have had)."""
    r = plan.rules
    turn, active = plan.state.turn.number, plan.active
    from app.rules import cast_limits  # -- cast limits (wave 5E) -- "until your next turn, … can't cast …"

    cast_limits.turn_began(plan, skipped)
    # CR 800.4m: an "until your next turn" cost effect also ends when a
    # departed player's next turn would have begun.
    r.cost_modifiers = [m for m in r.cost_modifiers if not (m.until == "next_turn" and (
        ((m.until_player or m.controller) == active and turn > m.turn)
        or any((m.until_player or m.controller) == p and n > m.turn for p, n in skipped or ())))]
    from app.rules import timed_damage_replacements

    timed_damage_replacements.turn_began(plan, skipped)
    r.delayed = [t for t in r.delayed if t.until_player is None or not ((t.until_player == active and turn > t.turn)  # -- turn-long triggers (wave 50G) -- "until your next turn" watches
                                                                        or any(t.until_player == p and n > t.turn for p, n in skipped or ()))]
    r.delayed = [t for t in r.delayed if not any(
        t.until_end_next_player == player and skipped_turn > t.turn for player, skipped_turn in skipped or ())]
    ended = [e for e in r.effects if (e.duration == "next_turn" and e.until_player == active and turn > e.turn)
             or (e.duration in ("next_turn", "end_of_next_turn", "next_upkeep")  # (-- end of next turn (wave 32C) -- a departed player's turn never gets a cleanup, 800.4m; wave 100A: nor an upkeep)
                 and any(e.until_player == p and n > e.turn for p, n in skipped or ()))]
    if ended:
        _end(plan, ended)
        from app.rules import layers

        layers.control_sync(plan)  # -- control (wave 3K) -- "until your next turn" ended: control reverts (613.1b)


def end_of_next_turn(plan: Plan) -> None:
    """-- end of next turn (wave 32C) -- 611.2a / 514.2: "until the end of your next turn" ends in the cleanup step of that player's next turn: a
    later turn than the one it began in, so one made in their own turn lasts through the next one (and one made in an opponent's, through theirs)."""
    r, turn = plan.rules, plan.state.turn.number
    due = [e for e in r.effects if e.duration == "end_of_next_turn" and e.until_player == plan.active and turn > e.turn]
    if due:
        _end(plan, due)


@world_native80
def expire(plan: Plan) -> None:
    """611.2b: "for as long as …" effects end as soon as it stops being true (checked after every
    table change: the source left, changed controller or untapped)."""
    from app.rules import phase_lifetimes43, timed_damage_replacements

    plan.rules.source_hand_reveals79 = [r for r in plan.rules.source_hand_reveals79
        if _source_ok(plan, 'source_on_battlefield', r.source_card, r.source_object, None)]
    phase_lifetimes43.expire(plan)
    timed_damage_replacements.expire_source_records(plan)
    r = plan.rules
    ended = [e for e in r.effects if e.duration.startswith("source_")
             and not _source_ok(plan, e.duration, e.source_card, e.source, e.until_player)]
    ended += [e for e in r.effects if e.duration == "monarch_player" and plan.state.table.monarch != e.until_player]  # (wave 110D)
    from app.rules import (
        wave110n_cards,  # -- (wave 110N) -- "for as long as that Aura is attached to it" (Eriette), 611.2b
    )

    ended += [e for e in r.effects if e.duration == "attached110n" and not wave110n_cards.still_attached(plan, e)]
    for e in r.effects:  # -- quoted grants (wave 2D) -- "for as long as it has a … counter on it": per object
        if e.duration == "while_counter":
            lost_last = {ev.object_id for ev in r.events if ev.kind == "counters" and ev.counter == e.counter
                         and ev.counter_remaining == 0 and ev.batch > e.counter_since_batch}
            kept = [oid for oid in e.affected if oid not in lost_last and _has_counter(plan, oid, e.counter or "")]
            if not kept:
                ended.append(e)
            elif len(kept) < len(e.affected):
                _drop(plan, e, kept)
    for e in r.effects:  # -- wave 110J -- "for as long as that creature is enchanted": per object, while an Aura is attached (611.2b)
        if e.duration == "while_enchanted":
            kept = [oid for oid in e.affected if _enchanted(plan, oid)]
            if not kept:
                ended.append(e)
            elif len(kept) < len(e.affected):
                _drop(plan, e, kept)
    from app.rules import (
        wave110k_cards,  # -- wave 110K -- Old Man of the Sea: "for as long as ~ remains tapped and that creature's power remains … ~'s power"
    )

    for e in r.effects:
        if e.duration == "source_tapped_power110k":
            kept = wave110k_cards.old_man_kept(plan, e)
            if not kept:
                ended.append(e)
            elif len(kept) < len(e.affected):
                _drop(plan, e, kept)
    for e in r.effects:  # -- wave 110L -- "for as long as this Equipment remains attached to it": per object, while that same Equipment is attached to it (611.2b)
        if e.duration == "while_attached110l":
            kept = [oid for oid in e.affected if _attached_by(plan, oid, e.source_card, e.source)]
            if not kept:
                ended.append(e)
            elif len(kept) < len(e.affected):
                _drop(plan, e, kept)
    if ended:
        _end(plan, ended)
    from app.rules import permissions

    permissions.expire_source(plan)  # -- durations (wave 30M) -- "You may play that card for as long as you control ~" (a stored permission)


def _held(plan: Plan, ctx: Context, inner: list[dict[str, Any]]) -> list[str]:
    from app.rules.effects import _cards

    return [c for x in inner[:1] for c in _cards(plan, ctx, x["who"])]


def _enchanted(plan: Plan, oid: str) -> bool:
    """303.4: the permanent (that object) has an Aura attached to it."""
    host = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None)
    return host is not None and any(a.attached_to == host.id and a.zone.endswith(":battlefield") and "Aura" in plan.ch(a).subtypes
                                    for a in plan.state.cards.values())


def _attached_by(plan: Plan, oid: str, equipment: str | None, equipment_oid: str | None) -> bool:
    """The permanent (that object) still has that object of the source attached to it."""
    host = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None)
    src = plan.state.cards.get(equipment or "")
    return (host is not None and src is not None and src.zone.endswith(":battlefield") and plan.oid(src) == equipment_oid
            and src.attached_to == host.id and plan.in_game(src))


def _has_counter(plan: Plan, oid: str, kind: str) -> bool:
    card = next((c for c in plan.state.cards.values() if c.zone.endswith(":battlefield") and plan.oid(c) == oid), None)
    return card is not None and card.counters.get(kind, 0) > 0


@world_native80
def _drop(plan: Plan, effect: ContinuousEffect, kept: list[str]) -> None:
    """Objects that no longer have the counter leave the effect (and its table markers)."""
    gone = set(effect.affected) - set(kept)
    effect.affected = kept
    for card in plan.state.cards.values():
        if plan.oid(card) in gone:
            for m in [m for m in card.effects if m.id in (effect.markers or ())]:
                plan.do({"type": "remove_effect", "card_ids": [card.id], "effect_id": m.id})


def bind_refs(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    """The first effect of a delayed trigger's resolution: its bindings, as captured (603.7c)."""
    ctx["refs"] = {k: v for k, v in (e.get("refs") or {}).items()}
    return True


# -- wording -----------------------------------------------------------------------------------------
LEADING = re.compile(rf"^at the beginning of (?P<when>{WHEN_RE}), (?P<clause>.+)$")
TRAILING = re.compile(rf"^(?P<clause>.+?) at the beginning of (?P<when>{WHEN_RE})$")
EVENT = re.compile(rf"^when (?P<subject>{'|'.join(re.escape(s) for s in EVENT_SUBJECTS)}) (?P<verb>{EVENT_RE})(?P<ctl> under your control)?(?P<turn> this turn)?, "
                   r"(?P<clause>.+)$")
UNTIL_LEADING = re.compile(rf"^(?P<duration>{DURATION_RE}), (?P<clause>.+)$")
UNTIL_TRAILING = re.compile(rf"^(?P<clause>.+?) (?P<duration>{DURATION_RE})$")
_EOT = re.compile(r"^(?P<clause>.+?)(?: until end of turn)$")
_RESTRICT = re.compile(r"^(?P<o>.+?) can't (?P<r>attack or block|block|attack you\b.*|attack|be blocked)$")  # (-- attack restrictions (wave 32B) -- "creatures can't attack you")


def duration_clause(m: re.Match[str]) -> tuple[str, str]:
    """(the clause as the ordinary grammar reads it — with "until end of turn" / "this turn"
    — the duration): "it gains haste until your next turn" → "it gains haste until end of turn"."""
    kind = m.groupdict().get("kind")
    clause, duration = m["clause"].strip(), (f"while_counter:{kind}" if kind else DURATIONS[m["duration"]])
    if _RESTRICT.fullmatch(clause):
        return clause + " this turn", duration
    return clause + " until end of turn", duration


# -- as long as (wave 37A) -- 611.2b: one duration over a list of effects of one sentence: "For as long as ~ remains on the battlefield, gain
# control of that permanent, it loses all abilities, and it can't attack or block." (Opportunistic Dragon), "… another target permanent loses all
# abilities and can't attack or block" (Immovable Rod): when the whole clause isn't one the grammar reads, each piece is read as a clause of its own
# (a piece with no subject is about "it", the object the first names) and they all last as long as the duration. No quote is split.
_PIECE_SEP = re.compile(r"(?:,? and |, )(?=(?:it|they|that \w+|those \w+|gain control|(?:can't|loses|gains|gets|has|doesn't) ))")  # (a clause starts after it: "base power and toughness" is not split)
_PREDICATE = re.compile(r"^(?:can't|loses|gains|gets|has|doesn't) ")


def duration_pieces(m: re.Match[str]) -> list[str] | None:
    """The clauses a compound "for as long as …" clause is made of, each as the ordinary grammar reads it (``duration_clause``), or None."""
    raw = m["clause"].strip()
    parts = [p.strip() for p in _PIECE_SEP.split(raw) if p.strip()]
    if '"' in raw or not 2 <= len(parts) <= 4:
        return None
    return [(f"it {p}" if i and _PREDICATE.match(p) else p) + (" this turn" if _RESTRICT.fullmatch(f"it {p}" if i and _PREDICATE.match(p) else p)
                                                                else " until end of turn") for i, p in enumerate(parts)]


def wrap_duration(effects: list[dict[str, Any]], duration: str) -> list[dict[str, Any]] | None:
    """The ``until`` effect over the continuous effects of a clause; only pumps, grants and
    restrictions (they never pause, and their effects carry a duration)."""
    if not effects or any(e.get("do") not in ("pump", "grant", "restrict", "gain_control", "become") or (
            e.get("do") == "become" and any(k in e for k in ("land_pick", "pick", "choose", "copy"))) for e in effects):
        return None  # (-- as long as (wave 25A) -- a "becomes" that asks nothing: "becomes an artifact creature … for as long as ~ remains on the battlefield")
    return [{"do": "until", "duration": duration, "n": len(effects)}, *effects]


def event_when(m: re.Match[str]) -> tuple[dict[str, Any], str]:
    """("when that creature dies this turn" → its trigger, the subject as a who-placeholder for
    scripts.resolve_it: "it" for a pronoun, "self" for ~, "target" for a target)."""
    subject = m["subject"]
    when = {"kind": "event", "event": EVENT_VERBS[m["verb"]], **({"ctl": "you"} if m["ctl"] else {}), **({"owner": "you"} if "your graveyard" in m["verb"] else {}),
            **({} if m["turn"] else {"open": True})}  # (16D: "dies under your control"; 18A: no "this turn": for as long as it takes)
    if subject in ("~", "this creature"):
        return when, "self"
    if subject.startswith("target "):
        return when, "target"
    return when, "it"
